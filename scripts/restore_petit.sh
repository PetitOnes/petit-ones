#!/usr/bin/env bash
# petit_claude リストアスクリプト
# 使い方: bash restore_petit.sh <バックアップディレクトリ>

set -euo pipefail

SRC="${1:?使い方: restore_petit.sh <バックアップディレクトリ>}"

if [ ! -d "$SRC" ]; then
    echo "エラー: $SRC が見つかりません"
    exit 1
fi

echo "[restore] ← $SRC"
echo "警告: 現在のデータを上書きします。続けますか？ [y/N]"
read -r ans
[ "$ans" = "y" ] || { echo "中止"; exit 0; }

[ -d "$SRC/petit_claude" ]                    && rsync -a --delete "$SRC/petit_claude/"                    "$HOME/petit_claude/"
[ -d "$SRC/embodied-claude_.claude" ]         && rsync -a --delete "$SRC/embodied-claude_.claude/"         "$HOME/work/embodied-claude/.claude/"
[ -d "$SRC/home_.claude" ]                    && rsync -a --delete "$SRC/home_.claude/"                    "$HOME/.claude/"
[ -d "$SRC/garmin-ble-mcp_.claude" ]          && { mkdir -p "$HOME/work/garmin-ble-mcp"; rsync -a --delete "$SRC/garmin-ble-mcp_.claude/"          "$HOME/work/garmin-ble-mcp/.claude/"; }
[ -d "$SRC/garmin-ble-android-mcp_.claude" ]  && { mkdir -p "$HOME/work/garmin-ble-android-mcp"; rsync -a --delete "$SRC/garmin-ble-android-mcp_.claude/"  "$HOME/work/garmin-ble-android-mcp/.claude/"; }

for src_dest in \
    "petit_claude.env:$HOME/petit_claude/.env" \
    "desire-system.env:$HOME/work/embodied-claude/desire-system/.env" \
    "garmin-health-mcp.env:$HOME/work/garmin-health-mcp/.env"
do
    src="$SRC/dotenv/${src_dest%%:*}"
    dst="${src_dest##*:}"
    if [ -f "$src" ]; then
        mkdir -p "$(dirname "$dst")"
        cp "$src" "$dst"
        echo "  .env: $(basename "$src")"
    fi
done

if [ -f "$SRC/crontab_backup.txt" ]; then
    crontab "$SRC/crontab_backup.txt"
    echo "  crontab: restored"
fi

if [ -d "$SRC/systemd" ] && [ "$(ls -A "$SRC/systemd" 2>/dev/null)" ]; then
    mkdir -p "$HOME/.config/systemd/user"
    cp "$SRC/systemd/"* "$HOME/.config/systemd/user/"
    systemctl --user daemon-reload
    echo "  systemd: restored"
fi

echo "[restore] done"
