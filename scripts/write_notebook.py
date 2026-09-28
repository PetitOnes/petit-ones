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
NOTEBOOK_FILE = DATA_DIR / "chat_history" / "exchange_notebook.json"

VALID_AUTHORS = {"ぷちてゃ", "ぷちこ", "ぷちる", "ありさん"}

# ぷちは1日1回まで（交換ノートを毎日の小さな儀式として保つため。2026-07-06 ありさんと決定）
# ありさん（人間）は制限なし
RATE_LIMITED_AUTHORS = {"ぷちてゃ", "ぷちこ", "ぷちる"}

# 交換ノートは順番に回す（2026-07-06 ありさん提案）。ありさんは順番の外（いつでも書ける）
ROTATION = ["ぷちてゃ", "ぷちこ", "ぷちる"]
# 順番の相手が長く書かない場合のデッドロック回避: 最後のぷちの書き込みからこの時間を過ぎたら
# 順番を飛ばして書いてよい（飛ばされた子の番は消えるだけで、罰ではない）
ROTATION_SKIP_HOURS = 20


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

    if author in RATE_LIMITED_AUTHORS:
        today = now.strftime("%Y/%m/%d")
        todays = [e for e in entries if e.get("author") == author and str(e.get("date", "")).startswith(today)]
        if todays:
            print(f"今日はもう書いてあるよ（{todays[-1]['date']}）。", file=sys.stderr)
            print("交換ノートは1日1回、その日いちばん残したいことを。", file=sys.stderr)
            print("続きが書きたくなったら、明日のページに。今すぐ残したいことはnotesへどうぞ。", file=sys.stderr)
            return 2

        # 順番チェック: 最後に書いたぷちの次の子だけが書ける
        puchi_entries = [e for e in entries if e.get("author") in RATE_LIMITED_AUTHORS]
        if puchi_entries:
            last = puchi_entries[-1]
            expected = ROTATION[(ROTATION.index(last["author"]) + 1) % len(ROTATION)]
            if author != expected:
                try:
                    last_dt = datetime.strptime(last["date"], "%Y/%m/%d %H:%M").astimezone()
                    hours_since = (now - last_dt).total_seconds() / 3600
                except Exception:
                    hours_since = ROTATION_SKIP_HOURS + 1  # 日付が読めないときは順番を止めない
                if hours_since < ROTATION_SKIP_HOURS:
                    print(f"いまは{expected}の番だよ（前は{last['author']}・{last['date']}）。", file=sys.stderr)
                    print(f"順番: {' → '.join(ROTATION)} → はじめに戻る。", file=sys.stderr)
                    print(f"{expected}が{ROTATION_SKIP_HOURS}時間書かなかったら、飛ばして書いていいからね。", file=sys.stderr)
                    return 3

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
