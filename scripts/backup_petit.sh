#!/usr/bin/env bash
# petit_claude バックアップスクリプト
# 使い方: bash backup_petit.sh [保存先ディレクトリ]
# 保存先省略時: ~/work/petit_backup_YYYYMMDD

set -euo pipefail

DEST="${1:-$HOME/work/petit_backup_$(date +%Y%m%d)}"
mkdir -p "$DEST"

echo "[backup] → $DEST"

# キャラデータ・メールボックス・チャット履歴・ノート・トークンログなど全体
rsync -a --delete "$HOME/petit_claude/"                              "$DEST/petit_claude/"
echo "  petit_claude/: done"

# Claude Code プロジェクト設定・コマンド・メモリ
rsync -a --delete "$HOME/work/embodied-claude/.claude/"              "$DEST/embodied-claude_.claude/"
rsync -a --delete "$HOME/.claude/"                                   "$DEST/home_.claude/"
echo "  .claude/: done"

# garmin 系（あれば）
[ -d "$HOME/work/garmin-ble-mcp/.claude" ]         && rsync -a --delete "$HOME/work/garmin-ble-mcp/.claude/"         "$DEST/garmin-ble-mcp_.claude/"
[ -d "$HOME/work/garmin-ble-android-mcp/.claude" ] && rsync -a --delete "$HOME/work/garmin-ble-android-mcp/.claude/" "$DEST/garmin-ble-android-mcp_.claude/"

# .env ファイル（gitignore対象）
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

# autonomous-action.sh（gitignore対象・個人設定が含まれる）
if [ -f "$HOME/work/embodied-claude/autonomous-action.sh" ]; then
    cp "$HOME/work/embodied-claude/autonomous-action.sh" "$DEST/autonomous-action.sh"
    echo "  autonomous-action.sh: saved"
fi

# crontab
crontab -l > "$DEST/crontab_backup.txt"
echo "  crontab: saved"

# dotfiles
mkdir -p "$DEST/dotfiles"
for f in .tmux.conf .bashrc .profile .zshrc; do
    [ -f "$HOME/$f" ] && cp "$HOME/$f" "$DEST/dotfiles/$f" && echo "  dotfile: $f"
done

# systemd ユーザーサービス
mkdir -p "$DEST/systemd"
find "$HOME/.config/systemd" \( -name "*.service" -o -name "*.timer" \) \
    ! -path "*/snap*" \
    -exec cp {} "$DEST/systemd/" \; 2>/dev/null || true
echo "  systemd: done"

echo "[backup] done — $(du -sh "$DEST" | cut -f1)"
