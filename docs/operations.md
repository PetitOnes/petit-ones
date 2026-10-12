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

## 家とコードを分けて、同期する

ぷちが動いている PC には、このリポジトリの checkout が **2 つ** ある。

| checkout | 役 | やること |
|---|---|---|
| 本番(例 `~/work/petit-ones`。cron とダッシュボードが見る所) | 動いている家 | **`git pull` だけ**。手で直さない。`git status` はいつも空 |
| 作業用(例 `~/work/petit-ones-dev`) | 直す所 | branch を切って直す → PR → マージ |

同期は一方向。**作業用 → GitHub main → 本番(pull)**。

- 家ごとの値はコードに書かない。`PETIT_DATA_DIR/.env`(`COMPANION_NAME`・`COMPANION_ID`・声のサーバー・鍵)と、任意の `PETIT_DATA_DIR/config/house.sh`(`USER_ROOM`、`CLAUDE_MODEL`、時間帯のルールの上書き)に置く。だから `autonomous-action.sh` は git のまま本番で動く
- 部品は `petit.repos` でコミットに固定してある。部品を上げるときは、部品のリポで PR → マージ → `petit.repos` の `version` を新しいコミットに書き換える PR → マージ → 本番で `vcs import src < petit.repos`(固定したコミットに動く)→ その部品で `uv sync`
- 本番で急いで直したことは、その日のうちに作業用で同じ変更を PR にする。本番の作業ツリーに差分を残さない
- 戻すとき: 本番で `git checkout <前のタグかコミット>`。部品は `petit.repos` を戻して `vcs import`

### 本番を止めない更新の順番

1. 作業用で PR を作り、CI が緑になるのを待つ
2. マージ
3. 本番で `git pull --ff-only`。`autonomous-action.sh` は次の cron から新しいものが動く(途中の回は止まらない)
4. 部品を上げた場合は `vcs import src < petit.repos` と `uv sync`。ダッシュボードを上げた場合は再起動(`/restart-dashboard`)
5. 次の自律行動のログ(`PETIT_DATA_DIR/.autonomous-logs/<id>/`)を一回分見る
