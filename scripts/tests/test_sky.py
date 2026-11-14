"""空の暦(scripts/sky.py)のテスト。2026 年の値は国立天文台の暦と合わせた"""

import calendar
import sys
from datetime import date as Date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import sky  # noqa: E402

PLACE = {"name": "東京都大田区", "lat": 35.56, "lon": 139.72}
DAYS = [Date(2026, m, d) for m in range(1, 13) for d in range(1, calendar.monthrange(2026, m)[1] + 1)]


def test_terms_2026():
    terms = {d: sky.term_of(d) for d in DAYS if sky.term_of(d)}
    assert terms[Date(2026, 2, 4)] == "立春" and terms[Date(2026, 3, 20)] == "春分" and terms[Date(2026, 6, 21)] == "夏至"
    assert terms[Date(2026, 9, 23)] == "秋分" and terms[Date(2026, 11, 7)] == "立冬" and terms[Date(2026, 11, 22)] == "小雪" and terms[Date(2026, 12, 22)] == "冬至"
    assert len(terms) == 24
    assert sky.current_term(Date(2026, 11, 14)) == ("立冬", Date(2026, 11, 22), "小雪")


def test_moon_2026():
    marks = {d: sky.moon_mark(d)[0] for d in DAYS if sky.moon_mark(d)}
    assert marks[Date(2026, 1, 3)] == "満月" and marks[Date(2026, 11, 9)] == "新月" and marks[Date(2026, 11, 24)] == "満月"
    assert marks[Date(2026, 12, 9)] == "新月" and marks[Date(2026, 12, 24)] == "満月" and marks[Date(2026, 11, 17)] == "上弦"
    assert Date(2026, 11, 14) not in marks
    info = sky.day_info(Date(2026, 11, 24), PLACE)
    assert 14 <= info["moon_age"] <= 15.5 and info["moon"] == "🌕" and info["moon_mark"] == "満月"


def test_sun_times_tokyo():
    def mins(t):
        h, m = t.split(":")
        return int(h) * 60 + int(m)
    r, s_ = sky.sun_times(Date(2026, 11, 14), 35.68, 139.77)   # 国立天文台(東京): 6:17 / 16:32
    assert abs(mins(r) - (6 * 60 + 17)) <= 3 and abs(mins(s_) - (16 * 60 + 32)) <= 3
    r, s_ = sky.sun_times(Date(2026, 6, 21), 35.68, 139.77)    # 4:25 / 19:00
    assert abs(mins(r) - (4 * 60 + 25)) <= 3 and abs(mins(s_) - (19 * 60)) <= 3
    assert ":60" not in r + s_
    assert sky.sun_times(Date(2026, 6, 21), 80.0, 0.0) is None   # 白夜


def test_line():
    assert sky.line(Date(2026, 11, 22), PLACE).endswith("きょうから二十四節気の 小雪")
    assert sky.line(Date(2026, 11, 14), None) == "きょうの空: 月齢 4.8(🌒)。二十四節気は 立冬(11/22 から 小雪)"
