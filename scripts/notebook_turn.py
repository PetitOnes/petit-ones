#!/usr/bin/env python3
"""交換ノートの順番(だれの番か)。決まりは scripts/write_notebook.py(ROTATION・ROTATION_SKIP_HOURS)と同じ。

- ぷちは ぷちてゃ → ぷちこ → ぷちる → はじめに戻る。前の子から ROTATION_SKIP_HOURS たったら、だれでも書いてよい
- 人(ありさん)は順番の外で、いつでも書ける。「ありさんの番」= ありさんが最後に書いたあとに、3 人とも書いた(一周した)
- 古い書き込みの id 表記(puchiko など)は名前に読み替える。それ以外の書き手(--help などの混入)は数えない

Usage:
    python3 notebook_turn.py [--me ありさん]    # いまの順番を JSON で
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from write_notebook import ROTATION, ROTATION_SKIP_HOURS  # noqa: E402

ALIASES = {"puchiteya": "ぷちてゃ", "puchiko": "ぷちこ", "puchiru": "ぷちる"}


def _name(author) -> str:
    a = str(author or "")
    return ALIASES.get(a, a)


def _when(date: str) -> datetime | None:
    try:
        return datetime.strptime(str(date), "%Y/%m/%d %H:%M")
    except (TypeError, ValueError):
        return None


def compute(entries: list[dict], me: str, now: datetime | None = None) -> dict:
    now = now or datetime.now()
    rot = list(ROTATION)
    petit = [(i, _name(e.get("author")), e.get("date", "")) for i, e in enumerate(entries) if _name(e.get("author")) in rot]
    last = petit[-1] if petit else None
    nxt = rot[(rot.index(last[1]) + 1) % len(rot)] if last else rot[0]
    hours = None
    if last:
        t = _when(last[2])
        hours = round((now - t).total_seconds() / 3600, 1) if t else None
    skippable = last is None or hours is None or hours >= ROTATION_SKIP_HOURS
    # 人の番: 自分の最後の書き込みのあとに、3 人とも書いた
    my_last = max((i for i, e in enumerate(entries) if _name(e.get("author")) == me), default=-1)
    since = {name for i, name, _ in petit if i > my_last}
    return {
        "order": rot, "next": nxt,
        "last": {"author": last[1], "date": last[2]} if last else None,
        "hours_since": hours, "skip_hours": ROTATION_SKIP_HOURS, "skippable": skippable,
        "me": me, "wrote_since_mine": [n for n in rot if n in since], "my_turn": set(rot) <= since,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--me", default="ありさん")
    a = ap.parse_args()
    base = Path(os.environ.get("PETIT_DATA_DIR") or Path.home() / "petit_claude")
    try:
        entries = json.loads((base / "chat_history" / "exchange_notebook.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        entries = []
    print(json.dumps(compute(entries, a.me), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
