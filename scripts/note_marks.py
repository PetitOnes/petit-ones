#!/usr/bin/env python3
"""ノートの ★ と 既読(人が付ける印)。置き場所と、ぷちへの知らせ。

人がダッシュボードのノートで付ける印。ぷちのノート(characters/<id>/notes/)の中身・ファイル名は触らず、家の state に置く:

    state/note_stars.json  {"puchiko": {"20261114_070000_あさ.md": {"by": "arisan", "at": "2026-11-14T17:20"}}}
    state/note_reads.json  {"arisan": {"puchiko": {"20261114_070000_あさ.md": "2026-11-14T17:20"}}}

- ★: 子(や人)ごとに、ファイル名 → だれが・いつ。外すと消える(古い形 {"id": ["名前", …]} も読める)
- 既読: 人ごと・子ごとに、ファイル名 → 開いた時刻。ノートがそれより新しければ「まだ見ていない」(ダッシュボードがピンクの丸を出す)

ぷちには、自分のノートが読まれた・★ が付いたことを、手紙の「読まれた・スタンプ」と同じく、前に伝えたあとの分をまとめて
次の自律行動か会話で 1 回だけ、さらっと伝える。伝えたことは characters/<id>/state/note_marks_told.json に残す。
はじめての回は、いまの状態を「伝えたこと」にして何も言わない。

Usage:
    python3 note_marks.py notice --character <id> [--mark]   # まだ伝えていない分を 1 行ずつ。--mark で「伝えた」と残す
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

STARS_MAX = 500
SHOWN = 3   # 知らせの 1 行に題を書く数(それより多い分は数だけ)


def data_dir() -> Path:
    return Path(os.environ.get("PETIT_DATA_DIR") or Path.home() / "petit_claude")


def _json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def note_title(filename: str) -> str:
    """20260303_093729_タイトル.md → タイトル(ダッシュボードの _note_title と同じ)"""
    name = filename.rsplit(".", 1)[0] if "." in filename else filename
    parts = name.split("_", 2)
    return parts[2] if len(parts) >= 3 and len(parts[0]) == 8 and len(parts[1]) == 6 else name


def valid_name(name: str) -> bool:
    return bool(name) and "/" not in name and "\\" not in name and name.endswith(".md") and not name.startswith(".")


# ---- ★ ----

def load_stars(base: Path) -> dict[str, dict[str, dict]]:
    raw = _json(base / "state" / "note_stars.json", {})
    out: dict[str, dict[str, dict]] = {}
    if not isinstance(raw, dict):
        return out
    for cid, v in raw.items():
        if isinstance(v, list):   # 古い形: 名前だけ
            out[cid] = {n: {"by": "", "at": ""} for n in v if isinstance(n, str)}
        elif isinstance(v, dict):
            out[cid] = {n: {"by": str(m.get("by", "")), "at": str(m.get("at", ""))} for n, m in v.items() if isinstance(m, dict)}
    return out


def set_star(base: Path, char: str, name: str, on: bool, by: str, now: datetime | None = None) -> dict:
    stars = load_stars(base)
    mine = stars.setdefault(char, {})
    mine.pop(name, None)
    if on:
        mine[name] = {"by": by, "at": (now or datetime.now()).isoformat(timespec="minutes")}
        while len(mine) > STARS_MAX:
            mine.pop(next(iter(mine)))
    _write(base / "state" / "note_stars.json", stars)
    return stars


# ---- 既読 ----

def load_reads(base: Path) -> dict[str, dict[str, dict[str, str]]]:
    raw = _json(base / "state" / "note_reads.json", {})
    return raw if isinstance(raw, dict) else {}


def set_read(base: Path, user: str, char: str, name: str, now: datetime | None = None) -> dict:
    reads = load_reads(base)
    reads.setdefault(user, {}).setdefault(char, {})[name] = (now or datetime.now()).isoformat(timespec="minutes")
    _write(base / "state" / "note_reads.json", reads)
    return reads[user]


# ---- ぷちへの知らせ ----

def _person_name(base: Path, who: str) -> str:
    people = _json(base / "config" / "people.json", {})
    return (people.get(who) or {}).get("name") or who if isinstance(people, dict) else who


def marks_of(base: Path, char: str) -> dict:
    """この子のノートに付いた印: {"star": {name: at}, "read": {"user:name": at}} に、だれが を添えて"""
    star = {n: m for n, m in load_stars(base).get(char, {}).items()}
    read = {}
    for user, per_char in load_reads(base).items():
        for n, at in (per_char.get(char) or {}).items():
            read[f"{user}:{n}"] = {"by": user, "at": at}
    return {"star": star, "read": read}


def notice(base: Path, char: str, mark: bool = False) -> list[str]:
    """まだ伝えていない「読まれた・★ が付いた」を、人ごとに 1 行ずつ"""
    told_path = base / "characters" / char / "state" / "note_marks_told.json"
    now = marks_of(base, char)
    told = _json(told_path, None)
    first = not isinstance(told, dict)
    told_star = {k: v for k, v in (told.get("star", {}) if not first else {n: m["at"] for n, m in now["star"].items()}).items()}
    told_read = {k: v for k, v in (told.get("read", {}) if not first else {k: m["at"] for k, m in now["read"].items()}).items()}

    by_person: dict[str, dict] = {}
    for n, m in now["star"].items():
        if told_star.get(n) != m["at"] and m["by"]:
            by_person.setdefault(m["by"], {"star": [], "read": []})["star"].append(note_title(n))
    for k, m in now["read"].items():
        if told_read.get(k) != m["at"]:
            by_person.setdefault(m["by"], {"star": [], "read": []})["read"].append(note_title(k.split(":", 1)[1]))

    def titles(ts: list[str]) -> str:
        s = "、".join(f"「{t}」" for t in ts[:SHOWN])
        return s + (f"、ほか {len(ts) - SHOWN} つ" if len(ts) > SHOWN else "")

    lines = []
    for who, got in by_person.items():
        person = _person_name(base, who)
        read, star = got["read"], got["star"]
        if read and star:
            lines.append(f"（ちなみに、{person}が、きみのノート {titles(read)} を読んだ。{titles(star)} には ★ を付けた）")
        elif read:
            lines.append(f"（ちなみに、{person}が、きみのノート {titles(read)} を読んだ）")
        else:
            lines.append(f"（ちなみに、{person}が、きみのノート {titles(star)} に ★ を付けた）")

    if mark and (lines or first):
        _write(told_path, {"star": {n: m["at"] for n, m in now["star"].items()}, "read": {k: m["at"] for k, m in now["read"].items()}})
    return lines


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("notice")
    p.add_argument("--character", required=True)
    p.add_argument("--mark", action="store_true")
    a = ap.parse_args()
    for line in notice(data_dir(), a.character, mark=a.mark):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
