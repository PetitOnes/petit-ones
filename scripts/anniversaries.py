#!/usr/bin/env python3
"""記念日。家ごとに自由に決める(誕生日・迎えた日・はじめての日など)。

置き場所は家の設定 PETIT_DATA_DIR/config/anniversaries.json:

    {"items": [{"id": "…", "name": "ぷちるの誕生日", "date": "2026-03-05", "repeat": "yearly", "note": ""}]}

- repeat: yearly(毎年その月日)/ monthly(毎月その日)/ once(その日だけ)
- 29〜31 日の記念日は、その日が無い月・年では月の最後の日
- 最初の日(date)より前には出ない

使うところ:
- ダッシュボード(記念日のページ、ぷちログのその日の行)
- 自律行動(今日が記念日のときだけ、プロンプトに 1 行。`anniversaries.py today`)

Usage:
    python3 anniversaries.py today [--date YYYY-MM-DD]      # 今日の記念日を 1 行ずつ(無ければ何も出さない)
    python3 anniversaries.py list                           # 全部と、次に来る日
"""

from __future__ import annotations

import argparse
import calendar
import json
import os
import sys
import uuid
from datetime import date as Date
from datetime import timedelta
from pathlib import Path

REPEATS = ("yearly", "monthly", "once")
NAME_MAX = 40
NOTE_MAX = 200
LOOKAHEAD_DAYS = 366   # 次に来る日を探す幅


def data_dir() -> Path:
    return Path(os.getenv("PETIT_DATA_DIR", str(Path.home() / "petit_claude")))


def path(base: Path | None = None) -> Path:
    return (base or data_dir()) / "config" / "anniversaries.json"


def clean(raw: dict) -> dict:
    """1 件を確かめて、保存する形にする。おかしければ ValueError(人に見せる言葉で)"""
    if not isinstance(raw, dict):
        raise ValueError("記念日の形がおかしい")
    name = str(raw.get("name", "")).strip()
    if not name:
        raise ValueError("名前を入れてください")
    if len(name) > NAME_MAX:
        raise ValueError(f"名前は {NAME_MAX} 字まで")
    try:
        day = Date.fromisoformat(str(raw.get("date", "")))
    except ValueError:
        raise ValueError("日付は 2026-03-05 の形で") from None
    repeat = raw.get("repeat", "yearly")
    if repeat not in REPEATS:
        raise ValueError("くり返しは yearly / monthly / once")
    note = str(raw.get("note", "")).strip()
    if len(note) > NOTE_MAX:
        raise ValueError(f"ひとことは {NOTE_MAX} 字まで")
    return {"id": str(raw.get("id") or uuid.uuid4().hex[:12]), "name": name, "date": day.isoformat(), "repeat": repeat, "note": note}


def load(base: Path | None = None) -> list[dict]:
    """家の記念日(読めないもの・形のおかしいものは飛ばす)。ファイルが無ければ空"""
    try:
        raw = json.loads(path(base).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    items = raw.get("items", []) if isinstance(raw, dict) else []
    out = []
    for it in items if isinstance(items, list) else []:
        try:
            out.append(clean(it))
        except ValueError:
            continue
    return out


def save(items: list[dict], base: Path | None = None) -> None:
    p = path(base)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({"items": items}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(p)


def _day_in_month(year: int, month: int, day: int) -> Date:
    """その月の day 日。無ければ月の最後の日"""
    return Date(year, month, min(day, calendar.monthrange(year, month)[1]))


def occurs_on(item: dict, day: Date) -> bool:
    first = Date.fromisoformat(item["date"])
    if day < first:
        return False
    if item["repeat"] == "once":
        return day == first
    if item["repeat"] == "monthly":
        return day == _day_in_month(day.year, day.month, first.day)
    return day == _day_in_month(day.year, first.month, first.day)


def elapsed(item: dict, day: Date) -> str:
    """最初の日からどれだけか(「1 年」「8 か月」「1 年 2 か月」)。その日そのもの・1 回だけの記念日は空"""
    first = Date.fromisoformat(item["date"])
    if item["repeat"] == "once" or day <= first:
        return ""
    months = (day.year - first.year) * 12 + (day.month - first.month)
    if item["repeat"] == "yearly":
        months -= months % 12
    years, rest = divmod(months, 12)
    parts = ([f"{years} 年"] if years else []) + ([f"{rest} か月"] if rest else [])
    return " ".join(parts)


def label(item: dict, day: Date) -> str:
    """その日の言い方(「ぷちるの誕生日(1 年)」)"""
    span = elapsed(item, day)
    return f"{item['name']}({span})" if span else item["name"]


def on_day(items: list[dict], day: Date) -> list[dict]:
    """その日に当たる記念日。{"id", "name", "label", "note"}"""
    return [{"id": it["id"], "name": it["name"], "label": label(it, day), "note": it["note"]} for it in items if occurs_on(it, day)]


def next_occurrence(item: dict, today: Date) -> Date | None:
    """今日からあとで、次に当たる日(今日も入る)。1 年先までに無ければ None"""
    for n in range(LOOKAHEAD_DAYS + 1):
        day = today + timedelta(days=n)
        if occurs_on(item, day):
            return day
    return None


def upcoming(items: list[dict], today: Date, days: int = 30) -> list[dict]:
    """今日から days 日のうちに来る記念日を、近い順に。{"id", "name", "label", "note", "date", "days_left"}"""
    out = []
    for it in items:
        day = next_occurrence(it, today)
        if day is None or (day - today).days > days:
            continue
        out.append({"id": it["id"], "name": it["name"], "label": label(it, day), "note": it["note"],
                    "date": day.isoformat(), "days_left": (day - today).days})
    return sorted(out, key=lambda x: (x["days_left"], x["name"]))


def today_lines(items: list[dict], day: Date) -> list[str]:
    """自律行動のプロンプトに入れる行。今日が記念日でなければ空"""
    lines = []
    for hit in on_day(items, day):
        note = f" — {hit['note']}" if hit["note"] else ""
        lines.append(f"- 今日は「{hit['label']}」の日{note}")
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description="家の記念日")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_today = sub.add_parser("today", help="今日の記念日を 1 行ずつ(無ければ何も出さない)")
    p_today.add_argument("--date", help="今日の代わりに見る日(YYYY-MM-DD)")
    sub.add_parser("list", help="全部と、次に来る日")
    args = parser.parse_args()
    items = load()
    if args.cmd == "today":
        try:
            day = Date.fromisoformat(args.date) if args.date else Date.today()
        except ValueError:
            print("--date は YYYY-MM-DD の形で", file=sys.stderr)
            return 2
        for line in today_lines(items, day):
            print(line)
        return 0
    today = Date.today()
    for it in items:
        nxt = next_occurrence(it, today)
        when = f"次は {nxt.isoformat()}(あと {(nxt - today).days} 日)" if nxt else "もう来ない"
        print(f"{it['date']} {it['repeat']:8s} {it['name']} … {when}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
