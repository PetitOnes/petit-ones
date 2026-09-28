#!/bin/bash
# 体験デーモン(experienced.py)の起動スクリプト。
#
# 既に動いていれば何もしない（pidファイルで判定）。
# 動いていなければ setsid nohup でバックグラウンド起動する。
#
# Usage:
#   ./start_experienced.sh <character_id>
#
# 提案crontab行は README.md を参照（crontab 自体は編集しない）。

set -u

CHARACTER_ID="${1:-}"
if [ -z "$CHARACTER_ID" ]; then
  echo "Usage: $0 <character_id>" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_DIR="${PETIT_DATA_DIR:-$HOME/petit_claude}"
LOG_DIR="$DATA_DIR/.autonomous-logs/$CHARACTER_ID"
LOG_FILE="$LOG_DIR/experienced.log"
PID_FILE="$LOG_DIR/experienced.pid"

mkdir -p "$LOG_DIR"

is_alive() {
  local pid="$1"
  [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null
}

# 1. pidファイルに生きているPIDが書いてあれば何もしない
if [ -f "$PID_FILE" ]; then
  OLD_PID="$(cat "$PID_FILE" 2>/dev/null || echo "")"
  if is_alive "$OLD_PID"; then
    echo "experienced は既に起動中 (pid=$OLD_PID, character=$CHARACTER_ID)。何もしない。"
    exit 0
  fi
  echo "古いpidファイルが残っている(pid=$OLD_PID は死んでいる)。再起動する。"
fi

# 2. pidファイルが無くても、同名プロセスが既に動いていないか念のため確認
EXISTING_PID="$(pgrep -f "experienced\.py --character ${CHARACTER_ID}\$" | head -1)"
if is_alive "$EXISTING_PID"; then
  echo "$EXISTING_PID" > "$PID_FILE"
  echo "experienced は既に起動中だった (pid=$EXISTING_PID, character=$CHARACTER_ID)。pidファイルを補完して終了。"
  exit 0
fi

cd "$SCRIPT_DIR" || exit 1

if command -v uv >/dev/null 2>&1; then
  RUN_CMD=(uv run python experienced.py --character "$CHARACTER_ID")
else
  RUN_CMD=(python3 experienced.py --character "$CHARACTER_ID")
fi

setsid nohup "${RUN_CMD[@]}" >> "$LOG_FILE" 2>&1 < /dev/null &
disown

# setsid/nohup を挟むと $! が最終的な子プロセスのPIDと一致しない場合があるため、
# 少し待ってから pgrep で実際のPIDを確認して記録する。
sleep 0.5
NEW_PID="$(pgrep -f "experienced\.py --character ${CHARACTER_ID}\$" | head -1)"
if [ -n "$NEW_PID" ]; then
  echo "$NEW_PID" > "$PID_FILE"
  echo "experienced 起動 (pid=$NEW_PID, character=$CHARACTER_ID)。ログ: $LOG_FILE"
else
  echo "起動を試みたが起動確認できなかった。ログを確認: $LOG_FILE" >&2
  exit 1
fi
