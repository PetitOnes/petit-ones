#!/usr/bin/env python3
"""日本の祝日(2000〜2099 年の決まりで計算。外のデータは要らない)。📅 よてい のカレンダーに出す。

- 決まった日: 元日・建国記念の日・天皇誕生日(2/23、2020 年〜)・昭和の日・憲法記念日・みどりの日・こどもの日・山の日(8/11、2016 年〜)・文化の日・勤労感謝の日
- 月曜の祝日: 成人の日(1 月第 2 月曜)・海の日(7 月第 3)・敬老の日(9 月第 3)・スポーツの日(10 月第 2)
- 春分・秋分: 1980〜2099 年の近似式
- 振替休日: 日曜の祝日のあとの、祝日でない最初の日
- 国民の休日: 祝日と祝日にはさまれた平日(9 月に起きることがある)
- 2020〜2021 年の東京オリンピックの特例(海の日・スポーツの日・山の日の移動)も入れてある

Usage:
    python3 jp_holidays.py 2026            # その年の祝日を 1 行ずつ
"""

from __future__ import annotations

import sys
from datetime import date as Date
from datetime import timedelta
from functools import lru_cache

FIXED = {(1, 1): "元日", (2, 11): "建国記念の日", (4, 29): "昭和の日", (5, 3): "憲法記念日", (5, 4): "みどりの日", (5, 5): "こどもの日",
         (11, 3): "文化の日", (11, 23): "勤労感謝の日"}
SUBSTITUTE = "振替休日"
CITIZENS = "国民の休日"


def _nth_monday(year: int, month: int, n: int) -> Date:
    first = Date(year, month, 1)
    return first + timedelta(days=(7 - first.weekday()) % 7 + 7 * (n - 1))


def _equinox(year: int, spring: bool) -> int:
    base = 20.8431 if spring else 23.2488
    return int(base + 0.242194 * (year - 1980) - int((year - 1980) / 4))


@lru_cache(maxsize=64)
def of_year(year: int) -> dict[Date, str]:
    """その年の祝日 {日付: 名前}(振替休日・国民の休日を含む)"""
    h: dict[Date, str] = {}
    for (m, d), name in FIXED.items():
        h[Date(year, m, d)] = name
    if year >= 2020:
        h[Date(year, 2, 23)] = "天皇誕生日"
    if year >= 2016:
        h[Date(year, 8, 11)] = "山の日"
    h[_nth_monday(year, 1, 2)] = "成人の日"
    h[_nth_monday(year, 7, 3)] = "海の日"
    h[_nth_monday(year, 9, 3)] = "敬老の日"
    h[_nth_monday(year, 10, 2)] = "スポーツの日" if year >= 2020 else "体育の日"
    h[Date(year, 3, _equinox(year, True))] = "春分の日"
    h[Date(year, 9, _equinox(year, False))] = "秋分の日"
    if year == 2020:   # 東京オリンピックの特例
        for d in (Date(2020, 7, 20), Date(2020, 10, 12), Date(2020, 8, 11)):
            h.pop(d, None)
        h.update({Date(2020, 7, 23): "海の日", Date(2020, 7, 24): "スポーツの日", Date(2020, 8, 10): "山の日"})
    if year == 2021:
        for d in (Date(2021, 7, 19), Date(2021, 10, 11), Date(2021, 8, 11)):
            h.pop(d, None)
        h.update({Date(2021, 7, 22): "海の日", Date(2021, 7, 23): "スポーツの日", Date(2021, 8, 8): "山の日"})
    # 振替休日: 日曜の祝日のあとの、祝日でない最初の日
    for d in sorted(h):
        if d.weekday() == 6:
            nxt = d + timedelta(days=1)
            while nxt in h:
                nxt += timedelta(days=1)
            h[nxt] = SUBSTITUTE
    # 国民の休日: 祝日と祝日にはさまれた平日(日曜は除く)
    for d in sorted(h):
        mid = d + timedelta(days=1)
        if mid not in h and (mid + timedelta(days=1)) in h and mid.weekday() != 6:
            h[mid] = CITIZENS
    return h


def name_of(day: Date) -> str | None:
    return of_year(day.year).get(day)


def main() -> int:
    year = int(sys.argv[1]) if len(sys.argv) > 1 else Date.today().year
    for d, n in sorted(of_year(year).items()):
        print(f"{d.isoformat()} {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
