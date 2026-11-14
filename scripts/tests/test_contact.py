"""接点(scripts/contact.py)のテスト"""

import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import contact

T0 = datetime(2026, 11, 14, 14, 5, 10)


def house(tmp_path: Path) -> Path:
    (tmp_path / "characters" / "puchi").mkdir(parents=True)
    return tmp_path


def test_talked_is_recorded_without_the_words(tmp_path):
    base = house(tmp_path)
    event = contact.record(base, "puchi", "talked", who="keeper", via="chat", now=T0)
    assert event == {"ts": "2026-11-14T14:05:10", "type": "talked", "with": "keeper", "via": "chat"}
    line = (base / "characters/puchi/state/contact/20261114.jsonl").read_text(encoding="utf-8")
    assert json.loads(line) == event


def test_mic_keeps_only_the_setting(tmp_path):
    """体のマイクは、だれの声かは分からない。体の設定がだれだったか、だけを残す"""
    event = contact.record(house(tmp_path), "puchi", "talked", via="mic", setting_to="keeper", now=T0)
    assert event == {"ts": "2026-11-14T14:05:10", "type": "talked", "cam_to": "keeper", "via": "mic"}


def test_unknown_character_or_type_writes_nothing(tmp_path):
    base = house(tmp_path)
    assert contact.record(base, "nobody", "talked", who="keeper", now=T0) is None
    assert contact.record(base, "../x", "talked", who="keeper", now=T0) is None
    assert contact.record(base, "puchi", "poked", who="keeper", now=T0) is None
    assert not (base / "characters/puchi/state").exists()


def test_bad_ids_are_dropped(tmp_path):
    event = contact.record(house(tmp_path), "puchi", "hello", who="a b", via="x/y", now=T0)
    assert event == {"ts": "2026-11-14T14:05:10", "type": "hello"}
