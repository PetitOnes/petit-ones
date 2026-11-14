"""experience_digest.py のフォーマット/カーソル挙動のテスト。"""

import json
from datetime import datetime, timedelta
from pathlib import Path

import experience_digest as ed


def _write_events(path: Path, events: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for e in events:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")


def _today_path(tmp_path: Path, character: str) -> Path:
    today = datetime.now().date()
    exp_dir = tmp_path / "characters" / character / "state" / "experience"
    return exp_dir / f"{today.strftime('%Y%m%d')}.jsonl"


def test_digest_formats_and_pairs_pickup_putdown(tmp_path, monkeypatch):
    monkeypatch.setattr(ed, "DATA_DIR", tmp_path)
    character = "testchar"
    # 現在時刻より確実に過去のタイムスタンプを使う（日付跨ぎ・時刻依存のflaky回避）
    base = datetime.now() - timedelta(minutes=30)
    events = [
        {"ts": base.isoformat(timespec="seconds"), "type": "picked_up", "detail": {}},
        {
            "ts": (base + timedelta(seconds=30)).isoformat(timespec="seconds"),
            "type": "put_down",
            "detail": {"carried_sec": 30},
        },
        {
            "ts": (base + timedelta(minutes=2)).isoformat(timespec="seconds"),
            "type": "ambient_jump",
            "detail": {"from": 89, "to": 412},
        },
        {
            "ts": (base + timedelta(minutes=3)).isoformat(timespec="seconds"),
            "type": "touch",
            "detail": {"count": 3},
        },
        {
            "ts": (base + timedelta(minutes=4)).isoformat(timespec="seconds"),
            "type": "sleep",
            "detail": {},
        },
    ]
    _write_events(_today_path(tmp_path, character), events)

    lines, _now = ed.build_digest(character)
    assert lines[0] == f"{base.strftime('%H:%M')} 持ち上げられて、30秒くらい運ばれた"
    assert lines[1].endswith("場所に移った（ambient 89→412）")
    assert lines[2].endswith("タッチされた（3回）")
    assert lines[3].endswith("眠りについた")


def test_digest_empty_when_no_unread(tmp_path, monkeypatch):
    monkeypatch.setattr(ed, "DATA_DIR", tmp_path)
    lines, _now = ed.build_digest("nochar")
    assert lines == []


def test_lone_pickup_without_putdown_still_reported(tmp_path, monkeypatch):
    monkeypatch.setattr(ed, "DATA_DIR", tmp_path)
    character = "testchar3"
    base = datetime.now() - timedelta(minutes=5)
    _write_events(
        _today_path(tmp_path, character),
        [{"ts": base.isoformat(timespec="seconds"), "type": "picked_up", "detail": {}}],
    )
    lines, _now = ed.build_digest(character)
    assert lines == [f"{base.strftime('%H:%M')} 持ち上げられた"]


def test_battery_low_and_offline_gap_formatting(tmp_path, monkeypatch):
    monkeypatch.setattr(ed, "DATA_DIR", tmp_path)
    character = "testchar4"
    base = datetime.now() - timedelta(minutes=20)
    events = [
        {
            "ts": base.isoformat(timespec="seconds"),
            "type": "offline_gap",
            "detail": {"minutes": 26.0},
        },
        {
            "ts": (base + timedelta(minutes=1)).isoformat(timespec="seconds"),
            "type": "battery_low",
            "detail": {"battery": 19.5, "threshold": 20},
        },
    ]
    _write_events(_today_path(tmp_path, character), events)
    lines, _now = ed.build_digest(character)
    assert lines[0] == f"{base.strftime('%H:%M')}から26分間、感覚がなかった"
    assert lines[1] == "電池が残り20%を切った"


def test_mark_read_advances_cursor(tmp_path, monkeypatch):
    monkeypatch.setattr(ed, "DATA_DIR", tmp_path)
    character = "testchar5"
    base = datetime.now() - timedelta(minutes=10)
    woken_event = {
        "ts": base.isoformat(timespec="seconds"),
        "type": "woken",
        "detail": {"source": "unknown"},
    }
    _write_events(_today_path(tmp_path, character), [woken_event])

    lines, now = ed.build_digest(character)
    assert lines == [f"{base.strftime('%H:%M')} 眠っているところを起こされた"]
    ed._write_cursor(character, now)

    lines2, _now2 = ed.build_digest(character)
    assert lines2 == []


def test_touch_kinds_are_told_apart(tmp_path, monkeypatch):
    """撫でられたのか、短く触られたのかを分けて伝える(体が種類を返すときだけ)"""
    monkeypatch.setattr(ed, "DATA_DIR", tmp_path)
    character = "testchar"
    base = datetime.now() - timedelta(minutes=30)

    def at(minute: int) -> str:
        return (base + timedelta(minutes=minute)).isoformat(timespec="seconds")

    _write_events(_today_path(tmp_path, character), [
        {"ts": at(1), "type": "touch", "detail": {"count": 2, "strokes": 2}},
        {"ts": at(2), "type": "touch", "detail": {"count": 3, "strokes": 1, "taps": 2}},
        {"ts": at(3), "type": "touch", "detail": {"count": 1, "taps": 1}},
        {"ts": at(4), "type": "touch", "detail": {"count": 4}},
    ])
    lines, _now = ed.build_digest(character)
    text = "\n".join(lines)
    assert "撫でられた（2回）" in text
    assert "撫でられた（1回）、タッチされた（2回）" in text
    assert "タッチされた（1回）" in text
    assert "タッチされた（4回）" in text
