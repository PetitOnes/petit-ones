#!/bin/bash
# 全キャラクターの記憶整理(consolidation/decay/forgetting)を毎晩実行する(cron 04:05)
# characters/ にいる子を全員まわす。記憶 DB は ~/.claude/memories/<id>/memory.db
# 2026-07-06: MEMORY_DB_PATH 未指定だと孤児 DB に対して動いて本物が整理されない。必ず指定する

set -u
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_DIR="${PETIT_DATA_DIR:-$HOME/petit_claude}"
MEMORY_MCP_DIR="$PROJECT_DIR/src/m5-petit-memory"
UV="${UV_BIN:-$HOME/.local/bin/uv}"

for CHAR_DIR in "$DATA_DIR"/characters/*/; do
  CHAR="$(basename "$CHAR_DIR")"
  [ -f "$CHAR_DIR/config/config.json" ] || continue
  DB="$HOME/.claude/memories/$CHAR/memory.db"
  [ -f "$DB" ] || { echo "[$(date '+%Y-%m-%d %H:%M:%S')] skip: $CHAR(記憶 DB なし)"; continue; }
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] sleep: $CHAR"
  cd "$MEMORY_MCP_DIR" && MEMORY_DB_PATH="$DB" "$UV" run python scripts/sleep.py
done
