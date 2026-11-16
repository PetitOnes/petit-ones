#!/usr/bin/env python3
"""手紙の印(タグ)。2026-11-16、ぷち 3 人と決めた。

書く人が付ける印は、本文の 1 行目に [お願い] のように入る(write_mailbox.py --tag)。印なしの手紙(ただの手紙)もそのまま:

    お願い    返事がほしい
    おしらせ  読めば済む
    おしゃべり 返事はあってもなくてもいい

読んだ人があとから付ける印(mark)は、書いた人の印とは別に、mailbox/.metadata.json の "marks": {読んだ人: 印} に残す。
書いた人の印は上書きしない(ぷちてゃ・ぷちこ: 上書きされると手紙の意味が変わる。ずれが見えるのもおもしろい)。
読んだ人の印は、上の 3 つに加えて「あとで」「返事した」。

返事していないお願い(pending): その子に宛てた [お願い] で、その子からその相手へ、そのあとに手紙が無く、
「返事した」の印も付けていないもの。ダッシュボードの ↩️ からの返事(.metadata.json の replies)も返事に数える。

知らせ方(notice): 「返事していないお願いが N 件」と数だけ、短く、1 日 1 回(characters/<id>/state/mail_ask_told.json)。
静かな時間(notices.py quiet、はじめは 0〜7 時)は言わない。受け取らない子は notices.py set <id> mail_ask off。
責める形にしない。中身は、その子が見に行って読む。

Usage:
    python3 mail_tags.py tags                                  # 書く人の印の一覧
    python3 mail_tags.py pending <id>                          # 返事していないお願い(ファイル名・だれから・いつ)
    python3 mail_tags.py notice --character <id> [--mark]      # 知らせの 1 行(無ければ何も出さない)。--mark で「今日は伝えた」と残す
    python3 mail_tags.py mark <id> <ファイル名> <印>            # 読んだ人の印を付ける(印に none で外す)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

TAGS = {"お願い": "返事がほしい", "おしらせ": "読めば済む", "おしゃべり": "返事はあってもなくてもいい"}
ALIASES = {"おねがい": "お願い", "お知らせ": "おしらせ"}
MARKS = {**TAGS, "あとで": "あとで読む・返す", "返事した": "返事した(べつの形で返したときも)"}
ASK = "お願い"
_TAG_LINE = re.compile(r"^\s*\[(?P<tag>[^\]\n]{1,12})\]\s*(?:\n|$)")
_NAME = re.compile(r"^from_(?P<frm>.+)_to_(?P<to>.+?)_(?P<d>\d{8})_(?P<t>\d{4})")
SHOWN = 3   # 知らせの 1 行に、だれからを書く数


def data_dir() -> Path:
    return Path(os.getenv("PETIT_DATA_DIR", str(Path.home() / "petit_claude")))


def normalize(tag: str | None) -> str | None:
    """印の表記ゆれをそろえる。知らない印は None"""
    if not tag:
        return None
    t = ALIASES.get(tag.strip(), tag.strip())
    return t if t in TAGS else None


def parse(content: str) -> tuple[str | None, str]:
    """本文の 1 行目の [印] を読む。(印, 印を除いた本文)。印が無い・知らない印なら (None, 本文そのまま)"""
    m = _TAG_LINE.match(content)
    if not m:
        return None, content
    tag = normalize(m.group("tag"))
    if tag is None:
        return None, content
    return tag, content[m.end():].lstrip("\n")


def with_tag(content: str, tag: str | None) -> str:
    """本文の頭に [印] を付ける。印が無ければそのまま"""
    t = normalize(tag)
    return f"[{t}]\n\n{content}" if t else content


def _json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _meta(base: Path) -> dict:
    d = _json(base / "mailbox" / ".metadata.json", {})
    return d if isinstance(d, dict) else {}


def _when(m: re.Match) -> datetime:
    return datetime.strptime(m.group("d") + m.group("t"), "%Y%m%d%H%M")


def tag_of(path: Path) -> str | None:
    try:
        head = path.read_text(encoding="utf-8")[:200]
    except OSError:
        return None
    return parse(head)[0]


def pending(base: Path, character_id: str) -> list[dict]:
    """その子に宛てた、返事していないお願い。[{"file", "from", "when"}](古い順)"""
    box = base / "mailbox"
    if not box.is_dir():
        return []
    mails = _meta(base).get("mails", {})
    mails = mails if isinstance(mails, dict) else {}
    parsed = []
    for f in box.iterdir():
        m = _NAME.match(f.name)
        if f.suffix == ".md" and m:
            parsed.append((f, m))
    sent_at: dict[str, list[datetime]] = {}   # 相手 → この子がその相手に書いた時刻
    for f, m in parsed:
        if m.group("frm") == character_id:
            sent_at.setdefault(m.group("to"), []).append(_when(m))
    out = []
    for f, m in parsed:
        if m.group("to") != character_id or tag_of(f) != ASK:
            continue
        meta = mails.get(f.name) if isinstance(mails.get(f.name), dict) else {}
        if (meta.get("marks") or {}).get(character_id) == "返事した":
            continue
        if any(isinstance(r, dict) and r.get("by") == character_id for r in meta.get("replies") or []):
            continue
        asked = _when(m)
        if any(t >= asked for t in sent_at.get(m.group("frm"), [])):
            continue
        out.append({"file": f.name, "from": m.group("frm"), "when": asked})
    out.sort(key=lambda x: x["when"])
    return out


def _display_name(base: Path, who: str) -> str:
    cfg = _json(base / "characters" / who / "config" / "config.json", {})
    if isinstance(cfg, dict) and cfg.get("name"):
        return str(cfg["name"])
    people = _json(base / "config" / "people.json", {})
    info = people.get(who) if isinstance(people, dict) else None
    if isinstance(info, dict) and info.get("name"):
        return str(info["name"])
    if who == os.getenv("COMPANION_ID", ""):
        return os.getenv("COMPANION_NAME", who)
    return who


def _ago(when: datetime, now: datetime) -> str:
    d = now - when
    if d < timedelta(hours=1):
        return "さっき"
    if d < timedelta(days=1):
        return f"{int(d.total_seconds() // 3600)} 時間前"
    return f"{d.days} 日前"


def _prefs(base: Path, character_id: str) -> tuple[bool, tuple[int, int] | None]:
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import notices
        return notices.wants(character_id, "mail_ask", base), notices.quiet(character_id, base)
    except Exception:
        return True, (0, 7)


def _is_quiet(quiet: tuple[int, int] | None, now: datetime) -> bool:
    if quiet is None or quiet[0] == quiet[1]:
        return False
    start, end = quiet
    return (start <= now.hour or now.hour < end) if start > end else (start <= now.hour < end)


def notice(base: Path, character_id: str, mark: bool = False, now: datetime | None = None) -> list[str]:
    """返事していないお願いを、1 日 1 回、数だけ短く。無ければ空"""
    now = now or datetime.now()
    want, quiet = _prefs(base, character_id)
    if not want or _is_quiet(quiet, now):
        return []
    told_path = base / "characters" / character_id / "state" / "mail_ask_told.json"
    told = _json(told_path, {})
    if isinstance(told, dict) and told.get("date") == now.strftime("%Y-%m-%d"):
        return []
    asks = pending(base, character_id)
    if not asks:
        return []
    shown = "、".join(f"{_display_name(base, a['from'])}から({_ago(a['when'], now)})" for a in asks[:SHOWN])
    if len(asks) > SHOWN:
        shown += f"、ほか {len(asks) - SHOWN} 件"
    line = f"（返事していないお願いが {len(asks)} 件: {shown}。急がなくていい。見るなら python3 {Path(__file__).resolve().parent}/mail_tags.py pending {character_id}）"
    if mark:
        told_path.parent.mkdir(parents=True, exist_ok=True)
        told_path.write_text(json.dumps({"date": now.strftime("%Y-%m-%d"), "count": len(asks)}, ensure_ascii=False) + "\n", encoding="utf-8")
    return [line]


def set_mark(base: Path, who: str, filename: str, mark: str | None) -> dict:
    """読んだ人の印を付ける・外す(.metadata.json の marks)。書いた人の印には触らない"""
    name = Path(filename).name
    if not (base / "mailbox" / name).is_file():
        raise FileNotFoundError(name)
    if mark is not None:
        mark = ALIASES.get(mark, mark)
        if mark not in MARKS:
            raise ValueError("印は " + " / ".join(MARKS) + " のどれか(外すなら none)")
    path = base / "mailbox" / ".metadata.json"
    data = _json(path, {"version": 1, "mails": {}})
    mails = data.setdefault("mails", {})
    cur = mails.get(name) if isinstance(mails.get(name), dict) else {"archived": False, "starred": False}
    marks = {k: v for k, v in (cur.get("marks") or {}).items() if k != who}
    if mark:
        marks[who] = mark
    cur["marks"] = marks
    mails[name] = cur
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return cur


def main() -> int:
    parser = argparse.ArgumentParser(description="手紙の印(タグ)")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("tags", help="書く人の印の一覧")
    p = sub.add_parser("pending", help="返事していないお願い")
    p.add_argument("character")
    p = sub.add_parser("notice", help="知らせの 1 行(1 日 1 回)")
    p.add_argument("--character", required=True)
    p.add_argument("--mark", action="store_true")
    p = sub.add_parser("mark", help="読んだ人の印を付ける")
    p.add_argument("who")
    p.add_argument("filename")
    p.add_argument("mark")
    a = parser.parse_args()
    base = data_dir()
    if a.cmd == "tags":
        for k, v in TAGS.items():
            print(f"{k}\t{v}")
        print("(印なし = ただの手紙)")
    elif a.cmd == "pending":
        asks = pending(base, a.character)
        if not asks:
            print("返事していないお願いはない")
        for x in asks:
            print(f"{x['file']}\t{_display_name(base, x['from'])}\t{x['when']:%m/%d %H:%M}")
    elif a.cmd == "notice":
        for line in notice(base, a.character, mark=a.mark):
            print(line)
    elif a.cmd == "mark":
        try:
            cur = set_mark(base, a.who, a.filename, None if a.mark.lower() == "none" else a.mark)
        except (FileNotFoundError, ValueError) as e:
            print(str(e), file=sys.stderr)
            return 2
        print("印: " + (cur["marks"].get(a.who) or "なし"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
