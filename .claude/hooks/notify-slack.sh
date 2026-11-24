#!/bin/bash
# Notificationフック: 許可待ちが発生したらSlackで呼ぶ（2026-07-06 ありさんと決定。入力待ちは 11/24 に外した）
# stdinにJSON（.messageに内容）が来る
DATA_DIR="${PETIT_DATA_DIR:-$HOME/petit_claude}"

# 家がない環境では、このリポを開いた人にだけ静かに何もしない。
if [ ! -d "$DATA_DIR" ]; then
    exit 0
fi

# 「入力を待っています」(手が止まっただけ)は知らせない。許可待ちなど、人の手が要るときだけ呼ぶ(2026-11-24)
MSG=$(python3 -c "
import json, sys
d = json.load(sys.stdin)
m = d.get('message', '')
idle = d.get('notification_type') == 'idle_prompt' or 'waiting for your input' in m.lower()
print('' if idle else m)
" 2>/dev/null)
[ -z "$MSG" ] && exit 0
python3 "$CLAUDE_PROJECT_DIR"/scripts/slack_notify.py "🔔 ありさん呼んでます（mainセッション）: $MSG" >/dev/null 2>&1 || true
exit 0
