"""欲求の様子(その子の欲求が、この数日どう動いたか)。

家にいまあるものから組み立てるだけで、新しく何も書かない:

- 欲求の決まり … characters/<id>/config/desire_config.json(名前・満たすまでの時間・満たしたことになる言葉・体や他の欲求からの効き方)
- 強さの記録 … .autonomous-logs/<id>/desire-YYYYMMDD.log(desire_updater が 5 分ごとに書く 1 行)
- 満たした記憶 … 記憶 DB で、その欲求の言葉(keywords)を含む記憶の時刻。欲求は、最後のそれからの時間で上がる
- 道具で満たした回数 … 自律行動の記録にある satisfy_desire の呼び出し
"""

from __future__ import annotations

import ast
import json
import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

DAYS_MAX = 31

# ---- 「眠い」の試し算(2026-11-13、ぷちたちと相談して決めた案。家の決まりは変えず、線を見比べるためだけに計算する)----
SLEEPY_ID = "want_to_sleep"
TRIAL_DARK = 100          # 明るさがこれより下なら「暗い」
TRIAL_BRIGHT = 300        # これ以上なら「明るい」
TRIAL_STILL = 3.0         # ジャイロの大きさがこれより下なら「動いていない」
TRIAL_FAST = 2.0          # 暗くて動いていないときの進み方(倍)
TRIAL_SLOW = 0.5          # 明るいときの進み方(倍)
TRIAL_WAKE_GAP_H = 3      # 眠ってからこれだけたって、その子が動き出したら(自律行動・会話)、起きたとみなす
TRIAL_RULE = [
    "起きたら 0 に戻る(体が起きた・起こされた・入れ直されたとき。または、眠って 3 時間よりあとに、ひとりの時間や会話で動き出したとき)",
    "眠り始めは、「おやすみ」などを記憶に書いたときと、体がスリープしたときの、早いほう。眠っているあいだは 0",
    "起きているあいだ、時間で上がる。暗くて動いていないときは 2 倍の速さ、明るいときは半分の速さ",
    "電池が少ないときの決まりは、いまと同じ",
]
FULL = 0.999   # これ以上を「上限に張りついている」と数える
_LINE = re.compile(r"^\[(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\] \[desire-updater\] 更新完了: dominant=(\w+) desires=(\{.*\})")
_SATISFY = re.compile(r'"name":\s*"mcp__desire-system[\w-]*__satisfy_desire",\s*"input":\s*\{"desire_name":\s*"(\w+)"')


def _samples(log_dir: Path, start: datetime, end: datetime) -> list[tuple[datetime, str, dict, dict]]:
    """強さの記録を、古い順に (時刻, いちばん強かった欲求, {欲求: 強さ}, そのときのセンサー)"""
    out: list = []
    day = start.date()
    while day <= end.date():
        try:
            lines = (log_dir / f"desire-{day.strftime('%Y%m%d')}.log").read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            lines = []
        for line in lines:
            if line.startswith("  sensor: ") and out and len(out[-1]) == 3:   # 直前の 1 行ぶんのセンサー
                try:
                    sensor = ast.literal_eval(line[10:].strip())
                except (ValueError, SyntaxError):
                    sensor = {}
                out[-1] = (*out[-1], sensor if isinstance(sensor, dict) else {})
                continue
            m = _LINE.match(line)
            if not m:
                continue
            try:
                ts = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
                levels = ast.literal_eval(m.group(3))
            except (ValueError, SyntaxError):
                continue
            if start <= ts <= end and isinstance(levels, dict):
                out.append((ts, m.group(2), levels))
        day += timedelta(days=1)
    return [s if len(s) == 4 else (*s, {}) for s in out]


def _body_events(char_dir: Path, start: datetime, end: datetime) -> list[tuple[datetime, str]]:
    """体の眠り・目覚め(state/experience の sleep / woken)を、古い順に"""
    out = []
    day = start.date()
    while day <= end.date():
        try:
            lines = (char_dir / "state" / "experience" / f"{day.strftime('%Y%m%d')}.jsonl").read_text(encoding="utf-8").splitlines()
        except OSError:
            lines = []
        for line in lines:
            try:
                ev = json.loads(line)
                if ev.get("type") in ("sleep", "woken"):
                    out.append((datetime.fromisoformat(ev["ts"][:19]), ev["type"]))
            except (json.JSONDecodeError, KeyError, ValueError, AttributeError):
                continue
        day += timedelta(days=1)
    return sorted(out)


