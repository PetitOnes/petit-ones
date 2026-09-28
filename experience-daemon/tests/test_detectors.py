"""detectors.ExperienceDetector の単体テスト。すべて合成データのみ、ネットワーク不使用。"""

from datetime import datetime, timedelta

from detectors import ExperienceDetector

BASE = datetime(2026, 7, 6, 12, 0, 0)


def ts(seconds: float) -> datetime:
    return BASE + timedelta(seconds=seconds)


def sensor_sample(**overrides) -> dict:
    base = {
        "ambient": 172,
        "proximity": 0,
        "ax": 0.0,
        "ay": 0.0,
        "az": 1.0,
        "gx": 0.0,
        "gy": 0.0,
        "gz": 0.0,
        "battery": 100.0,
        "voltage": 4102.0,
        "rssi": -34,
        "lastTouchEventTime": 0,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# picked_up / carried / put_down
# ---------------------------------------------------------------------------


def test_picked_up_then_put_down_with_carried_duration():
    d = ExperienceDetector()
    all_events = []

    # t=0, 0.5: 静止（baseline確立）
    all_events += d.process_sensors(ts(0.0), sensor_sample(ax=0.0, ay=0.0, az=1.0))
    all_events += d.process_sensors(ts(0.5), sensor_sample(ax=0.0, ay=0.0, az=1.0))
    assert all_events == []

    # t=1.0 から傾きが90度変わる（持ち上げ）。1.0秒継続でconfirm。
    all_events += d.process_sensors(ts(1.0), sensor_sample(ax=1.0, ay=0.0, az=0.0))
    all_events += d.process_sensors(ts(1.5), sensor_sample(ax=1.0, ay=0.0, az=0.0))
    events_at_confirm = d.process_sensors(ts(2.0), sensor_sample(ax=1.0, ay=0.0, az=0.0))
    all_events += events_at_confirm

    picked_up_events = [e for e in all_events if e.type == "picked_up"]
    assert len(picked_up_events) == 1
    assert picked_up_events[0].ts == ts(1.0)

    # 揺れが続く(carried)。t=2.5〜5.5
    for s in (2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 5.5):
        all_events += d.process_sensors(ts(s), sensor_sample(ax=1.0, ay=0.0, az=0.0))

    # t=6.0 から静止に戻る。3秒継続(6.0〜9.0)でput_down確定。
    for s in (6.0, 6.5, 7.0, 7.5, 8.0, 8.5):
        all_events += d.process_sensors(ts(s), sensor_sample(ax=0.0, ay=0.0, az=1.0))
    confirm_events = d.process_sensors(ts(9.0), sensor_sample(ax=0.0, ay=0.0, az=1.0))
    all_events += confirm_events

    put_down_events = [e for e in all_events if e.type == "put_down"]
    assert len(put_down_events) == 1
    assert put_down_events[0].ts == ts(6.0)
    assert put_down_events[0].detail["carried_sec"] == 5


def test_brief_stillness_blip_does_not_reset_pickup_candidate():
    """持ち上げ判定中に1サンプルだけ静止が混ざっても、猶予内ならcandidateは維持される。"""
    d = ExperienceDetector()
    events = []
    events += d.process_sensors(ts(0.0), sensor_sample(ax=0.0, ay=0.0, az=1.0))
    # 0.5秒時点で動き出し(candidate開始)、1.0秒だけ一瞬静止(blip)、1.5秒でまた動く
    events += d.process_sensors(ts(0.5), sensor_sample(ax=1.0, ay=0.0, az=0.0))
    events += d.process_sensors(ts(1.0), sensor_sample(ax=0.0, ay=0.0, az=1.0))
    events += d.process_sensors(ts(1.5), sensor_sample(ax=1.0, ay=0.0, az=0.0))
    events += d.process_sensors(ts(2.0), sensor_sample(ax=1.0, ay=0.0, az=0.0))
    picked_up_events = [e for e in events if e.type == "picked_up"]
    # 猶予(1.0秒)以内のブリップなので、0.5秒時点からの継続として confirm される
    assert len(picked_up_events) == 1


def test_no_motion_no_events():
    d = ExperienceDetector()
    events = []
    for s in range(20):
        events += d.process_sensors(ts(s * 0.5), sensor_sample(ax=0.01, ay=0.0, az=0.99))
    assert events == []


# ---------------------------------------------------------------------------
# ambient_jump
# ---------------------------------------------------------------------------


def test_ambient_jump_requires_two_samples_and_reports_before_after():
    d = ExperienceDetector()
    events = []
    events += d.process_sensors(ts(0.0), sensor_sample(ambient=100))
    events += d.process_sensors(ts(0.5), sensor_sample(ambient=100))
    assert events == []

    # 1発目のジャンプ: まだconfirmしない
    events += d.process_sensors(ts(1.0), sensor_sample(ambient=400))
    assert [e for e in events if e.type == "ambient_jump"] == []

    # 2発目で確定
    events += d.process_sensors(ts(1.5), sensor_sample(ambient=400))
    jumps = [e for e in events if e.type == "ambient_jump"]
    assert len(jumps) == 1
    assert jumps[0].detail == {"from": 100, "to": 400}


def test_ambient_jump_single_glitch_sample_is_ignored():
    d = ExperienceDetector()
    events = []
    events += d.process_sensors(ts(0.0), sensor_sample(ambient=100))
    events += d.process_sensors(ts(0.5), sensor_sample(ambient=100))
    events += d.process_sensors(ts(1.0), sensor_sample(ambient=500))  # glitch 1発だけ
    events += d.process_sensors(ts(1.5), sensor_sample(ambient=100))  # 元に戻る
    assert [e for e in events if e.type == "ambient_jump"] == []


def test_ambient_jump_cooldown_suppresses_second_event():
    d = ExperienceDetector()
    events = []
    events += d.process_sensors(ts(0.0), sensor_sample(ambient=100))
    events += d.process_sensors(ts(0.5), sensor_sample(ambient=100))
    events += d.process_sensors(ts(1.0), sensor_sample(ambient=400))
    events += d.process_sensors(ts(1.5), sensor_sample(ambient=400))  # 1件目確定
    events += d.process_sensors(ts(2.0), sensor_sample(ambient=50))
    events += d.process_sensors(ts(2.5), sensor_sample(ambient=50))  # 60秒以内なので抑制される

    jumps = [e for e in events if e.type == "ambient_jump"]
    assert len(jumps) == 1

    # 60秒経過後なら再び発火する
    events2 = []
    events2 += d.process_sensors(ts(65.0), sensor_sample(ambient=500))
    events2 += d.process_sensors(ts(65.5), sensor_sample(ambient=500))
    jumps2 = [e for e in events2 if e.type == "ambient_jump"]
    assert len(jumps2) == 1


# ---------------------------------------------------------------------------
# touch
# ---------------------------------------------------------------------------


def test_touch_events_within_window_are_grouped():
    d = ExperienceDetector()
    events = []
    events += d.process_sensors(ts(0.0), sensor_sample(lastTouchEventTime=0))
    events += d.process_sensors(ts(1.0), sensor_sample(lastTouchEventTime=555))
    events += d.process_sensors(ts(2.0), sensor_sample(lastTouchEventTime=777))
    events += d.process_sensors(ts(2.5), sensor_sample(lastTouchEventTime=999))
    # まだフラッシュされない
    assert [e for e in events if e.type == "touch"] == []

    # 30秒以上経過後の次のポーリングでフラッシュされる
    events += d.process_sensors(ts(40.0), sensor_sample(lastTouchEventTime=999))
    touch_events = [e for e in events if e.type == "touch"]
    assert len(touch_events) == 1
    assert touch_events[0].ts == ts(1.0)
    assert touch_events[0].detail == {"count": 3}


def test_touch_groups_split_after_gap():
    d = ExperienceDetector()
    events = []
    events += d.process_sensors(ts(0.0), sensor_sample(lastTouchEventTime=0))
    events += d.process_sensors(ts(1.0), sensor_sample(lastTouchEventTime=111))
    # 40秒後にまた1回タッチ → 前のグループがflushされ、新グループが始まる
    events += d.process_sensors(ts(41.0), sensor_sample(lastTouchEventTime=222))
    touch_events = [e for e in events if e.type == "touch"]
    assert len(touch_events) == 1
    assert touch_events[0].detail == {"count": 1}


# ---------------------------------------------------------------------------
# offline_gap
# ---------------------------------------------------------------------------


def test_offline_gap_emitted_only_after_threshold():
    d = ExperienceDetector()

    # 短い失敗（5秒）は無視される
    d.record_poll_failure(ts(0.0))
    events = d.record_poll_success(ts(5.0))
    assert events == []

    # 20秒以上の失敗は offline_gap になる
    d.record_poll_failure(ts(10.0))
    d.record_poll_failure(ts(15.0))
    events = d.record_poll_success(ts(30.0))
    assert len(events) == 1
    assert events[0].type == "offline_gap"
    assert events[0].ts == ts(10.0)
    assert events[0].detail["minutes"] == round(20.0 / 60.0, 1)


# ---------------------------------------------------------------------------
# sleep / woken
# ---------------------------------------------------------------------------


def test_sleep_and_woken_transitions():
    d = ExperienceDetector()
    events = []
    events += d.process_status(ts(0.0), {"is_sleeping": False, "power_save": False})
    assert events == []  # 初回は基準値を覚えるだけ

    events += d.process_status(ts(10.0), {"is_sleeping": True, "power_save": False})
    sleep_events = [e for e in events if e.type == "sleep"]
    assert len(sleep_events) == 1
    assert sleep_events[0].ts == ts(10.0)

    events += d.process_status(ts(20.0), {"is_sleeping": False, "power_save": False})
    woken_events = [e for e in events if e.type == "woken"]
    assert len(woken_events) == 1
    assert woken_events[0].detail == {"source": "unknown"}


# ---------------------------------------------------------------------------
# battery_low
# ---------------------------------------------------------------------------


def test_battery_low_fires_once_per_threshold_with_hysteresis():
    d = ExperienceDetector()
    events = []
    events += d.process_sensors(ts(0.0), sensor_sample(battery=50.0))
    events += d.process_sensors(ts(1.0), sensor_sample(battery=25.0))
    assert [e for e in events if e.type == "battery_low"] == []

    events += d.process_sensors(ts(2.0), sensor_sample(battery=19.0))
    low20 = [e for e in events if e.type == "battery_low" and e.detail["threshold"] == 20]
    assert len(low20) == 1

    # 20%未満のまま推移しても再発火しない
    events += d.process_sensors(ts(3.0), sensor_sample(battery=18.0))
    low20_again = [e for e in events if e.type == "battery_low" and e.detail["threshold"] == 20]
    assert len(low20_again) == 1

    events += d.process_sensors(ts(4.0), sensor_sample(battery=9.0))
    low10 = [e for e in events if e.type == "battery_low" and e.detail["threshold"] == 10]
    assert len(low10) == 1

    # 25%まで回復して再アーム、再び20%を切ったらもう一度発火する
    events += d.process_sensors(ts(5.0), sensor_sample(battery=26.0))
    events += d.process_sensors(ts(6.0), sensor_sample(battery=19.0))
    low20_rearmed = [e for e in events if e.type == "battery_low" and e.detail["threshold"] == 20]
    assert len(low20_rearmed) == 2
