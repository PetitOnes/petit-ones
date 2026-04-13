#!/usr/bin/env bash
# 話者声紋登録スクリプト
# 使い方: ./scripts/register_speaker.sh [speaker_id] [character_id]
#
# speaker_id: 登録する話者 (省略時は speaker_config.json の my_speaker_id)
# character_id: どのM5のMICを使うか (puchiteya / puchiko / puchiru)
#
# 例: ./scripts/register_speaker.sh arisan puchiteya
#     ./scripts/register_speaker.sh  # speaker_config.json から読む

set -e

DATA_DIR="${PETIT_DATA_DIR:-$HOME/petit_claude}"
SPEAKER_CONFIG="$DATA_DIR/speaker_config.json"
AUTH_FILE="$DATA_DIR/auth.json"
DASHBOARD_URL="${DASHBOARD_URL:-http://localhost:8765}"

# speaker_config.json から読む（なければデフォルト）
if [ -f "$SPEAKER_CONFIG" ]; then
  DEFAULT_SPEAKER=$(jq -r '.my_speaker_id // "unknown"' "$SPEAKER_CONFIG")
  DEFAULT_USERNAME=$(jq -r '.my_username // "arisan"' "$SPEAKER_CONFIG")
else
  DEFAULT_SPEAKER="unknown"
  DEFAULT_USERNAME="arisan"
fi

SPEAKER_ID="${1:-$DEFAULT_SPEAKER}"
CHAR_ID="${2:-puchiteya}"

if [ "$SPEAKER_ID" = "unknown" ]; then
  echo "エラー: speaker_id が設定されていません。"
  echo "  $SPEAKER_CONFIG を作成するか、引数で指定してください。"
  echo "  例: ./scripts/register_speaker.sh arisan puchiteya"
  exit 1
fi

# トークン生成
TOKEN=$(python3 - <<PYEOF
import sys, json, hmac, hashlib, time, os
auth_file = os.path.expanduser("$AUTH_FILE")
auth = json.load(open(auth_file))
secret = auth["secret"]
username = "$DEFAULT_USERNAME"
# ユーザーのロール取得
role = auth.get("users", {}).get(username, {}).get("role", "admin")
expires = int(time.time()) + 86400
payload = f"{username}:{role}:{expires}"
sig = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
print(f"{payload}:{sig}")
PYEOF
)

if [ -z "$TOKEN" ]; then
  echo "エラー: トークンを生成できませんでした"
  exit 1
fi

echo "========================================="
echo "  話者声紋登録"
echo "========================================="
echo "  話者ID  : $SPEAKER_ID"
echo "  使用M5  : $CHAR_ID"
echo "========================================="
echo ""
echo "▶ 登録モードをセットしています..."

RESULT=$(curl -s -X POST "${DASHBOARD_URL}/api/${CHAR_ID}/register_speaker_next" \
  -H "Content-Type: application/json" \
  -H "Cookie: petit_session=$TOKEN" \
  -d "{\"speaker_id\": \"${SPEAKER_ID}\"}")

if echo "$RESULT" | grep -q '"ok":true'; then
  echo "✓ 準備完了！"
  echo ""
  echo "================================================================"
  echo "  ${CHAR_ID} の MICボタンを押して 10〜20秒 話してください。"
  echo "  （無音5秒で自動的に録音が終わり、登録が完了します）"
  echo ""
  echo "  精度を上げる場合は、このスクリプトをもう一度実行して"
  echo "  別の内容を話してください（3〜5回推奨）。"
  echo "================================================================"
else
  echo "エラー: $RESULT"
  exit 1
fi
