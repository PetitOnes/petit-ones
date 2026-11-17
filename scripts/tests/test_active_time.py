"""active_time.py: いまの回がアクティブタイムのどこか"""
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import active_time as at  # noqa: E402

S = {"active_hours": {"weekday": [[7, 0, 8, 10], [22, 0, 23, 10], [12, 0, 13, 10]], "weekend": [[7, 30, 8, 10], [22, 0, 23, 10]]}}


def test_inside_with_later_slots():
    assert at.line(S, datetime(2026, 11, 17, 7, 30)) == "いまの回: アクティブタイム 7:00〜8:10 の中(このあとは 12:00〜13:10・22:00〜23:10。きょうは平日)"


def test_last_slot_points_to_tomorrow_weekend():
    # 2026-11-20 は金曜。あすは土曜(休日)
    assert at.line(S, datetime(2026, 11, 20, 22, 30)).endswith("(そのあとは あす 7:30〜。きょうは平日)")


def test_awake_outside():
    s = {**S, "awake": {"until": "2026-11-18T01:30"}}
    assert at.line(s, datetime(2026, 11, 18, 0, 30)) == "いまの回: 時間外も起きている(1:30 まで。このあとは 7:00〜8:10・12:00〜13:10・22:00〜23:10)"


def test_override_today():
    s = {**S, "day_type_override": "weekend"}
    assert "きょうは休日" in at.line(s, datetime(2026, 11, 17, 7, 45))
