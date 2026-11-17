#!/usr/bin/env bash
# ダッシュボードを、ぷちが返事を考えている最中でないときに再起動する(2026-11-17)。
# 考えている最中に再起動すると、claude も一緒に止まって「言葉にならなかったよ」になる。
# /api/busy の chats が 0 になるのを待つ(既定 180 秒まで。過ぎたら再起動する)。
#   scripts/restart_dashboard.sh [待つ秒数]
set -u
WAIT="${1:-180}"
URL="${DASHBOARD_URL:-http://127.0.0.1:8765}"
for ((i = 0; i < WAIT; i += 3)); do
  n=$(curl -s -m 2 "$URL/api/busy" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("chats", 0))' 2>/dev/null || echo 0)
  [ "$n" = "0" ] && break
  [ "$i" = 0 ] && echo "ぷちが返事を考えている($n)。終わるのを待つ…"
  sleep 3
done
systemctl --user restart petit-dashboard
for _ in $(seq 1 20); do curl -s -m 2 -o /dev/null "$URL/api/busy" && { echo "再起動した"; exit 0; }; sleep 1; done
echo "再起動したが、まだ答えない(systemctl --user status petit-dashboard)" >&2
exit 1
