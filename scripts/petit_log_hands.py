#!/usr/bin/env python3
"""ぷちログの「だれの手か」の直し。

体は、触られた・持ち上げられた・置かれた・起こされた のが だれの手かまでは分からない。ぷちログは
家の持ち主と見なして書く(dashboard/petit_log.py)ので、違ったときに、家の人が「この時間は この人」と直せるようにする。
直しは体の記録(state/experience)を書き換えず、別に 1 行ずつ足す。同じ時間に重ねたら、あとの行が勝つ。

残す場所: PETIT_DATA_DIR/characters/<id>/state/petit_log_hands.jsonl

    {"from": "2026-11-23T14:49:02", "to": "2026-11-23T15:07:40", "who": "<世話人の ID>", "by": "<直した人の ID>", "at": "…"}

- who: だれの手だったか。"" は「わからない」(名前を付けない)
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

FILE = "petit_log_hands.jsonl"


def _file(char_dir: Path) -> Path:
    return char_dir / "state" / FILE


def _time(text: object) -> datetime | None:
    try:
        return datetime.fromisoformat(str(text)).replace(tzinfo=None)
    except ValueError:
        return None


def load(char_dir: Path) -> list[dict]:
    """直しの一覧(古い順)。[{"from": datetime, "to": datetime, "who": str}]。読めない行は捨てる"""
    try:
        lines = _file(char_dir).read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out: list[dict] = []
    for line in lines:
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(raw, dict) or not isinstance(raw.get("who"), str):
            continue
        start, end = _time(raw.get("from")), _time(raw.get("to"))
        if start is not None and end is not None and start <= end:
            out.append({"from": start, "to": end, "who": raw["who"]})
    return out


def hand_of(marks: list[dict], ts: datetime) -> str | None:
    """その時刻の手。直しが無ければ None(家の持ち主と見なす)、"" は「わからない」"""
    for m in reversed(marks):
        if m["from"] <= ts <= m["to"]:
            return m["who"]
    return None


def mark(char_dir: Path, start: datetime, end: datetime, who: str, by: str, now: datetime | None = None) -> dict:
    """start〜end の手を who に直す(1 行足す)"""
    if start > end:
        raise ValueError("from は to より前に")
    row = {"from": start.isoformat(timespec="seconds"), "to": end.isoformat(timespec="seconds"), "who": who, "by": by,
           "at": (now or datetime.now()).isoformat(timespec="seconds")}
    f = _file(char_dir)
    f.parent.mkdir(parents=True, exist_ok=True)
    with f.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row
