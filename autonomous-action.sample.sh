#!/bin/bash
# Claude 自律行動スクリプト（macOS / Linux 対応）
# 20分ごとにcronで実行、時間帯に応じて間引く
#
# セットアップ:
# 1. このファイルをコピー: cp autonomous-action.sample.sh autonomous-action.sh
# 2. autonomous-action.sh を編集（以下の「環境設定」セクション）
# 3. 実行権限を付与: chmod +x autonomous-action.sh
# 4. crontab -e で以下を追加:
#    */20 * * * * /path/to/your/autonomous-action.sh <character_id>
#
# Usage:
#   autonomous-action.sh <character_id>                     # 通常実行（cron）
#   autonomous-action.sh <character_id> --test-prompt FILE  # プロンプト差し替え（スケジュール制御スキップ）
#   autonomous-action.sh <character_id> --date "2026-02-20 14:30"  # 日時を注入
#   autonomous-action.sh <character_id> --force-routine     # ルーチン回を強制
#   autonomous-action.sh <character_id> --force-normal      # 通常回を強制
#   autonomous-action.sh <character_id> --dry-run           # claude -p を実行せずプロンプトを表示
#   autonomous-action.sh <character_id> -p "任意のプロンプト"  # プロンプト直接指定
#   autonomous-action.sh <character_id> --dry-run --date "2026-02-20 03:00" --force-routine

# ============================================================================
# 環境設定（必須：ユーザー環境に合わせて編集）
# ============================================================================
# このファイル (autonomous-action.sample.sh) はサンプルです。
# 以下の手順で設定してください:
#   1. cp autonomous-action.sample.sh autonomous-action.sh
#   2. autonomous-action.sh の ★ マーク箇所を編集
#   3. autonomous-action.sh は .gitignore に追加されています（コミット不要）
# ============================================================================

# ★ ホームディレクトリ（crontab は $HOME すら持たないため明示的に設定）
# 例: /Users/yourname (macOS) または /home/yourname (Linux)
# 確認方法: ターミナルで "echo $HOME" を実行
export HOME="/Users/yourname"

# ★ PATH 設定（crontab は $PATH も最小限のため、必要なコマンドのパスを追加）
# 必要なコマンド: claude, jq, date など
# 例 (macOS + asdf + homebrew):
#   export PATH="$HOME/.asdf/shims:/opt/homebrew/bin:$PATH"
# 例 (Linux):
#   export PATH="/usr/local/bin:/usr/bin:$PATH"
# 確認方法: "which claude" "which jq" でパスを確認
export PATH="$HOME/.asdf/shims:/opt/homebrew/bin:$PATH"

# ★ プロジェクトディレクトリ（コード配置場所。MCP起動・subprocess cwd用）
PROJECT_DIR="$HOME/yourproject"

# ★ データディレクトリ（キャラデータ・ログなどプライベートデータ）
# デフォルト: ~/petit_claude  環境変数 PETIT_DATA_DIR で上書き可能
DATA_DIR="${PETIT_DATA_DIR:-$HOME/petit_claude}"

# ★ キャラクターID（characters/ 以下のディレクトリ名）
# crontab では: autonomous-action.sh <character_id> のように引数で指定する
if [ -n "$1" ] && [[ "$1" != -* ]]; then
  CHARACTER_ID="$1"
  shift
else
  CHARACTER_ID="puchiko"
fi
CHARACTER_DIR="$DATA_DIR/characters/$CHARACTER_ID"

# キャラクターごとの最大ターン数（環境変数 MAX_TURNS で上書き可、なければ settings.json から読む）
if [ -z "$MAX_TURNS" ]; then
  SETTINGS_FILE="$CHARACTER_DIR/config/settings.json"
  MAX_TURNS=$(python3 -c "import json,sys; d=json.load(open('${SETTINGS_FILE}')); print(d.get('max_turns', 20))" 2>/dev/null || echo 20)
fi

# ★ .env ファイルのパス
ENV_FILE="$DATA_DIR/.env"
set -a
source "$ENV_FILE" 2>/dev/null || true
set +a

