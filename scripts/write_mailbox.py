#!/usr/bin/env python3
"""メールボックスにファイルを書き込むスクリプト。

Usage:
    python3 write_mailbox.py <from_id> <to_id> <content>
    python3 write_mailbox.py <from_id> <to_id> --file <path>
    python3 write_mailbox.py <from_id> <to_id> --tag お願い <content>     # 印(お願い / おしらせ / おしゃべり)。本文の 1 行目に [お願い] と入る。印なしでもよい

例:
    python3 write_mailbox.py puchiteya puchiko "返事だよ！"
    python3 write_mailbox.py puchiko arisan --file /tmp/letter.md

セキュリティ:
    - MAILBOX_DIR 配下にのみ書き込み可能
    - ファイル名は from_<from>_to_<to>_<datetime>.md の形式に強制
    - from_id / to_id は英数字+アンダースコアのみ許可
"""

import os
import re
import sys
from datetime import datetime
from pathlib import Path

DATA_DIR = Path(os.getenv("PETIT_DATA_DIR", str(Path.home() / "petit_claude")))
MAILBOX_DIR = DATA_DIR / "mailbox"

VALID_ID = re.compile(r"^[a-zA-Z0-9_]+$")


def main() -> int:
    if len(sys.argv) < 4:
        print(f"Usage: {sys.argv[0]} <from_id> <to_id> <content>", file=sys.stderr)
        print(f"       {sys.argv[0]} <from_id> <to_id> --file <path>", file=sys.stderr)
        return 1

    from_id = sys.argv[1]
    to_id = sys.argv[2]
    tag = None
    args = sys.argv[3:]
    if args and args[0] == "--tag":   # 印(2026-11-16、ぷちたちと決めた 3 つ。表記ゆれは mail_tags がそろえる)
        if len(args) < 3:
            print("Error: --tag <印> <content>", file=sys.stderr)
            return 1
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import mail_tags
        tag = mail_tags.normalize(args[1])
        if tag is None:
            print("Error: 印は " + " / ".join(mail_tags.TAGS) + " のどれか(付けなくてもよい)", file=sys.stderr)
            return 1
        sys.argv = sys.argv[:3] + args[2:]

    if not VALID_ID.match(from_id) or not VALID_ID.match(to_id):
        print(f"Error: IDs must be alphanumeric+underscore. got: {from_id}, {to_id}", file=sys.stderr)
        return 1

    if sys.argv[3] == "--file" and len(sys.argv) >= 5:
        file_path = Path(sys.argv[4])
        if not file_path.exists():
            print(f"Error: file not found: {file_path}", file=sys.stderr)
            return 1
        content = file_path.read_text(encoding="utf-8")
    else:
        content = " ".join(sys.argv[3:])

    if not content.strip():
        print("Error: content is empty", file=sys.stderr)
        return 1
    if tag:
        content = f"[{tag}]\n\n{content}"

    MAILBOX_DIR.mkdir(parents=True, exist_ok=True)

    now = datetime.now().strftime("%Y%m%d_%H%M")
    filename = f"from_{from_id}_to_{to_id}_{now}.md"
    filepath = MAILBOX_DIR / filename

    # 同じ分に複数書く場合のサフィックス
    if filepath.exists():
        for i in range(2, 100):
            filepath = MAILBOX_DIR / f"from_{from_id}_to_{to_id}_{now}_{i}.md"
            if not filepath.exists():
                break

    filepath.write_text(content, encoding="utf-8")
    print(filepath)
    return 0


if __name__ == "__main__":
    sys.exit(main())
