"""気配(scripts/presence_watch.py)のテスト"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import presence_watch as pw

T0 = datetime(2026, 11, 14, 9, 0)


def house(tmp_path: Path, away_min: int = 20) -> Path:
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "presence.json").write_text(json.dumps({
        "away_min": away_min,
        "sensors": [{"kind": "fake", "id": "s1", "place": "つくえ"}],
    }, ensure_ascii=False), encoding="utf-8")
    return tmp_path


def run(base: Path, pattern: list[tuple[int, bool | None]]) -> list[dict]:
    """(分, 動きがあるか) の並びを順に見せて、足された出来事を集める"""
    out = []
    for minute, moving in pattern:
        out += pw.poll(base, T0 + timedelta(minutes=minute), {"fake": lambda b, i, m=moving: m})
    return out


def test_first_motion_is_an_arrival_without_away_time(tmp_path):
    events = run(house(tmp_path), [(0, False), (1, True)])
    assert events == [{"ts": "2026-11-14T09:01:00", "type": "arrived", "place": "つくえ"}]


def test_staying_is_not_counted(tmp_path):
    """居続けるあいだは数えない。短く動きが止まっても、いるまま"""
    events = run(house(tmp_path), [(0, True), (1, True), (5, False), (10, True), (25, True), (30, False)])
    assert [e["type"] for e in events] == ["arrived"]


def test_left_after_quiet_and_next_arrival_knows_how_long(tmp_path):
    events = run(house(tmp_path), [(0, True), (30, True), (31, False), (49, False), (50, False), (140, True)])
    assert events == [
        {"ts": "2026-11-14T09:00:00", "type": "arrived", "place": "つくえ"},
        {"ts": "2026-11-14T09:30:00", "type": "left", "place": "つくえ", "stayed_min": 30},
        {"ts": "2026-11-14T11:20:00", "type": "arrived", "place": "つくえ", "away_min": 110},
    ]


def test_unreadable_sensor_changes_nothing(tmp_path):
    events = run(house(tmp_path), [(0, True), (1, None), (60, None), (61, True)])
    assert [e["type"] for e in events] == ["arrived"]   # 読めないあいだに「離れた」と決めない


def test_events_are_written_by_day(tmp_path):
    base = house(tmp_path)
    run(base, [(0, True)])
    lines = (base / "state" / "presence" / "20261114.jsonl").read_text(encoding="utf-8").splitlines()
    assert json.loads(lines[0])["type"] == "arrived"


def test_no_config_does_nothing(tmp_path):
    assert pw.poll(tmp_path, T0, {"fake": lambda b, i: True}) == []
    assert not (tmp_path / "state").exists()


def test_line_does_not_say_who(tmp_path):
    base = house(tmp_path)
    run(base, [(0, True), (5, True)])
    assert pw.line(base, T0 + timedelta(minutes=6)) == "つくえのあたり: 動きがある(9:00 から)"
    run(base, [(6, False), (30, False)])
    assert pw.line(base, T0 + timedelta(minutes=31)) == "つくえのあたり: いまは動きがない(最後は 9:05)"
    # 見張りが止まっていたら、いまのことは言わない
    assert pw.line(base, T0 + timedelta(minutes=60)) == ""
