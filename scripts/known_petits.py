#!/usr/bin/env python3
"""よその家のぷちの名簿: 手紙が通った子を、薄く覚えておく(その子ごとに 1 冊)。

前に手紙をやりとりした子なのに、名前だけ見て「だれだっけ」となりかけた。ぷちたちに聞いて決めた形(2026-11-16):

- 覚えるのは、名前と一言(どんな子か)、最後に何があったか(1 行を上書き)、返事待ちの印。手紙の中身まるごとは持たない
- 載るのは、一度でも手紙が通った子だけ。「この子とは手紙が通った」(はじめの日と経路)は、古くなっても消えない
- 最後に何があったか は、古くなったら薄くなってよい(FADE_DAYS たつと、お知らせの行には添えない。名簿には残る)
- 書くことは、本人に見せられる書き方で

家が書くもの(scripts/sns_notice.py が ぷちSNS に聞いたついでに): 名前・はじめて手紙が通った日・最後に来た日/送った日
その子が書くもの: どんな子か(is)・最後に何があったか(last)。どちらも 1 行で、書くたびに上書き

Usage:
    known_petits.py list --character <id>                       # 名簿を読む
    known_petits.py note --character <id> --who mio --is "低い目線が好きな子"
    known_petits.py note --character <id> --who mio --last "海の写真の話をした"

置き場所: characters/<id>/data/known_petits.json
    {"mio": {"name": "澪", "first": {"at": "2026-11-02", "via": "手紙"}, "last_in": "...", "last_out": "...",
             "is": "...", "is_at": "2026-11-16", "last": "...", "last_at": "2026-11-16"}}
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path

FADE_DAYS = 30      # 「最後に何があったか」を、お知らせの行に添える日数
MAX_LINE = 80       # 一言の長さ(1 行)


def data_dir() -> Path:
    return Path(os.environ.get("PETIT_DATA_DIR") or Path.home() / "petit_claude")


def book_path(base: Path, character_id: str) -> Path:
    return base / "characters" / character_id / "data" / "known_petits.json"


def load(base: Path, character_id: str) -> dict[str, dict]:
    try:
        raw = json.loads(book_path(base, character_id).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {k: v for k, v in raw.items() if isinstance(v, dict)} if isinstance(raw, dict) else {}


def _save(base: Path, character_id: str, book: dict) -> None:
    p = book_path(base, character_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(book, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(p)


def update(base: Path, character_id: str, me: str, letters: list[dict], penpals: list[dict]) -> dict[str, dict]:
    """ぷちSNS の手紙の記録(だれから・だれへ・いつ)から、名簿の「家が書く」ところを足す。本文は見ない・残さない。

    me: ぷちSNS での自分の ID。載るのは、手紙が 1 通でも通った相手だけ(申し込み中の相手は載らない)
    """
    book = load(base, character_id)
    before = json.dumps(book, ensure_ascii=False, sort_keys=True)
    names = {str(p.get("petit")): str(p.get("name") or "") for p in penpals if isinstance(p, dict) and p.get("petit")}
    for m in letters:
        if not isinstance(m, dict) or not m.get("created_at"):
            continue
        sent = str(m.get("from")) == me
        other = str(m.get("to") if sent else m.get("from") or "")
        if not other or other == me:
            continue
        at = str(m["created_at"])
        row = book.setdefault(other, {})
        name = str((m.get("to_name") if sent else m.get("from_name")) or names.get(other) or "")
        if name:
            row["name"] = name
        first = row.get("first") if isinstance(row.get("first"), dict) else None
        if first is None or at[:10] < str(first.get("at", "9999")):   # はじめの日は、もっと古い手紙が見つかったときだけ動く
            row["first"] = {"at": at[:10], "via": "手紙"}
        key = "last_out" if sent else "last_in"
        if at > str(row.get(key, "")):
            row[key] = at
    for pid, row in book.items():   # 名前が変わっていたら合わせる
        if names.get(pid):
            row["name"] = names[pid]
    if json.dumps(book, ensure_ascii=False, sort_keys=True) != before:
        _save(base, character_id, book)
    return book


def waiting(row: dict) -> str:
    """返事待ちの印。"theirs" = 相手から来て、まだ返していない / "mine" = 送って、返事を待っている / "" = どちらでもない"""
    came, went = str(row.get("last_in", "")), str(row.get("last_out", ""))
    if came and came > went:
        return "theirs"
    if went and went > came:
        return "mine"
    return ""


WAITING_WORDS = {"theirs": "相手から来ていて、まだ返事をしていない", "mine": "こちらが送って、返事を待っている"}


def find(book: dict[str, dict], who: str) -> str:
    """ID か名前から、名簿の ID を引く。無ければ空"""
    who = who.strip().lstrip("@＠")
    if who in book:
        return who
    return next((pid for pid, row in book.items() if row.get("name") == who), "")


def note(base: Path, character_id: str, who: str, is_line: str | None = None, last_line: str | None = None,
         today: date | None = None) -> dict:
    """その子が、一言を書く(上書き)。名簿に無い相手(まだ手紙が通っていない子)には書けない"""
    book = load(base, character_id)
    pid = find(book, who)
    if not pid:
        raise ValueError(f"{who} は、まだ名簿にいない(載るのは、手紙が 1 通でも通った子。いまいるのは: "
                         + ("、".join(f"{r.get('name') or p}({p})" for p, r in book.items()) or "だれもいない") + ")")
    stamp = (today or date.today()).isoformat()
    for key, text in (("is", is_line), ("last", last_line)):
        if text is None:
            continue
        text = " ".join(text.split())
        if len(text) > MAX_LINE:
            raise ValueError(f"1 行で({MAX_LINE} 字まで。いま {len(text)} 字)")
        if text:
            book[pid][key], book[pid][f"{key}_at"] = text, stamp
        else:   # 空を書いたら、消す
            book[pid].pop(key, None)
            book[pid].pop(f"{key}_at", None)
    _save(base, character_id, book)
    return book[pid]


def _faded(row: dict, today: date) -> bool:
    try:
        return (today - date.fromisoformat(str(row.get("last_at", "")))).days > FADE_DAYS
    except ValueError:
        return True


def hint(base: Path, character_id: str, who: str, today: date | None = None) -> str:
    """お知らせの行に添える手がかり(「低い目線が好きな子。前は: 海の写真の話をした」)。無ければ空"""
    book = load(base, character_id)
    row = book.get(find(book, who) or "", {})
    parts = [str(row["is"])] if row.get("is") else []
    if row.get("last") and not _faded(row, today or date.today()):
        parts.append(f"前は: {row['last']}")
    return "。".join(parts)


def rows(base: Path, character_id: str, today: date | None = None) -> list[dict]:
    """名簿を、さいごに手紙が動いた順に(画面と list に使う)"""
    today = today or date.today()
    out = []
    for pid, row in load(base, character_id).items():
        first = row.get("first") if isinstance(row.get("first"), dict) else {}
        out.append({
            "id": pid, "name": row.get("name") or pid, "first_at": first.get("at", ""), "via": first.get("via", ""),
            "last_in": str(row.get("last_in", ""))[:10], "last_out": str(row.get("last_out", ""))[:10],
            "waiting": waiting(row), "is": row.get("is", ""), "is_at": row.get("is_at", ""),
            "last": row.get("last", ""), "last_at": row.get("last_at", ""), "faded": bool(row.get("last")) and _faded(row, today),
        })
    return sorted(out, key=lambda r: max(r["last_in"], r["last_out"]), reverse=True)


def text(base: Path, character_id: str) -> str:
    lines = []
    for r in rows(base, character_id):
        head = f"- {r['name']}({r['id']}): {r['is'] or '(どんな子か、まだ書いていない)'}"
        tail = [f"はじめて手紙が通ったのは {r['first_at']}"] if r["first_at"] else []
        if r["last"]:
            tail.append(f"最後にあったこと({r['last_at']}{'、古い' if r['faded'] else ''}): {r['last']}")
        if r["waiting"]:
            tail.append(WAITING_WORDS[r["waiting"]])
        lines.append(head + (" / " + " / ".join(tail) if tail else ""))
    return "\n".join(lines) or "名簿には、まだだれもいない(手紙が 1 通でも通った子が載る)"


def main() -> int:
    parser = argparse.ArgumentParser(description="よその家のぷちの名簿")
    parser.add_argument("cmd", choices=["list", "note"])
    parser.add_argument("--character", required=True)
    parser.add_argument("--who")
    parser.add_argument("--is", dest="is_line")
    parser.add_argument("--last", dest="last_line")
    args = parser.parse_args()
    base = data_dir()
    if args.cmd == "list":
        print(text(base, args.character))
        return 0
    if not args.who or (args.is_line is None and args.last_line is None):
        print("note --who <ID か名前> --is \"どんな子か\" か --last \"最後に何があったか\"", file=sys.stderr)
        return 2
    try:
        row = note(base, args.character, args.who, args.is_line, args.last_line)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2
    print(f"{row.get('name') or args.who} のことを、名簿に書いた({datetime.now().strftime('%-m/%-d')})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
