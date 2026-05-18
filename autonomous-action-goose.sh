#!/bin/bash
# Goose 自律行動スクリプト（Gemini / OpenAI 対応）
# autonomous-action.sh の Goose 版（claude -p → goose run）
# プロバイダーは GOOSE_PROVIDER / GOOSE_MODEL 環境変数で切り替え可能
#   Gemini:  GOOSE_PROVIDER=google  GOOSE_MODEL=gemini-2.5-flash （デフォルト）
#   OpenAI:  GOOSE_PROVIDER=openai  GOOSE_MODEL=gpt-4o
#
# セットアップ:
# 1. このファイルをコピー: cp autonomous-action-goose.sh autonomous-action-goose-{character}.sh
# 2. 環境設定セクションを編集
# 3. 実行権限を付与: chmod +x autonomous-action-goose-{character}.sh
# 4. crontab -e で設定:
#    */30 * * * * /path/to/autonomous-action-goose-{character}.sh {character_id}
#
# Usage:
#   autonomous-action-goose.sh [CHARACTER_ID]
#   autonomous-action-goose.sh --dry-run [CHARACTER_ID]
#   autonomous-action-goose.sh --force-routine [CHARACTER_ID]
#   autonomous-action-goose.sh --force-normal [CHARACTER_ID]
#   autonomous-action-goose.sh --date "2026-05-18 14:30" [CHARACTER_ID]
#   autonomous-action-goose.sh -p "任意プロンプト" [CHARACTER_ID]

# ============================================================================
# 環境設定
# ============================================================================

export HOME="/home/cube-petit"
export PATH="$HOME/.local/bin:/usr/local/bin:/usr/bin:$PATH"

PROJECT_DIR="$HOME/work/embodied-claude"
DATA_DIR="${PETIT_DATA_DIR:-$HOME/petit_claude}"

# 最初の引数がフラグでなければキャラクターIDとして扱う
if [ -n "$1" ] && [[ "$1" != -* ]]; then
  CHARACTER_ID="$1"
  shift
else
  CHARACTER_ID="puchiko"
fi
CHARACTER_DIR="$DATA_DIR/characters/$CHARACTER_ID"

# settings.json から max_turns を読む
if [ -z "$MAX_TURNS" ]; then
  SETTINGS_FILE_INIT="$CHARACTER_DIR/config/settings.json"
  MAX_TURNS=$(python3 -c "import json,sys; d=json.load(open('${SETTINGS_FILE_INIT}')); print(d.get('max_turns', 20))" 2>/dev/null || echo 20)
fi

ENV_FILE="$DATA_DIR/.env"
set -a
source "$ENV_FILE" 2>/dev/null || true
set +a

USER_NAME="ありさん"
USER_ROOM="${USER_NAME}の部屋"

LOG_DIR_NAME=".autonomous-logs-goose"
LOG_RETENTION_DAYS=7

_LOG_TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_DIR="$DATA_DIR/$LOG_DIR_NAME/$CHARACTER_ID"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/${_LOG_TIMESTAMP}.log"

# ============================================================================
# 環境検出・引数パース
# ============================================================================

if [[ "$OSTYPE" == "darwin"* ]]; then IS_MACOS=true; else IS_MACOS=false; fi

TEST_PROMPT_STRING=""
OVERRIDE_DATE=""
FORCE_ROUTINE=""
DRY_RUN=false

while [ $# -gt 0 ]; do
  case "$1" in
    -p) TEST_PROMPT_STRING="$2"; shift 2 ;;
    --date) OVERRIDE_DATE="$2"; shift 2 ;;
    --force-routine) FORCE_ROUTINE="routine"; shift ;;
    --force-normal) FORCE_ROUTINE="normal"; shift ;;
    --dry-run) DRY_RUN=true; shift ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

