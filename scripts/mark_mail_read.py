#!/usr/bin/env python3
"""メールを既読にするスクリプト。

.metadata.json の read_by フィールドにキャラクターIDを追加する。
ファイルのリネームは不要。

Usage:
    python3 mark_mail_read.py <character_id> <filename> [<filename2> ...]
    python3 mark_mail_read.py <character_id> --all

例:
    python3 mark_mail_read.py puchiko from_puchiteya_to_puchiko_20260301_2201.md
    python3 mark_mail_read.py puchiteya --all
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


def save_metadata(data: dict) -> None:
    METADATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    METADATA_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def mark_read(character_id: str, filenames: list[str]) -> int:
    meta = load_metadata()
    count = 0
    for fn in filenames:
        safe = Path(fn).name
        if not (MAILBOX_DIR / safe).exists():
            print(f"skip (not found): {safe}", file=sys.stderr)
            continue
        entry = meta["mails"].setdefault(safe, {"archived": False, "starred": False})
        read_by = entry.get("read_by", [])
        if character_id not in read_by:
            read_by.append(character_id)
            entry["read_by"] = read_by
            count += 1
    save_metadata(meta)
    print(f"Marked {count} mail(s) as read by {character_id}")
    return 0


def main() -> int:
    if len(sys.argv) < 3:
        print(
            f"Usage: {sys.argv[0]} <character_id> <filename> [<filename2> ...]\n"
            f"       {sys.argv[0]} <character_id> --all",
            file=sys.stderr,
        )
        return 1

    character_id = sys.argv[1]

    if sys.argv[2] == "--all":
        # 自分宛のメールを全部既読にする
        filenames = []
        if MAILBOX_DIR.exists():
            for f in MAILBOX_DIR.iterdir():
                if not f.name.endswith(".md"):
                    continue
                name = f.stem
                if f"_to_{character_id}_" in name or name.startswith(f"to_{character_id}"):
                    filenames.append(f.name)
        if not filenames:
            print(f"No mail for {character_id}")
            return 0
        return mark_read(character_id, filenames)
    else:
        return mark_read(character_id, sys.argv[2:])


if __name__ == "__main__":
    sys.exit(main())
