#!/bin/bash
# chat_startup_3p.sh
# 3プロセス版チャット起動スクリプト
# tmuxセッション claude3 に3ウィンドウを作成し、各キャラ専用のclaudeを起動する

export HOME="/home/cube-petit"
DATA_DIR="${PETIT_DATA_DIR:-$HOME/petit_claude}"
PROJECT_DIR="$HOME/work/embodied-claude"
SCRIPTS_DIR="$PROJECT_DIR/scripts"
MAILBOX_DIR="$DATA_DIR/mailbox"
NOW=$(date "+%Y-%m-%d %H:%M (JST)")

char_name() {
    case "$1" in
        puchiteya) echo "ぷちてゃ" ;;
        puchiko)   echo "ぷちこ" ;;
        puchiru)   echo "ぷちる" ;;
        *)         echo "$1" ;;
    esac
}

build_prompt() {
    local char_id="$1"
    local name
    name=$(char_name "$char_id")
    local prompt_file
    prompt_file=$(mktemp /tmp/chat3-${char_id}-XXXXXX.txt)

    # 文面は prompts/chat/system.md(1 人ぶん。chat_startup.sh と同じ文)
    PETIT_DATA_DIR="$DATA_DIR" python3 "$SCRIPTS_DIR/build_chat_prompt.py" "$char_id" > "$prompt_file"

    echo "$prompt_file"
}

# mcp-config: 汎用サーバー(CHARACTER_ID未設定)を排除し、自分専用ツールだけに絞り込む
# これがないと mcp__m5-mcp__speak 等の汎用ツールが混在で見えてしまい、
# 誤って呼ぶと声がデフォルト話者に戻る事故が起きる
build_mcp_config() {
    local char_id="$1"
    local cfg_file
    cfg_file=$(mktemp "/tmp/chat3-mcp-${char_id}-XXXXXX.json")
    python3 "$SCRIPTS_DIR/gen_chat_mcp_config.py" "$char_id" > "$cfg_file"
    echo "$cfg_file"
}

# 各キャラのシステムプロンプト・mcp-configを生成
PUCHIKO_PROMPT=$(build_prompt puchiko)
PUCHIRU_PROMPT=$(build_prompt puchiru)
PUCHITEYA_PROMPT=$(build_prompt puchiteya)
PUCHIKO_MCP=$(build_mcp_config puchiko)
PUCHIRU_MCP=$(build_mcp_config puchiru)
PUCHITEYA_MCP=$(build_mcp_config puchiteya)

# 現在のウィンドウをpuchikoにリネームして追加ウィンドウを作成
# start_chat_session.sh でセッションIDを引き継ぎ
tmux rename-window puchiko
tmux new-window -n puchiru   "bash $PROJECT_DIR/scripts/start_chat_session.sh puchiru   $PUCHIRU_PROMPT $PUCHIRU_MCP"
tmux new-window -n puchiteya "bash $PROJECT_DIR/scripts/start_chat_session.sh puchiteya $PUCHITEYA_PROMPT $PUCHITEYA_MCP"

# --- 自律行動ループウィンドウ（現在は無効: ENABLE_AUTO_LOOP=1 で有効化） ---
# 有効にするには下の3行のコメントを外す。
# 各キャラのautonomous-action-terminal.shを20分間隔でループ実行するウィンドウを追加する。
# chat（インタラクティブ）セッションとは独立した別のclaudeプロセスとして動く。
#
# tmux new-window -n auto-puchiko   "bash $PROJECT_DIR/autonomous-action-terminal.sh puchiko   --force-loop"
# tmux new-window -n auto-puchiru   "bash $PROJECT_DIR/autonomous-action-terminal.sh puchiru   --force-loop"
# tmux new-window -n auto-puchiteya "bash $PROJECT_DIR/autonomous-action-terminal.sh puchiteya --force-loop"
#
# --force-loop を autonomous-action-terminal.sh に追加実装すると
# 20分ごとに自動実行するループが走る（スケジュール制御はスキップ）。
# 停止するには tmux kill-window -t claude3:auto-puchiko 等を実行。
# --- ここまで ---

# 各ウィンドウのClaudeの返答を自動キャプチャしてchat_historyに保存
(sleep 3 && \
  tmux pipe-pane -o -t ":puchiko"   "python3 $PROJECT_DIR/scripts/tmux_chat_capture.py --char-id puchiko" && \
  tmux pipe-pane -o -t ":puchiru"   "python3 $PROJECT_DIR/scripts/tmux_chat_capture.py --char-id puchiru" && \
  tmux pipe-pane -o -t ":puchiteya" "python3 $PROJECT_DIR/scripts/tmux_chat_capture.py --char-id puchiteya") &

# puchikoウィンドウに戻る
tmux select-window -t ":puchiko"

# puchikoのclaudeを起動（このウィンドウのプロセスとして）
exec bash "$PROJECT_DIR/scripts/start_chat_session.sh" puchiko "$PUCHIKO_PROMPT" "$PUCHIKO_MCP"
