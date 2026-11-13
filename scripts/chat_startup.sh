#!/bin/bash
# chat-startup.sh
# 3人チャット用 claude 起動スクリプト
# --system-prompt-file でClaudeのデフォルト人格を置き換え、ぷちたちの人格を注入する
#
# 使い方:
#   bash chat_startup.sh               # 3人全員
#   bash chat_startup.sh puchiko       # ぷちこのみ
#   bash chat_startup.sh puchiko puchiteya  # 2人

export HOME="/home/cube-petit"
DATA_DIR="${PETIT_DATA_DIR:-$HOME/petit_claude}"
PROJECT_DIR="$HOME/work/embodied-claude"
SCRIPTS_DIR="$PROJECT_DIR/scripts"
MAILBOX_DIR="$DATA_DIR/mailbox"

# キャラクターID（引数で指定、なければ3人全員）
if [ $# -gt 0 ]; then
    CHAR_IDS=("$@")
else
    CHAR_IDS=("puchiteya" "puchiko" "puchiru")
fi


# システムプロンプトを組み立て(文面は prompts/chat/system.md。家の PETIT_DATA_DIR/prompts/ に同名があればそちら)
PROMPT_FILE=$(mktemp /tmp/chat-system-prompt-XXXXXX.txt)
PETIT_DATA_DIR="$DATA_DIR" python3 "$SCRIPTS_DIR/build_chat_prompt.py" "${CHAR_IDS[@]}" > "$PROMPT_FILE"

# --- mcp-config: 汎用サーバー(CHARACTER_ID未設定)を排除し、各キャラ専用ツールだけに絞り込む ---
# これがないと mcp__m5-mcp__speak 等の汎用ツールが混在で見えてしまい、
# 誤って呼ぶと声がデフォルト話者に戻る事故が起きる
MCP_CONFIG_FILE=$(mktemp /tmp/chat-mcp-config-XXXXXX.json)
python3 "$SCRIPTS_DIR/gen_chat_mcp_config.py" "${CHAR_IDS[@]}" > "$MCP_CONFIG_FILE"

# スマホ等の狭いターミナルでもEnterで送信できるようウィンドウ幅を固定
# window-size manual にすることでクライアント側の画面幅に引っ張られなくなる
tmux set-option -g window-size manual 2>/dev/null || true
tmux resize-window -x 220 -y 50 2>/dev/null || true

# tmux pipe-pane でClaudeの返答を自動キャプチャしてchat_historyに保存
# 複数キャラモード: **ぷちこ**: 形式のプレフィックスでキャラを判定
# 起動前にペインIDを取得（exec後は変更できないため）
PANE_ID=$(tmux display-message -p "#{pane_id}" 2>/dev/null || echo "")
(sleep 3 && if [ -n "$PANE_ID" ]; then
    tmux pipe-pane -o -t "$PANE_ID" "python3 $SCRIPTS_DIR/tmux_chat_capture.py --multi"
else
    tmux pipe-pane -o "python3 $SCRIPTS_DIR/tmux_chat_capture.py --multi"
fi) &

# claude を起動（セッション引き継ぎあり）
# 全員版は "all" という共通セッションIDで管理
exec bash "$(dirname "$0")/start_chat_session.sh" "all" "$PROMPT_FILE" "$MCP_CONFIG_FILE"