def _session_starts(log_dir: Path, start: datetime) -> list[datetime]:
    """その子が動き出した時刻(自律行動・会話の記録の始まり)"""
    out = []
    try:
        names = [f.name for f in log_dir.iterdir() if f.name.endswith("_stream.jsonl")]
    except OSError:
        return out
    for name in names:
        try:
            ts = datetime.strptime(name[:15], "%Y%m%d_%H%M%S")
        except ValueError:
            continue
        if ts >= start:
            out.append(ts)
    return sorted(out)


def _trial_sleepy(samples: list, hours: float, sleep_marks: list[datetime], body: list[tuple[datetime, str]],
                  sessions: list[datetime], battery_rules: list[dict]) -> list[float | None]:
    """「眠い」を、相談して決めた案で計算し直す(TRIAL_RULE)。samples と同じ並びの強さを返す"""
    events = [(t, "sleep") for t in sleep_marks] + list(body) + [(t, "session") for t in sessions]
    events.sort()
    out: list[float | None] = []
    level, asleep_since, prev, i = 0.0, None, None, 0
    for ts, _, _, sensor in samples:
        while i < len(events) and events[i][0] <= ts:
            when, kind = events[i]
            i += 1
            if kind == "sleep":
                if asleep_since is None:
                    asleep_since = when
            elif kind == "woken" or (asleep_since is not None and (when - asleep_since).total_seconds() >= TRIAL_WAKE_GAP_H * 3600):
                if asleep_since is not None or kind == "woken":
                    asleep_since, level = None, 0.0
        if asleep_since is not None:
            level = 0.0
        elif prev is not None:
            step_h = min((ts - prev).total_seconds() / 3600, 0.5)   # 記録が空いたところは、進めすぎない
            ambient = sensor.get("ambient")
            gyro = max((abs(sensor.get(k) or 0) for k in ("gx", "gy", "gz")), default=0)
            speed = 1.0
            if isinstance(ambient, (int, float)):
                if ambient < TRIAL_DARK and gyro < TRIAL_STILL:
                    speed = TRIAL_FAST
                elif ambient >= TRIAL_BRIGHT:
                    speed = TRIAL_SLOW
            level = min(1.0, level + speed * step_h / hours)
        prev = ts
        shown = level
        battery = sensor.get("battery")
        for rule in battery_rules:   # 電池の決まりは、いまと同じ(その時の値に足す・決める)
            cond, eff = rule["condition"], rule["effects"].get(SLEEPY_ID, {})
            if isinstance(battery, (int, float)) and cond.get("op") == "range" and cond.get("min", 0) <= battery <= cond.get("max", 0):
                shown = float(eff["set"]) if "set" in eff else shown + float(eff.get("add", 0))
        out.append(round(max(0.0, min(1.0, shown)), 3))
    return out


def _satisfied_times(memory_db: Path, keywords: list[str], start: datetime) -> list[str]:
    """その欲求の言葉を含む記憶の時刻(start からあと、古い順)"""
    if not keywords or not memory_db.exists():
        return []
    try:
        conn = sqlite3.connect(f"file:{memory_db}?mode=ro", uri=True)
        cond = " OR ".join("content LIKE ?" for _ in keywords)
        rows = conn.execute(
            f"SELECT timestamp FROM memories WHERE timestamp >= ? AND ({cond}) ORDER BY timestamp",
            [start.isoformat(), *[f"%{k}%" for k in keywords]],
        ).fetchall()
        conn.close()
    except sqlite3.Error:
        return []
    return [r[0][:19] for r in rows if r[0]]


