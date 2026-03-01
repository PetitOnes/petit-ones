#!/usr/bin/env python3
"""未読メール一覧を表示するスクリプト。

.metadata.json の read_by フィールドを参照して、
指定キャラクター宛の未読メールだけを表示する。

Usage:
    python3 list_unread_mail.py <character_id>

例:
    python3 list_unread_mail.py puchiko
    python3 list_unread_mail.py puchiteya
"""

import json
import os
import sys
from pathlib import Path

DATA_DIR = Path(os.getenv("PETIT_DATA_DIR", str(Path.home() / "petit_claude")))
MAILBOX_DIR = DATA_DIR / "mailbox"
METADATA_FILE = MAILBOX_DIR / ".metadata.json"


def load_metadata() -> dict:
    if METADATA_FILE.exists():
        try:
            return json.loads(METADATA_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"version": 1, "mails": {}}


def is_addressed_to(filename_stem: str, character_id: str) -> bool:
    """ファイル名からこのキャラクター宛かどうかを判定する。"""
    # 新形式: from_X_to_Y_日時
    if f"_to_{character_id}_" in filename_stem:
        return True
    # 旧形式: to_Y_日時
    if filename_stem.startswith(f"to_{character_id}_") or filename_stem.startswith(f"to_{character_id}"):
        return True
    return False


def extract_sender(filename_stem: str) -> str:
    """ファイル名から送信者を抽出する。"""
    parts = filename_stem.split("_")
    if parts[0] == "from" and "to" in parts:
        ti = parts.index("to")
        return "_".join(parts[1:ti])
    return ""


def main() -> int:
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <character_id>", file=sys.stderr)
        return 1

    character_id = sys.argv[1]

    if not MAILBOX_DIR.exists():
        print("No mailbox directory")
        return 0

    meta = load_metadata()
    unread = []

    for f in sorted(MAILBOX_DIR.iterdir()):
        if not f.name.endswith(".md"):
            continue
        name = f.stem
        if not is_addressed_to(name, character_id):
            continue
        entry = meta.get("mails", {}).get(f.name, {})
        read_by = entry.get("read_by", [])
        if character_id in read_by:
            continue
        sender = extract_sender(name)
        content = f.read_text(encoding="utf-8").strip()
        # 先頭100文字をプレビューとして表示
        preview = content[:100].replace("\n", " ")
        if len(content) > 100:
            preview += "..."
        unread.append((f.name, sender, preview))

    if not unread:
        print(f"未読メールはありません ({character_id})")
        return 0

    print(f"未読メール ({character_id}): {len(unread)}件\n")
    for filename, sender, preview in unread:
        sender_str = f" from {sender}" if sender else ""
        print(f"  {filename}{sender_str}")
        print(f"    {preview}")
        print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
