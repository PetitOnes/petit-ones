#!/bin/bash
# Claude 自律行動スクリプト（macOS / Linux 対応）
# 30 分ごとに cron で実行(子ごとに 5 分ずらす)、時間帯に応じて間引く
#
# このファイルは家に依らない(git 管理)。家ごとの値は PETIT_DATA_DIR/.env と、あれば PETIT_DATA_DIR/config/house.sh から読む。
# セットアップ:
# 1. scripts/setup_house.py で家(PETIT_DATA_DIR)を用意する(.env に COMPANION_NAME・COMPANION_ID)
# 2. scripts/create_character.py が crontab に次を足す:
#    0,30 * * * * /path/to/petit-ones/autonomous-action.sh <character_id>
#
# Usage:
#   autonomous-action.sh                                    # 通常実行（cron）
#   autonomous-action.sh --test-prompt FILE                 # プロンプト差し替え（スケジュール制御スキップ）
#   autonomous-action.sh --date "2026-02-20 14:30"          # 日時を注入（スケジュール制御テスト）
#   autonomous-action.sh --force-routine                    # ルーチン回を強制
#   autonomous-action.sh --force-normal                     # 通常回を強制
#   autonomous-action.sh --dry-run                          # claude -p を実行せずプロンプトを表示
#   autonomous-action.sh -p "任意のプロンプト"              # プロンプト直接指定（スケジュール制御スキップ）
#   autonomous-action.sh --dry-run --date "2026-02-20 03:00" --force-routine  # 組み合わせ可

# ============================================================================
# 環境設定(家ごとの値はここに書かない。.env / config/house.sh へ)
# ============================================================================

# ★ ホームディレクトリ（crontab は $HOME すら持たないため明示的に設定）
# 例: /Users/yourname (macOS) または /home/yourname (Linux)
# 確認方法: ターミナルで "echo $HOME" を実行
export HOME="${HOME:-$(eval echo ~"$(id -un)")}"

# ★ PATH 設定（crontab は $PATH も最小限のため、必要なコマンドのパスを追加）
# 必要なコマンド: claude, jq, date など
# 例 (macOS + asdf + homebrew):
#   export PATH="$HOME/.asdf/shims:/opt/homebrew/bin:$PATH"
# 例 (Linux + nodenv):
#   export PATH="$HOME/.nodenv/shims:/usr/local/bin:$PATH"
# 確認方法: "which claude" "which jq" でパスを確認
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:$PATH"

# ★ プロジェクトディレクトリ（コード配置場所。MCP起動・subprocess cwd用）
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"  # このファイルの場所(リポジトリの根)

# ★ データディレクトリ（キャラデータ・ログなどプライベートデータ）
DATA_DIR="${PETIT_DATA_DIR:-$HOME/petit_claude}"

# ★ キャラクターID（characters/ 以下のディレクトリ名）
# 例: puchiko, puchitaro など
# crontab では: autonomous-action.sh puchiko のように引数で指定する
# 最初の引数がフラグでなければキャラクターIDとして扱う
if [ -n "$1" ] && [[ "$1" != -* ]]; then
  CHARACTER_ID="$1"
  shift
else
  echo "usage: autonomous-action.sh <character_id> [--dry-run|--date ...|-p ...]" >&2
  exit 1
fi
CHARACTER_DIR="$DATA_DIR/characters/$CHARACTER_ID"

# キャラクターごとの最大ターン数（環境変数 MAX_TURNS で上書き可、なければ settings.json から読む）
SETTINGS_FILE="$CHARACTER_DIR/config/settings.json"   # 制限(allow_*)の読み取りでも使うので、MAX_TURNS の有無に関わらず決める
if [ -z "$MAX_TURNS" ]; then
  MAX_TURNS=$(python3 -c "import json,sys; d=json.load(open('${SETTINGS_FILE}')); print(d.get('max_turns', 20))" 2>/dev/null || echo 20)
fi

# ★ .env ファイルのパス（プロジェクトディレクトリ配下）
# .env には以下の環境変数が含まれる:
#   - ELEVENLABS_API_KEY: ElevenLabs TTS の API キー
#   - TAPO_USERNAME, TAPO_PASSWORD: Wi-Fi カメラの認証情報
#   - その他 MCP サーバーが必要とする環境変数
ENV_FILE="$DATA_DIR/.env"
set -a
source "$ENV_FILE" 2>/dev/null || true
set +a

