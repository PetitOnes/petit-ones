#!/usr/bin/env python3
"""チャットログに1エントリ追記する。

使い方:
  # 引数で渡す（推奨・権限チェックを回避）
  python3 append_chat_log.py --character-id puchiko --role user --text "おはよ"

  # JSONをstdinから渡す（旧来）
  echo '{"character_id": "puchiko", "role": "user", "text": "..."}' | python3 append_chat_log.py
"""
import json
import sys
import argparse
from datetime import datetime, timezone
from pathlib import Path

parser = argparse.ArgumentParser(add_help=False)
parser.add_argument("--character-id", dest="character_id")
parser.add_argument("--role")
parser.add_argument("--text")
args, _ = parser.parse_known_args()

if args.character_id and args.role and args.text is not None:
    char_id = args.character_id
    role = args.role
    text = args.text
else:
    data = json.load(sys.stdin)
    char_id = data["character_id"]
    role = data["role"]
    text = data["text"]

p = Path(f"/home/cube-petit/petit_claude/characters/{char_id}/chat_histories/chat_history.json")
p.parent.mkdir(parents=True, exist_ok=True)

try:
    log = json.loads(p.read_text(encoding="utf-8")) if p.exists() else []
except Exception:
    log = []

log.append({"role": role, "text": text, "timestamp": datetime.now(timezone.utc).isoformat()})
p.write_text(json.dumps(log[-200:], ensure_ascii=False, indent=2), encoding="utf-8")
