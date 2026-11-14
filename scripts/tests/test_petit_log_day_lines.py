"""日記の材料(dashboard/petit_log.day_lines)のテスト"""

import json
import sys
from datetime import date as Date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "dashboard"))

import petit_log as pl  # noqa: E402

DAY = Date(2026, 11, 13)


def _house(tmp_path: Path) -> pl.Sources:
    char = tmp_path / "characters" / "puchiko"
    exp = char / "state" / "experience"
    exp.mkdir(parents=True)
    events = [
        ("2026-11-13T15:31:39", "picked_up"),
        ("2026-11-13T15:31:41", "put_down"),
        ("2026-11-13T17:43:00", "picked_up"),
        ("2026-11-13T17:43:20", "put_down"),
        ("2026-11-13T22:00:10", "sleep"),
    ]
    (exp / "20261113.jsonl").write_text("".join(json.dumps({"ts": ts, "type": t, "detail": {}}) + "\n" for ts, t in events), encoding="utf-8")
    chats = char / "chat_histories"
    chats.mkdir()
    msgs = [{"role": "user", "text": "x", "timestamp": f"2026-11-13T17:{m:02d}:00"} for m in (39, 45, 50, 55)]
    msgs.append({"role": "puchiko", "text": "y", "timestamp": "2026-11-13T17:56:00"})
    (chats / "chat_history.json").write_text(json.dumps(msgs), encoding="utf-8")
    (char / "notes").mkdir()
    for d in ("album", "voice", "mailbox", "logs"):
        (tmp_path / d).mkdir()
    return pl.Sources(
        char_id="puchiko", char_dir=char, album_dir=tmp_path / "album", voice_dir=tmp_path / "voice",
        mailbox_dir=tmp_path / "mailbox", auto_log_dir=tmp_path / "logs", memory_db=tmp_path / "none.db",
        user_label=lambda i: "ありさん", name_of=lambda i: i, owner_name="ありさん",
        anniversaries=lambda day: [{"label": "ぷちるの誕生日", "note": ""}] if day == DAY else [],
    )


def test_day_lines_are_oldest_first_and_without_memory(tmp_path):
    lines = pl.day_lines(_house(tmp_path), DAY)
    assert lines[0] == "記念日: ぷちるの誕生日"
    assert lines[1:] == [
        "15:31 ありさんに持ち上げられた",
        "15:31 ありさんに置かれた",
        "17:39〜17:56 ありさんと話した(4 回)",
        "17:43 ありさんに持ち上げられた",
        "17:43 ありさんに置かれた",
        "22:00 眠った",
    ]
    assert not any("記憶" in line for line in lines)


def test_day_lines_empty_day(tmp_path):
    assert pl.day_lines(_house(tmp_path), Date(2026, 11, 1)) == []


def test_hello_shows_up_with_the_sender(tmp_path):
    """「ここにいるよ」は、押した人の名前で出る。続けて押した分は 1 件にまとめる。話しかけた、は出さない"""
    src = _house(tmp_path)
    contact = src.char_dir / "state" / "contact"
    contact.mkdir()
    events = [
        {"ts": "2026-11-13T14:21:00", "type": "hello", "with": "arisan", "via": "dashboard"},
        {"ts": "2026-11-13T14:23:00", "type": "hello", "with": "arisan", "via": "dashboard"},
        {"ts": "2026-11-13T14:30:00", "type": "talked", "with": "arisan", "via": "chat"},
        {"ts": "2026-11-13T20:00:00", "type": "hello", "with": "arisan", "via": "dashboard"},
    ]
    (contact / "20261113.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events) + "not json\n", encoding="utf-8")
    lines = pl.day_lines(src, DAY)
    hello = [line for line in lines if "ここにいるよ" in line]
    assert len(hello) == 2
    assert hello[0].startswith("14:21 ありさんから「ここにいるよ」が届いた")
    assert hello[1].startswith("20:00 ありさんから「ここにいるよ」が届いた")
