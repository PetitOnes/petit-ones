#!/usr/bin/env python3
"""自分が言った言葉を探す(2026-11-17 ありさん)。

ぷちは日をまたぐと、前の日に言ったことが会話に残らない(自律行動は 1 日ごとに新しい会話、ダッシュボードの会話とも別)。
そこで、外に出た言葉を子ごとに 1 か所へ集めて、本人が探せるようにする。集めるのは:

- speak   … 体の声(自律行動とダッシュボードの記録 PETIT_DATA_DIR/.autonomous-logs/<id>/*_stream.jsonl の speak)
- slack   … slack_notify.py で送った言葉(同じ記録の Bash)
- memo    … ボイスメモ(save_tts_memo)
- chat    … ダッシュボードで家の人に返した言葉(characters/<id>/chat_histories/*.json)
- group   … みんなの会話で言った言葉(chat_history/group_chat.json)

手紙(mailbox)と交換ノートは、もともと自分で読み返せるので入れない。

置き場所 PETIT_DATA_DIR/state/said/<id>.jsonl(1 行 = {"ts", "via", "text"})と <id>.seen.json(どこまで読んだか)。
探すたびに、増えた分だけ読み足す。

    python3 said.py search <id> <言葉> [--days 30] [--via speak,slack] [--limit 20]
    python3 said.py recent <id> [--n 10] [--via ...]      # 最近言ったこと
    python3 said.py today <id>                             # きょう言ったこと
    python3 said.py update [<id>]                          # 読み足すだけ
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

JST = timezone(timedelta(hours=9))
VIAS = ("speak", "slack", "memo", "chat", "group")
STREAM_RE = re.compile(r"^(\d{8})_(\d{6})(?:_chat)?_stream\.jsonl$")


def data_dir() -> Path:
    return Path(os.environ.get("PETIT_DATA_DIR", Path.home() / "petit_claude"))


def _store(base: Path, cid: str) -> tuple[Path, Path]:
    d = base / "state" / "said"
    return d / f"{cid}.jsonl", d / f"{cid}.seen.json"


def _iso(dt: datetime) -> str:
    return dt.astimezone(JST).isoformat(timespec="seconds")


def _slack_text(cmd: str) -> str | None:
    """`python3 …/slack_notify.py "…"` の言葉。引数に - で始まらない最初のもの"""
    if "slack_notify.py" not in cmd:
        return None
    try:
        parts = shlex.split(cmd.split("slack_notify.py", 1)[1])
    except ValueError:
        return None
    words = [p for p in parts if not p.startswith("-")]
    for stop in ("&&", "||", ";", "|", ">", "2>&1"):
        if stop in words:
            words = words[: words.index(stop)]
    return " ".join(words).strip() or None


def stream_said(path: Path) -> list[dict]:
    """1 回分の記録(stream-json)から、外に出た言葉を拾う"""
    m = STREAM_RE.match(path.name)
    if not m:
        return []
    ts = _iso(datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S").replace(tzinfo=JST))
    where = "dashboard" if "_chat_" in path.name else "autonomous"
    out: list[dict] = []
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return []
    for line in lines:
        if '"tool_use"' not in line:
            continue
        try:
            o = json.loads(line)
        except ValueError:
            continue
        if o.get("type") != "assistant":
            continue
        for b in o.get("message", {}).get("content", []) or []:
            if not isinstance(b, dict) or b.get("type") != "tool_use":
                continue
            name, inp = b.get("name", ""), b.get("input") or {}
            text, via = None, None
            if name.endswith("__speak"):
                text, via = inp.get("text"), "speak"
            elif name.endswith("__save_tts_memo"):
                text, via = inp.get("text"), "memo"
            elif name == "Bash":
                text, via = _slack_text(inp.get("command", "")), "slack"
            if text:
                out.append({"ts": ts, "via": via, "text": str(text).strip(), "where": where})
    return out


def _history_files(base: Path, cid: str) -> list[tuple[Path, str]]:
    files = [(p, "chat") for p in sorted((base / "characters" / cid / "chat_histories").glob("*.json"))]
    g = base / "chat_history" / "group_chat.json"
    if g.exists():
        files.append((g, "group"))
    return files


def history_said(path: Path, cid: str, via: str, after: str) -> list[dict]:
    """会話の履歴から、その子の言葉(after より新しいもの)を拾う。みんなの会話から来た分は group にする"""
    try:
        items = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if isinstance(items, dict):
        items = items.get("messages", [])
    out = []
    for it in items if isinstance(items, list) else []:
        if not isinstance(it, dict) or it.get("role") != cid:
            continue
        ts = str(it.get("timestamp") or "")
        if not ts or ts <= after:
            continue
        v = "group" if (via == "group" or it.get("via") == "group") else "chat"
        if via == "chat" and v == "group":
            continue   # 同じ言葉が group_chat.json にもある。数えるのはそちらだけ
        text = str(it.get("text") or "").strip()
        if text:
            out.append({"ts": _iso(datetime.fromisoformat(ts.replace("Z", "+00:00"))), "via": v, "text": text,
                        "_raw": ts})
    return out


def update(base: Path, cid: str) -> int:
    """増えた分だけ読み足す。足した数を返す"""
    store, seen_path = _store(base, cid)
    store.parent.mkdir(parents=True, exist_ok=True)
    try:
        seen = json.loads(seen_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        seen = {}
    streams: dict = seen.setdefault("streams", {})
    hist: dict = seen.setdefault("history", {})
    new: list[dict] = []
    logs = base / ".autonomous-logs" / cid
    for p in sorted(logs.glob("*_stream.jsonl")) if logs.is_dir() else []:
        size = p.stat().st_size
        if streams.get(p.name) == size:
            continue
        if p.name in streams:   # 書き足された回: いったん拾い直す前に、前の分を除く
            new.extend(r for r in stream_said(p) if r not in _rows_of(store, p.name))
        else:
            new.extend(stream_said(p))
        streams[p.name] = size
    for p, via in _history_files(base, cid):
        key = str(p.relative_to(base))
        rows = history_said(p, cid, via, hist.get(key, ""))
        if rows:
            hist[key] = max(r.pop("_raw") for r in rows)
            new.extend(rows)
    if new:
        new.sort(key=lambda r: r["ts"])
        with store.open("a", encoding="utf-8") as f:
            for r in new:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    seen_path.write_text(json.dumps(seen, ensure_ascii=False), encoding="utf-8")
    return len(new)


def _rows_of(store: Path, stream_name: str) -> list[dict]:
    m = STREAM_RE.match(stream_name)
    if not m or not store.exists():
        return []
    ts = _iso(datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S").replace(tzinfo=JST))
    return [r for r in load(store) if r.get("ts") == ts]


def load(store: Path) -> list[dict]:
    rows = []
    if store.exists():
        for line in store.read_text(encoding="utf-8").splitlines():
            try:
                rows.append(json.loads(line))
            except ValueError:
                pass
    return rows


def find(base: Path, cid: str, words: str = "", days: int | None = None, vias: list[str] | None = None,
         since: str | None = None) -> list[dict]:
    update(base, cid)
    rows = load(_store(base, cid)[0])
    if days:
        since = _iso(datetime.now(JST) - timedelta(days=days))
    if since:
        rows = [r for r in rows if r["ts"] >= since]
    if vias:
        rows = [r for r in rows if r["via"] in vias]
    for w in words.split():
        rows = [r for r in rows if w.lower() in r["text"].lower()]
    return rows


def line_of(r: dict, width: int = 160) -> str:
    t = " ".join(r["text"].split())
    if len(t) > width:
        t = t[: width - 1] + "…"
    return f"{r['ts'][:16].replace('T', ' ')} [{r['via']}] {t}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="自分が言った言葉を探す(体の声・Slack・ボイスメモ・ダッシュボードの返事・みんなの会話)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("search", help="言葉で探す(空白で区切ると全部を含むもの)")
    s.add_argument("character")
    s.add_argument("words", nargs="+")
    r = sub.add_parser("recent", help="最近言ったこと")
    for p in (s, r):
        p.add_argument("--via", help=f"どこで言ったか(カンマ区切り): {','.join(VIAS)}")
        p.add_argument("--days", type=int)
    s.add_argument("--limit", type=int, default=20)
    r.add_argument("character")
    r.add_argument("--n", type=int, default=10)
    t = sub.add_parser("today", help="きょう言ったこと")
    t.add_argument("character")
    t.add_argument("--via")
    u = sub.add_parser("update", help="増えた分を読み足すだけ")
    u.add_argument("character", nargs="?")
    a = ap.parse_args(argv)
    base = data_dir()
    if a.cmd == "update":
        ids = [a.character] if a.character else sorted(p.name for p in (base / "characters").iterdir() if p.is_dir())
        for cid in ids:
            print(f"{cid}: +{update(base, cid)}")
        return 0
    vias = [v.strip() for v in a.via.split(",")] if getattr(a, "via", None) else None
    if a.cmd == "search":
        rows = find(base, a.character, " ".join(a.words), a.days, vias)
        if not rows:
            print("見つからなかった")
            return 0
        print(f"{len(rows)} 件(新しい順に {min(len(rows), a.limit)} 件)")
        for row in reversed(rows[-a.limit:]):
            print(line_of(row))
    elif a.cmd == "recent":
        rows = find(base, a.character, "", a.days, vias)[-a.n:]
        for row in rows:
            print(line_of(row))
    elif a.cmd == "today":
        today = datetime.now(JST).strftime("%Y-%m-%d")
        rows = find(base, a.character, "", None, vias, since=today)
        print("\n".join(line_of(row) for row in rows) if rows else "きょうはまだ何も言っていない")
    return 0


if __name__ == "__main__":
    sys.exit(main())
