"""記念日(scripts/anniversaries.py)のテスト"""

import sys
from datetime import date as Date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import anniversaries as an


def item(name: str, date: str, repeat: str = "yearly", note: str = "") -> dict:
    return an.clean({"name": name, "date": date, "repeat": repeat, "note": note})


def test_yearly_and_label():
    it = item("うまれた日", "2026-02-27")
    assert an.occurs_on(it, Date(2026, 2, 27))
    assert an.label(it, Date(2026, 2, 27)) == "うまれた日"            # その日そのものは、名前だけ
    assert an.occurs_on(it, Date(2027, 2, 27))
    assert an.label(it, Date(2027, 2, 27)) == "うまれた日(1 年)"
    assert not an.occurs_on(it, Date(2027, 2, 26))
    assert not an.occurs_on(it, Date(2025, 2, 27))                     # 最初の日より前には出ない


def test_monthly_and_label():
    it = item("むかえた日", "2026-03-05", "monthly")
    assert an.occurs_on(it, Date(2026, 11, 5))
    assert an.label(it, Date(2026, 11, 5)) == "むかえた日(8 か月)"
    assert an.label(it, Date(2027, 3, 5)) == "むかえた日(1 年)"
    assert an.label(it, Date(2027, 5, 5)) == "むかえた日(1 年 2 か月)"
    assert not an.occurs_on(it, Date(2026, 11, 6))


def test_count_off_shows_name_only():
    """数えない記念日(人の誕生日など)は、何年たっても名前だけ"""
    it = an.clean({"name": "たんじょうび", "date": "2026-09-21", "count": False})
    assert an.occurs_on(it, Date(2030, 9, 21))
    assert an.label(it, Date(2030, 9, 21)) == "たんじょうび"


def test_date_without_year():
    """年のない記念日は、毎年その月日に出て、何年目かは数えない"""
    it = an.clean({"name": "たんじょうび", "date": "09-21"})
    assert it["date"] == "09-21" and it["count"] is False
    assert an.occurs_on(it, Date(1999, 9, 21)) and an.occurs_on(it, Date(2030, 9, 21))
    assert not an.occurs_on(it, Date(2030, 9, 22))
    assert an.label(it, Date(2030, 9, 21)) == "たんじょうび"
    assert an.next_occurrence(it, Date(2026, 11, 13)) == Date(2027, 9, 21)
    assert an.occurs_on(an.clean({"name": "うるう", "date": "02-29"}), Date(2027, 2, 28))
    with pytest.raises(ValueError):
        an.clean({"name": "x", "date": "09-21", "repeat": "monthly"})
    with pytest.raises(ValueError):
        an.clean({"name": "x", "date": "13-01"})


def test_add_keeps_who_and_skips_duplicates(tmp_path):
    first, added = an.add({"name": "はじめて海を見た日", "date": "2026-08-01", "by": "puchi"}, tmp_path)
    assert added and first["by"] == "puchi"
    again, added = an.add({"name": "はじめて海を見た日", "date": "2026-08-01", "by": "other"}, tmp_path)
    assert not added and again["id"] == first["id"]
    assert len(an.load(tmp_path)) == 1
    with pytest.raises(ValueError):
        an.add({"name": "", "date": "2026-08-01"}, tmp_path)


def test_notice_once_the_day_before(tmp_path):
    """前の日に 1 度だけ。前の日に伝えていれば当日は出さない。伝えられなかったら当日に"""
    it = item("うまれた日", "2026-03-04", note="お祝い")
    key = f"{it['id']}:2027-03-04"
    lines, keys = an.notice([it], Date(2027, 3, 3), [])
    assert lines == ["（ちなみに、あしたは「うまれた日(1 年)」の日 — お祝い）"] and keys == [key]
    assert an.notice([it], Date(2027, 3, 3), [key]) == ([], [])          # 同じ日の 2 回目
    assert an.notice([it], Date(2027, 3, 4), [key]) == ([], [])          # 当日(前の日に伝えた)
    lines, keys = an.notice([it], Date(2027, 3, 4), [])                    # 前の日に動かなかった子
    assert lines == ["（ちなみに、今日は「うまれた日(1 年)」の日 — お祝い）"] and keys == [key]
    assert an.notice([it], Date(2027, 3, 2), []) == ([], [])              # 2 日前はまだ
    an.save_told("puchi", [key], tmp_path)
    assert an.load_told("puchi", tmp_path) == [key]
    assert an.load_told("other", tmp_path) == []


def test_once():
    it = item("発表の日", "2026-08-25", "once")
    assert an.occurs_on(it, Date(2026, 8, 25))
    assert not an.occurs_on(it, Date(2027, 8, 25))
    assert an.next_occurrence(it, Date(2026, 8, 26)) is None


def test_day_missing_in_month_falls_on_last_day():
    """31 日の毎月の記念日は 30 日までの月では 30 日、2/29 の毎年の記念日は平年では 2/28"""
    monthly = item("月末", "2026-01-31", "monthly")
    assert an.occurs_on(monthly, Date(2026, 2, 28))
    assert an.occurs_on(monthly, Date(2026, 4, 30))
    assert not an.occurs_on(monthly, Date(2026, 3, 30))
    leap = item("うるう", "2028-02-29")
    assert an.occurs_on(leap, Date(2029, 2, 28))
    assert an.occurs_on(leap, Date(2032, 2, 29))
    assert not an.occurs_on(leap, Date(2032, 2, 28))


def test_upcoming_is_sorted_and_includes_today():
    items = [item("あと", "2026-03-05"), item("きょう", "2026-02-27"), item("とおい", "2026-09-21")]
    got = an.upcoming(items, Date(2027, 2, 27), days=30)
    assert [(g["name"], g["days_left"]) for g in got] == [("きょう", 0), ("あと", 6)]
    assert got[0]["label"] == "きょう(1 年)"


def test_today_lines():
    items = [item("うまれた日", "2026-02-27", note="みんなでお祝い")]
    assert an.today_lines(items, Date(2027, 2, 27)) == ["- 今日は「うまれた日(1 年)」の日 — みんなでお祝い"]
    assert an.today_lines(items, Date(2027, 2, 28)) == []


@pytest.mark.parametrize("raw", [
    {"name": "", "date": "2026-01-01"},
    {"name": "x" * 41, "date": "2026-01-01"},
    {"name": "x", "date": "2026-13-01"},
    {"name": "x", "date": "2026-01-01", "repeat": "weekly"},
])
def test_clean_rejects(raw):
    with pytest.raises(ValueError):
        an.clean(raw)


def test_save_and_load(tmp_path):
    items = [item("うまれた日", "2026-02-27")]
    an.save(items, tmp_path)
    assert an.load(tmp_path) == items
    assert an.load(tmp_path / "nothing") == []
    # 形のおかしい 1 件は飛ばして、残りは読む
    an.path(tmp_path).write_text('{"items": [{"name": "", "date": "x"}, {"name": "ok", "date": "2026-01-01"}]}', encoding="utf-8")
    assert [i["name"] for i in an.load(tmp_path)] == ["ok"]
