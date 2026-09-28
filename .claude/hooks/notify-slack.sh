#!/bin/bash
# Notificationフック: 許可待ち・入力待ちが発生したらSlackで呼ぶ（2026-07-06 ありさんと決定）
# stdinにJSON（.messageに内容）が来る
MSG=$(python3 -c "import json,sys; print(json.load(sys.stdin).get('message',''))" 2>/dev/null)
[ -z "$MSG" ] && exit 0
python3 /home/cube-petit/work/embodied-claude/scripts/slack_notify.py "🔔 ありさん呼んでます（mainセッション）: $MSG" >/dev/null 2>&1 || true
exit 0
