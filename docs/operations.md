# 運用（バックアップ・crontab）

[README](../README.md) に戻る

## バックアップ・復元

```bash
# バックアップ（保存先省略時: ~/work/petit_backup_YYYYMMDD）
bash scripts/backup_petit.sh

# 保存先を指定する場合
bash scripts/backup_petit.sh /path/to/dest

# 復元
bash scripts/restore_petit.sh /path/to/petit_backup_YYYYMMDD
```

バックアップ対象:
- `~/petit_claude/` — キャラデータ・チャット履歴・ノート・トークンログなど全体
- `~/.claude/` — Claude Code の会話ログ・メモリDB・プロジェクト設定
- `~/work/petit-ones/.claude/` — スラッシュコマンド・プロジェクト設定
- `autonomous-action.sh` — gitignore 対象の個人設定スクリプト
- `.env` ファイル各種
- crontab
- dotfiles (`.tmux.conf`, `.bashrc` 等)
- systemd ユーザーサービス

## crontab

`setup_house.py` が家の共通分を、`create_character.py` がキャラ別の分を足す。手で確かめるときの形:

```bash
# --- キャラ別(create_character.py が足す。自律行動は子ごとに 5 分ずらす) ---
*/5 * * * * cd /path/to/petit-ones/src/m5-petit-desire && mkdir -p ~/petit_claude/.autonomous-logs/<char_id> && PETIT_DATA_DIR=~/petit_claude uv run python desire_updater.py <char_id> >> ~/petit_claude/.autonomous-logs/<char_id>/desire-$(date +\%Y\%m\%d).log 2>&1
0,30 * * * * /path/to/petit-ones/autonomous-action.sh <char_id>      # 次の子は 5,35、その次は 10,40
@reboot /path/to/petit-ones/experience-daemon/start_experienced.sh <char_id>
*/5 * * * * /path/to/petit-ones/experience-daemon/start_experienced.sh <char_id>

# --- 共通(setup_house.py が足す) ---
5 4 * * * PETIT_DATA_DIR=~/petit_claude /path/to/petit-ones/scripts/memory_sleep_all.sh >> ~/petit_claude/.autonomous-logs/memory-sleep.log 2>&1   # 記憶の整理
30 4 * * * cd ~/petit_claude/textbook && git pull -q --ff-only >/dev/null 2>&1   # ぷちの教科書(petit-textbook)を毎朝取り直す
50 23 * * * cd /path/to/petit-ones/dashboard && PETIT_DATA_DIR=~/petit_claude uv run python generate_diary.py >> ~/petit_claude/.autonomous-logs/diary.log 2>&1   # 日記

# --- 任意 ---
0 4 * * * bash ~/petit_claude/backup/save.sh   # バックアップ(scripts/backup_petit.sh)
```
