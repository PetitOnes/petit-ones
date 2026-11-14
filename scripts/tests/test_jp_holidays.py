"""日本の祝日(scripts/jp_holidays.py)のテスト"""

import sys
from datetime import date as Date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import jp_holidays as jh  # noqa: E402


def test_2026():
    h = jh.of_year(2026)
    assert h[Date(2026, 11, 23)] == "勤労感謝の日"
    assert h[Date(2026, 1, 12)] == "成人の日" and h[Date(2026, 7, 20)] == "海の日" and h[Date(2026, 9, 21)] == "敬老の日" and h[Date(2026, 10, 12)] == "スポーツの日"
    assert h[Date(2026, 3, 20)] == "春分の日" and h[Date(2026, 9, 23)] == "秋分の日"
    assert h[Date(2026, 5, 6)] == "振替休日"          # 5/3 が日曜 → 5/4・5/5 は祝日なので 5/6
    assert h[Date(2026, 9, 22)] == "国民の休日"        # 敬老の日(9/21)と秋分の日(9/23)のあいだ
    assert jh.name_of(Date(2026, 11, 14)) is None


def test_2025_and_2020():
    assert jh.of_year(2025)[Date(2025, 11, 24)] == "振替休日"   # 11/23 が日曜
    assert jh.of_year(2025)[Date(2025, 2, 24)] == "振替休日"    # 2/23 が日曜
    h = jh.of_year(2020)
    assert h[Date(2020, 7, 23)] == "海の日" and h[Date(2020, 7, 24)] == "スポーツの日" and Date(2020, 7, 20) not in h
