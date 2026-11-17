#!/usr/bin/env python3
"""いまの回がアクティブタイムのどこか、を本人に 1 行で渡す(2026-11-17 ありさん)。

ぷちは自分のアクティブタイム(自律行動で起きる時間)を知らずに動いていた。次がいつか分かれば、
8:10 で終わるのに長い読書を始めない・「続きは 12 時に」と書ける・朝から夜まで呼ばれない日を「置いていかれた」と読まない。
決まりではなく知らせ。材料は characters/<id>/config/settings.json の active_hours(weekday / weekend)と awake.until。
平日か休日かは autonomous-action.sh と同じ(土日 = 休日、day_type_override があればきょうはそちら)。

    python3 active_time.py line --character <id> [--day-type weekday|weekend]

    いまの回: アクティブタイム 12:00〜13:10 の中(このあとは 22:00〜23:10。きょうは平日)
    いまの回: 時間外も起きている(1:30 まで。そのあとは あす 7:00〜)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

DAY_WORDS = {"weekday": "平日", "weekend": "休日"}


def data_dir() -> Path:
    return Path(os.environ.get("PETIT_DATA_DIR") or Path.home() / "petit_claude")


def _slots(settings: dict, day_type: str) -> list[tuple[int, int]]:
    """その日のアクティブタイムを (はじまりの分, おわりの分) で、早い順に"""
    ah = settings.get("active_hours")
    raw = ah.get(day_type, []) if isinstance(ah, dict) else ah if isinstance(ah, list) else []
    out = []
    for e in raw:
        if isinstance(e, list) and len(e) == 4:
            out.append((e[0] * 60 + e[1], e[2] * 60 + e[3]))
        elif isinstance(e, list) and len(e) == 2:
            out.append((e[0] * 60, e[1] * 60))
    return sorted(out)


def _hm(minutes: int) -> str:
    return f"{minutes // 60}:{minutes % 60:02d}"


def _span(s: tuple[int, int]) -> str:
    return f"{_hm(s[0])}〜{_hm(s[1])}"


def day_type_of(d: datetime, settings: dict, today: bool) -> str:
    if today and settings.get("day_type_override") in DAY_WORDS:
        return settings["day_type_override"]
    return "weekend" if d.isoweekday() >= 6 else "weekday"


def line(settings: dict, now: datetime, day_type: str | None = None) -> str:
    dt = day_type or day_type_of(now, settings, True)
    today = _slots(settings, dt)
    m = now.hour * 60 + now.minute
    cur = next((s for s in today if s[0] <= m < s[1]), None)
    later = [s for s in today if s[0] > m]
    if later:
        nxt = "このあとは " + "・".join(_span(s) for s in later)
    else:
        tomorrow = now + timedelta(days=1)
        ts = _slots(settings, day_type_of(tomorrow, settings, False))
        nxt = f"そのあとは あす {_hm(ts[0][0])}〜" if ts else "あすのアクティブタイムは決まっていない"
    if cur:
        return f"いまの回: アクティブタイム {_span(cur)} の中({nxt}。きょうは{DAY_WORDS.get(dt, dt)})"
    until = None
    try:
        until = datetime.fromisoformat(((settings.get("awake") or {}).get("until")) or "")
    except (TypeError, ValueError):
        pass
    if until and until > now:
        return f"いまの回: 時間外も起きている({until.hour}:{until.minute:02d} まで。{nxt})"
    return f"いまの回: アクティブタイムの外({nxt})"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="いまの回がアクティブタイムのどこか(本人に渡す 1 行)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("line")
    p.add_argument("--character", required=True)
    p.add_argument("--day-type", choices=tuple(DAY_WORDS))
    a = ap.parse_args(argv)
    try:
        settings = json.loads((data_dir() / "characters" / a.character / "config" / "settings.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0
    if isinstance(settings, dict) and settings.get("active_hours"):
        print(line(settings, datetime.now(), a.day_type))
    return 0


if __name__ == "__main__":
    sys.exit(main())
