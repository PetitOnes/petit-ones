#!/usr/bin/env python3
"""チャットログに1エントリ追記する。JSONをstdinから受け取る。
{"character_id": "puchiko", "role": "user", "text": "..."}
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

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