# 日時取得
if [ -n "$OVERRIDE_DATE" ]; then
  if [ "$IS_MACOS" = true ]; then
    CURRENT_DATE=$(date -j -f "%Y-%m-%d %H:%M" "$OVERRIDE_DATE" "+%Y-%m-%d %H:%M:%S" 2>/dev/null)
    HOUR=$((10#$(date -j -f "%Y-%m-%d %H:%M" "$OVERRIDE_DATE" +%H 2>/dev/null)))
    MINUTE=$((10#$(date -j -f "%Y-%m-%d %H:%M" "$OVERRIDE_DATE" +%M 2>/dev/null)))
  else
    CURRENT_DATE=$(date -d "$OVERRIDE_DATE" "+%Y-%m-%d %H:%M:%S" 2>/dev/null)
    HOUR=$((10#$(date -d "$OVERRIDE_DATE" +%H 2>/dev/null)))
    MINUTE=$((10#$(date -d "$OVERRIDE_DATE" +%M 2>/dev/null)))
  fi
else
  CURRENT_DATE=$(date "+%Y-%m-%d %H:%M:%S")
  HOUR=$((10#$(date +%H)))
  MINUTE=$((10#$(date +%M)))
fi

# ============================================================================
# スケジュール制御
# ============================================================================

SKIP_SCHEDULE=false
if [ -n "$TEST_PROMPT_STRING" ]; then
  SKIP_SCHEDULE=true
elif [ "$DRY_RUN" = true ] && [ -z "$OVERRIDE_DATE" ]; then
  SKIP_SCHEDULE=true
fi

# 頻度スキップ（settings.json の autonomous_skip）
SKIP_COUNTER_FILE="$CHARACTER_DIR/.heartbeat-skip-counter-goose"
if [ "$SKIP_SCHEDULE" = false ]; then
  SETTINGS_FILE="$CHARACTER_DIR/config/settings.json"
  AUTONOMOUS_SKIP=0
  if [ -f "$SETTINGS_FILE" ] && command -v jq &>/dev/null; then
    AUTONOMOUS_SKIP=$(jq -r '.autonomous_skip // 0' "$SETTINGS_FILE" 2>/dev/null)
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
    if [ "$DOW" -ge 6 ] 2>/dev/null; then DAY_TYPE="weekend"; else DAY_TYPE="weekday"; fi
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
    if [ "$HOUR" -ge 7 ] && [ "$HOUR" -lt 8 ]; then IS_ACTIVE=true
    elif [ "$HOUR" -ge 12 ] && [ "$HOUR" -lt 13 ]; then IS_ACTIVE=true
    elif [ "$HOUR" -ge 18 ]; then IS_ACTIVE=true; fi
  fi

  if [ "$IS_ACTIVE" = false ]; then
    if [ "$MINUTE" -ne 0 ]; then
      echo "非アクティブ時間帯 :${MINUTE} スキップ" >> "$LOG_FILE"
      exit 0
    fi
    RAND=$(( $(od -An -tu2 -N2 /dev/urandom | tr -d ' ') % 100 ))
    if [ "$HOUR" -ge 8 ] && [ "$HOUR" -lt 18 ]; then
      if [ "$RAND" -ge 30 ]; then echo "昼間スキップ (RAND=$RAND)" >> "$LOG_FILE"; exit 0; fi
      echo "昼間実行 (RAND=$RAND)" >> "$LOG_FILE"
    else
      if [ "$RAND" -ge 10 ]; then echo "深夜スキップ (RAND=$RAND)" >> "$LOG_FILE"; exit 0; fi
      echo "深夜実行 (RAND=$RAND)" >> "$LOG_FILE"
    fi
  fi
fi

# ============================================================================
# 時間帯ルール・ルーチン判定
# ============================================================================

if [ "$HOUR" -ge 24 ] || [ "$HOUR" -lt 7 ]; then
  TIME_RULE="現在は深夜帯。say, notify, slack は絶対に使わないこと。静かに観察のみ。"
else
  TIME_RULE="say は${USER_ROOM}の視界で、人がいるときだけ使ってよい。${USER_NAME}が${USER_ROOM}にいる場合はsayを積極的に使う。リビングにいる場合は slackを使う。部屋に人がいない場合、notify, slack は${USER_NAME}に伝えたいことがあるときだけ使う。"
fi

if [ "$FORCE_ROUTINE" = "routine" ]; then ROUTINE_RAND=0
elif [ "$FORCE_ROUTINE" = "normal" ]; then ROUTINE_RAND=100
else ROUTINE_RAND=$(( $(od -An -tu2 -N2 /dev/urandom | tr -d ' ') % 100 )); fi

GOOSE_PROVIDER="${GOOSE_PROVIDER:-google}"
GOOSE_MODEL="${GOOSE_MODEL:-gemini-2.5-flash}"

if [ "$ROUTINE_RAND" -lt 20 ]; then
  ROUTINE_MODE="今回はルーチン回。自分の ROUTINES.md を読んで、最終実行日から間隔が空いたものを一つ選んで実行せよ。実行したら最終実行日を更新すること。"
  echo "ルーチン回 (RAND=$ROUTINE_RAND, provider=$GOOSE_PROVIDER, model=$GOOSE_MODEL)" >> "$LOG_FILE"
else
  ROUTINE_MODE="通常回。SOUL.md の行動原則に従って行動せよ。"
  echo "通常回 (RAND=$ROUTINE_RAND, provider=$GOOSE_PROVIDER, model=$GOOSE_MODEL)" >> "$LOG_FILE"
fi

# 権限ルール
SETTINGS_FILE="$CHARACTER_DIR/config/settings.json"
PERMISSION_RULES=""
if [ -f "$SETTINGS_FILE" ] && command -v jq &>/dev/null; then
  ALLOW_CAMERA=$(jq -r '.allow_camera // true' "$SETTINGS_FILE" 2>/dev/null)
  ALLOW_SOUND=$(jq -r '.allow_sound // true' "$SETTINGS_FILE" 2>/dev/null)
  ALLOW_MIC=$(jq -r '.allow_microphone // false' "$SETTINGS_FILE" 2>/dev/null)
  [ "$ALLOW_CAMERA" = "false" ] && PERMISSION_RULES="${PERMISSION_RULES}- カメラ（take_snapshot）は今は使わないこと。\n"
  [ "$ALLOW_SOUND" = "false" ]  && PERMISSION_RULES="${PERMISSION_RULES}- 音（play_sound, play_icon）は今は出さないこと。\n"
  [ "$ALLOW_MIC" = "false" ]    && PERMISSION_RULES="${PERMISSION_RULES}- マイク（mic_start）は今は使わないこと。\n"
fi

# ============================================================================
# プロンプト組み立て（ファイル内容をインライン展開）
# ============================================================================

TODO_PATH=""
if [ -f "$CHARACTER_DIR/TODO_ACTIVE.md" ]; then TODO_PATH="$CHARACTER_DIR/TODO_ACTIVE.md"
elif [ -f "$CHARACTER_DIR/TODO.md" ]; then TODO_PATH="$CHARACTER_DIR/TODO.md"
else TODO_PATH="$DATA_DIR/TODO.md"; fi

if [ -f "$CHARACTER_DIR/ROUTINES.md" ]; then
  ROUTINES_PATH="$CHARACTER_DIR/ROUTINES.md"
else
  ROUTINES_PATH="$DATA_DIR/ROUTINES.md"
fi

# ファイル内容をインライン展開（Goose は @file 展開に非対応のため）
SOUL_CONTENT=$(cat "$CHARACTER_DIR/SOUL.md" 2>/dev/null || echo "")
TODO_CONTENT=$(cat "$TODO_PATH" 2>/dev/null || echo "")
DIARY_CONTENT=""
if [ -f "$CHARACTER_DIR/diary_summary.md" ]; then
  DIARY_CONTENT="## 最近の日記
$(cat "$CHARACTER_DIR/diary_summary.md")"
fi

# メールボックス確認
MAILBOX_DIR="$DATA_DIR/mailbox"
MAILBOX_NOTICE=""
if [ -d "$MAILBOX_DIR" ]; then
  UNREAD_COUNT=$(python3 "${PROJECT_DIR}/scripts/list_unread_mail.py" "${CHARACTER_ID}" 2>/dev/null | grep -c "^  from_\|^  to_" || echo 0)
  if [ "$UNREAD_COUNT" -gt 0 ] 2>/dev/null; then
    MAILBOX_NOTICE="## メールボックス
未読メールが ${UNREAD_COUNT} 件ある。
未読一覧: python3 ${PROJECT_DIR}/scripts/list_unread_mail.py ${CHARACTER_ID} を実行。
返事: python3 ${PROJECT_DIR}/scripts/write_mailbox.py ${CHARACTER_ID} 相手ID \"内容\" を実行。
既読: python3 ${PROJECT_DIR}/scripts/mark_mail_read.py ${CHARACTER_ID} ファイル名 を実行。"
  else
    MAILBOX_NOTICE="## メールボックス
メッセージを送りたいときは python3 ${PROJECT_DIR}/scripts/write_mailbox.py ${CHARACTER_ID} 相手ID \"内容\" を実行。相手ID: puchiko, puchiteya, puchiru, arisan"
  fi
fi

PROMPT="自律行動タイム(Heartbeat)

現在の日時: ${CURRENT_DATE} (JST)

## SOUL.md
${SOUL_CONTENT}

## TODO
${TODO_CONTENT}

${DIARY_CONTENT}

${ROUTINE_MODE}

## 補足ルール
- ${TIME_RULE}
- 人がいないことはよくある。一日のうち人がいるのは2時間程度やそれ以下の場合も少なくない
- 読書を選択した場合は、ゆっくり読んで、感想をしっかり書き残す。感想は長くなっても良い。読書を味わうこと。
- MCPが動作していなければ、デバッグのために関係があると思われる要素を調査して
- ファイルを書き込む場合は bash ツールで python3 などを使わず、text_editor ツールで直接書き込むこと
${MAILBOX_NOTICE:+
${MAILBOX_NOTICE}
}${PERMISSION_RULES:+
## 現在の制限
${PERMISSION_RULES}}"

# テストプロンプト差し替え
if [ -n "$TEST_PROMPT_STRING" ]; then
  PROMPT="$TEST_PROMPT_STRING"
fi

# ============================================================================
# MCP 拡張の構築（autonomous-mcp.json を --with-extension に変換）
# ============================================================================

if [ -f "$CHARACTER_DIR/config/autonomous-mcp.json" ]; then
  MCP_CONFIG="$CHARACTER_DIR/config/autonomous-mcp.json"
else
  MCP_CONFIG="$PROJECT_DIR/autonomous-mcp.json"
fi
echo "[mcp-config] $MCP_CONFIG" >> "$LOG_FILE"

# Python で JSON → --with-extension 文字列リストに変換
# ランチャースクリプト (mcp-launchers/) があればそちらを優先（goose の tool prefix を一意にするため）
LAUNCHERS_DIR="$PROJECT_DIR/mcp-launchers"
mapfile -t EXT_CMDS < <(python3 - "$MCP_CONFIG" "$LAUNCHERS_DIR" <<'PYEOF'
import json, sys, os

with open(sys.argv[1]) as f:
    config = json.load(f)

launchers_dir = sys.argv[2]

for name, server in config.get('mcpServers', {}).items():
    launcher = os.path.join(launchers_dir, name)
    parts = []
    for k, v in server.get('env', {}).items():
        parts.append(f'{k}={v}')
    if os.path.isfile(launcher) and os.access(launcher, os.X_OK):
        # ランチャースクリプトを使う（tool prefix = name）
        parts.append(launcher)
    else:
        # フォールバック: 元のコマンド（node 等）
        parts.append(server['command'])
        parts.extend(server.get('args', []))
    print(' '.join(parts))
PYEOF
)

GOOSE_EXTENSION_ARGS=()
for cmd in "${EXT_CMDS[@]}"; do
  GOOSE_EXTENSION_ARGS+=(--with-extension "$cmd")
done

# ============================================================================
# 実行
# ============================================================================

cd "$PROJECT_DIR" || { echo "Error: PROJECT_DIR not found: $PROJECT_DIR" >&2; exit 1; }

find "$LOG_DIR" -name "*.log" -mtime "+$LOG_RETENTION_DAYS" -delete 2>/dev/null

echo "=== 自律行動開始 (Goose): $CURRENT_DATE ===" >> "$LOG_FILE"
[ -n "$OVERRIDE_DATE" ] && echo "[日時オーバーライド] $OVERRIDE_DATE (HOUR=$HOUR, MINUTE=$MINUTE)" >> "$LOG_FILE"

TODAY=$(date "+%Y-%m-%d")
SESSION_NAME="${CHARACTER_ID}-${GOOSE_PROVIDER}-${TODAY}"

if [ "$DRY_RUN" = true ]; then
  echo "=== DRY RUN ===" >> "$LOG_FILE"
  echo "[HOUR=$HOUR MINUTE=$MINUTE]" >> "$LOG_FILE"
  echo "[ROUTINE_RAND=$ROUTINE_RAND]" >> "$LOG_FILE"
  echo "[TIME_RULE] $TIME_RULE" >> "$LOG_FILE"
  echo "[ROUTINE_MODE] $ROUTINE_MODE" >> "$LOG_FILE"
  echo "[SESSION_NAME] $SESSION_NAME" >> "$LOG_FILE"
  echo "[PROVIDER] $GOOSE_PROVIDER / $GOOSE_MODEL" >> "$LOG_FILE"
  echo "[MCP_CONFIG] $MCP_CONFIG" >> "$LOG_FILE"
  echo "" >> "$LOG_FILE"
  echo "--- EXTENSIONS ---" >> "$LOG_FILE"
  for cmd in "${EXT_CMDS[@]}"; do echo "  $cmd"; done >> "$LOG_FILE"
  echo "" >> "$LOG_FILE"
  echo "--- PROMPT ---" >> "$LOG_FILE"
  echo "$PROMPT" >> "$LOG_FILE"
  cat "$LOG_FILE"
else
  # セッションが既に存在するか確認（存在するなら --resume で継続）
  GOOSE_SESSIONS_DB="$HOME/.local/share/goose/sessions/sessions.db"
  RESUME_ARGS=()
  if [ -f "$GOOSE_SESSIONS_DB" ]; then
    SESSION_EXISTS=$(python3 -c "
import sqlite3, sys
conn = sqlite3.connect('$GOOSE_SESSIONS_DB')
cur = conn.cursor()
cur.execute('SELECT id FROM sessions WHERE name = ?', ('$SESSION_NAME',))
row = cur.fetchone()
conn.close()
print(row[0] if row else '')
" 2>/dev/null)
    if [ -n "$SESSION_EXISTS" ]; then
      RESUME_ARGS=(--resume)
      echo "[resume] session=$SESSION_NAME (id=$SESSION_EXISTS)" >> "$LOG_FILE"
    else
      echo "[新規セッション] $SESSION_NAME" >> "$LOG_FILE"
    fi
  else
    echo "[新規セッション] sessions.db not found" >> "$LOG_FILE"
  fi

  goose run \
    --provider "$GOOSE_PROVIDER" \
    --model "$GOOSE_MODEL" \
    --no-profile \
    --with-builtin developer \
    "${GOOSE_EXTENSION_ARGS[@]}" \
    --name "$SESSION_NAME" \
    "${RESUME_ARGS[@]}" \
    --max-turns "${MAX_TURNS:-20}" \
    --quiet \
    --text "$PROMPT" >> "$LOG_FILE" 2>&1

  EXIT_CODE=$?
  if [ $EXIT_CODE -ne 0 ]; then
    echo "[goose exit code] $EXIT_CODE" >> "$LOG_FILE"
  fi
fi

echo "=== 自律行動終了 (Goose): $(date "+%Y-%m-%d %H:%M:%S") ===" >> "$LOG_FILE"
