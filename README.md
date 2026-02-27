# Cube Petit Claude

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

[embodied-claude](https://github.com/kmizu/embodied-claude) のフォーク。M5Stack に身体を持つ小さなプチたちが、それぞれの性格・欲求・記憶で自律的に生きるシステム。

## 概要

M5Stack + Claude Code + 記憶システムの組み合わせで、目（カメラ）・感情（顔表示）・感覚（センサー）・記憶（SQLite）・欲求（desire-system）を持つキャラクターを作れる。

```
[M5Stack] ←HTTP/WS→ [m5-mcp] ←stdio→ [Claude Code]
                                              ↕
                     [memory-mcp] ←→ [SQLite (記憶DB)]
                     [desire-system] ←→ [desires.json]
                     [relations-mcp] ←→ [relations.json]
```

## ディレクトリ構造

```
embodied-claude/              ← コード（git管理、public）
├── m5-mcp/                   # M5Stack 制御 MCP
├── memory-mcp/               # 長期記憶 MCP
├── desire-system/            # 欲求システム MCP + updater
├── relations-mcp/            # 関係性 MCP
├── dashboard/                # Web UI
├── system-temperature-mcp/   # 体温感覚 MCP
├── autonomous-action.sh      # 自律行動スクリプト（.gitignore）
└── create_character.py       # キャラ追加スクリプト

~/petit_claude/               ← データ（PETIT_DATA_DIR、private）
├── characters/
│   ├── puchiko/              # config.json, SOUL.md, settings.json, ...
│   └── puchiteya/
├── .autonomous-logs/         # 行動ログ
├── SOUL.md, TODO.md, ROUTINES.md
├── settings.json, group_chat.json
└── backup/                   # バックアップスクリプト + データ
```

コードとデータは分離されている。環境変数 `PETIT_DATA_DIR` でデータディレクトリを変更可能（デフォルト: `~/petit_claude`）。

## セットアップ

### 1. 前提ソフト

```bash
# uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Claude Code
npm install -g @anthropic-ai/claude-code

# その他
sudo apt install -y jq sqlite3
```

### 2. コード取得

```bash
git clone https://github.com/fruitriin/embodied-claude.git
cd embodied-claude
```

### 3. 依存関係インストール

```bash
for dir in m5-mcp memory-mcp desire-system dashboard relations-mcp system-temperature-mcp; do
  echo "--- $dir ---"
  (cd "$dir" && uv sync)
done
```

### 4. キャラクター追加

```bash
uv run python create_character.py <id> <名前> <カラー> <M5のIP>

# 例:
uv run python create_character.py puchiko ぷちこ "#cab8d9" 10.42.138.100
```

自動で以下が作られる:
- `~/petit_claude/characters/{id}/` に設定ファイル一式
- crontab に欲求更新（5分毎）と自律行動（20分毎）

追加後に `characters/{id}/SOUL.md` を編集して性格を書く。

### 5. 自律行動スクリプト

```bash
cp autonomous-action.sample.sh autonomous-action.sh
vim autonomous-action.sh  # HOME, PATH, PROJECT_DIR を編集
chmod +x autonomous-action.sh
```

### 6. 環境変数

```bash
cd desire-system
cp .env.example .env
# .env に COMPANION_NAME 等を設定
```

### 7. ダッシュボード起動

```bash
cd dashboard
uv run python main.py
# → http://0.0.0.0:8765
```

## MCP サーバー

### m5-mcp（目・感情・センサー）

M5Stack のファームウェアセットアップは [m5_petit](https://github.com/AiriYokochi/m5_petit) を参照。IP は環境変数 `M5_HOST` で指定（`autonomous-mcp.json` から渡される）。

| ツール | 説明 |
|--------|------|
| `take_snapshot` | M5カメラで撮影 |
| `look` | 視線を動かす (x/y: -100〜100) |
| `blink` | ウィンクする |
| `show_face` | 顔画像を表示（SDカードのJPEG） |
| `play_sound` | 効果音を再生 |
| `play_icon` | アイコンを表示（love / cry） |
| `get_sensor_data` | 近接・照度・加速度・バッテリー取得 |
| `wait_for_touch` | タッチイベント待機 |
| `set_volume` / `get_volume` | 音量設定 |
| `sleep` / `wake` | スリープ制御 |

### memory-mcp（記憶）

| ツール | 説明 |
|--------|------|
| `remember` | 記憶を保存 |
| `recall` / `recall_divergent` | 文脈に基づく想起 |
| `search_memories` | セマンティック検索 |
| `save_visual_memory` | 画像付き記憶保存 |
| `create_episode` / `search_episodes` | エピソード管理 |
| `link_memories` / `get_causal_chain` | 因果リンク |
| `tom` | Theory of Mind |

### desire-system（欲求）

| ツール | 説明 |
|--------|------|
| `get_desires` | 現在の欲求レベル取得 |
| `satisfy_desire` | 欲求を満たす（行動後に呼ぶ） |
| `boost_desire` | 欲求を刺激する（驚き・発見時） |

欲求の種類と間隔は `characters/{id}/settings.json` でカスタマイズ可能。

### relations-mcp（関係性）

| ツール | 説明 |
|--------|------|
| `get_relations` | 自分と他キャラの関係性を取得 |
| `update_relation` | 関係性情報を更新 |

## ダッシュボード

- 欲求バー: 各プチの欲求レベルをリアルタイム表示
- チャット: プチに直接話しかける
- グループチャット（みんなで）: 全プチに同時送信
- 交流（ふたりで話させる）: プチ同士の会話
- 設定: アクティブタイム・カメラ/音/マイクの ON/OFF
- 記憶一覧: 日付別の記憶表示

## ダッシュボードの常時起動（systemd）

PC再起動後も自動でダッシュボードが起動するようにする。

```bash
# サービスファイルをコピー（User, WorkingDirectory, PATH を環境に合わせて編集）
sudo cp dashboard/petit-dashboard.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable petit-dashboard
sudo systemctl start petit-dashboard

# 状態確認
sudo systemctl status petit-dashboard

# ログ確認
journalctl -u petit-dashboard -f
```

## API利用量の管理

Claude API の使いすぎを防ぐ設定:

- **自律行動の頻度調整**: `autonomous-action.sh` のスケジュール制御で、アクティブ時間帯（毎回実行）と非アクティブ時間帯（確率実行）を制御。`characters/{id}/settings.json` の `active_hours` で時間帯を設定
- **自律行動の停止**: crontab の該当行をコメントアウト（`#` を先頭に付ける）すれば即停止
- **ダッシュボードの日記生成**: 手動ボタン or 1日1回（23:50）のみ。自動では頻繁に呼ばない
- **Anthropic Console**: https://console.anthropic.com/settings/usage で利用量を確認、spending limit を設定できる

```bash
# 一時的に全自律行動を止める
crontab -l | sed 's/^\(.*autonomous-action\)/#\1/' | crontab -

# 再開する
crontab -l | sed 's/^#\(.*autonomous-action\)/\1/' | crontab -
```

## バックアップ・復元

```bash
# バックアップ
bash ~/petit_claude/backup/save.sh

# 復元
bash ~/petit_claude/backup/restore.sh ~/petit_claude/backup/YYYYMMDD_HHMMSS
```

cron で毎日4時に自動バックアップ（7日分保持）。詳細は `~/petit_claude/backup/README.md` を参照。

## crontab

`create_character.py` がキャラ別のエントリを自動追加するが、手動で確認・編集する場合:

```bash
# --- キャラ別（キャラごとに2行ずつ） ---

# 欲求レベル更新（5分毎）
*/5  * * * * cd /path/to/embodied-claude/desire-system && uv run python desire_updater.py <char_id> >> ~/petit_claude/.autonomous-logs/<char_id>/desire-$(date +\%Y\%m\%d).log 2>&1

# 自律行動（20分毎）
*/20 * * * * /path/to/embodied-claude/autonomous-action.sh <char_id>

# --- 共通 ---

# 日記サマリー生成（毎日23:50、全キャラ分）
50 23 * * * cd /path/to/embodied-claude/dashboard && uv run python generate_diary.py >> ~/petit_claude/.autonomous-logs/diary.log 2>&1

# バックアップ（毎日4:00、7日分保持）
0 4 * * * bash ~/petit_claude/backup/save.sh && find ~/petit_claude/backup -maxdepth 1 -type d -name "[0-9]*" -mtime +7 -exec rm -rf {} \;
```

## ライセンス

MIT License

## 謝辞

- [kmizu](https://github.com/kmizu) - [embodied-claude](https://github.com/kmizu/embodied-claude) オリジナル作者
- [ROS版キューブプチ](https://github.com/sbgisen/cube_petit_ros) - 元となったロボットプロジェクト
