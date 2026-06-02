#!/bin/bash
# chat_startup_3p.sh
# 3プロセス版チャット起動スクリプト
# tmuxセッション claude3 に3ウィンドウを作成し、各キャラ専用のclaudeを起動する

export HOME="/home/cube-petit"
DATA_DIR="$HOME/petit_claude"
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

    {
        echo "あなたは${name}（ID: ${char_id}）です。以下があなたの魂の定義です。"
        echo ""
        cat "$DATA_DIR/characters/$char_id/SOUL.md" 2>/dev/null
        echo ""
        echo "現在の日時: ${NOW}"
        echo "今話しかけているのはありさんです。ありさんと自然に会話してください。必要があればMCPツールを使ってください。"
        echo "印象に残った話題や気づきは \`remember\` で記憶に残してください。"
        echo ""
        echo "## ファイル"
        echo "- 自分のデータ: $DATA_DIR/characters/$char_id/ (SOUL.md, TODO.md, ROUTINES.md など)"
        echo "- メールボックス: $MAILBOX_DIR/"
        echo ""
        echo "## メールの送受信"
        echo "送信: \`python3 $SCRIPTS_DIR/write_mailbox.py $char_id <宛先ID> '<内容>'\`"
        echo "未読確認: \`python3 $SCRIPTS_DIR/list_unread_mail.py $char_id\`"
        echo "既読にする: \`python3 $SCRIPTS_DIR/mark_mail_read.py $char_id <ファイル名>\`"
        echo "全既読: \`python3 $SCRIPTS_DIR/mark_mail_read.py $char_id --all\`"
        echo "宛先ID: puchiko, puchiteya, puchiru, arisan"
        echo "**重要**: メールを読んだら必ず既読にすること。"
        echo ""
        echo "## チャットログ保存"
        echo "返答のたびに以下のBashコマンドを実行して返答を記録してください:"
        echo "python3 $SCRIPTS_DIR/append_chat_log.py --character-id $char_id --role $char_id --text '返答内容'"
        echo "テキスト中にシングルクォートがある場合は '\"'\"' でエスケープすること。"
        echo ""
        echo "## M5デバイス操作"
        echo "自分専用ツールを使う: mcp__m5-${char_id}__*"
        echo "音量: set_volume(value=N) / 省電力: set_power_save(enabled=True)"
    } > "$prompt_file"

    echo "$prompt_file"
}

# 各キャラのシステムプロンプトを生成
PUCHIKO_PROMPT=$(build_prompt puchiko)
PUCHIRU_PROMPT=$(build_prompt puchiru)
PUCHITEYA_PROMPT=$(build_prompt puchiteya)

# 現在のウィンドウをpuchikoにリネームして追加ウィンドウを作成
tmux rename-window puchiko
tmux new-window -n puchiru   "claude --system-prompt-file $PUCHIRU_PROMPT   --dangerously-skip-permissions"
tmux new-window -n puchiteya "claude --system-prompt-file $PUCHITEYA_PROMPT --dangerously-skip-permissions"

# puchikoウィンドウに戻る
tmux select-window -t ":puchiko"

# puchikoのclaudeを起動（このウィンドウのプロセスとして）
exec claude --system-prompt-file "$PUCHIKO_PROMPT" --dangerously-skip-permissions