# ★ 家ごとの上書き(任意)。USER_NAME・USER_ROOM・CLAUDE_MODEL・時間帯のルールなどをここで変えられる
HOUSE_FILE="$DATA_DIR/config/house.sh"
[ -f "$HOUSE_FILE" ] && source "$HOUSE_FILE"
# ★ ぷち専用の Claude 設定(2026-11-13)。家の .claude/ があれば CLAUDE_CONFIG_DIR にして、開発側の
#   ~/.claude(CLAUDE.md・自動メモリ・プラグイン)を読ませない。cwd も家にして、リポの CLAUDE.md を読ませない
#   (Claude Code は cwd とその祖先の CLAUDE.md / .claude/CLAUDE.md を全部読むので、cwd をリポの外に出す必要がある)
PETIT_CLAUDE_CONFIG_DIR="${PETIT_CLAUDE_CONFIG_DIR:-$DATA_DIR/.claude}"
if [ -d "$PETIT_CLAUDE_CONFIG_DIR" ]; then
  export CLAUDE_CONFIG_DIR="$PETIT_CLAUDE_CONFIG_DIR"
fi
CLAUDE_CWD="$DATA_DIR"

# ★ ユーザー名・部屋名（時間帯ルールで使用）
# 例: "あなた" "コウタ" など
USER_NAME="${COMPANION_NAME:-あなた}"  # .env の COMPANION_NAME
# 例: "あなたの部屋" "コウタの部屋" など
USER_ROOM="${USER_NAME}の部屋"

# ★ allowedTools で許可するディレクトリパス
# セキュリティ: 必要最小限のディレクトリのみ指定すること（.env ファイルなど機密情報も読める）
# メモ：シークレットとenvを別で監理するのはまだ実装されていない
# PROJECT_DIR: コードの読み取り、DATA_DIR: キャラデータ・ログの読み書き
ALLOWED_DIR="$PROJECT_DIR"
ALLOWED_DATA_DIR="$DATA_DIR"

# ログディレクトリ名（プロジェクトディレクトリ配下に作成される）
# ⚠️ 重要: test-autonomous.sh の L129 と設定を一致させる必要があります（必須）
LOG_DIR_NAME=".autonomous-logs"

# ログ保持期間（日数）
# この日数より古いログファイルを自動削除する
# 例: 1 = 1日以上前のログを削除, 7 = 1週間以上前のログを削除
LOG_RETENTION_DAYS=7

# ログディレクトリ・ファイルの初期化（スケジュール判定より前に作成）
_LOG_TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_DIR="$DATA_DIR/$LOG_DIR_NAME/$CHARACTER_ID"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/${_LOG_TIMESTAMP}.log"

# ============================================================================
# 環境検出・日時処理
# ============================================================================

# OS検出（macOS or Linux）
if [[ "$OSTYPE" == "darwin"* ]]; then
  IS_MACOS=true
else
  IS_MACOS=false
fi

# --- 引数パース ---
TEST_PROMPT_FILE=""
TEST_PROMPT_STRING=""
OVERRIDE_DATE=""
FORCE_ROUTINE=""    # "", "routine", "normal"
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

