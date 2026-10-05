#!/usr/bin/env bash
# petit-ones のセットアップ。何度実行してもよい。
#   1. 部品リポを src/ に並べる(vcs import)
#   2. 各部品の Python 環境を作る(uv sync)
#   3. データのひな型を ~/petit_data に置く(すでにあれば触らない)
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_DIR="${PETIT_DATA_DIR:-$HOME/petit_data}"

command -v vcs >/dev/null || { echo "vcs が要ります: pip install vcstool (または apt install python3-vcstool)" >&2; exit 1; }
command -v uv  >/dev/null || { echo "uv が要ります: https://docs.astral.sh/uv/" >&2; exit 1; }

mkdir -p "$ROOT/src"
vcs import "$ROOT/src" < "$ROOT/petit.repos"

for d in "$ROOT"/src/*/; do
  [ -f "$d/pyproject.toml" ] || continue
  echo "uv sync: $(basename "$d")"
  (cd "$d" && uv sync) || echo "警告: $(basename "$d") の uv sync に失敗(あとで確認)" >&2
done

if [ -d "$DATA_DIR" ]; then
  echo "データは $DATA_DIR にあります(触りません)"
else
  cp -r "$ROOT/template/petit_data" "$DATA_DIR"
  echo "データのひな型を $DATA_DIR に置きました。characters/sample を自分のぷちの id に改名してください"
fi

cat <<MSG

できました。つぎは:
  - config/env.example を見て、PETIT_DATA_DIR=$DATA_DIR を設定
  - config/autonomous-mcp.json.example を $DATA_DIR/characters/<id>/config/autonomous-mcp.json へ(パスと id を書き換え)
  - config/cron.example を見て crontab に登録
MSG
