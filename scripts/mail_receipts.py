#!/usr/bin/env python3
"""手紙が「届いた」ことを、書いたぷちに知らせる(読まれた・スタンプが付いた)。

人(ぷち以外)に宛てた手紙について、mailbox/.metadata.json の印を見る:

- read_by に宛先の人が入っていれば、読まれた
- stamps に {人の id: 絵文字} があれば、スタンプが付いた(ダッシュボードのメールボックスから付ける)

ぷちには、前に伝えたあとの分をまとめて、次の自律行動か会話のときに 1 回だけ、さらっと伝える。
伝えたことは characters/<id>/state/mail_receipts_told.json に残す。
はじめての回は、いまの状態を「伝えたこと」にして、何も言わない(昔の手紙をまとめて数えないため)。

Usage:
    python3 mail_receipts.py notice --character <id> [--mark]   # まだ伝えていない分を 1 行ずつ。--mark で「伝えた」と残す
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

# スタンプは 5 つに絞る(2026-11-13)。選ぶ手間を増やさない
STAMPS = {"💛": "すき", "😊": "うれしい", "✨": "すてき", "🥹": "じんとした", "👀": "読んだよ"}
# ぷちに伝えるときの言い方。ハートは、画面ではその子の色で描いている(文字では色を渡せないので、言葉で)
STAMP_WORDS = {"💛": "きみの色のハート"}
STAMPS_SHOWN = 3   # 知らせの 1 行に、どの手紙かを書く数(それより多い分は数だけ)
_NAME = re.compile(r"^from_(.+)_to_(.+?)_(\d{8})_(\d{4})")


def data_dir() -> Path:
    return Path(os.getenv("PETIT_DATA_DIR", str(Path.home() / "petit_claude")))


def _json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _is_petit(base: Path, who: str) -> bool:
    return (base / "characters" / who / "config" / "config.json").exists()


def _person_name(base: Path, who: str) -> str:
    people = _json(base / "config" / "people.json", {})
    info = people.get(who) if isinstance(people, dict) else None
    if isinstance(info, dict) and info.get("name"):
        return str(info["name"])
    return os.getenv("COMPANION_NAME", who) if who == os.getenv("COMPANION_ID", "") else who


def receipts(base: Path, character_id: str) -> dict:
    """その子が人に宛てた手紙の、いまの状態。{"read": {ファイル名: 読んだ人}, "stamp": {ファイル名: [人, 絵文字]}}"""
    mails = _json(base / "mailbox" / ".metadata.json", {}).get("mails", {})
    read: dict[str, str] = {}
    stamp: dict[str, list[str]] = {}
    for name, meta in mails.items() if isinstance(mails, dict) else []:
        m = _NAME.match(name)
        if not m or m.group(1) != character_id or not isinstance(meta, dict):
            continue
        to = m.group(2)
        if _is_petit(base, to):
            continue
        if to in (meta.get("read_by") or []):
            read[name] = to
        emoji = (meta.get("stamps") or {}).get(to) if isinstance(meta.get("stamps"), dict) else None
        if emoji in STAMPS:
            stamp[name] = [to, emoji]
    return {"read": read, "stamp": stamp}


def _when(name: str) -> str:
    m = _NAME.match(name)
    d, t = m.group(3), m.group(4)
    return f"{int(d[4:6])}/{int(d[6:8])} {t[:2]}:{t[2:]}"


def notice(base: Path, character_id: str, mark: bool = False) -> list[str]:
    """まだ伝えていない「読まれた・スタンプが付いた」を、宛先の人ごとに 1 行ずつ"""
    told_path = base / "characters" / character_id / "state" / "mail_receipts_told.json"
    now = receipts(base, character_id)
    told = _json(told_path, None)
    first_time = not isinstance(told, dict)
    told_read = set(told.get("read", [])) if not first_time else set(now["read"])
    told_stamp = dict(told.get("stamp", {})) if not first_time else {k: v[1] for k, v in now["stamp"].items()}

    by_person: dict[str, dict] = {}
    for name, who in now["read"].items():
        if name not in told_read:
            by_person.setdefault(who, {"read": 0, "stamps": []})["read"] += 1
    for name, (who, emoji) in now["stamp"].items():
        if told_stamp.get(name) != emoji:
            by_person.setdefault(who, {"read": 0, "stamps": []})["stamps"].append((name, emoji))

    lines = []
    for who, got in by_person.items():
        person = _person_name(base, who)
        stamps = sorted(got["stamps"])
        shown = "、".join(f"{_when(n)} の手紙に {STAMP_WORDS.get(e, e)}" for n, e in stamps[:STAMPS_SHOWN])
        if len(stamps) > STAMPS_SHOWN:
            shown += f"、ほか {len(stamps) - STAMPS_SHOWN} 通にも"
        if got["read"] and stamps:
            lines.append(f"（ちなみに、{person}が、きみの手紙を {got['read']} 通読んだ。スタンプも付いていた: {shown}）")
        elif got["read"]:
            lines.append(f"（ちなみに、{person}が、きみの手紙を {got['read']} 通読んだ）")
        else:
            lines.append(f"（ちなみに、{person}が、きみの手紙にスタンプを付けた: {shown}）")

    if mark and (lines or first_time):
        told_path.parent.mkdir(parents=True, exist_ok=True)
        state = {"read": sorted(now["read"]), "stamp": {k: v[1] for k, v in now["stamp"].items()}}
        told_path.write_text(json.dumps(state, ensure_ascii=False) + "\n", encoding="utf-8")
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description="手紙が届いたこと(読まれた・スタンプ)を、書いたぷちに知らせる")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("notice", help="まだ伝えていない分を 1 行ずつ(無ければ何も出さない)")
    p.add_argument("--character", required=True)
    p.add_argument("--mark", action="store_true", help="伝えた、と残す")
    args = parser.parse_args()
    for line in notice(data_dir(), args.character, mark=args.mark):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