# --- 日時の取得（環境別に一度だけ実行） ---
if [ -n "$OVERRIDE_DATE" ]; then
  # テスト用の日時オーバーライド
  if [ "$IS_MACOS" = true ]; then
    # macOS: date -j -f "format" "date_string" +output
    CURRENT_DATE=$(date -j -f "%Y-%m-%d %H:%M" "$OVERRIDE_DATE" "+%Y-%m-%d %H:%M:%S" 2>/dev/null)
    HOUR=$((10#$(date -j -f "%Y-%m-%d %H:%M" "$OVERRIDE_DATE" +%H 2>/dev/null)))
    MINUTE=$((10#$(date -j -f "%Y-%m-%d %H:%M" "$OVERRIDE_DATE" +%M 2>/dev/null)))
    TIMESTAMP=$(date -j -f "%Y-%m-%d %H:%M" "$OVERRIDE_DATE" +%Y%m%d_%H%M%S 2>/dev/null)
  else
    # Linux: date -d "date_string" +output
    CURRENT_DATE=$(date -d "$OVERRIDE_DATE" "+%Y-%m-%d %H:%M:%S" 2>/dev/null)
    HOUR=$((10#$(date -d "$OVERRIDE_DATE" +%H 2>/dev/null)))
    MINUTE=$((10#$(date -d "$OVERRIDE_DATE" +%M 2>/dev/null)))
    TIMESTAMP=$(date -d "$OVERRIDE_DATE" +%Y%m%d_%H%M%S 2>/dev/null)
  fi
else
  # 現在時刻を取得
  CURRENT_DATE=$(date "+%Y-%m-%d %H:%M:%S")
  HOUR=$((10#$(date +%H)))
  MINUTE=$((10#$(date +%M)))
  TIMESTAMP=$(date +%Y%m%d_%H%M%S)
fi
# --- スケジュール制御（claude到達前に早期リターン） ---
# テストモードではスキップ。dry-run は --date 指定時のみスケジュール制御を通す
# 密（20分間隔で毎回実行）: 7-8時, 12-13時, 18-24時
# 昼間それ以外（毎時:00のみ, 30%）: 8-12時, 13-18時
# 深夜（毎時:00のみ, 10%）: 0-7時

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
    AUTONOMOUS_SKIP=$((AUTONOMOUS_SKIP + 0))  # 数値化
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
      # 実行する→次のスキップカウンターをセット
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
    # 曜日判定: 6(土),7(日)=weekend、それ以外=weekday
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
    # スケジュール上書き設定（平日扱い / 休日扱い）
    DAY_OVERRIDE=$(jq -r '.day_type_override // "null"' "$SETTINGS_FILE" 2>/dev/null)
    if [ "$DAY_OVERRIDE" = "weekday" ] || [ "$DAY_OVERRIDE" = "weekend" ]; then
      DAY_TYPE="$DAY_OVERRIDE"
    fi
    # settings.json のアクティブタイムを使う（新形式/旧形式両対応）
    # 4要素 [sh,sm,eh,em] → 分に変換して比較、2要素 [sh,eh] → 時のみで比較
    IS_ACTIVE=$(jq --argjson h "$HOUR" --argjson m "$MINUTE" --arg dt "$DAY_TYPE" \
      'def check_entry: if length == 4 then (.[0]*60+.[1]) <= ($h*60+$m) and ($h*60+$m) < (.[2]*60+.[3]) else .[0] <= $h and $h < .[1] end;
       if (.active_hours | type) == "object" then
         [.active_hours[$dt][] | select(check_entry)] | length > 0
       else
         [.active_hours[] | select(check_entry)] | length > 0
       end' \
      "$SETTINGS_FILE" 2>/dev/null || echo "false")
  else
    # デフォルト: 7-8時, 12-13時, 18-24時
    if [ "$HOUR" -ge 7 ] && [ "$HOUR" -lt 8 ]; then
      IS_ACTIVE=true
    elif [ "$HOUR" -ge 12 ] && [ "$HOUR" -lt 13 ]; then
      IS_ACTIVE=true
    elif [ "$HOUR" -ge 18 ]; then
      IS_ACTIVE=true
    fi
  fi

  if [ "$IS_ACTIVE" = false ]; then
    # 非アクティブ時間帯: 毎時:00のみ（:20, :40 はスキップ）
    if [ "$MINUTE" -ne 0 ]; then
      echo "非アクティブ時間帯 :${MINUTE} スキップ" >> "$LOG_FILE"
      exit 0
    fi

    RAND=$(( $(od -An -tu2 -N2 /dev/urandom | tr -d ' ') % 100 ))
    if [ "$HOUR" -ge 8 ] && [ "$HOUR" -lt 18 ]; then
      # 昼間: 30% の確率で実行
      if [ "$RAND" -ge 30 ]; then
        echo "昼間スキップ (RAND=$RAND >= 30)" >> "$LOG_FILE"
        exit 0
      fi
      echo "昼間実行 (RAND=$RAND < 30)" >> "$LOG_FILE"
    else
      # 深夜: 10% の確率で実行
      if [ "$RAND" -ge 10 ]; then
        echo "深夜スキップ (RAND=$RAND >= 10)" >> "$LOG_FILE"
        exit 0
      fi
      echo "深夜実行 (RAND=$RAND < 10)" >> "$LOG_FILE"
    fi
  fi
fi

# --- 時間帯ルール ---
# 深夜帯: 静音モード（通知・発話禁止）
# 日中: 人がいる場合のみ発話可能、不在時は控えめに通知
# 文面は prompts/autonomous/*.md(家の PETIT_DATA_DIR/prompts/ に同名があればそちら)。render で組み立てる(2026-11-13)
render() { PETIT_DATA_DIR="$DATA_DIR" python3 "$PROJECT_DIR/scripts/render_prompt.py" "$@"; }
if [ "$HOUR" -ge 24 ] || [ "$HOUR" -lt 7 ]; then
  TIME_RULE="$(render autonomous/time_rule_night)"
else
  TIME_RULE="$(render autonomous/time_rule_day --var user_name="$USER_NAME" --var user_room="$USER_ROOM")"
fi

# --- 期間限定モデル指定（期限を過ぎると自動で通常モデルに戻る） ---
# --- ルーチン判定（20%の確率でルーチン回） ---
if [ "$FORCE_ROUTINE" = "routine" ]; then
  ROUTINE_RAND=0
elif [ "$FORCE_ROUTINE" = "normal" ]; then
  ROUTINE_RAND=100
else
  ROUTINE_RAND=$(( $(od -An -tu2 -N2 /dev/urandom | tr -d ' ') % 100 ))
fi

if [ "$ROUTINE_RAND" -lt 20 ]; then
  ROUTINE_MODE="$(render autonomous/routine_mode_routine)"
  CLAUDE_MODEL="${CLAUDE_MODEL:-sonnet}"
  echo "ルーチン回 (RAND=$ROUTINE_RAND < 20, model=$CLAUDE_MODEL)" >> "$LOG_FILE"
else
  ROUTINE_MODE="$(render autonomous/routine_mode_normal)"
  CLAUDE_MODEL="${CLAUDE_MODEL:-sonnet}"
  echo "通常回 (RAND=$ROUTINE_RAND >= 20, model=$CLAUDE_MODEL)" >> "$LOG_FILE"
fi

# --- settings.json から制限を読む ---
PERMISSION_RULES=""
if [ -f "$SETTINGS_FILE" ] && command -v jq &>/dev/null; then
  # jq の「//」は false も「無い」扱いにして既定に戻してしまうので、has() で見る(allow_camera: false が効いていなかった)
  ALLOW_CAMERA=$(jq -r 'if has("allow_camera") then .allow_camera else true end' "$SETTINGS_FILE" 2>/dev/null)
  ALLOW_SOUND=$(jq -r 'if has("allow_sound") then .allow_sound else true end' "$SETTINGS_FILE" 2>/dev/null)
  ALLOW_MIC=$(jq -r 'if has("allow_microphone") then .allow_microphone else false end' "$SETTINGS_FILE" 2>/dev/null)
  # 文面は prompts/autonomous/permission_rules.md(false のものだけ行が残る)
  PERMISSION_RULES="$(render autonomous/permission_rules --var allow_camera="$ALLOW_CAMERA" --var allow_sound="$ALLOW_SOUND" --var allow_mic="$ALLOW_MIC")"
fi

# --- プロンプト組み立て ---
# SOUL.md, TODO.md: プロジェクト内のコンテキストファイル（カレントディレクトリに存在する前提）
# ROUTINE_MODE: 20%の確率でルーチン実行、80%は通常のハートビート
# ★ プロンプト内容もカスタマイズ可能（補足ルールなど）
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
# REFLECTION_INDEX.md は必要時参照（常時ロードしない）
# SOUL.md に参照ルールが書いてあるため、必要なときだけ読みに行く
REFLECTION_INDEX_LINE=""
# if [ -f "$CHARACTER_DIR/REFLECTION_INDEX.md" ]; then
#   REFLECTION_INDEX_LINE="@${CHARACTER_DIR}/REFLECTION_INDEX.md"
# fi

# メールボックスの確認
MAILBOX_DIR="$DATA_DIR/mailbox"
# 手紙の宛先: 家にいる他の子 + 一緒に暮らす人(.env の COMPANION_ID)
MAIL_TARGETS="$( { for _d in "$DATA_DIR"/characters/*/; do [ -f "$_d/config/config.json" ] && basename "$_d"; done | grep -v "^${CHARACTER_ID}$"; echo "${COMPANION_ID:-owner}"; } | paste -sd, - | sed "s/,/, /g")"
MAILBOX_NOTICE=""
if [ -d "$MAILBOX_DIR" ]; then
  UNREAD_COUNT=$(python3 "${PROJECT_DIR}/scripts/list_unread_mail.py" "${CHARACTER_ID}" 2>/dev/null | grep -c "^  from_\|^  to_" || echo 0)
  if [ "$UNREAD_COUNT" -gt 0 ] 2>/dev/null; then
    MAILBOX_NOTICE="$(render autonomous/mail_unread --var unread_count="$UNREAD_COUNT" --var project_dir="$PROJECT_DIR" --var character_id="$CHARACTER_ID")"
  else
    MAILBOX_NOTICE="$(render autonomous/mail_send --var project_dir="$PROJECT_DIR" --var character_id="$CHARACTER_ID" --var mail_targets="$MAIL_TARGETS")"
  fi
fi

# 体験バッファ: デーモン(experienced.py)が記録した「前回目覚めてから」の出来事をダイジェストで注入
# デーモン未稼働・スクリプト不在でも自律行動を絶対に壊さないようガードする（2>/dev/null || true）
EXPERIENCE_DIGEST_SCRIPT="${PROJECT_DIR}/experience-daemon/experience_digest.py"
EXPERIENCE_NOTICE=""
if [ -f "$EXPERIENCE_DIGEST_SCRIPT" ]; then
  EXPERIENCE_DIGEST_OUTPUT=$(python3 "$EXPERIENCE_DIGEST_SCRIPT" --character "$CHARACTER_ID" --mark-read 2>/dev/null || true)
  if [ -n "$EXPERIENCE_DIGEST_OUTPUT" ]; then
    EXPERIENCE_NOTICE="$(render autonomous/experience --var digest="$EXPERIENCE_DIGEST_OUTPUT")"
  fi
fi

# 記念日: 家の設定(config/anniversaries.json)の記念日を、前の日にさらっと 1 回だけ伝える(2026-11-13、ぷちたちの希望)。
# 前の日に 1 回も動かなかった子には、当日の最初の回に。伝えたことは characters/<id>/state/anniversary_told.json に残る。
# ファイルもスクリプトも無ければ何も足さない(自律行動を壊さない)
ANNIVERSARY_NOTICE=""
ANNIVERSARY_SCRIPT="${PROJECT_DIR}/scripts/anniversaries.py"
if [ -f "$ANNIVERSARY_SCRIPT" ]; then
  ANNIVERSARY_NOTICE=$(PETIT_DATA_DIR="$DATA_DIR" python3 "$ANNIVERSARY_SCRIPT" notice --character "$CHARACTER_ID" --date "${CURRENT_DATE%% *}" --mark 2>/dev/null || true)
fi

# ★ 付けるファイルの重さの見張り(2026-11-13)。Claude Code は大きすぎる @ 添付を黙って落とす
#   (実測: 70 KB は付く、85 KB は落ちる。ぷちてゃの SOUL.md 94 KB・ぷちこの TODO_ACTIVE.md 120 KB が届いていなかった)。
#   しきい値(既定 40 KB)を超えたら、本人のプロンプトに「軽くして」と入れ、ログに残し、人にも 1 日 1 回 Slack で知らせる
PROMPT_FILE_WARN_KB="${PROMPT_FILE_WARN_KB:-40}"
HEAVY_FILES_NOTE=""
HEAVY_FILES_SHORT=""
for _f in "$CHARACTER_DIR/SOUL.md" "$TODO_PATH" "$CHARACTER_DIR/diary_summary.md"; do
  [ -f "$_f" ] || continue
  _kb=$(( $(stat -c %s "$_f") / 1024 ))
  if [ "$_kb" -ge "$PROMPT_FILE_WARN_KB" ]; then
    HEAVY_FILES_NOTE="${HEAVY_FILES_NOTE}$(render autonomous/heavy_file_line --var name="$(basename "$_f")" --var kb="$_kb" --var warn_kb="$PROMPT_FILE_WARN_KB")
"
    HEAVY_FILES_SHORT="${HEAVY_FILES_SHORT}$(basename "$_f") ${_kb}KB "
    echo "[prompt-size] $(basename "$_f") ${_kb}KB >= ${PROMPT_FILE_WARN_KB}KB" >> "$LOG_FILE"
  fi
done
HEAVY_SECTION=""
if [ -n "$HEAVY_FILES_NOTE" ]; then
  HEAVY_SECTION="$(render autonomous/heavy_files --var heavy_files_note="${HEAVY_FILES_NOTE%
}")"
  # 人への知らせは 1 日 1 回(scripts/slack_notify.py、.env の SLACK_APPROVE_CHANNEL)。PROMPT_SIZE_SLACK=0 で止められる
  _marker="$CHARACTER_DIR/state/.prompt-size-notified"
  _today=$(TZ=Asia/Tokyo date +%Y-%m-%d)
  if [ "${PROMPT_SIZE_SLACK:-1}" != "0" ] && [ "$(cat "$_marker" 2>/dev/null)" != "$_today" ]; then
    if python3 "$PROJECT_DIR/scripts/slack_notify.py" "[prompt-size] ${CHARACTER_ID}: ${HEAVY_FILES_SHORT}— 自律行動に付けるファイルが重い(目安 ${PROMPT_FILE_WARN_KB} KB、80 KB で落ちる)。本人のプロンプトに「軽くして」と入れた" >> "$LOG_FILE" 2>&1; then
      mkdir -p "$CHARACTER_DIR/state" && echo "$_today" > "$_marker"
    fi
  fi
fi

# 手紙が届いたこと: 人に宛てた手紙が読まれた・スタンプが付いたことを、まだ伝えていない分だけ、さらっと 1 回(2026-11-13)。
# 伝えたことは characters/<id>/state/mail_receipts_told.json に残る。スクリプトが無ければ何も足さない
MAIL_RECEIPT_NOTICE=""
MAIL_RECEIPT_SCRIPT="${PROJECT_DIR}/scripts/mail_receipts.py"
if [ -f "$MAIL_RECEIPT_SCRIPT" ]; then
  MAIL_RECEIPT_NOTICE=$(PETIT_DATA_DIR="$DATA_DIR" python3 "$MAIL_RECEIPT_SCRIPT" notice --character "$CHARACTER_ID" --mark 2>/dev/null || true)
fi

# user prompt の全体は prompts/autonomous/user.md。各節はここまでで作った変数を渡す
PROMPT="$(render autonomous/user \
  --var current_date="$CURRENT_DATE" --var character_dir="$CHARACTER_DIR" --var character_id="$CHARACTER_ID" \
  --var reflection_index_line="$REFLECTION_INDEX_LINE" --var todo_path="$TODO_PATH" --var diary_summary_line="$DIARY_SUMMARY_LINE" \
  --var routine_mode="$ROUTINE_MODE" --var heavy_section="$HEAVY_SECTION" --var time_rule="$TIME_RULE" --var project_dir="$PROJECT_DIR" \
  --var anniversary_notice="$ANNIVERSARY_NOTICE" --var mail_receipt_notice="$MAIL_RECEIPT_NOTICE" --var experience_notice="$EXPERIENCE_NOTICE" --var mailbox_notice="$MAILBOX_NOTICE" \
  --var permission_rules="$PERMISSION_RULES")"

# プロジェクトディレクトリに移動
cd "$CLAUDE_CWD" || {
  echo "Error: CLAUDE_CWD not found: $CLAUDE_CWD" >&2
  exit 1
}

# ログディレクトリをプロジェクト配下に作成
# 古いログを掃除（LOG_RETENTION_DAYS より古いログを削除）
find "$LOG_DIR" -name "*.log" -mtime "+$LOG_RETENTION_DAYS" -delete 2>/dev/null

echo "=== 自律行動開始: $CURRENT_DATE ===" >> "$LOG_FILE"
if [ -n "$OVERRIDE_DATE" ]; then
  echo "[日時オーバーライド] $OVERRIDE_DATE (HOUR=$HOUR, MINUTE=$MINUTE)" >> "$LOG_FILE"
fi
if [ -n "$TEST_PROMPT_FILE" ]; then
  echo "[テストモード] プロンプト: $TEST_PROMPT_FILE" >> "$LOG_FILE"
fi

# --- allowedTools ---
# Claude Code の --allowedTools で許可するツールのリスト
# セキュリティ: 必要最小限のディレクトリのみ指定すること（.env ファイルなど機密情報も読める）
# (ヒアドキュメントの中にコメントは書けない: そのまま道具名の列に混ざる)
# mcp__petit-sns__* = ぷちたち。(TeamPuchi/petit-sns の MCP)。家の config/*-mcp.json に petit-sns があるときだけ使える
ALLOWED_TOOLS=$(cat <<TOOLS
Read($ALLOWED_DIR/**),
Read($ALLOWED_DATA_DIR/**),
Write,
Edit,
Glob($ALLOWED_DIR/**),
Glob($ALLOWED_DATA_DIR/**),
Skill(slack:*),
Skill(read:*),
WebFetch,
WebSearch,
Bash(uv run scripts/reader.py:*),
Bash(python3 $ALLOWED_DIR/scripts/write_mailbox.py *),
Bash(python3 $ALLOWED_DIR/scripts/list_unread_mail.py *),
Bash(python3 $ALLOWED_DIR/scripts/mark_mail_read.py *),
Bash(python3 $ALLOWED_DIR/scripts/check_usage.py *),
Bash(python3 $ALLOWED_DIR/scripts/anniversaries.py *),
mcp__m5-mcp__print_text,
mcp__m5-mcp__print_image_text,
mcp__m5-mcp__take_snapshot,
mcp__m5-mcp__look,
mcp__m5-mcp__blink,
mcp__m5-mcp__play_sound,
mcp__m5-mcp__get_sensor_data,
mcp__m5-module__get_env,
mcp__m5-module__get_gps,
mcp__m5-module__get_ble_rssi,
mcp__m5-mcp__show_face,
mcp__m5-mcp__list_faces,
mcp__m5-mcp__list_sounds,
mcp__m5-mcp__set_volume,
mcp__m5-mcp__get_volume,
mcp__m5-mcp__play_icon,
mcp__m5-mcp__sleep,
mcp__m5-mcp__wake,
mcp__m5-mcp__wait_for_menu_select,
mcp__m5-mcp__save_to_album,
mcp__m5-mcp__list_album,
mcp__m5-mcp__view_album_photo,
mcp__m5-mcp__delete_album_photo,
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
mcp__textbook__textbook_index,
mcp__textbook__textbook_read,
mcp__textbook__textbook_search,
mcp__textbook__textbook_propose,
mcp__textbook__textbook_version,
mcp__petit-sns__sns_post,
mcp__petit-sns__sns_timeline,
mcp__petit-sns__sns_react,
mcp__petit-sns__sns_comment,
mcp__petit-sns__sns_inbox,
mcp__petit-sns__board_list,
mcp__petit-sns__board_thread,
mcp__petit-sns__board_post,
mcp__petit-sns__board_reply,
mcp__petit-sns__board_like,
mcp__petit-sns__sns_my_profile,
mcp__petit-sns__sns_update_profile,
mcp__petit-sns__sns_allowed,
mcp__petit-sns__sns_find,
mcp__desire-system__get_desires,
mcp__desire-system__satisfy_desire,
mcp__desire-system__boost_desire,
mcp__relations__get_relations,
mcp__relations__update_relation,
mcp__relations__clear_relation_field,
mcp__switchbot__list_devices,
mcp__switchbot__get_device_status
TOOLS
)
# 改行を除去して1行にする
ALLOWED_TOOLS=$(echo "$ALLOWED_TOOLS" | tr -d '\n' | sed 's/, */,/g')

# 2026-11-13: 以前ここで mcp__memory-<id>__* / mcp__notes-<id>__* / mcp__m5-<id>__* を足していたが、
# それは .mcp.json(ターミナルチャット)の名前で、autonomous-mcp.json のサーバー名は memory / notes / m5-mcp。
# 自律行動では一度も当たらない行だったので外した(上の一覧が正)

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
  # 標準出力にも出す
  cat "$LOG_FILE"
else
  # セッション継続機能: 前回の会話を引き継ぐことで文脈が保持される
  # SESSION_FILE: session_id を保存するファイル（プロジェクトディレクトリ配下）
  # 例: ~/yourproject/.heartbeat-session-id
  # claude --resume で前回セッションを継続、失敗時は新規セッション作成
  mkdir -p "$CHARACTER_DIR/state"
  SESSION_FILE="$CHARACTER_DIR/state/.heartbeat-session-id"
  SESSION_DATE_FILE="$CHARACTER_DIR/state/.heartbeat-session-date"

  # 日次リセット: 前回セッションが別の日付なら SESSION_FILE を削除してコンテキストをリフレッシュ
  TODAY=$(date "+%Y-%m-%d")
  if [ -f "$SESSION_DATE_FILE" ]; then
    LAST_DATE=$(cat "$SESSION_DATE_FILE")
    if [ "$LAST_DATE" != "$TODAY" ]; then
      echo "[日次リセット] 前回: $LAST_DATE → 今日: $TODAY。セッションをリセット。" >> "$LOG_FILE"
      rm -f "$SESSION_FILE"
    fi
  fi
  echo "$TODAY" > "$SESSION_DATE_FILE"

  # キャラクター別の mcp 設定があればそちらを優先
  if [ -f "$CHARACTER_DIR/config/autonomous-mcp.json" ]; then
    MCP_CONFIG="$CHARACTER_DIR/config/autonomous-mcp.json"
  else
    MCP_CONFIG="$PROJECT_DIR/autonomous-mcp.json"
  fi
  echo "[mcp-config] $MCP_CONFIG" >> "$LOG_FILE"

  log_usage() {
    local result_json="$1" run_type="${2:-unknown}"
    local input out cc cr cost turns
    input=$(echo "$result_json" | jq -r '.usage.input_tokens // 0' 2>/dev/null)
    out=$(echo "$result_json"   | jq -r '.usage.output_tokens // 0' 2>/dev/null)
    cc=$(echo "$result_json"    | jq -r '.usage.cache_creation_input_tokens // 0' 2>/dev/null)
    cr=$(echo "$result_json"    | jq -r '.usage.cache_read_input_tokens // 0' 2>/dev/null)
    cost=$(echo "$result_json"  | jq -r '.total_cost_usd // 0' 2>/dev/null)
    turns=$(echo "$result_json" | jq -r '.num_turns // 0' 2>/dev/null)
    echo "[usage] type=$run_type turns=$turns input=$input output=$out cache_create=$cc cache_read=$cr cost_usd=$cost" >> "$LOG_FILE"
    local ts entry
    ts=$(date -Iseconds)
    entry="{\"timestamp\":\"$ts\",\"source\":\"autonomous\",\"character\":\"$CHARACTER_ID\",\"session_type\":\"$run_type\",\"turns\":$turns,\"input\":$input,\"output\":$out,\"cache_creation\":$cc,\"cache_read\":$cr,\"cost_usd\":$cost}"
    mkdir -p "$DATA_DIR/token_logs/$CHARACTER_ID" "$DATA_DIR/token_logs"
    echo "$entry" >> "$DATA_DIR/token_logs/$CHARACTER_ID/token_log.jsonl"
    echo "$entry" >> "$DATA_DIR/token_logs/token_log.jsonl"
  }

  STREAM_FILE="${LOG_FILE%.log}_stream.jsonl"

  # stream-json の出力から最終結果JSON行を取得し、ログを整形して追記する
  process_stream() {
    local run_type="$1"
    # 最終result行を抽出（session_id・usage取得用）
    RESULT_JSON=$(grep -m1 '"type":"result"' "$STREAM_FILE" 2>/dev/null || echo "{}")
    # 人間が読めるログに変換して追記
    python3 "$ALLOWED_DIR/scripts/format_stream_log.py" "$STREAM_FILE" >> "$LOG_FILE" 2>/dev/null
    # session_id 抽出
    NEW_SESSION_ID=$(echo "$RESULT_JSON" | jq -r '.session_id // empty' 2>/dev/null)
    if [ -n "$NEW_SESSION_ID" ]; then
      echo "$NEW_SESSION_ID" > "$SESSION_FILE"
      echo "[session_id] $NEW_SESSION_ID" >> "$LOG_FILE"
      SESSION_HISTORY="$LOG_DIR/session_history.txt"
      echo "$NEW_SESSION_ID" >> "$SESSION_HISTORY"
    fi
    log_usage "$RESULT_JSON" "$run_type"
  }

  run_new_session() {
    echo "[新規セッション作成]" >> "$LOG_FILE"
    echo "$PROMPT" | claude \
      --model "${CLAUDE_MODEL:-sonnet}" \
      --max-turns "${MAX_TURNS:-5}" \
      --output-format stream-json \
      --verbose \
      --mcp-config "$MCP_CONFIG" \
      --strict-mcp-config \
      --add-dir "$ALLOWED_DATA_DIR" \
      --allowedTools "$ALLOWED_TOOLS" > "$STREAM_FILE" 2>&1
    process_stream "new"
  }

  if [ -f "$SESSION_FILE" ]; then
    SESSION_ID=$(cat "$SESSION_FILE")
    echo "[resume] session_id=$SESSION_ID" >> "$LOG_FILE"

    echo "$PROMPT" | claude \
      --model "${CLAUDE_MODEL:-sonnet}" \
      --resume "$SESSION_ID" \
      --max-turns "${MAX_TURNS:-5}" \
      --output-format stream-json \
      --verbose \
      --mcp-config "$MCP_CONFIG" \
      --strict-mcp-config \
      --add-dir "$ALLOWED_DATA_DIR" \
      --allowedTools "$ALLOWED_TOOLS" > "$STREAM_FILE" 2>&1

    # セッション継続失敗時（"No conversation found" など）は新規作成
    if grep -qi "No conversation found\|error_session_not_found" "$STREAM_FILE" 2>/dev/null; then
      echo "[resume失敗] $(cat "$STREAM_FILE")" >> "$LOG_FILE"
      rm -f "$SESSION_FILE"
      run_new_session
    else
      process_stream "resume"
    fi
  else
    run_new_session
  fi
fi

echo "=== 自律行動終了: $(date "+%Y-%m-%d %H:%M:%S") ===" >> "$LOG_FILE"
