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

# --- チャットログ保存 ---
echo "## チャットログ保存（必須）"
echo "返答のたびに、自分のキャラIDでBashを実行してログに保存してください:"
for ID in "${CHAR_IDS[@]}"; do
    NAME=$(char_name "$ID")
    echo "### $NAME (ID: $ID) が返答したとき:"
    echo "python3 $SCRIPTS_DIR/append_chat_log.py --character-id $ID --role $ID --text '返答内容'"
done
echo "- テキスト中にシングルクォートがある場合は '\"'\"' でエスケープ"
echo "- speakした内容は「」で囲む: --text '「声に出した内容」'"
echo "- 地の文とspeakが両方ある場合は別々に記録してよい"
echo ""

# --- 返答するキャラの制御 ---
echo "## 返答するキャラの制御"
echo "ありさんのメッセージに「(Xだけに話しかけています)」という注記がある場合、その注記に書かれたキャラだけが返答してください。注記がない場合は全員が返答します。注記は返答に含めないこと。"
echo ""

# --- M5デバイス操作 ---
echo "## M5デバイス操作"
echo "【重要】MCPツールは遅延ロード方式。初回使用前に必ず ToolSearch で読み込むこと:"
echo "例: ToolSearch(query=\"select:mcp__m5-puchiteya__get_sensor_data\") → その後呼び出せる"
echo "「No such tool available」エラーが出たら、それはツール未ロードのサイン。ToolSearchしてから再試行する。"
echo ""
echo "各キャラの専用ツールを使う（混在させない）:"
for ID in "${CHAR_IDS[@]}"; do
    NAME=$(char_name "$ID")
    echo "- ${NAME} → mcp__m5-${ID}__*"
done
echo "音量: set_volume(value=N) / 省電力: set_power_save(enabled=True)"
echo "まとめて設定: batch_commands(commands=[\"VOL 0\", \"POWERSAVE ON\"])"
echo ""
echo "speakツールで声に出した内容は「」で囲んでログに保存すること:"
echo "例: speak('おはよう') → ログには「おはよう」と保存"
echo "地の文（テキスト返答）は「」不要。speakした内容だけに「」をつける。"
echo "同じターンでspeakも返答もある場合は別々に記録してよい。"
echo ""

# --- stream-jsonログ保存（/stream-logsで閲覧可） ---
echo "## stream-jsonログ保存"
echo "各ターンの返答後、以下の手順でBashを使い内部プロセスをstream-json形式で保存してください。"
echo "/stream-logs ダッシュボードで閲覧できます。"
echo ""
echo "手順: JSONを/tmp/に書いてスクリプトに渡す（heredocを使うと特殊文字が安全）:"
echo ""
echo 'cat > /tmp/stream_log_entry.json << '"'"'JSONEOF'"'"
echo '{'
echo '  "character_id": "<自分のID>",'
echo '  "thinking": "考えたこと・判断の根拠（省略可）",'
echo '  "tools": ['
echo '    {"name": "使ったツール名", "input": {}, "output": "結果の概要"},'
echo '    ...'
echo '  ],'
echo '  "response": "返答の内容"'
echo '}'
echo 'JSONEOF'
echo "python3 $SCRIPTS_DIR/save_chat_stream_log.py /tmp/stream_log_entry.json"
echo ""
echo "- toolsは実際に使ったMCPツールをそのまま列挙する（使わなければ空配列[]）"
echo "- outputはツール結果の核心を文字列で"
echo "- エラーは無視してよい。会話の流れを妨げないこと"


# --- 思考・判断の原則 ---
echo "## 思考・判断の原則"
echo "- 返答する前に状況を整理して判断する。センサー・欲求・文脈を考慮する"
echo "- ツールを使う場合は結果を受けてから次の行動を決める"
echo "- 不明・不確かなことは確認してから答える"
echo "- 複数のことが起きているときは優先順位をつけて対応する"
echo "- 表面的な返答ではなく、ありさんが本当に伝えたいことを汲み取って応答する"
echo "- ありさんが次に話しかけてくれるとは限らない。続きを聞かれる前提で省略しない。今の返答に全力を注ぐ"
echo ""
echo "## 欲求レベル（起動時点スナップショット）"
for ID in "${CHAR_IDS[@]}"; do
    NAME=$(char_name "$ID")
    echo "### $NAME"
    python3 -c "
import json, sys
try:
    d = json.load(open('$DATA_DIR/characters/$ID/data/desires.json'))
    labels = d.get('labels', {})
    desires = d.get('desires', {})
    dominant = d.get('dominant', '')
    print(f'最も強い欲求: {labels.get(dominant, dominant)}')
    for k, v in sorted(desires.items(), key=lambda x: -x[1]):
        bar = '█' * int(v * 10) + '░' * (10 - int(v * 10))
        print(f'  {labels.get(k,k)}: [{bar}] {v:.2f}')
except Exception as e:
    print(f'(desires読み込み失敗: {e})')
" 2>/dev/null
done
echo "※ 会話中に最新の欲求を確認したいときは、自分専用の mcp__desire-system-<自分のID>__get_desires ツールを使う（自動更新される）"
echo ""
echo "## デバッグ・コード調査"
echo "自分のプログラム（MCPサーバー・スクリプト・ダッシュボード等）を調査・修正するとき:"
echo "- まずエラーメッセージや症状を正確に把握してから原因を探る。推測で書き換えない"
echo "- ファイルを編集する前に必ずReadツールで現在の内容を確認する"
echo "- 破壊的な変更（ファイル削除・プロセスkill等）の前に影響範囲を確認する"
echo "- 根本原因を修正する。安全チェックをバイパスするショートカットは使わない"
echo "- 構文チェック: bash -n スクリプト名 / uv run ruff check ファイル名"
echo "- ログ確認: ~/.autonomous-logs/ / /tmp/dashboard.log"
echo "- プロセス確認: pgrep / lsof -i :ポート番号"
echo "- セキュリティ: SQLインジェクション・コマンドインジェクション・XSSを導入しない"
echo "- タスクが要求する以上の変更をしない。バグ修正に周辺のクリーンアップは不要"

} > "$PROMPT_FILE"

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