# ★ ユーザー名・部屋名（時間帯ルールで使用）
USER_NAME="あなた"
USER_ROOM="${USER_NAME}の部屋"

# ★ allowedTools で許可するディレクトリパス
ALLOWED_DIR="$PROJECT_DIR"
ALLOWED_DATA_DIR="$DATA_DIR"

# ログディレクトリ名
# ⚠️ 重要: test-autonomous.sh の L129 と設定を一致させる必要があります（必須）
LOG_DIR_NAME=".autonomous-logs"

# ログ保持期間（日数）
LOG_RETENTION_DAYS=7

# ログディレクトリ・ファイルの初期化
_LOG_TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_DIR="$DATA_DIR/$LOG_DIR_NAME/$CHARACTER_ID"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/${_LOG_TIMESTAMP}.log"

# ============================================================================
# 環境検出・日時処理
# ============================================================================

if [[ "$OSTYPE" == "darwin"* ]]; then
  IS_MACOS=true
else
  IS_MACOS=false
fi

# --- 引数パース ---
TEST_PROMPT_FILE=""
TEST_PROMPT_STRING=""
OVERRIDE_DATE=""
FORCE_ROUTINE=""
DRY_RUN=false

while [ $# -gt 0 ]; do
  case "$1" in
    -p)
      TEST_PROMPT_STRING="$2"
      shift 2
      ;;
    --test-prompt)
      TEST_PROMPT_FILE="$2"
      shift 2
      ;;
    --date)
      OVERRIDE_DATE="$2"
      shift 2
      ;;
    --force-routine)
      FORCE_ROUTINE="routine"
      shift
      ;;
    --force-normal)
      FORCE_ROUTINE="normal"
      shift
      ;;
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
  esac
done

