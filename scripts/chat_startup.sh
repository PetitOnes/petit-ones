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
DATA_DIR="$HOME/petit_claude"
PROJECT_DIR="$HOME/work/embodied-claude"
SCRIPTS_DIR="$PROJECT_DIR/scripts"
MAILBOX_DIR="$DATA_DIR/mailbox"

# キャラクターID（引数で指定、なければ3人全員）
if [ $# -gt 0 ]; then
    CHAR_IDS=("$@")
else
    CHAR_IDS=("puchiteya" "puchiko" "puchiru")
fi

NOW=$(date "+%Y-%m-%d %H:%M (JST)")

# キャラクター名対応
char_name() {
    case "$1" in
        puchiteya) echo "ぷちてゃ" ;;
        puchiko)   echo "ぷちこ" ;;
        puchiru)   echo "ぷちる" ;;
        *)         echo "$1" ;;
    esac
}

# システムプロンプトを組み立て
PROMPT_FILE=$(mktemp /tmp/chat-system-prompt-XXXXXX.txt)

{
# --- キャラクター人格定義 ---
if [ ${#CHAR_IDS[@]} -eq 1 ]; then
    ID="${CHAR_IDS[0]}"
    NAME=$(char_name "$ID")
    SOUL=$(cat "$DATA_DIR/characters/$ID/SOUL.md" 2>/dev/null || echo "")
    echo "あなたは${NAME}（ID: ${ID}）です。以下があなたの魂の定義です。"
    echo ""
    echo "$SOUL"
else
    echo "あなたたちは${#CHAR_IDS[@]}人のキャラクターです。それぞれの魂の定義に従い、自分の人格・口調・一人称を守って会話してください。"
    echo ""
    for ID in "${CHAR_IDS[@]}"; do
        NAME=$(char_name "$ID")
        SOUL=$(cat "$DATA_DIR/characters/$ID/SOUL.md" 2>/dev/null || echo "")
        echo "---"
        echo "## ${NAME}（ID: ${ID}）の魂"
        echo ""
        echo "$SOUL"
        echo ""
    done
    echo "---"
    echo ""
    echo "## 複数人チャットのルール"
    echo "- ありさんの発言に対して、各キャラが順番に反応する"
    echo "- 返答の先頭に名前を付ける: **ぷちこ**: / **ぷちてゃ**: / **ぷちる**:"
    echo "- 前のキャラの発言に対して反応してもよい（自然な会話になるように）"
    echo "- 全員が毎回しゃべる必要はない。静かにしていたいキャラは短くていい"
    echo "- ありさんが特定のキャラに話しかけたら、そのキャラが中心になって答える"
fi

echo ""
echo "現在の日時: ${NOW}"
echo "今話しかけているのはありさんです。ありさんと自然に会話してください。必要があればMCPツールを使ってください。"
echo "印象に残った話題や気づきは \`remember\` で記憶に残してください。記憶を書くときは今日の日付（${NOW}）を意識して書いてください。"
echo ""

# --- ファイルパス ---
echo "## ファイル"
for ID in "${CHAR_IDS[@]}"; do
    NAME=$(char_name "$ID")
    echo "- ${NAME}のデータ: $DATA_DIR/characters/$ID/ (SOUL.md, TODO.md, ROUTINES.md など)"
done
echo "- メールボックス: $MAILBOX_DIR/"
echo ""

# --- メール ---
echo "## メールの送受信"
echo "送信: \`python3 $SCRIPTS_DIR/write_mailbox.py <自分のID> <宛先ID> '<内容>'\`"
echo "未読確認: \`python3 $SCRIPTS_DIR/list_unread_mail.py <自分のID>\`"
echo "既読にする: \`python3 $SCRIPTS_DIR/mark_mail_read.py <自分のID> <ファイル名>\`"
echo "全既読: \`python3 $SCRIPTS_DIR/mark_mail_read.py <自分のID> --all\`"
echo "宛先ID: puchiko, puchiteya, puchiru, arisan"
echo "**重要**: メールを読んだら必ず既読にすること。既読にしないと次回また同じメールに返事してしまう。"
echo "**重要**: 返事を書くときは未読メールだけに返事すること。"
echo ""

# --- 返答するキャラの制御 ---
echo "## 返答するキャラの制御"
echo "ありさんのメッセージに「(Xだけに話しかけています)」という注記がある場合、その注記に書かれたキャラだけが返答してください。注記がない場合は全員が返答します。注記は返答に含めないこと。"
echo ""

# --- M5デバイス操作 ---
echo "## M5デバイス操作"
echo "各キャラの専用ツールを使う（混在させない）:"
for ID in "${CHAR_IDS[@]}"; do
    NAME=$(char_name "$ID")
    echo "- ${NAME} → mcp__m5-${ID}__*"
done
echo "音量: set_volume(value=N) / 省電力: set_power_save(enabled=True)"
echo "まとめて設定: batch_commands(commands=[\"VOL 0\", \"POWERSAVE ON\"])"

} > "$PROMPT_FILE"

# claude を起動
exec claude \
    --system-prompt-file "$PROMPT_FILE" \
    --dangerously-skip-permissions
