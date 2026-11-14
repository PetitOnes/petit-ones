"""予定(scripts/events.py)のテスト"""

import json
import sys
from datetime import date as Date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import events as ev  # noqa: E402

TODAY = Date(2026, 11, 15)   # 展示会(11/22)まで 7 日


def _house(tmp_path: Path) -> Path:
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "people.json").write_text(json.dumps({"arisan": {"name": "ありさん"}}), encoding="utf-8")
    for cid, name in (("puchiko", "ぷちこ"), ("puchiru", "ぷちる")):
        (tmp_path / "characters" / cid / "config").mkdir(parents=True)
        (tmp_path / "characters" / cid / "config" / "config.json").write_text(json.dumps({"id": cid, "name": name}), encoding="utf-8")
    return tmp_path


def test_clean_and_errors():
    it = ev.clean({"title": " 展示会 ", "date": "2026-11-22", "time": "14:00", "place": "ビッグサイト", "who": ["puchiko", "arisan"]})
    assert it["end"] == "2026-11-22" and it["title"] == "展示会" and it["who"] == ["puchiko", "arisan"] and len(it["id"]) == 12
    for bad in ({"title": "", "date": "2026-11-22"}, {"title": "x", "date": "11/22"}, {"title": "x", "date": "2026-11-22", "end": "2026-11-21"},
                {"title": "x", "date": "2026-11-22", "time": "14時"}):
        with pytest.raises(ValueError):
            ev.clean(bad)


def test_on_day_upcoming_and_lines(tmp_path):
    base = _house(tmp_path)
    ev.add({"title": "展示会", "date": "2026-11-22", "time": "14:00", "place": "ビッグサイト", "who": ["puchiko", "puchiru", "arisan"]}, base)
    ev.add({"title": "合宿", "date": "2026-11-13", "end": "2026-11-15", "place": "山口", "who": ["puchiko"]}, base)
    ev.add({"title": "来年", "date": "2027-01-10"}, base)
    items = ev.load(base)
    assert [it["title"] for it in ev.on_day(items, Date(2026, 11, 14))] == ["合宿"]
    assert [it["title"] for it in ev.upcoming(items, TODAY)] == ["合宿", "展示会"]     # 7 日以内。来年は入らない
    assert ev.lines(base, "puchiko", TODAY) == [
        "きょうも 11/13(金)〜11/15 合宿(山口)。行く: ぷちこ(自分も行く)",
        "11/22(日) 展示会(ビッグサイト、14:00 から)。あと 7 日。行く: ぷちこ・ぷちる・ありさん(自分も行く)",
    ]
    assert ev.lines(base, "puchiteya", TODAY)[1].endswith("(自分は留守番)")
    assert ev.lines(base, None, Date(2026, 12, 1)) == []


def test_load_skips_broken(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "events.json").write_text(json.dumps({"items": [{"title": "", "date": "x"}, {"title": "ok", "date": "2026-11-20"}]}), encoding="utf-8")
    assert [it["title"] for it in ev.load(tmp_path)] == ["ok"]
