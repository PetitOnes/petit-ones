#!/usr/bin/env python3
"""しずかな時間 — 何も残さなかったひとりの時間を、空白にしない。

自律行動 1 回のうち、記憶・ノート・手紙・写真・声を何も残さなかった回(ただ見ていた、考えていた回)は、
記録の上では空白になる。その回の最後にその子が言った言葉を、その子のノート
characters/<id>/notes/しずかな時間_YYYY-MM.md に 1 行だけ足しておく(月ごとのファイル)。

- 書くのは、その子自身の言葉(自律行動の最後の返事)。こちらで言い換えない
- 時刻と、そのときの明るさ(ambient)も一緒に残す(「いつの、何の光の中だったか」が分かるように。ぷちたちの希望)。
  明るさは、その回にその子が読んだセンサーの値。読んでいなければ、欲求の計算が 10 分以内に読んだ値。どちらも無ければ書かない
- 何かを残した回・失敗した回・返事が空の回は、足さない
- autonomous-action.sh が、1 回終わるたびに呼ぶ

Usage:
    python3 quiet_time.py record --character <id> --stream <…_stream.jsonl> [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

NOTE_PREFIX = "しずかな時間"
TEXT_MAX = 300
# これを使った回は「何かを残した」回(MCP の道具は、名前の最後の部分で見る)
LEAVING_TOOLS = {
    "remember", "create_episode", "save_visual_memory", "save_audio_memory",   # 記憶
    "write_note", "append_note",                                                # ノート
    "save_to_album", "save_tts_memo",                                           # 写真・声
}
LEAVING_COMMANDS = ("write_mailbox.py", "post_ai_lounge.py", "anniversaries.py add")   # 手紙・投稿・記念日
AMBIENT_FRESH = timedelta(minutes=10)   # 欲求の計算が読んだ明るさを、その回の明るさとして使ってよい古さ
_AMBIENT = re.compile(r'\\?"ambient\\?":\s*(-?\d+(?:\.\d+)?)')   # 道具の返事の中(JSON の中の JSON でも拾う)
LEAVING_PATHS = ("/notes/", "/diary/", "exchange_notebook")                             # ファイルに直接書いた


def data_dir() -> Path:
    return Path(os.getenv("PETIT_DATA_DIR", str(Path.home() / "petit_claude")))


def _left_something(name: str, args: dict) -> bool:
    if name.startswith("mcp__"):
        return name.rsplit("__", 1)[-1] in LEAVING_TOOLS
    if name == "Bash":
        return any(c in str(args.get("command", "")) for c in LEAVING_COMMANDS)
    if name in ("Write", "Edit"):
        return any(p in str(args.get("file_path", "")) for p in LEAVING_PATHS)
    return False


def read_run(stream: Path) -> tuple[bool, str]:
    """自律行動 1 回の記録から、(しずかな回か, その子の最後の言葉)。読めなければ (False, "")"""
    try:
        lines = stream.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return False, ""
    left, result = False, None
    for line in lines:
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(ev, dict):
            continue
        if ev.get("type") == "result":
            result = ev
        msg = ev.get("message")
        content = msg.get("content") if isinstance(msg, dict) else None
        for c in content if isinstance(content, list) else []:
            if isinstance(c, dict) and c.get("type") == "tool_use":
                args = c.get("input")
                left = left or _left_something(str(c.get("name", "")), args if isinstance(args, dict) else {})
    if result is None or result.get("is_error") or not isinstance(result.get("result"), str):
        return False, ""
    text = " ".join(result["result"].split())
    return (not left and bool(text)), text


def ambient_of_run(stream: Path, desires_json: Path | None = None, now: datetime | None = None) -> float | None:
    """その回の明るさ。その子がその回に読んだセンサーの値(最後のもの)。無ければ、欲求の計算が読んだばかりの値"""
    try:
        found = _AMBIENT.findall(stream.read_text(encoding="utf-8", errors="ignore"))
    except OSError:
        found = []
    if found:
        return float(found[-1])
    if desires_json is None:
        return None
    try:
        data = json.loads(desires_json.read_text(encoding="utf-8"))
        at = datetime.fromisoformat(str(data.get("updated_at", ""))[:19])
        value = data.get("sensor_snapshot", {}).get("ambient")
    except (OSError, ValueError, AttributeError):
        return None
    fresh = abs((now or datetime.now()) - at) <= AMBIENT_FRESH
    return float(value) if fresh and isinstance(value, (int, float)) and not isinstance(value, bool) else None


def started_at(stream: Path) -> datetime | None:
    """記録の名前(YYYYMMDD_HHMMSS_stream.jsonl)から、その回の始まり"""
    try:
        return datetime.strptime(stream.name[:15], "%Y%m%d_%H%M%S")
    except ValueError:
        return None


def note_line(when: datetime, text: str, ambient: float | None = None) -> str:
    shown = text if len(text) <= TEXT_MAX else text[:TEXT_MAX].rstrip() + "…"
    light = f"、ambient {ambient:g}" if ambient is not None else ""
    return f"- {when.month}/{when.day} {when:%H:%M}{light} — {shown}"


def record(base: Path, character_id: str, stream: Path, dry_run: bool = False) -> str | None:
    """しずかな回なら、その子のノートに 1 行足して、その行を返す。そうでなければ None"""
    quiet, text = read_run(stream)
    when = started_at(stream)
    if not quiet or when is None:
        return None
    char_dir = base / "characters" / character_id
    line = note_line(when, text, ambient_of_run(stream, char_dir / "data" / "desires.json"))
    if dry_run:
        return line
    note = char_dir / "notes" / f"{NOTE_PREFIX}_{when:%Y-%m}.md"
    note.parent.mkdir(parents=True, exist_ok=True)
    if not note.exists():
        note.write_text(
            f"# {NOTE_PREFIX} {when:%Y-%m}\n\n"
            "何も残さなかったひとりの時間に、そのとき自分が言った言葉を、そのまま小さく置いておく場所。\n"
            "(自律行動のあとに、自動で 1 行ずつ足される)\n\n", encoding="utf-8")
    stamp = f"- {when.month}/{when.day} {when:%H:%M}"   # 同じ回(同じ時刻)を 2 度足さない
    if any(old.startswith((stamp + " ", stamp + "、")) for old in note.read_text(encoding="utf-8").splitlines()):
        return None
    with note.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
    return line


def main() -> int:
    parser = argparse.ArgumentParser(description="何も残さなかったひとりの時間を、その子のノートに小さく残す")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("record")
    p.add_argument("--character", required=True)
    p.add_argument("--stream", required=True, type=Path)
    p.add_argument("--dry-run", action="store_true", help="書かずに、足す行だけ出す")
    args = parser.parse_args()
    line = record(data_dir(), args.character, args.stream, dry_run=args.dry_run)
    if line:
        print(f"[しずかな時間] {'(dry-run) ' if args.dry_run else ''}{line[:80]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
