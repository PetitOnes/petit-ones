#!/bin/bash
# start_chat_session.sh
# インタラクティブチャットセッションを起動する。
# 前回のセッションIDを引き継いで --resume で起動する。
# 日次リセット（4時JST）でセッションをリフレッシュ。
#
# 使い方: bash start_chat_session.sh <char_id> <system_prompt_file> [mcp_config_file]
#
# mcp_config_file を渡すと --mcp-config --strict-mcp-config で絞り込む。
# 省略した場合はプロジェクトの .mcp.json がそのまま使われる（汎用サーバーも見える点に注意）。

CHAR_ID="$1"
PROMPT_FILE="$2"
MCP_CONFIG="$3"

if [ -z "$CHAR_ID" ] || [ -z "$PROMPT_FILE" ]; then
    echo "Usage: $0 <char_id> <system_prompt_file> [mcp_config_file]" >&2
    exit 1
fi

DATA_DIR="/home/cube-petit/petit_claude"
STATE_DIR="$DATA_DIR/characters/$CHAR_ID/state"
SESSION_FILE="$STATE_DIR/.chat-terminal-session-id"
SESSION_DATE_FILE="$STATE_DIR/.chat-terminal-session-date"
PROJECTS_DIR="$HOME/.claude/projects/-home-cube-petit-work-embodied-claude"

mkdir -p "$STATE_DIR"

# 日次リセット（4時JST = 前日の19時UTC）
TODAY=$(TZ=Asia/Tokyo date "+%Y-%m-%d")
RESET_HOUR=4

should_reset() {
    [ ! -f "$SESSION_DATE_FILE" ] && return 0
    LAST_DATE=$(cat "$SESSION_DATE_FILE")
    [ "$LAST_DATE" != "$TODAY" ] && return 0
    # 4時以前なら前日扱い
    HOUR_JST=$(TZ=Asia/Tokyo date "+%H")
    [ "$((10#$HOUR_JST))" -lt "$RESET_HOUR" ] && return 0
    return 1
}

if should_reset; then
    echo "[$CHAR_ID] セッションリセット" >&2
    rm -f "$SESSION_FILE"
    echo "$TODAY" > "$SESSION_DATE_FILE"
fi

# 起動前のセッションファイル一覧を記録
BEFORE_SESSIONS=$(ls "$PROJECTS_DIR"/*.jsonl 2>/dev/null | sort)

# セッションID引き継ぎ
RESUME_ARGS=""
if [ -f "$SESSION_FILE" ]; then
    SESSION_ID=$(cat "$SESSION_FILE")
    echo "[$CHAR_ID] セッション引き継ぎ: $SESSION_ID" >&2
    RESUME_ARGS="--resume $SESSION_ID"
else
    echo "[$CHAR_ID] 新規セッション" >&2
fi

# 起動後に新しいセッションIDを保存するバックグラウンドジョブ
(
    sleep 5
    AFTER_SESSIONS=$(ls "$PROJECTS_DIR"/*.jsonl 2>/dev/null | sort)
    # 新しく追加されたセッションファイルを探す
    NEW_FILE=$(comm -13 <(echo "$BEFORE_SESSIONS") <(echo "$AFTER_SESSIONS") | head -1)
    if [ -n "$NEW_FILE" ]; then
        NEW_ID=$(basename "$NEW_FILE" .jsonl)
        echo "$NEW_ID" > "$SESSION_FILE"
        echo "[$CHAR_ID] 新セッションID保存: $NEW_ID" >&2
    else
        # 新規でなくresumeの場合、既存IDを保持（何もしない）
        echo "[$CHAR_ID] セッションID変更なし" >&2
    fi
) &

# ターミナル幅が狭いと長文入力でEnterが改行になるため、最小幅を確保
CURRENT_COLS=$(tput cols 2>/dev/null || echo 0)
if [ "$CURRENT_COLS" -lt 160 ] 2>/dev/null; then
    # xterm互換端末ではエスケープシーケンスでリサイズ試行
    printf '\e[8;40;200t' 2>/dev/null || true
fi

# claudeを起動
MCP_CONFIG_ARGS=""
if [ -n "$MCP_CONFIG" ] && [ -f "$MCP_CONFIG" ]; then
    MCP_CONFIG_ARGS="--mcp-config $MCP_CONFIG --strict-mcp-config"
fi

exec claude \
    --system-prompt-file "$PROMPT_FILE" \
    --dangerously-skip-permissions \
    $MCP_CONFIG_ARGS \
    $RESUME_ARGS
