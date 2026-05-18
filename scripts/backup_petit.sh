#!/usr/bin/env bash
# petit_claude バックアップスクリプト
# 使い方: bash backup_petit.sh [保存先ディレクトリ]
# 保存先省略時: ~/work/petit_backup_YYYYMMDD

set -euo pipefail

DEST="${1:-$HOME/work/petit_backup_$(date +%Y%m%d)}"
mkdir -p "$DEST"

echo "[backup] → $DEST"

rsync -a --delete "$HOME/petit_claude/"                              "$DEST/petit_claude/"
rsync -a --delete "$HOME/work/embodied-claude/.claude/"              "$DEST/embodied-claude_.claude/"
rsync -a --delete "$HOME/.claude/"                                   "$DEST/home_.claude/"
[ -d "$HOME/work/garmin-ble-mcp/.claude" ]         && rsync -a --delete "$HOME/work/garmin-ble-mcp/.claude/"         "$DEST/garmin-ble-mcp_.claude/"
[ -d "$HOME/work/garmin-ble-android-mcp/.claude" ] && rsync -a --delete "$HOME/work/garmin-ble-android-mcp/.claude/" "$DEST/garmin-ble-android-mcp_.claude/"

mkdir -p "$DEST/dotenv"
for src_dest in \
    "$HOME/petit_claude/.env:petit_claude.env" \
    "$HOME/work/embodied-claude/desire-system/.env:desire-system.env" \
    "$HOME/work/garmin-health-mcp/.env:garmin-health-mcp.env"
do
    src="${src_dest%%:*}"
    dst="${src_dest##*:}"
    if [ -f "$src" ]; then
        cp "$src" "$DEST/dotenv/$dst"
        echo "  .env: $dst"
    fi
done

crontab -l > "$DEST/crontab_backup.txt"
echo "  crontab: saved"

mkdir -p "$DEST/systemd"
find "$HOME/.config/systemd" \( -name "*.service" -o -name "*.timer" \) \
    ! -path "*/snap*" \
    -exec cp {} "$DEST/systemd/" \; 2>/dev/null || true

echo "[backup] done — $(du -sh "$DEST" | cut -f1)"
