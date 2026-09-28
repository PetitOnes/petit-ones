"""イベント検出ロジック。

このモジュールはネットワークから完全に分離されている。すべて純粋な関数/クラスで、
「タイムスタンプ付きのサンプルを食わせるとイベントのリストが返る」という形になっている。
これによりモックサーバーなしでも合成データだけで単体テストできる。

呼び出し側（experienced.py）の想定フロー（1ポーリングサイクルにつき1回）:

    detector = ExperienceDetector()
    ...
    if sensors is None and status is None:
        events = detector.record_poll_failure(now)
    else:
        events = detector.record_poll_success(now)
        if sensors is not None:
            events += detector.process_sensors(now, sensors)
        if status is not None:
            events += detector.process_status(now, status)
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime

# ============================================================================
# 閾値定数（根拠つき）
# ============================================================================

# --- 持ち上げ/運ばれ/置かれた検出 ---
# 重力ベクトルの向きが何度変わったら「動いた」とみなすか。
# 静止時 |a|≈1.0g。机の上で少し傾ける程度（〜10度）はノイズとして無視し、
# 手で持ち上げて向きが変わるレベル（20〜30度）を狙う。設計書の指定値。
ACCEL_ANGLE_THRESHOLD_DEG = 25.0
# |a| の分散がこれを超えたら「揺れている」とみなす（g^2単位）。
# 静止時は加速度センサーのノイズで分散は非常に小さい（<0.001g^2程度）。
# 歩いて運ぶ・電車の揺れなどは容易にこれを超える。
ACCEL_VARIANCE_THRESHOLD = 0.02
# 分散を計算する際のスライディングウィンドウ長（秒）。MOTION_CONFIRM_SEC と揃える。
ACCEL_VAR_WINDOW_SEC = 1.0
# 「動いている」状態が何秒継続したら picked_up を確定するか。
MOTION_CONFIRM_SEC = 1.0
# 「静止している」状態が何秒継続したら put_down を確定するか。
STILL_CONFIRM_SEC = 3.0
# フラッピング防止用のヒステリシス猶予（秒）。この時間内の単発ノイズは無視する
# （移動判定中に一瞬静止した/静止判定中に一瞬動いた、を許容する）。
MOTION_GRACE_SEC = 1.0
# 静止中の姿勢基準ベクトル（baseline）を追従させる指数移動平均の係数。
# 小さいほどゆっくり追従＝ちょっとした持ち直しでbaselineが飛ばない。
BASELINE_EMA_ALPHA = 0.05

# --- 照度急変検出 ---
# 比が3倍以上 or 1/3以下、かつ絶対差が50以上で「急変」とみなす。
# 室内灯(数百lux相当のambient値)と暗い部屋(数十)の差はこれくらい離れる想定。
AMBIENT_JUMP_RATIO = 3.0
AMBIENT_JUMP_ABS_DIFF = 50
# 急変が何サンプル連続で維持されたら確定するか（単発のセンサーグリッチを弾く）。
AMBIENT_JUMP_CONFIRM_SAMPLES = 2
# 同種イベントの連続抑制（秒）。電灯のちらつきなどで大量発火しないように。
AMBIENT_JUMP_COOLDOWN_SEC = 60.0

# --- タッチ検出 ---
# 連続タッチをまとめる時間窓（秒）。
TOUCH_GROUP_WINDOW_SEC = 30.0

# --- オフライン検出 ---
# ポーリング失敗がこの秒数以上続いたら offline_gap イベントとして記録する。
OFFLINE_GAP_THRESHOLD_SEC = 15.0

# --- 電池残量 ---
BATTERY_LOW_THRESHOLDS = (20, 10)
# 一度下回ったアラートを再アームするためのヒステリシス（この値まで回復したら再度鳴らせる）。
BATTERY_LOW_HYSTERESIS = 5


@dataclass
class Event:
    """1件のイベント。JSONL の1行に対応する。"""

    ts: datetime
    type: str
    detail: dict

    def to_dict(self) -> dict:
        return {
            "ts": self.ts.isoformat(timespec="seconds"),
            "type": self.type,
            "detail": self.detail,
        }


def _vector_angle_deg(v1: tuple[float, float, float], v2: tuple[float, float, float]) -> float:
    """2つの3次元ベクトルのなす角度（度）。どちらかがゼロベクトルなら0を返す。"""
    dot = v1[0] * v2[0] + v1[1] * v2[1] + v1[2] * v2[2]
    n1 = math.sqrt(v1[0] ** 2 + v1[1] ** 2 + v1[2] ** 2)
    n2 = math.sqrt(v2[0] ** 2 + v2[1] ** 2 + v2[2] ** 2)
    if n1 == 0 or n2 == 0:
        return 0.0
    cos_theta = max(-1.0, min(1.0, dot / (n1 * n2)))
    return math.degrees(math.acos(cos_theta))


def _ema_vector(
    baseline: tuple[float, float, float], new: tuple[float, float, float], alpha: float
) -> tuple[float, float, float]:
    return (
        baseline[0] * (1 - alpha) + new[0] * alpha,
        baseline[1] * (1 - alpha) + new[1] * alpha,
        baseline[2] * (1 - alpha) + new[2] * alpha,
    )


def _population_variance(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    return sum((v - mean) ** 2 for v in values) / len(values)


@dataclass
class _MotionState:
    confirmed: bool = False
    baseline: tuple[float, float, float] | None = None
    motion_candidate_start: datetime | None = None
    motion_last_true: datetime | None = None
    picked_up_ts: datetime | None = None
    still_candidate_start: datetime | None = None
    still_last_true: datetime | None = None
    accel_history: deque = field(default_factory=deque)


@dataclass
class _AmbientState:
    baseline: int | None = None
    pending_value: int | None = None
    pending_count: int = 0
    last_jump_ts: datetime | None = None


@dataclass
class _TouchState:
    last_seen: int | None = None
    group_start: datetime | None = None
    group_last: datetime | None = None
    group_count: int = 0


@dataclass
class _OfflineState:
    failure_start: datetime | None = None


@dataclass
class _BatteryState:
    alerted: dict = field(default_factory=lambda: dict.fromkeys(BATTERY_LOW_THRESHOLDS, False))


@dataclass
class _SleepState:
    last_is_sleeping: bool | None = None


class ExperienceDetector:
    """センサー/ステータスのサンプル列からイベント列を生成するステートフルな検出器。

    ネットワークやファイルI/Oには一切触れない。呼び出し側がサンプルを渡し、
    返り値の Event リストを好きなように保存・整形すればよい。
    """

    def __init__(self) -> None:
        self._motion = _MotionState()
        self._ambient = _AmbientState()
        self._touch = _TouchState()
        self._offline = _OfflineState()
        self._battery = _BatteryState()
        self._sleep = _SleepState()

    # ------------------------------------------------------------------
    # 公開プロパティ（デーモン側で状態ファイルを書くために使う）
    # ------------------------------------------------------------------

    @property
    def is_sleeping(self) -> bool | None:
        """最後に観測された is_sleeping。まだ観測がなければ None。"""
        return self._sleep.last_is_sleeping

    # ------------------------------------------------------------------
    # オフライン検出
    # ------------------------------------------------------------------

    def record_poll_failure(self, ts: datetime) -> list[Event]:
        """このサイクルのポーリングが失敗したことを記録する。イベントは返さない
        （復帰時に record_poll_success 側で1件にまとめて記録する）。
        """
        if self._offline.failure_start is None:
            self._offline.failure_start = ts
        return []

    def record_poll_success(self, ts: datetime) -> list[Event]:
        """このサイクルのポーリングが成功したことを記録する。直前まで
        OFFLINE_GAP_THRESHOLD_SEC 以上失敗が続いていた場合は offline_gap を1件返す。
        """
        events: list[Event] = []
        if self._offline.failure_start is not None:
            gap_sec = (ts - self._offline.failure_start).total_seconds()
            if gap_sec >= OFFLINE_GAP_THRESHOLD_SEC:
                events.append(
                    Event(
                        ts=self._offline.failure_start,
                        type="offline_gap",
                        detail={
                            "start": self._offline.failure_start.isoformat(timespec="seconds"),
                            "end": ts.isoformat(timespec="seconds"),
                            "minutes": round(gap_sec / 60.0, 1),
                        },
                    )
                )
            self._offline.failure_start = None
        return events

    # ------------------------------------------------------------------
    # /sensors の処理（picked_up/carried/put_down, ambient_jump, touch, battery_low）
    # ------------------------------------------------------------------

    def process_sensors(self, ts: datetime, sensors: dict) -> list[Event]:
        events: list[Event] = []
        events += self._process_motion(ts, sensors)
        events += self._process_ambient(ts, sensors)
        events += self._process_touch(ts, sensors)
        events += self._process_battery(ts, sensors)
        return events

    def _process_motion(self, ts: datetime, sensors: dict) -> list[Event]:
        ax = float(sensors.get("ax", 0.0))
        ay = float(sensors.get("ay", 0.0))
        az = float(sensors.get("az", 0.0))
        vec = (ax, ay, az)
        mag = math.sqrt(ax * ax + ay * ay + az * az)

        m = self._motion
        m.accel_history.append((ts, mag))
        while m.accel_history and (
            ts - m.accel_history[0][0]
        ).total_seconds() > ACCEL_VAR_WINDOW_SEC:
            m.accel_history.popleft()
        variance = _population_variance([v for _, v in m.accel_history])

        if m.baseline is None:
            # 起動直後の1発目：基準姿勢を設定するだけでイベントは出さない
            m.baseline = vec
            return []

        angle = _vector_angle_deg(vec, m.baseline)
        moving_now = angle >= ACCEL_ANGLE_THRESHOLD_DEG or variance >= ACCEL_VARIANCE_THRESHOLD

        if not m.confirmed:
            if moving_now:
                m.motion_last_true = ts
                if m.motion_candidate_start is None:
                    m.motion_candidate_start = ts
                elapsed = (ts - m.motion_candidate_start).total_seconds()
                if elapsed >= MOTION_CONFIRM_SEC:
                    m.confirmed = True
                    m.picked_up_ts = m.motion_candidate_start
                    m.motion_candidate_start = None
                    m.still_candidate_start = None
                    m.still_last_true = None
                    return [Event(ts=m.picked_up_ts, type="picked_up", detail={})]
            else:
                if m.motion_candidate_start is not None:
                    if m.motion_last_true is not None and (
                        ts - m.motion_last_true
                    ).total_seconds() > MOTION_GRACE_SEC:
                        m.motion_candidate_start = None
                        m.motion_last_true = None
                if m.motion_candidate_start is None:
                    # 完全に静止しているときだけ基準姿勢をゆっくり追従させる
                    m.baseline = _ema_vector(m.baseline, vec, BASELINE_EMA_ALPHA)
            return []

        # confirmed == True（carried 状態、静止の継続を待っている）
        if not moving_now:
            m.still_last_true = ts
            if m.still_candidate_start is None:
                m.still_candidate_start = ts
            elapsed_still = (ts - m.still_candidate_start).total_seconds()
            if elapsed_still >= STILL_CONFIRM_SEC:
                carried_sec = (m.still_candidate_start - m.picked_up_ts).total_seconds()
                event = Event(
                    ts=m.still_candidate_start,
                    type="put_down",
                    detail={"carried_sec": round(carried_sec)},
                )
                m.confirmed = False
                m.baseline = vec
                m.picked_up_ts = None
                m.motion_candidate_start = None
                m.still_candidate_start = None
                m.still_last_true = None
                return [event]
        else:
            # 静止判定中に一瞬また動いても、猶予内なら静止カウントを維持する（ヒステリシス）
            if m.still_candidate_start is not None:
                if m.still_last_true is not None and (
                    ts - m.still_last_true
                ).total_seconds() > MOTION_GRACE_SEC:
                    m.still_candidate_start = None
                    m.still_last_true = None
        return []

    def _process_ambient(self, ts: datetime, sensors: dict) -> list[Event]:
        if "ambient" not in sensors:
            return []
        value = int(sensors["ambient"])
        a = self._ambient

        if a.baseline is None:
            a.baseline = value
            return []

        if a.baseline == 0:
            is_jump = value >= AMBIENT_JUMP_ABS_DIFF
        else:
            ratio = value / a.baseline
            is_jump = (
                ratio >= AMBIENT_JUMP_RATIO or ratio <= 1.0 / AMBIENT_JUMP_RATIO
            ) and abs(value - a.baseline) >= AMBIENT_JUMP_ABS_DIFF

        events: list[Event] = []
        if is_jump:
            same_as_pending = (
                a.pending_value is not None
                and abs(value - a.pending_value) <= AMBIENT_JUMP_ABS_DIFF
            )
            if same_as_pending:
                a.pending_count += 1
            else:
                a.pending_value = value
                a.pending_count = 1

            if a.pending_count >= AMBIENT_JUMP_CONFIRM_SAMPLES:
                cooldown_ok = (
                    a.last_jump_ts is None
                    or (ts - a.last_jump_ts).total_seconds() >= AMBIENT_JUMP_COOLDOWN_SEC
                )
                if cooldown_ok:
                    events.append(
                        Event(
                            ts=ts,
                            type="ambient_jump",
                            detail={"from": a.baseline, "to": value},
                        )
                    )
                    a.last_jump_ts = ts
                a.baseline = value
                a.pending_value = None
                a.pending_count = 0
        else:
            a.pending_value = None
            a.pending_count = 0
            a.baseline = value
        return events

    def _process_touch(self, ts: datetime, sensors: dict) -> list[Event]:
        if "lastTouchEventTime" not in sensors:
            return []
        value = sensors["lastTouchEventTime"]
        t = self._touch
        events: list[Event] = []

        if t.last_seen is None:
            # 起動直後：既存の値を初期値として覚えるだけ（過去のタッチとして扱わない）
            t.last_seen = value
            return []

        if value != t.last_seen and value != 0:
            t.last_seen = value
            if t.group_count > 0 and t.group_last is not None:
                if (ts - t.group_last).total_seconds() > TOUCH_GROUP_WINDOW_SEC:
                    events.append(self._flush_touch_group())
            if t.group_count == 0:
                t.group_start = ts
            t.group_last = ts
            t.group_count += 1
        else:
            # タッチが無いサイクルでも、時間経過でグループを確定させる
            if t.group_count > 0 and t.group_last is not None:
                if (ts - t.group_last).total_seconds() > TOUCH_GROUP_WINDOW_SEC:
                    events.append(self._flush_touch_group())

        return events

    def _flush_touch_group(self) -> Event:
        t = self._touch
        event = Event(ts=t.group_start, type="touch", detail={"count": t.group_count})
        t.group_start = None
        t.group_last = None
        t.group_count = 0
        return event

    def _process_battery(self, ts: datetime, sensors: dict) -> list[Event]:
        if "battery" not in sensors:
            return []
        value = float(sensors["battery"])
        b = self._battery
        events: list[Event] = []
        for threshold in BATTERY_LOW_THRESHOLDS:
            if value < threshold and not b.alerted[threshold]:
                events.append(
                    Event(
                        ts=ts,
                        type="battery_low",
                        detail={"battery": value, "threshold": threshold},
                    )
                )
                b.alerted[threshold] = True
            elif value >= threshold + BATTERY_LOW_HYSTERESIS:
                b.alerted[threshold] = False
        return events

    # ------------------------------------------------------------------
    # /status の処理（sleep/woken）
    # ------------------------------------------------------------------

    def process_status(self, ts: datetime, status: dict) -> list[Event]:
        if "is_sleeping" not in status:
            return []
        is_sleeping = bool(status["is_sleeping"])
        s = self._sleep

        if s.last_is_sleeping is None:
            s.last_is_sleeping = is_sleeping
            return []

        events: list[Event] = []
        if is_sleeping and not s.last_is_sleeping:
            events.append(Event(ts=ts, type="sleep", detail={}))
        elif not is_sleeping and s.last_is_sleeping:
            events.append(Event(ts=ts, type="woken", detail={"source": "unknown"}))
        s.last_is_sleeping = is_sleeping
        return events
