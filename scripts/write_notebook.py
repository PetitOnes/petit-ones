#!/usr/bin/env python3
"""交換ノートにエントリを書き込むスクリプト。

Usage:
    python3 write_notebook.py <author> <content>
    python3 write_notebook.py <author> --file <path>

例:
    python3 write_notebook.py ぷちてゃ "今日はいい天気だった"
    python3 write_notebook.py ぷちこ --file /tmp/entry.txt

著者: ぷちてゃ / ぷちこ / ぷちる / ありさん
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(os.getenv("PETIT_DATA_DIR", str(Path.home() / "petit_claude")))
NOTEBOOK_FILE = DATA_DIR / "exchange_notebook.json"

VALID_AUTHORS = {"ぷちてゃ", "ぷちこ", "ぷちる", "ありさん"}


def main() -> int:
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <author> <content>", file=sys.stderr)
        print(f"       {sys.argv[0]} <author> --file <path>", file=sys.stderr)
        print(f"著者: {', '.join(sorted(VALID_AUTHORS))}", file=sys.stderr)
        return 1

    author = sys.argv[1]

    if author not in VALID_AUTHORS:
        print(f"Error: author must be one of {VALID_AUTHORS}. got: {author}", file=sys.stderr)
        return 1

    if sys.argv[2] == "--file" and len(sys.argv) >= 4:
        file_path = Path(sys.argv[3])
        if not file_path.exists():
            print(f"Error: file not found: {file_path}", file=sys.stderr)
            return 1
        content = file_path.read_text(encoding="utf-8")
    else:
        content = " ".join(sys.argv[2:])

    if not content.strip():
        print("Error: content is empty", file=sys.stderr)
        return 1

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if NOTEBOOK_FILE.exists():
        try:
            entries = json.loads(NOTEBOOK_FILE.read_text(encoding="utf-8"))
        except Exception:
            entries = []
    else:
        entries = []

    now = datetime.now(timezone.utc).astimezone()
    entries.append({
        "author": author,
        "date": now.strftime("%Y/%m/%d %H:%M"),
        "content": content.strip(),
    })

    NOTEBOOK_FILE.write_text(
        json.dumps(entries, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"書きました ({author}, {now.strftime('%H:%M')})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
