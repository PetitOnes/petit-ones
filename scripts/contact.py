#!/usr/bin/env python3
"""接点: 人がその子に向けて何かしたこと(話しかけた・合図を送った)を、その子の出来事として残す。

体の出来事(触られた・持たれた)は experience-daemon が体から拾う。こちらは、ダッシュボードなど
「人の側の入口」で起きたことを残す。欲求の部品(m5-petit-desire の relief)が読んで、
「話したい」などを満たす(Issue #67)。

残す場所: PETIT_DATA_DIR/characters/<id>/state/contact/YYYYMMDD.jsonl(1 行 1 件)

    {"ts": "2026-11-14T14:05:10", "type": "talked", "with": "<世話人の ID>", "via": "chat"}
    {"ts": "2026-11-14T14:06:00", "type": "talked", "cam_to": "<世話人の ID>", "via": "mic"}
    {"ts": "2026-11-14T14:07:30", "type": "hello",  "with": "<世話人の ID>", "via": "dashboard"}

- with: だれがしたか、が確かなとき(ダッシュボードにログインしている人)
- cam_to: 体のマイクのように、だれの声かは分からないとき。体の設定(CAM TO)がだれだったか、だけを残す
- 話した中身は残さない

Usage:
    contact.py record --character <id> --type talked --with <ID> --via chat
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

_ID = re.compile(r"^[a-zA-Z0-9_]+$")
TYPES = ("talked", "hello")


def data_dir() -> Path:
    return Path(os.environ.get("PETIT_DATA_DIR") or Path.home() / "petit_claude")


def contact_dir(base: Path, character: str) -> Path:
    return base / "characters" / character / "state" / "contact"


def record(base: Path, character: str, kind: str, who: str = "", via: str = "",
           setting_to: str = "", now: datetime | None = None) -> dict | None:
    """接点を 1 件残す。残した 1 件を返す(ID や種類がおかしければ何もせず None)"""
    if kind not in TYPES or not _ID.match(character or ""):
        return None
    if not (base / "characters" / character).is_dir():
        return None
    now = now or datetime.now()
    event: dict = {"ts": now.isoformat(timespec="seconds"), "type": kind}
    if who and _ID.match(who):
        event["with"] = who
    if setting_to and _ID.match(setting_to):
        event["cam_to"] = setting_to
    if via and _ID.match(via):
        event["via"] = via
    path = contact_dir(base, character) / f"{now.strftime('%Y%m%d')}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")
    return event


def main() -> int:
    parser = argparse.ArgumentParser(description="接点(人がその子に向けて何かした)を残す")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("record")
    p.add_argument("--character", required=True)
    p.add_argument("--type", required=True, choices=TYPES)
    p.add_argument("--with", dest="who", default="")
    p.add_argument("--cam-to", default="")
    p.add_argument("--via", default="")
    args = parser.parse_args()
    event = record(data_dir(), args.character, args.type, args.who, args.via, args.cam_to)
    if event is None:
        print("残せなかった(その子がいない、または ID がおかしい)", file=sys.stderr)
        return 1
    print(json.dumps(event, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