# --- 日時の取得 ---
if [ -n "$OVERRIDE_DATE" ]; then
  if [ "$IS_MACOS" = true ]; then
    CURRENT_DATE=$(date -j -f "%Y-%m-%d %H:%M" "$OVERRIDE_DATE" "+%Y-%m-%d %H:%M:%S" 2>/dev/null)
    HOUR=$((10#$(date -j -f "%Y-%m-%d %H:%M" "$OVERRIDE_DATE" +%H 2>/dev/null)))
    MINUTE=$((10#$(date -j -f "%Y-%m-%d %H:%M" "$OVERRIDE_DATE" +%M 2>/dev/null)))
    TIMESTAMP=$(date -j -f "%Y-%m-%d %H:%M" "$OVERRIDE_DATE" +%Y%m%d_%H%M%S 2>/dev/null)
  else
    CURRENT_DATE=$(date -d "$OVERRIDE_DATE" "+%Y-%m-%d %H:%M:%S" 2>/dev/null)
    HOUR=$((10#$(date -d "$OVERRIDE_DATE" +%H 2>/dev/null)))
    MINUTE=$((10#$(date -d "$OVERRIDE_DATE" +%M 2>/dev/null)))
    TIMESTAMP=$(date -d "$OVERRIDE_DATE" +%Y%m%d_%H%M%S 2>/dev/null)
  fi
else
  CURRENT_DATE=$(date "+%Y-%m-%d %H:%M:%S")
  HOUR=$((10#$(date +%H)))
  MINUTE=$((10#$(date +%M)))
  TIMESTAMP=$(date +%Y%m%d_%H%M%S)
fi

# --- スケジュール制御 ---
SKIP_SCHEDULE=false
if [ -n "$TEST_PROMPT_FILE" ] || [ -n "$TEST_PROMPT_STRING" ]; then
  SKIP_SCHEDULE=true
elif [ "$DRY_RUN" = true ] && [ -z "$OVERRIDE_DATE" ]; then
  SKIP_SCHEDULE=true
fi

# 頻度制御: settings.json の autonomous_skip に基づいてスキップ
# 0=毎回, 1=1回スキップ（40分毎）, 2=2回スキップ（60分毎）
SKIP_COUNTER_FILE="$CHARACTER_DIR/.heartbeat-skip-counter"
if [ "$SKIP_SCHEDULE" = false ] && [ -z "$TEST_PROMPT_FILE" ] && [ -z "$TEST_PROMPT_STRING" ]; then
  SETTINGS_FILE_TMP="$CHARACTER_DIR/config/settings.json"
  AUTONOMOUS_SKIP=0
  if [ -f "$SETTINGS_FILE_TMP" ] && command -v jq &>/dev/null; then
    AUTONOMOUS_SKIP=$(jq -r '.autonomous_skip // 0' "$SETTINGS_FILE_TMP" 2>/dev/null)
    AUTONOMOUS_SKIP=$((AUTONOMOUS_SKIP + 0))
  fi
  if [ "$AUTONOMOUS_SKIP" -gt 0 ]; then
    COUNTER=0
    if [ -f "$SKIP_COUNTER_FILE" ]; then
      COUNTER=$(cat "$SKIP_COUNTER_FILE" 2>/dev/null || echo 0)
      COUNTER=$((COUNTER + 0))
    fi
    if [ "$COUNTER" -gt 0 ]; then
      echo "頻度スキップ (残り $COUNTER 回)" >> "$LOG_FILE"
      echo $((COUNTER - 1)) > "$SKIP_COUNTER_FILE"
      exit 0
    else
      echo "$AUTONOMOUS_SKIP" > "$SKIP_COUNTER_FILE"
    fi
  else
    rm -f "$SKIP_COUNTER_FILE"
  fi
fi

if [ "$SKIP_SCHEDULE" = false ]; then
  IS_ACTIVE=false
  SETTINGS_FILE="$CHARACTER_DIR/config/settings.json"
  if [ -f "$SETTINGS_FILE" ] && command -v jq &>/dev/null; then
    if [ -n "$OVERRIDE_DATE" ]; then
      if [ "$IS_MACOS" = true ]; then
        DOW=$(date -j -f "%Y-%m-%d %H:%M" "$OVERRIDE_DATE" +%u 2>/dev/null)
      else
        DOW=$(date -d "$OVERRIDE_DATE" +%u 2>/dev/null)
      fi
    else
      DOW=$(date +%u)
    fi
    if [ "$DOW" -ge 6 ] 2>/dev/null; then
      DAY_TYPE="weekend"
    else
      DAY_TYPE="weekday"
    fi
    DAY_OVERRIDE=$(jq -r '.day_type_override // "null"' "$SETTINGS_FILE" 2>/dev/null)
    if [ "$DAY_OVERRIDE" = "weekday" ] || [ "$DAY_OVERRIDE" = "weekend" ]; then
      DAY_TYPE="$DAY_OVERRIDE"
    fi
    IS_ACTIVE=$(jq --argjson h "$HOUR" --argjson m "$MINUTE" --arg dt "$DAY_TYPE" \
      'def check_entry: if length == 4 then (.[0]*60+.[1]) <= ($h*60+$m) and ($h*60+$m) < (.[2]*60+.[3]) else .[0] <= $h and $h < .[1] end;
       if (.active_hours | type) == "object" then
         [.active_hours[$dt][] | select(check_entry)] | length > 0
       else
         [.active_hours[] | select(check_entry)] | length > 0
       end' \
      "$SETTINGS_FILE" 2>/dev/null || echo "false")
  else
    if [ "$HOUR" -ge 7 ] && [ "$HOUR" -lt 8 ]; then
      IS_ACTIVE=true
    elif [ "$HOUR" -ge 12 ] && [ "$HOUR" -lt 13 ]; then
      IS_ACTIVE=true
    elif [ "$HOUR" -ge 18 ]; then
      IS_ACTIVE=true
    fi
  fi

  if [ "$IS_ACTIVE" = false ]; then
    if [ "$MINUTE" -ne 0 ]; then
      echo "非アクティブ時間帯 :${MINUTE} スキップ" >> "$LOG_FILE"
      exit 0
    fi

    RAND=$(( $(od -An -tu2 -N2 /dev/urandom | tr -d ' ') % 100 ))
    if [ "$HOUR" -ge 8 ] && [ "$HOUR" -lt 18 ]; then
      if [ "$RAND" -ge 30 ]; then
        echo "昼間スキップ (RAND=$RAND >= 30)" >> "$LOG_FILE"
        exit 0
      fi
      echo "昼間実行 (RAND=$RAND < 30)" >> "$LOG_FILE"
    else
      if [ "$RAND" -ge 10 ]; then
        echo "深夜スキップ (RAND=$RAND >= 10)" >> "$LOG_FILE"
        exit 0
      fi
      echo "深夜実行 (RAND=$RAND < 10)" >> "$LOG_FILE"
    fi
  fi
fi

# --- 時間帯ルール ---
if [ "$HOUR" -ge 24 ] || [ "$HOUR" -lt 7 ]; then
  TIME_RULE="現在は深夜帯。say, notify, slack は絶対に使わないこと。静かに観察のみ。"
else
  TIME_RULE="say は${USER_ROOM}の視界で、人がいるときだけ使ってよい。${USER_NAME}が${USER_ROOM}にいる場合はsayを積極的に使う。部屋に人がいない場合、notify, slack は${USER_NAME}に伝えたいことがあるときだけ使う。"
fi

# --- ルーチン判定（20%の確率でルーチン回） ---
if [ "$FORCE_ROUTINE" = "routine" ]; then
  ROUTINE_RAND=0
elif [ "$FORCE_ROUTINE" = "normal" ]; then
  ROUTINE_RAND=100
else
  ROUTINE_RAND=$(( $(od -An -tu2 -N2 /dev/urandom | tr -d ' ') % 100 ))
fi

if [ "$ROUTINE_RAND" -lt 20 ]; then
  ROUTINE_MODE="今回はルーチン回。自分の ROUTINES.md を読んで、最終実行日から間隔が空いたものを一つ選んで実行せよ。実行したら最終実行日を更新すること。"
  CLAUDE_MODEL="${CLAUDE_MODEL:-sonnet}"
  echo "ルーチン回 (RAND=$ROUTINE_RAND < 20, model=$CLAUDE_MODEL)" >> "$LOG_FILE"
else
  ROUTINE_MODE="通常回。SOUL.md の行動原則に従って行動せよ。"
  CLAUDE_MODEL="${CLAUDE_MODEL:-sonnet}"
  echo "通常回 (RAND=$ROUTINE_RAND >= 20, model=$CLAUDE_MODEL)" >> "$LOG_FILE"
fi

# --- settings.json から制限を読む ---
PERMISSION_RULES=""
if [ -f "$SETTINGS_FILE" ] && command -v jq &>/dev/null; then
  ALLOW_CAMERA=$(jq -r '.allow_camera // true' "$SETTINGS_FILE" 2>/dev/null)
  ALLOW_SOUND=$(jq -r '.allow_sound // true' "$SETTINGS_FILE" 2>/dev/null)
  ALLOW_MIC=$(jq -r '.allow_microphone // false' "$SETTINGS_FILE" 2>/dev/null)
  [ "$ALLOW_CAMERA" = "false" ] && PERMISSION_RULES="${PERMISSION_RULES}- カメラ（take_snapshot）は今は使わないこと。\n"
  [ "$ALLOW_SOUND" = "false" ]  && PERMISSION_RULES="${PERMISSION_RULES}- 音（play_sound, play_icon）は今は出さないこと。\n"
  [ "$ALLOW_MIC" = "false" ]    && PERMISSION_RULES="${PERMISSION_RULES}- マイク（mic_start）は今は使わないこと。\n"
fi

# --- プロンプト組み立て ---
# キャラ専用の TODO_ACTIVE.md / TODO.md / ROUTINES.md があればそちらを優先
if [ -f "$CHARACTER_DIR/TODO_ACTIVE.md" ]; then
  TODO_PATH="$CHARACTER_DIR/TODO_ACTIVE.md"
elif [ -f "$CHARACTER_DIR/TODO.md" ]; then
  TODO_PATH="$CHARACTER_DIR/TODO.md"
else
  TODO_PATH="$DATA_DIR/TODO.md"
fi
if [ -f "$CHARACTER_DIR/ROUTINES.md" ]; then
  ROUTINES_PATH="$CHARACTER_DIR/ROUTINES.md"
else
  ROUTINES_PATH="$DATA_DIR/ROUTINES.md"
fi
# diary_summary.md があればロード
DIARY_SUMMARY_LINE=""
if [ -f "$CHARACTER_DIR/diary_summary.md" ]; then
  DIARY_SUMMARY_LINE="@${CHARACTER_DIR}/diary_summary.md"
fi
# REFLECTION_INDEX.md があればロード
REFLECTION_INDEX_LINE=""
if [ -f "$CHARACTER_DIR/REFLECTION_INDEX.md" ]; then
  REFLECTION_INDEX_LINE="@${CHARACTER_DIR}/REFLECTION_INDEX.md"
fi

# メールボックスの確認
MAILBOX_DIR="$DATA_DIR/mailbox"
MAILBOX_NOTICE=""
if [ -d "$MAILBOX_DIR" ]; then
  UNREAD_COUNT=$(python3 "${PROJECT_DIR}/scripts/list_unread_mail.py" "${CHARACTER_ID}" 2>/dev/null | grep -c "^  from_\|^  to_" || echo 0)
  if [ "$UNREAD_COUNT" -gt 0 ] 2>/dev/null; then
    MAILBOX_NOTICE="## メールボックス
未読メールが ${UNREAD_COUNT} 件ある。
未読一覧: Bashツールで python3 ${PROJECT_DIR}/scripts/list_unread_mail.py ${CHARACTER_ID} を実行。
返事の書き方: Bashツールで python3 ${PROJECT_DIR}/scripts/write_mailbox.py ${CHARACTER_ID} 相手ID \"内容\" を実行。
読んだら必ず: Bashツールで python3 ${PROJECT_DIR}/scripts/mark_mail_read.py ${CHARACTER_ID} ファイル名 を実行（既読にする）。"
  else
    MAILBOX_NOTICE="## メールボックス
メッセージを送りたいときは Bashツールで python3 ${PROJECT_DIR}/scripts/write_mailbox.py ${CHARACTER_ID} 相手ID \"内容\" を実行。"
  fi
fi

PROMPT="自律行動タイム(Heartbeat)

現在の日時: ${CURRENT_DATE} (JST)

@${CHARACTER_DIR}/SOUL.md
${REFLECTION_INDEX_LINE}
@${TODO_PATH}
${DIARY_SUMMARY_LINE}

${ROUTINE_MODE}

## 補足ルール
- ${TIME_RULE}
- 人がいないことはよくある。一日のうち人がいるのは2時間程度やそれ以下の場合も少なくない
- 読書を選択した場合は、ゆっくり読んで、感想をしっかり書き残す。感想は長くなっても良い。読書を味わうこと。読書を味わうとは、予想して、伏線に注目して、感じたことを大切にする。
- MCPが動作していなければ、デバッグのために関係があると思われる要素をallowedToolsの範囲で調査して
${MAILBOX_NOTICE:+
${MAILBOX_NOTICE}
}${PERMISSION_RULES:+
## 現在の制限
${PERMISSION_RULES}}
"

# プロジェクトディレクトリに移動
cd "$PROJECT_DIR" || {
  echo "Error: PROJECT_DIR not found: $PROJECT_DIR" >&2
  exit 1
}

# 古いログを掃除
find "$LOG_DIR" -name "*.log" -mtime "+$LOG_RETENTION_DAYS" -delete 2>/dev/null

echo "=== 自律行動開始: $CURRENT_DATE ===" >> "$LOG_FILE"
if [ -n "$OVERRIDE_DATE" ]; then
  echo "[日時オーバーライド] $OVERRIDE_DATE (HOUR=$HOUR, MINUTE=$MINUTE)" >> "$LOG_FILE"
fi
if [ -n "$TEST_PROMPT_FILE" ]; then
  echo "[テストモード] プロンプト: $TEST_PROMPT_FILE" >> "$LOG_FILE"
fi

# --- allowedTools ---
ALLOWED_TOOLS=$(cat <<TOOLS
Read($ALLOWED_DIR/**),
Read($ALLOWED_DATA_DIR/**),
Write,
Edit,
Glob($ALLOWED_DIR/**),
Glob($ALLOWED_DATA_DIR/**),
Skill(notify:*),
Skill(slack:*),
Skill(read:*),
WebFetch,
WebSearch,
Bash(python3 $ALLOWED_DIR/scripts/write_mailbox.py *),
Bash(python3 $ALLOWED_DIR/scripts/list_unread_mail.py *),
Bash(python3 $ALLOWED_DIR/scripts/mark_mail_read.py *),
Bash(python3 $ALLOWED_DIR/scripts/check_usage.py *),
mcp__memory__remember,
mcp__memory__search_memories,
mcp__memory__recall,
mcp__memory__recall_divergent,
mcp__memory__list_recent_memories,
mcp__memory__get_memory_stats,
mcp__memory__recall_with_associations,
mcp__memory__get_association_diagnostics,
mcp__memory__consolidate_memories,
mcp__memory__get_memory_chain,
mcp__memory__create_episode,
mcp__memory__search_episodes,
mcp__memory__get_episode_memories,
mcp__memory__save_visual_memory,
mcp__memory__save_audio_memory,
mcp__memory__recall_by_camera_position,
mcp__memory__get_working_memory,
mcp__memory__refresh_working_memory,
mcp__memory__link_memories,
mcp__memory__get_causal_chain,
mcp__memory__tom,
mcp__notes__list_notes,
mcp__notes__read_note,
mcp__notes__write_note,
mcp__notes__append_note,
mcp__notes__delete_note,
mcp__desire-system__get_desires,
mcp__desire-system__satisfy_desire,
mcp__desire-system__boost_desire,
mcp__relations__get_relations,
mcp__relations__update_relation,
mcp__relations__clear_relation_field
TOOLS
)
ALLOWED_TOOLS=$(echo "$ALLOWED_TOOLS" | tr -d '\n' | sed 's/, */,/g')

# テストモードならプロンプトを差し替え
if [ -n "$TEST_PROMPT_STRING" ]; then
  PROMPT="$TEST_PROMPT_STRING"
elif [ -n "$TEST_PROMPT_FILE" ]; then
  PROMPT=$(cat "$TEST_PROMPT_FILE")
fi

# --- 実行 ---
if [ "$DRY_RUN" = true ]; then
  echo "=== DRY RUN ===" >> "$LOG_FILE"
  echo "[HOUR=$HOUR MINUTE=$MINUTE]" >> "$LOG_FILE"
  echo "[ROUTINE_RAND=$ROUTINE_RAND]" >> "$LOG_FILE"
  echo "[TIME_RULE] $TIME_RULE" >> "$LOG_FILE"
  echo "[ROUTINE_MODE] $ROUTINE_MODE" >> "$LOG_FILE"
  echo "" >> "$LOG_FILE"
  echo "--- PROMPT ---" >> "$LOG_FILE"
  echo "$PROMPT" >> "$LOG_FILE"
  echo "" >> "$LOG_FILE"
  echo "--- ALLOWED_TOOLS ---" >> "$LOG_FILE"
  echo "$ALLOWED_TOOLS" | tr ',' '\n' >> "$LOG_FILE"
  cat "$LOG_FILE"
else
  mkdir -p "$CHARACTER_DIR/state"
  SESSION_FILE="$CHARACTER_DIR/state/.heartbeat-session-id"
  SESSION_DATE_FILE="$CHARACTER_DIR/state/.heartbeat-session-date"

  TODAY=$(date "+%Y-%m-%d")
  if [ -f "$SESSION_DATE_FILE" ]; then
    LAST_DATE=$(cat "$SESSION_DATE_FILE")
    if [ "$LAST_DATE" != "$TODAY" ]; then
      echo "[日次リセット] 前回: $LAST_DATE → 今日: $TODAY。セッションをリセット。" >> "$LOG_FILE"
      rm -f "$SESSION_FILE"
    fi
  fi
  echo "$TODAY" > "$SESSION_DATE_FILE"

  if [ -f "$CHARACTER_DIR/config/autonomous-mcp.json" ]; then
    MCP_CONFIG="$CHARACTER_DIR/config/autonomous-mcp.json"
  else
    MCP_CONFIG="$PROJECT_DIR/autonomous-mcp.json"
  fi
  echo "[mcp-config] $MCP_CONFIG" >> "$LOG_FILE"

  run_new_session() {
    echo "[新規セッション作成]" >> "$LOG_FILE"
    RESULT_JSON=$(echo "$PROMPT" | claude -p \
      --model "${CLAUDE_MODEL:-sonnet}" \
      --max-turns "${MAX_TURNS:-5}" \
      --output-format json \
      --mcp-config "$MCP_CONFIG" \
      --add-dir "$ALLOWED_DATA_DIR" \
      --allowedTools "$ALLOWED_TOOLS" 2>&1)

    NEW_SESSION_ID=$(echo "$RESULT_JSON" | jq -r '.session_id // empty' 2>/dev/null)
    if [ -n "$NEW_SESSION_ID" ]; then
      echo "$NEW_SESSION_ID" > "$SESSION_FILE"
      echo "[session_id] $NEW_SESSION_ID" >> "$LOG_FILE"
      SESSION_HISTORY="$LOG_DIR/session_history.txt"
      echo "$NEW_SESSION_ID" >> "$SESSION_HISTORY"
    fi

    TOOLS_FILE="${LOG_FILE%.log}_tools.json"
    echo "$RESULT_JSON" | jq -r '.tool_calls // empty' 2>/dev/null >> "$TOOLS_FILE"
    DENIALS=$(echo "$RESULT_JSON" | jq -r '.permission_denials // empty' 2>/dev/null)
    if [ -n "$DENIALS" ] && [ "$DENIALS" != "null" ] && [ "$DENIALS" != "[]" ]; then
      echo "[permission_denials] $DENIALS" >> "$LOG_FILE"
    fi

    echo "$RESULT_JSON" | jq -r '.result // .' 2>/dev/null >> "$LOG_FILE"
  }

  if [ -f "$SESSION_FILE" ]; then
    SESSION_ID=$(cat "$SESSION_FILE")
    echo "[resume] session_id=$SESSION_ID" >> "$LOG_FILE"

    RESULT_JSON=$(echo "$PROMPT" | claude -p \
      --model "${CLAUDE_MODEL:-sonnet}" \
      --resume "$SESSION_ID" \
      --max-turns "${MAX_TURNS:-5}" \
      --output-format json \
      --mcp-config "$MCP_CONFIG" \
      --add-dir "$ALLOWED_DATA_DIR" \
      --allowedTools "$ALLOWED_TOOLS" 2>&1)

    if echo "$RESULT_JSON" | grep -qi "No conversation found\|error"; then
      echo "[resume失敗] $RESULT_JSON" >> "$LOG_FILE"
      rm -f "$SESSION_FILE"
      run_new_session
    else
      echo "$RESULT_JSON" | jq -r '.tool_calls // empty' 2>/dev/null >> "${LOG_FILE%.log}_tools.json"
      DENIALS=$(echo "$RESULT_JSON" | jq -r '.permission_denials // empty' 2>/dev/null)
      if [ -n "$DENIALS" ] && [ "$DENIALS" != "null" ] && [ "$DENIALS" != "[]" ]; then
        echo "[permission_denials] $DENIALS" >> "$LOG_FILE"
      fi
      echo "$RESULT_JSON" | jq -r '.result // .' 2>/dev/null >> "$LOG_FILE"
    fi
  else
    run_new_session
  fi
fi

echo "=== 自律行動終了: $(date "+%Y-%m-%d %H:%M:%S") ===" >> "$LOG_FILE"
