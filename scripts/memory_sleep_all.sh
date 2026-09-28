#!/bin/bash
# 全キャラクターの記憶整理（consolidation/decay/forgetting）を毎晩実行する
# 2026-07-06: 従来のcronはMEMORY_DB_PATH未指定で孤児DB（~/.claude/memories/memory.db）
# に対して動いており、ぷちたちの本物のDBは一度も整理されていなかった。その修正。

set -u
MEMORY_MCP_DIR="/home/cube-petit/work/embodied-claude/memory-mcp"
UV="/home/cube-petit/.local/bin/uv"

for CHAR in puchiteya puchiko puchiru; do
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] sleep: $CHAR"
  cd "$MEMORY_MCP_DIR" && \
    MEMORY_DB_PATH="/home/cube-petit/.claude/memories/$CHAR/memory.db" \
    "$UV" run python scripts/sleep.py
done
