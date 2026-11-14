#!/usr/bin/env python3
"""空の暦: 月齢(満月・新月・上弦・下弦)、二十四節気、日の出・日の入。計算だけで出す(外のデータ・鍵は要らない)。

家の場所は PETIT_DATA_DIR/config/place.json(git には入れない):

    {"name": "東京都大田区", "lat": 35.56, "lon": 139.72}

- 月: 新月・上弦・満月・下弦の時刻は Meeus「天文計算」49 章の式(太陽・月の近点離角の補正つき。誤差は数分)。
  その時刻が JST で入る日に印(🌑🌓🌕🌗)。月齢は直前の新月からの日数。ふだんの日は 8 つの形の絵文字だけ
- 二十四節気: 太陽の黄経(Meeus の低精度式)が 15° の区切りを通る日。立春 315° … 冬至 270°
- 日の出・日の入: NOAA の式(見かけの高度 -0.833°)。場所が無ければ出さない

使うところ: 📅 よてい(マスの端に小さく、日の欄に 1 行)、ぷちへ 1 日 1 行(`sky.py line`)。ぷちたちの希望で「小さく、端に」。

Usage:
    python3 sky.py day [--date YYYY-MM-DD]     # その日の空(JSON)
    python3 sky.py line [--date YYYY-MM-DD]    # ぷちに渡す 1 行
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from datetime import date as Date
from datetime import datetime, timedelta, timezone
from pathlib import Path

JST = timezone(timedelta(hours=9))
SYNODIC = 29.530588853
PHASE_NAMES = [("新月", "🌑"), ("上弦", "🌓"), ("満月", "🌕"), ("下弦", "🌗")]
MOON_EMOJI = ["🌑", "🌒", "🌓", "🌔", "🌕", "🌖", "🌗", "🌘"]
TERMS = ["春分", "清明", "穀雨", "立夏", "小満", "芒種", "夏至", "小暑", "大暑", "立秋", "処暑", "白露",
         "秋分", "寒露", "霜降", "立冬", "小雪", "大雪", "冬至", "小寒", "大寒", "立春", "雨水", "啓蟄"]   # 黄経 0° から 15° ごと


def data_dir() -> Path:
    return Path(os.environ.get("PETIT_DATA_DIR") or Path.home() / "petit_claude")


def load_place(base: Path | None = None) -> dict | None:
    try:
        d = json.loads(((base or data_dir()) / "config" / "place.json").read_text(encoding="utf-8"))
        return {"name": str(d.get("name", "")), "lat": float(d["lat"]), "lon": float(d["lon"])}
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None


def _jd(dt: datetime) -> float:
    """ユリウス日(dt はタイムゾーン付き)"""
    u = dt.astimezone(timezone.utc)
    return 2440587.5 + (u - datetime(1970, 1, 1, tzinfo=timezone.utc)).total_seconds() / 86400


def _phase_jde(k: float) -> float:
    """Meeus 49 章: k(整数 = 新月、+0.25 上弦、+0.5 満月、+0.75 下弦)の真の時刻(JDE)。ΔT は無視(1 分ほど)"""
    t = k / 1236.85
    jde = 2451550.09766 + 29.530588861 * k + 0.00015437 * t * t - 0.000000150 * t ** 3 + 0.00000000073 * t ** 4
    e = 1 - 0.002516 * t - 0.0000074 * t * t
    m = math.radians((2.5534 + 29.10535670 * k - 0.0000014 * t * t - 0.00000011 * t ** 3) % 360)
    mp = math.radians((201.5643 + 385.81693528 * k + 0.0107582 * t * t + 0.00001238 * t ** 3 - 0.000000058 * t ** 4) % 360)
    f = math.radians((160.7108 + 390.67050284 * k - 0.0016118 * t * t - 0.00000227 * t ** 3 + 0.000000011 * t ** 4) % 360)
    om = math.radians((124.7746 - 1.56375588 * k + 0.0020672 * t * t + 0.00000215 * t ** 3) % 360)
    phase = round((k % 1) * 4) % 4
    s_, c_ = math.sin, math.cos
    if phase == 0:
        corr = (-0.40720 * s_(mp) + 0.17241 * e * s_(m) + 0.01608 * s_(2 * mp) + 0.01039 * s_(2 * f) + 0.00739 * e * s_(mp - m)
                - 0.00514 * e * s_(mp + m) + 0.00208 * e * e * s_(2 * m) - 0.00111 * s_(mp - 2 * f) - 0.00057 * s_(mp + 2 * f)
                + 0.00056 * e * s_(2 * mp + m) - 0.00042 * s_(3 * mp) + 0.00042 * e * s_(m + 2 * f) + 0.00038 * e * s_(m - 2 * f)
                - 0.00024 * e * s_(2 * mp - m) - 0.00017 * s_(om) - 0.00007 * s_(mp + 2 * m) + 0.00004 * s_(2 * mp - 2 * f)
                + 0.00004 * s_(3 * m) + 0.00003 * s_(mp + m - 2 * f) + 0.00003 * s_(2 * mp + 2 * f) - 0.00003 * s_(mp + m + 2 * f)
                + 0.00003 * s_(mp - m + 2 * f) - 0.00002 * s_(mp - m - 2 * f) - 0.00002 * s_(3 * mp + m) + 0.00002 * s_(4 * mp))
    elif phase == 2:
        corr = (-0.40614 * s_(mp) + 0.17302 * e * s_(m) + 0.01614 * s_(2 * mp) + 0.01043 * s_(2 * f) + 0.00734 * e * s_(mp - m)
                - 0.00515 * e * s_(mp + m) + 0.00209 * e * e * s_(2 * m) - 0.00111 * s_(mp - 2 * f) - 0.00057 * s_(mp + 2 * f)
                + 0.00056 * e * s_(2 * mp + m) - 0.00042 * s_(3 * mp) + 0.00042 * e * s_(m + 2 * f) + 0.00038 * e * s_(m - 2 * f)
                - 0.00024 * e * s_(2 * mp - m) - 0.00017 * s_(om) - 0.00007 * s_(mp + 2 * m) + 0.00004 * s_(2 * mp - 2 * f)
                + 0.00004 * s_(3 * m) + 0.00003 * s_(mp + m - 2 * f) + 0.00003 * s_(2 * mp + 2 * f) - 0.00003 * s_(mp + m + 2 * f)
                + 0.00003 * s_(mp - m + 2 * f) - 0.00002 * s_(mp - m - 2 * f) - 0.00002 * s_(3 * mp + m) + 0.00002 * s_(4 * mp))
    else:
        corr = (-0.62801 * s_(mp) + 0.17172 * e * s_(m) - 0.01183 * e * s_(mp + m) + 0.00862 * s_(2 * mp) + 0.00804 * s_(2 * f)
                + 0.00454 * e * s_(mp - m) + 0.00204 * e * e * s_(2 * m) - 0.00180 * s_(mp - 2 * f) - 0.00070 * s_(mp + 2 * f)
                - 0.00040 * s_(3 * mp) - 0.00034 * e * s_(2 * mp - m) + 0.00032 * e * s_(m + 2 * f) + 0.00032 * e * s_(m - 2 * f)
                - 0.00028 * e * e * s_(mp + 2 * m) + 0.00027 * e * s_(2 * mp + m) - 0.00017 * s_(om) - 0.00005 * s_(mp - m - 2 * f)
                + 0.00004 * s_(2 * mp + 2 * f) - 0.00004 * s_(mp + m + 2 * f) + 0.00004 * s_(mp - 2 * m) + 0.00003 * s_(mp + m - 2 * f)
                + 0.00003 * s_(3 * m) + 0.00002 * s_(2 * mp - 2 * f) + 0.00002 * s_(mp - m + 2 * f) - 0.00002 * s_(3 * mp + m))
        w = 0.00306 - 0.00038 * e * c_(m) + 0.00026 * c_(mp) - 0.00002 * c_(mp - m) + 0.00002 * c_(mp + m) + 0.00002 * c_(2 * f)
        corr += w if phase == 1 else -w
    return jde + corr


def _jde_to_jst(jde: float) -> datetime:
    return (datetime(2000, 1, 1, 12, tzinfo=timezone.utc) + timedelta(days=jde - 2451545.0)).astimezone(JST)


def phases_around(day: Date) -> list[tuple[datetime, int]]:
    """その日の前後 1 か月の 新月(0)・上弦(1)・満月(2)・下弦(3) の時刻(JST)"""
    k0 = math.floor((day.year + (day.timetuple().tm_yday - 1) / 365.25 - 2000) * 12.3685) - 2
    out = []
    for k in range(k0, k0 + 4):
        for q in range(4):
            out.append((_jde_to_jst(_phase_jde(k + q / 4)), q))
    return sorted(out)


def moon_age(dt: datetime) -> float:
    """直前の新月からの日数"""
    news = [t for t, q in phases_around(dt.date()) if q == 0 and t <= dt]
    return (dt - news[-1]).total_seconds() / 86400 if news else 0.0


def sun_longitude(dt: datetime) -> float:
    """太陽の見かけの黄経(度)。Meeus の低精度式"""
    t = (_jd(dt) - 2451545.0) / 36525
    l0 = (280.46646 + 36000.76983 * t + 0.0003032 * t * t) % 360
    m = math.radians((357.52911 + 35999.05029 * t - 0.0001537 * t * t) % 360)
    c = (1.914602 - 0.004817 * t) * math.sin(m) + (0.019993 - 0.000101 * t) * math.sin(2 * m) + 0.000289 * math.sin(3 * m)
    omega = math.radians(125.04 - 1934.136 * t)
    return (l0 + c - 0.00569 - 0.00478 * math.sin(omega)) % 360


def _crosses(day: Date, fn, period: float, marks: list[float]) -> int | None:
    """その日(JST 0:00〜24:00)のうちに fn が marks のどれかを通るか。通る印の番号(回る量は period)"""
    a = fn(datetime(day.year, day.month, day.day, tzinfo=JST))
    b = fn(datetime(day.year, day.month, day.day, tzinfo=JST) + timedelta(days=1))
    span = (b - a) % period
    for i, mk in enumerate(marks):
        if (mk - a) % period < span:
            return i
    return None


def term_of(day: Date) -> str | None:
    """その日に始まる二十四節気(無ければ None)"""
    i = _crosses(day, sun_longitude, 360.0, [k * 15.0 for k in range(24)])
    return TERMS[i] if i is not None else None


def current_term(day: Date) -> tuple[str, Date | None, str]:
    """いまの節気と、次の節気の日と名前"""
    lam = sun_longitude(datetime(day.year, day.month, day.day, 12, tzinfo=JST))
    k = int(lam // 15)
    nxt = None
    for i in range(1, 20):
        d = day + timedelta(days=i)
        if term_of(d):
            nxt = d
            break
    return TERMS[k], nxt, TERMS[(k + 1) % 24]


def moon_mark(day: Date) -> tuple[str, str] | None:
    """その日(JST)に 新月・上弦・満月・下弦 の時刻が入るなら (名前, 絵文字)"""
    for t, q in phases_around(day):
        if t.date() == day:
            return PHASE_NAMES[q]
    return None


def moon_emoji(age: float) -> str:
    return MOON_EMOJI[int((age / SYNODIC) * 8 + 0.5) % 8]


def sun_times(day: Date, lat: float, lon: float) -> tuple[str, str] | None:
    """日の出・日の入(JST の "6:17")。NOAA の式(均時差と赤緯をユリウス世紀から。誤差 1 分ほど)。出ない・沈まない日は None"""
    jd = _jd(datetime(day.year, day.month, day.day, 12, tzinfo=JST))   # 正午(JST)で均時差・赤緯を出す
    t = (jd - 2451545.0) / 36525
    l0 = (280.46646 + t * (36000.76983 + 0.0003032 * t)) % 360
    m = (357.52911 + t * (35999.05029 - 0.0001537 * t)) % 360
    ecc = 0.016708634 - t * (0.000042037 + 0.0000001267 * t)
    mr = math.radians(m)
    c = math.sin(mr) * (1.914602 - t * (0.004817 + 0.000014 * t)) + math.sin(2 * mr) * (0.019993 - 0.000101 * t) + math.sin(3 * mr) * 0.000289
    lam = math.radians(l0 + c - 0.00569 - 0.00478 * math.sin(math.radians(125.04 - 1934.136 * t)))
    eps0 = 23 + (26 + (21.448 - t * (46.815 + t * (0.00059 - t * 0.001813))) / 60) / 60
    eps = math.radians(eps0 + 0.00256 * math.cos(math.radians(125.04 - 1934.136 * t)))
    decl = math.asin(math.sin(eps) * math.sin(lam))
    y = math.tan(eps / 2) ** 2
    l0r = math.radians(l0)
    eqt = 4 * math.degrees(y * math.sin(2 * l0r) - 2 * ecc * math.sin(mr) + 4 * ecc * y * math.sin(mr) * math.cos(2 * l0r)
                           - 0.5 * y * y * math.sin(4 * l0r) - 1.25 * ecc * ecc * math.sin(2 * mr))   # 分
    latr = math.radians(lat)
    cos_ha = math.cos(math.radians(90.833)) / (math.cos(latr) * math.cos(decl)) - math.tan(latr) * math.tan(decl)
    if cos_ha > 1 or cos_ha < -1:
        return None
    ha = math.degrees(math.acos(cos_ha))
    noon = 720 - 4 * lon - eqt + 9 * 60   # JST の分
    out = []
    for mins in (noon - 4 * ha, noon + 4 * ha):
        total = int(round(mins)) % 1440   # 分に丸めてから時と分に分ける(18:60 にならないように)
        out.append(f"{total // 60}:{total % 60:02d}")
    return out[0], out[1]


def day_info(day: Date, place: dict | None) -> dict:
    noon = datetime(day.year, day.month, day.day, 12, tzinfo=JST)
    age = moon_age(noon)
    mark = moon_mark(day)
    term = term_of(day)
    cur, nxt_day, nxt_name = current_term(day)
    out = {"date": day.isoformat(), "moon_age": round(age, 1), "moon": moon_emoji(age), "moon_mark": mark[0] if mark else None,
           "moon_mark_emoji": mark[1] if mark else None, "term": term, "current_term": cur,
           "next_term": {"name": nxt_name, "date": nxt_day.isoformat()} if nxt_day else None, "sunrise": None, "sunset": None}
    if place:
        st = sun_times(day, place["lat"], place["lon"])
        if st:
            out["sunrise"], out["sunset"] = st
    return out


def line(day: Date, place: dict | None) -> str:
    """「きょうの空: 月齢 24.3(🌘)。日の出 6:17・日の入 16:33。二十四節気は 立冬(11/22 から 小雪)」"""
    d = day_info(day, place)
    moon = f"月齢 {d['moon_age']}({d['moon_mark'] + '、' if d['moon_mark'] else ''}{d['moon']})"
    sun = f"。日の出 {d['sunrise']}・日の入 {d['sunset']}" if d["sunrise"] else ""
    nxt = d["next_term"]
    term = f"。二十四節気は {d['current_term']}" + (f"({nxt['date'][5:].replace('-', '/')} から {nxt['name']})" if nxt else "")
    if d["term"]:
        term = f"。きょうから二十四節気の {d['term']}"
    return f"きょうの空: {moon}{sun}{term}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("day", "line"):
        p = sub.add_parser(name)
        p.add_argument("--date", default=None)
    a = ap.parse_args()
    day = Date.fromisoformat(a.date) if a.date else datetime.now(JST).date()
    place = load_place()
    if a.cmd == "day":
        print(json.dumps(day_info(day, place), ensure_ascii=False, indent=2))
    else:
        print(line(day, place))
    return 0


if __name__ == "__main__":
    sys.exit(main())
