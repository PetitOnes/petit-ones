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

# キャラデータ・メールボックス・チャット履歴・ノート・トークンログなど全体
[ -d "$SRC/petit_claude" ] && {
    rsync -a --delete "$SRC/petit_claude/" "$HOME/petit_claude/"
    echo "  petit_claude/: restored"
}

# Claude Code プロジェクト設定・コマンド・メモリ
[ -d "$SRC/embodied-claude_.claude" ] && {
    rsync -a --delete "$SRC/embodied-claude_.claude/" "$HOME/work/embodied-claude/.claude/"
    echo "  embodied-claude/.claude/: restored"
}
[ -d "$SRC/home_.claude" ] && {
    rsync -a --delete "$SRC/home_.claude/" "$HOME/.claude/"
    echo "  ~/.claude/: restored"
}

# garmin 系（あれば）
[ -d "$SRC/garmin-ble-mcp_.claude" ] && {
    mkdir -p "$HOME/work/garmin-ble-mcp"
    rsync -a --delete "$SRC/garmin-ble-mcp_.claude/" "$HOME/work/garmin-ble-mcp/.claude/"
}
[ -d "$SRC/garmin-ble-android-mcp_.claude" ] && {
    mkdir -p "$HOME/work/garmin-ble-android-mcp"
    rsync -a --delete "$SRC/garmin-ble-android-mcp_.claude/" "$HOME/work/garmin-ble-android-mcp/.claude/"
}

# .env ファイル
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

# autonomous-action.sh（gitignore対象）
if [ -f "$SRC/autonomous-action.sh" ]; then
    cp "$SRC/autonomous-action.sh" "$HOME/work/embodied-claude/autonomous-action.sh"
    chmod +x "$HOME/work/embodied-claude/autonomous-action.sh"
    echo "  autonomous-action.sh: restored"
fi

# crontab
if [ -f "$SRC/crontab_backup.txt" ]; then
    crontab "$SRC/crontab_backup.txt"
    echo "  crontab: restored"
fi

# dotfiles
if [ -d "$SRC/dotfiles" ]; then
    for f in .tmux.conf .bashrc .profile .zshrc; do
        [ -f "$SRC/dotfiles/$f" ] && cp "$SRC/dotfiles/$f" "$HOME/$f" && echo "  dotfile: $f"
    done
fi

# systemd ユーザーサービス
if [ -d "$SRC/systemd" ] && [ "$(ls -A "$SRC/systemd" 2>/dev/null)" ]; then
    mkdir -p "$HOME/.config/systemd/user"
    cp "$SRC/systemd/"* "$HOME/.config/systemd/user/"
    systemctl --user daemon-reload
    echo "  systemd: restored"
    echo "  ↳ 必要に応じて: systemctl --user enable <service> && systemctl --user start <service>"
fi

echo ""
echo "[restore] done"
echo ""
echo "次のステップ:"
echo "  1. ダッシュボードを起動: cd ~/work/embodied-claude/dashboard && uv run python main.py &"
echo "  2. ttyd サービスを起動: systemctl --user start ttyd-claude"
echo "  3. 新しいシェルを開いてパスを反映させる"
