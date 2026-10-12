#!/bin/bash
# Notificationフック: 許可待ち・入力待ちが発生したらSlackで呼ぶ（2026-07-06 ありさんと決定）
# stdinにJSON（.messageに内容）が来る
DATA_DIR="${PETIT_DATA_DIR:-$HOME/petit_claude}"

# 家がない環境では、このリポを開いた人にだけ静かに何もしない。
if [ ! -d "$DATA_DIR" ]; then
    exit 0
fi

MSG=$(python3 -c "import json,sys; print(json.load(sys.stdin).get('message',''))" 2>/dev/null)
[ -z "$MSG" ] && exit 0
python3 "$CLAUDE_PROJECT_DIR"/scripts/slack_notify.py "🔔 ありさん呼んでます（mainセッション）: $MSG" >/dev/null 2>&1 || true
exit 0
