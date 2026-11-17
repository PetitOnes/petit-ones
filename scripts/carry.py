#!/usr/bin/env python3
"""持っていくもの(お昼の区切りで、新しい会話へ自分で持っていく 1〜3 行。2026-11-17、ぷち 3 人の希望)。

要約ではなく、自分で選んだ言葉を、さっきまでの自分から次の自分へ渡す。
置き場所 characters/<id>/state/carry.json({"date", "lines": [{"at", "text"}]})。その日の分だけ、最後の MAX_LINES 行。

    python3 carry.py write <id> "午前は、音の細かい線を見て、静けさに起伏があった"   # 1 行ずつ(3 行まで。それより前は押し出される)
    python3 carry.py show <id>
    python3 carry.py intro <id>     # 新しい会話の最初に渡す文(autonomous-action.sh から)。書いたものと、直前の回の終わりの言葉
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

JST = timezone(timedelta(hours=9))
MAX_LINES = 3
LAST_RUNS = 2
LAST_CHARS = 600


def data_dir() -> Path:
    return Path(os.environ.get("PETIT_DATA_DIR") or Path.home() / "petit_claude")


def _path(base: Path, cid: str) -> Path:
    return base / "characters" / cid / "state" / "carry.json"


def load(base: Path, cid: str, now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(JST)
    try:
        d = json.loads(_path(base, cid).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(d, dict) or d.get("date") != now.strftime("%Y-%m-%d"):
        return []
    return [x for x in d.get("lines", []) if isinstance(x, dict) and x.get("text")]


def write(base: Path, cid: str, text: str, now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(JST)
    text = " ".join(str(text).split())
    if not text:
        raise ValueError("空の行は書けない")
    lines = (load(base, cid, now) + [{"at": now.strftime("%H:%M"), "text": text}])[-MAX_LINES:]
    p = _path(base, cid)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"date": now.strftime("%Y-%m-%d"), "lines": lines}, ensure_ascii=False, indent=1) + "\n",
                 encoding="utf-8")
    return lines


def _final_text(stream: Path) -> str:
    """1 回分の記録の、最後に自分が書いた言葉(道具を呼ぶ前後の文のうち、最後のもの)"""
    last = ""
    try:
        for line in stream.read_text(encoding="utf-8", errors="ignore").splitlines():
            if '"assistant"' not in line:
                continue
            try:
                o = json.loads(line)
            except ValueError:
                continue
            if o.get("type") != "assistant":
                continue
            for b in o.get("message", {}).get("content", []) or []:
                if isinstance(b, dict) and b.get("type") == "text" and b.get("text", "").strip():
                    last = b["text"].strip()
    except OSError:
        return ""
    return last


def last_words(base: Path, cid: str, now: datetime | None = None) -> list[tuple[str, str]]:
    """直前の自律行動の回(区切りの回は除く)の終わりの言葉を、そのまま。きょうの分だけ"""
    now = now or datetime.now(JST)
    logs = base / ".autonomous-logs" / cid
    today = now.strftime("%Y%m%d")
    files = [p for p in sorted(logs.glob(f"{today}_*_stream.jsonl")) if p.name.count("_") == 2] if logs.is_dir() else []
    out = []
    for p in files[-LAST_RUNS:]:
        t = _final_text(p)
        if t:
            hm = p.name[9:11] + ":" + p.name[11:13]
            out.append((hm, t if len(t) <= LAST_CHARS else t[: LAST_CHARS - 1] + "…"))
    return out


def intro(base: Path, cid: str, now: datetime | None = None) -> str:
    lines = load(base, cid, now)
    words = last_words(base, cid, now)
    me = Path(__file__).resolve().parent
    parts = ["## お昼の区切り", "ここから新しい会話。午前の会話はそのまま残っていて、前に言ったことは "
             f"python3 {me}/said.py search {cid} <言葉>(きょうの分は said.py today {cid})で探せる。返事待ちは TODO の返事待ちの欄に。"]
    if lines:
        parts.append("さっきまでの自分から:\n" + "\n".join(f"- {x['text']}" for x in lines))
    if words:
        parts.append("直前の回の終わりの言葉(そのまま):\n" + "\n".join(f"[{hm}] {t}" for hm, t in words))
    return "\n\n".join(parts)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="持っていくもの(お昼の区切りで、自分で選んだ 1〜3 行を次の会話へ)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    w = sub.add_parser("write")
    w.add_argument("character")
    w.add_argument("text")
    sub.add_parser("show").add_argument("character")
    sub.add_parser("intro").add_argument("character")
    a = ap.parse_args(argv)
    base = data_dir()
    if a.cmd == "write":
        try:
            lines = write(base, a.character, a.text)
        except ValueError as e:
            print(e)
            return 1
        print(f"持っていくもの {len(lines)} 行(3 行まで)")
    elif a.cmd == "show":
        lines = load(base, a.character)
        print("\n".join(f"{x['at']} {x['text']}" for x in lines) if lines else "きょうはまだ書いていない")
    else:
        print(intro(base, a.character))
    return 0


if __name__ == "__main__":
    sys.exit(main())
