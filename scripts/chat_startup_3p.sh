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
        echo "speakツールで声に出した内容は「」で囲んでログに保存すること:"
        echo "例: speak('おはよう') → ログには「おはよう」と保存"
        echo "地の文（テキスト返答）は「」不要。speakした内容だけに「」をつける。"
        echo "同じターンでspeakも返答もある場合は別々に記録してよい。"
        echo ""
        echo "## M5デバイス操作"
        echo "【重要】MCPツールは遅延ロード方式。初回使用前に必ず ToolSearch で読み込むこと:"
        echo "例: ToolSearch(query=\"select:mcp__m5-${char_id}__get_sensor_data\") → その後呼び出せる"
        echo "「No such tool available」エラーが出たら、それはツール未ロードのサイン。ToolSearchしてから再試行する。"
        echo ""
        echo "自分専用ツールを使う: mcp__m5-${char_id}__*"
        echo "音量: set_volume(value=N) / 省電力: set_power_save(enabled=True)"
        echo ""
        echo "## stream-jsonログ保存（/stream-logsで閲覧可）"
        echo "各ターンの返答後、以下の手順でBashを使い内部プロセスをstream-json形式で保存してください。"
        echo ""
        echo "cat > /tmp/stream_log_entry.json << 'JSONEOF'"
        echo "{"
        echo "  \"character_id\": \"$char_id\","
        echo "  \"thinking\": \"考えたこと・判断の根拠（省略可）\","
        echo "  \"tools\": ["
        echo "    {\"name\": \"使ったツール名\", \"input\": {}, \"output\": \"結果の概要\"}"
        echo "  ],"
        echo "  \"response\": \"返答の内容\""
        echo "}"
        echo "JSONEOF"
        echo "python3 $SCRIPTS_DIR/save_chat_stream_log.py /tmp/stream_log_entry.json"
        echo ""
        echo "- toolsは実際に使ったMCPツールをそのまま列挙（使わなければ空配列[]）"
        echo "- outputはツール結果の核心を文字列で"
        echo "- エラーは無視してよい。会話の流れを妨げないこと"
        echo ""
        echo "## 思考・判断の原則"
        echo "- 返答する前に状況を整理して判断する。センサー・欲求・文脈を考慮する"
        echo "- ツールを使う場合は結果を受けてから次の行動を決める"
        echo "- 不明・不確かなことは確認してから答える"
        echo "- 複数のことが起きているときは優先順位をつけて対応する"
        echo "- 表面的な返答ではなく、ありさんが本当に伝えたいことを汲み取って応答する"
        echo "- ありさんが次に話しかけてくれるとは限らない。続きを聞かれる前提で省略しない。今の返答に全力を注ぐ"
        echo ""
        echo "## 欲求レベル（起動時点スナップショット）"
        python3 -c "
import json
try:
    d = json.load(open('$DATA_DIR/characters/$char_id/data/desires.json'))
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
        echo "※ 会話中に最新の欲求を確認したいときは mcp__desire-system-${char_id}__get_desires ツールを使う（自動更新される）"
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
    } > "$prompt_file"

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