def _tool_satisfies(log_dir: Path, start: datetime) -> dict[str, int]:
    """自律行動・会話の記録で、satisfy_desire を呼んだ回数(欲求ごと)"""
    counts: dict[str, int] = {}
    try:
        files = [f for f in log_dir.iterdir() if f.name.endswith("_stream.jsonl")]
    except OSError:
        return counts
    for f in files:
        try:
            if datetime.strptime(f.name[:15], "%Y%m%d_%H%M%S") < start - timedelta(hours=1):
                continue
            text = f.read_text(encoding="utf-8", errors="ignore")
        except (ValueError, OSError):
            continue
        if "satisfy_desire" not in text:
            continue
        for name in _SATISFY.findall(text):
            counts[name] = counts.get(name, 0) + 1
    return counts


def build(char_dir: Path, log_dir: Path, memory_db: Path, days: int = 7, now: datetime | None = None) -> dict:
    """その子の欲求の様子。days 日ぶん。

    返すもの: {"from", "to", "times": [...], "desires": [{"id", "name", "color", "description", "hours", "keywords",
    "time_driven", "base_level", "values": [...], "now", "full_pct", "top_pct", "mean", "satisfied": [...], "tool_satisfied"}],
    "sensor_effects": [...], "cross_effects": [...], "priority": [...], "samples"}
    """
    now = now or datetime.now()
    days = max(1, min(days, DAYS_MAX))
    start = now - timedelta(days=days)
    try:
        cfg = json.loads((char_dir / "config" / "desire_config.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        cfg = {}
    desires_cfg = cfg.get("desires") if isinstance(cfg.get("desires"), dict) else {}
    samples = _samples(log_dir, start, now)
    tool = _tool_satisfies(log_dir, start)
    n = len(samples)
    ids = list(desires_cfg) + sorted({k for _, _, lv, _ in samples for k in lv} - set(desires_cfg))
    desires = []
    for did in ids:
        d = desires_cfg.get(did, {}) if isinstance(desires_cfg.get(did, {}), dict) else {}
        values = [lv.get(did) for _, _, lv, _ in samples]
        seen = [v for v in values if isinstance(v, (int, float))]
        keywords = [k for k in d.get("keywords", []) if isinstance(k, str)]
        desires.append({
            "id": did, "name": d.get("name_ja", did), "color": d.get("color", "#cab8d9"), "description": d.get("description", ""),
            "hours": d.get("satisfaction_hours"), "keywords": keywords,
            "time_driven": d.get("time_driven", True), "base_level": d.get("base_level"),
            "values": values, "now": seen[-1] if seen else None,
            "full_pct": round(100 * sum(v >= FULL for v in seen) / len(seen)) if seen else None,
            "top_pct": round(100 * sum(top == did for _, top, _, _ in samples) / n) if n else None,
            "mean": round(sum(seen) / len(seen), 2) if seen else None,
            "satisfied": _satisfied_times(memory_db, keywords, start),
            "tool_satisfied": tool.get(did, 0),
        })
        if did == SLEEPY_ID and samples and isinstance(d.get("satisfaction_hours"), (int, float)):
            battery_rules = [s for s in cfg.get("sensor_effects", []) if isinstance(s, dict) and s.get("sensor") == "battery"
                             and isinstance(s.get("condition"), dict) and isinstance(s.get("effects"), dict)]
            marks = [datetime.fromisoformat(t) for t in desires[-1]["satisfied"]]
            trial = _trial_sleepy(samples, float(d["satisfaction_hours"]), marks, _body_events(char_dir, start, now),
                                  _session_starts(log_dir, start), battery_rules)
            got = [v for v in trial if v is not None]
            desires[-1]["trial"] = {"values": trial, "rule": TRIAL_RULE,
                                    "full_pct": round(100 * sum(v >= FULL for v in got) / len(got)) if got else None}

    def _desc(items: object) -> list[str]:
        return [str(i.get("description", "")) for i in items if isinstance(i, dict) and i.get("description")] if isinstance(items, list) else []

    return {
        "from": start.isoformat(timespec="seconds"), "to": now.isoformat(timespec="seconds"), "samples": n,
        "times": [ts.isoformat(timespec="minutes") for ts, _, _, _ in samples],
        "desires": desires,
        "sensor_effects": _desc(cfg.get("sensor_effects")), "cross_effects": _desc(cfg.get("cross_effects")),
        "priority": [p for p in cfg.get("priority", []) if isinstance(p, str)],
    }
