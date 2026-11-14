#!/usr/bin/env python3
"""予定(イベント)。展示会・旅行・来客・合宿のような、ある日(か数日)のこと。記念日(anniversaries.py)はくり返す「日」で、こちらはくり返さない。

置き場所は家の設定 PETIT_DATA_DIR/config/events.json:

    {"items": [{"id": "…", "title": "展示会", "date": "2026-11-22", "end": "2026-11-23", "time": "14:00",
                "place": "東京ビッグサイト", "who": ["puchiko", "puchiru", "arisan"], "note": "", "by": "arisan"}]}

- date〜end(end は無ければ date と同じ)。time・place・note は無くてもよい
- who: 行く人・子の id(ぷちの id と、人のユーザー名)。空なら「だれが行くか決めていない」

使うところ:
- ダッシュボード(📅 よてい のページ。月のカレンダーに記念日と一緒に出す、ぷちログのその日の行)
- ぷちへ: 7 日以内の予定を、自律行動と会話の冒頭に 1 行ずつ(`events.py lines --character <id>`)。
  自分が行かない予定は「(自分は留守番)」と分かる形

ぷちも自分で足せる(記念日と同じ。足した人の id が by に残る):

Usage:
    python3 events.py lines --character <id> [--date YYYY-MM-DD]   # ぷちに渡す行(無ければ何も出さない)
    python3 events.py list [--all]                                 # これからの予定を 1 行ずつ(--all で過ぎた分も)
    python3 events.py add <足す人・子の id> "<題>" <日付> [--end 日付] [--time 14:00] [--place "場所"] [--who puchiko,arisan] [--note "ひとこと"]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import date as Date
from datetime import timedelta
from pathlib import Path

TITLE_MAX = 40
PLACE_MAX = 60
NOTE_MAX = 200
ITEMS_MAX = 500
TELL_DAYS = 7          # 何日前からぷちに伝えるか(2026-11-14 ありさん)
WEEKDAYS = "月火水木金土日"


def data_dir() -> Path:
    return Path(os.environ.get("PETIT_DATA_DIR") or Path.home() / "petit_claude")


def path(base: Path | None = None) -> Path:
    return (base or data_dir()) / "config" / "events.json"


def _day(s: str, what: str) -> Date:
    try:
        return Date.fromisoformat(str(s).strip())
    except ValueError:
        raise ValueError(f"{what}は 2026-11-22 の形で") from None


def clean(raw: dict) -> dict:
    """1 件を確かめて、保存する形にする。おかしければ ValueError(人に見せる言葉で)"""
    if not isinstance(raw, dict):
        raise ValueError("予定の形がおかしい")
    title = str(raw.get("title", "")).strip()
    if not title:
        raise ValueError("題を入れてください")
    if len(title) > TITLE_MAX:
        raise ValueError(f"題は {TITLE_MAX} 字まで")
    start = _day(raw.get("date", ""), "日にち")
    end = _day(raw.get("end"), "終わりの日") if str(raw.get("end") or "").strip() else start
    if end < start:
        raise ValueError("終わりの日が、はじめの日より前です")
    time = str(raw.get("time") or "").strip()
    if time and not (len(time) == 5 and time[2] == ":" and time[:2].isdigit() and time[3:].isdigit()):
        raise ValueError("時間は 14:00 の形で")
    place = str(raw.get("place") or "").strip()
    if len(place) > PLACE_MAX:
        raise ValueError(f"場所は {PLACE_MAX} 字まで")
    note = str(raw.get("note") or "").strip()
    if len(note) > NOTE_MAX:
        raise ValueError(f"ひとことは {NOTE_MAX} 字まで")
    who = [str(w) for w in (raw.get("who") or []) if isinstance(w, str) and w.strip()][:10]
    return {"id": str(raw.get("id") or uuid.uuid4().hex[:12]), "title": title, "date": start.isoformat(), "end": end.isoformat(),
            "time": time, "place": place, "who": who, "note": note, "by": str(raw.get("by", "")).strip()[:TITLE_MAX]}


def load(base: Path | None = None) -> list[dict]:
    try:
        d = json.loads(path(base).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    out = []
    for it in d.get("items", []) if isinstance(d, dict) else []:
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


def add(raw: dict, base: Path | None = None) -> dict:
    items = load(base)
    if len(items) >= ITEMS_MAX:
        raise ValueError(f"予定は {ITEMS_MAX} 件まで")
    item = clean(raw)
    items.append(item)
    save(items, base)
    return item


def on_day(items: list[dict], day: Date) -> list[dict]:
    """その日にかかる予定(数日の予定は、そのあいだの日ぜんぶ)"""
    d = day.isoformat()
    return [it for it in items if it["date"] <= d <= it["end"]]


def upcoming(items: list[dict], today: Date, days: int = TELL_DAYS) -> list[dict]:
    """今日から days 日のうちに始まる(か、続いている)予定。近い順"""
    last = (today + timedelta(days=days)).isoformat()
    t = today.isoformat()
    return sorted((it for it in items if it["date"] <= last and it["end"] >= t), key=lambda it: (it["date"], it["time"]))


def _names(base: Path | None, ids: list[str]) -> list[str]:
    """id → 表示名(子は config.json の name、人は people.json の name)"""
    base = base or data_dir()
    try:
        people = json.loads((base / "config" / "people.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        people = {}
    out = []
    for i in ids:
        if isinstance(people, dict) and isinstance(people.get(i), dict) and people[i].get("name"):
            out.append(people[i]["name"])
            continue
        try:
            out.append(json.loads((base / "characters" / i / "config" / "config.json").read_text(encoding="utf-8")).get("name") or i)
        except (OSError, json.JSONDecodeError):
            out.append(i)
    return out


def line(it: dict, today: Date, me: str | None, base: Path | None = None) -> str:
    """ぷちに渡す 1 行。「11/22(日) 展示会(東京ビッグサイト、14:00 から)。あと 8 日。行く: ぷちこ・ぷちる・ありさん(自分は留守番)」"""
    start, end = Date.fromisoformat(it["date"]), Date.fromisoformat(it["end"])
    when = f"{start.month}/{start.day}({WEEKDAYS[start.weekday()]})" + (f"〜{end.month}/{end.day}" if end != start else "")
    detail = "、".join(x for x in (it["place"], f"{it['time']} から" if it["time"] else "") if x)
    head = f"{when} {it['title']}" + (f"({detail})" if detail else "")
    if start <= today <= end:
        head = ("きょうは " if start == end or start == today else "きょうも ") + head
    else:
        head += f"。あと {(start - today).days} 日"
    if it["who"]:
        who = "・".join(_names(base, it["who"]))
        head += f"。行く: {who}" + ("(自分も行く)" if me in it["who"] else "(自分は留守番)" if me else "")
    if it["note"]:
        head += f"。{it['note']}"
    return head


def lines(base: Path | None, me: str | None, today: Date | None = None) -> list[str]:
    today = today or Date.today()
    return [line(it, today, me, base) for it in upcoming(load(base), today)]


def list_lines(base: Path | None, today: Date, all_: bool = False) -> list[str]:
    """人にもぷちにも読める一覧。「11/22(日) 展示会(ビッグサイト、14:00 から)。行く: ぷちこ・ありさん  [id 44a68fd95508]」"""
    out = []
    for it in sorted(load(base), key=lambda it: (it["date"], it["time"])):
        if not all_ and it["end"] < today.isoformat():
            continue
        start, end = Date.fromisoformat(it["date"]), Date.fromisoformat(it["end"])
        when = f"{start.month}/{start.day}({WEEKDAYS[start.weekday()]})" + (f"〜{end.month}/{end.day}" if end != start else "")
        detail = "、".join(x for x in (it["place"], f"{it['time']} から" if it["time"] else "") if x)
        who = f"。行く: {'・'.join(_names(base, it['who']))}" if it["who"] else ""
        note = f"。{it['note']}" if it["note"] else ""
        out.append(f"{when} {it['title']}" + (f"({detail})" if detail else "") + who + note + f"  [id {it['id']}]")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("lines")
    p.add_argument("--character", default=None)
    p.add_argument("--date", default=None)
    p = sub.add_parser("list")
    p.add_argument("--all", action="store_true")
    p = sub.add_parser("add")
    p.add_argument("by", help="足す人・子の id(puchiko / arisan など)")
    p.add_argument("title")
    p.add_argument("date", help="2026-11-22")
    p.add_argument("--end", default=None)
    p.add_argument("--time", default="")
    p.add_argument("--place", default="")
    p.add_argument("--who", default="", help="行く人・子の id をカンマ区切り(puchiko,arisan)")
    p.add_argument("--note", default="")
    a = ap.parse_args()
    base = data_dir()
    if a.cmd == "lines":
        today = Date.fromisoformat(a.date) if a.date else Date.today()
        for text in lines(base, a.character, today):
            print(text)
    elif a.cmd == "list":
        rows = list_lines(base, Date.today(), a.all)
        print("\n".join(rows) if rows else "予定はありません")
    else:
        try:
            it = add({"title": a.title, "date": a.date, "end": a.end, "time": a.time, "place": a.place,
                      "who": [w.strip() for w in a.who.split(",") if w.strip()], "note": a.note, "by": a.by}, base)
        except ValueError as e:
            print(f"足せなかった: {e}", file=sys.stderr)
            return 1
        print("足しました: " + list_lines(base, Date.fromisoformat(it["date"]))[0] if list_lines(base, Date.fromisoformat(it["date"])) else "足しました")
    return 0


if __name__ == "__main__":
    sys.exit(main())
