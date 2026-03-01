# Cube Petit Claude

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

[embodied-claude](https://github.com/kmizu/embodied-claude) のフォーク。M5Stack に身体を持つ小さなプチたちが、それぞれの性格・欲求・記憶で自律的に生きるシステム。

## フォーク元との違い

[kmizu/embodied-claude](https://github.com/kmizu/embodied-claude) は「Claude に身体を与える」MCP サーバー群。Wi-Fi PTZ カメラ・USB カメラ・TTS・長期記憶・温度センサーなどのモジュールで、単一の Claude インスタンスに感覚を提供する。

このフォークは、そのコンセプトを**マルチキャラクター自律エージェント**へ拡張したもの。

### 主な違い

| | フォーク元 (kmizu) | このフォーク (cube-petit) |
|---|---|---|
| **ハードウェア** | Wi-Fi PTZ カメラ (Tapo C210等) | M5Stack CoreS3 |
| **キャラクター** | 単一インスタンス | 複数キャラ（独立した性格・記憶・欲求） |
| **自律性** | ユーザー主導（リアクティブ） | cron で20分毎に自律行動（欲求ベース） |
| **欲求** | オプション | 中核機能（sensor_effects, cross_effects） |
| **UI** | CLI のみ | Web ダッシュボード（チャット・欲求表示・日記・記憶閲覧） |
| **社会性** | なし | キャラ同士の関係性・メールボックス |
| **携帯性** | 据え置き | M5Stack + モバイルバッテリーで外出可能 |

### 追加コンポーネント

| コンポーネント | 説明 |
|---|---|
| **m5-mcp** | M5Stack 制御（カメラ・顔・センサー・音・スリープ）。wifi-cam-mcp/usb-webcam-mcp に代わるもの |
| **desire-system** | 欲求システム。時間経過 + センサー + 相互作用の3段階で欲求レベルを計算 |
| **relations-mcp** | キャラ間の関係性（好き嫌い・親密度・メモ） |
| **notes-mcp** | 永続ノート（光の値メモ、センサー範囲表など） |
| **dashboard** | Web UI（チャット・グループチャット・欲求表示・記憶閲覧・日記・認証） |
| **create_character.py** | キャラクター追加スクリプト（設定ファイル + cron 自動登録） |
| **autonomous-action.sh** | 自律行動オーケストレーション（スケジュール・確率制御・セッション管理） |
| **scripts/** | メールボックス書き込み (`write_mailbox.py`)、メモリ読み出し (`reader.py`) |

### フォーク元から引き継いでいるもの

memory-mcp, tts-mcp, system-temperature-mcp, mobility-mcp, ip-webcam-mcp, mcp-pet, morning-call-mcp はフォーク元にも存在する。memory-mcp は視覚記憶・エピソード・因果リンク・Theory of Mind・記憶整理 (sleep) などが追加されている。

## 概要

M5Stack + Claude Code + 記憶システムの組み合わせで、目（カメラ）・感情（顔表示）・感覚（センサー）・記憶（SQLite）・欲求（desire-system）を持つキャラクターを作れる。

```
[M5Stack] ←HTTP/WS→ [m5-mcp] ←stdio→ [Claude Code]
                                             ↕
                    [memory-mcp] ←→ [SQLite (記憶DB)]
                    [desire-system] ←→ [desires.json]
                    [relations-mcp] ←→ [relations.json]
                    [notes-mcp] ←→ [notes/*.md]
```

## ディレクトリ構造

```
embodied-claude/              ← コード（git管理、public）
├── m5-mcp/                   # M5Stack 制御 MCP
├── memory-mcp/               # 長期記憶 MCP
├── desire-system/            # 欲求システム（MCP + updater）
├── relations-mcp/            # 関係性 MCP
├── notes-mcp/                # 永続ノート MCP
├── dashboard/                # Web ダッシュボード
├── tts-mcp/                  # 音声合成 MCP（ElevenLabs / VOICEVOX）
├── system-temperature-mcp/   # 体温感覚 MCP
├── scripts/                  # ユーティリティスクリプト
│   ├── write_mailbox.py      #   メールボックス書き込み
│   └── reader.py             #   メモリ読み出し
├── autonomous-action.sh      # 自律行動スクリプト（.gitignore）
├── autonomous-action.sample.sh # ↑のテンプレート
├── create_character.py       # キャラ追加スクリプト
│
│  # フォーク元由来（未使用 or 用途限定）
├── wifi-cam-mcp/             # Wi-Fi PTZ カメラ（Tapo 用）
├── usb-webcam-mcp/           # USB カメラ
├── ip-webcam-mcp/            # Android スマホカメラ
├── mobility-mcp/             # ロボット掃除機
├── mcp-pet/                  # PErsonal Terminal
└── morning-call-mcp/         # 目覚ましコール

~/petit_claude/               ← データ（PETIT_DATA_DIR、private）
├── characters/
│   ├── puchiko/
│   │   ├── config.json       # M5ホスト・キャラ名・カラー
│   │   ├── SOUL.md           # 性格設定
│   │   ├── settings.json     # アクティブ時間帯・機能ON/OFF
│   │   ├── desires.json      # 現在の欲求レベル（5分毎更新）
│   │   ├── desire_config.json # 欲求定義・sensor_effects・cross_effects
│   │   ├── relations.json    # 他キャラ/ユーザーへの感情
│   │   ├── autonomous-mcp.json # 自律行動用 MCP 設定
│   │   ├── chat_history.json # チャット履歴
│   │   └── notes/            # 永続ノート
│   └── puchiteya/
├── mailbox/                  # キャラ間メッセージ
├── .autonomous-logs/         # 自律行動ログ
├── SOUL.md, TODO.md, ROUTINES.md
├── settings.json, group_chat.json
├── auth.json                 # ダッシュボード認証（オプション）
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
for dir in m5-mcp memory-mcp desire-system dashboard relations-mcp notes-mcp system-temperature-mcp; do
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
| `get_sensor_data` | 近接・照度・加速度・ジャイロ・バッテリー取得 |
| `wait_for_touch` | タッチイベント待機 |
| `set_volume` / `get_volume` | 音量設定 |
| `sleep` / `wake` | スリープ制御 |

### memory-mcp（記憶）

| ツール | 説明 |
|--------|------|
| `remember` | 記憶を保存（emotion, importance, category 付き） |
| `recall` / `recall_divergent` | 文脈に基づく想起（発散的想起は連想展開付き） |
| `search_memories` | セマンティック検索 |
| `recall_with_associations` | 関連記憶も含めて想起 |
| `save_visual_memory` | 画像 + カメラ角度付き記憶保存 |
| `save_audio_memory` | 音声 + 書き起こし付き記憶保存 |
| `recall_by_camera_position` | カメラの向きで記憶を想起 |
| `create_episode` / `search_episodes` | エピソード管理 |
| `link_memories` / `get_causal_chain` | 因果リンク |
| `get_working_memory` / `refresh_working_memory` | 作業記憶 |
| `consolidate_memories` | 記憶の再生・統合 |
| `sleep` | 記憶整理（圧縮・減衰・忘却） |
| `tom` | Theory of Mind（相手の視点取得） |

### desire-system（欲求）

3段階パイプラインで欲求レベルを計算:

1. **時間ベース**: 記憶DB内のキーワード最終出現時刻からの経過時間
2. **センサー効果**: M5のセンサー値（ambient, gx, battery等）で加減算
3. **相互作用**: 欲求間の影響（例: 疲労が高いと好奇心が下がる）

| ツール | 説明 |
|--------|------|
| `get_desires` | 現在の欲求レベル取得 |
| `satisfy_desire` | 欲求を満たす（行動後に呼ぶ） |
| `boost_desire` | 欲求を刺激する（驚き・発見時） |

欲求の定義・キーワード・センサー効果は `characters/{id}/desire_config.json` でカスタマイズ可能。cron で5分毎に `desire_updater.py` がレベルを再計算し `desires.json` に書き出す。

### relations-mcp（関係性）

| ツール | 説明 |
|--------|------|
| `get_relations` | 自分と他キャラの関係性を取得 |
| `update_relation` | 関係性情報を更新（好き嫌い・親密度・メモ） |

### notes-mcp（ノート）

| ツール | 説明 |
|--------|------|
| `list_notes` | ノート一覧 |
| `read_note` | ノート読み取り |
| `write_note` | ノート作成・更新 |

記憶 (memory) と違い、検索・想起の対象にならない永続的な参照ドキュメント。光の値メモ、センサー範囲表などに使う。

## 自律行動

`autonomous-action.sh` が cron で20分毎に実行され、キャラクターが自律的に行動する。

### 実行フロー

```
[cron: 5分毎]
└→ desire_updater.py <char_id>
   ├ desire_config.json を読む
   ├ memory.db からキーワード検索（時間ベース計算）
   ├ M5の /sensors にHTTPリクエスト（センサー効果）
   ├ 相互作用を計算
   └→ desires.json に書き出す

[cron: 20分毎]
└→ autonomous-action.sh <char_id>
   ├ アクティブ時間帯か確認（非アクティブなら確率実行）
   ├ SOUL.md, ROUTINES.md, desires.json, relations.json を読む
   ├ M5センサーのスナップショットを取得
   ├ プロンプトを組み立て
   ├ claude -p <prompt> --allowedTools ... を実行
   │  ├ m5-mcp: take_snapshot, show_face, ...
   │  ├ memory-mcp: remember, recall, ...
   │  ├ desire-system: satisfy_desire, ...
   │  └ notes-mcp, relations-mcp, ...
   └→ .autonomous-logs/<char_id>/ にログ

[cron: 毎日23:50]
└→ generate_diary.py（全キャラの日記サマリー生成）
```

### スケジュール制御

- **アクティブ時間帯**（`settings.json` の `active_hours`）: 20分毎に毎回実行
- **昼間の非アクティブ**: 毎時:00 に30%の確率で実行
- **深夜の非アクティブ**: 毎時:00 に10%の確率で実行

## ダッシュボード

- 欲求バー: 各プチの欲求レベルをリアルタイム表示
- チャット: プチに直接話しかける
- グループチャット（みんなで）: 全プチに同時送信
- 交流（ふたりで話させる）: プチ同士の会話
- 設定: アクティブタイム・カメラ/音/マイクの ON/OFF
- 記憶一覧: 日付別の記憶表示
- 日記: 1日のサマリー（毎日23:50に自動生成）

## お散歩（外出モード）

M5Stack を外に連れ出して散歩できる。Android スマホのテザリング + Tailscale VPN で自宅PCからM5Stackに接続する。

### 必要なもの

- Android スマホ（テザリング + Tailscale）
- モバイルバッテリー（M5Stack 給電用）
- 自宅PC に Tailscale がインストール済み

### 構成

```
[M5Stack] ──WiFi──▶ [スマホ(テザリング)]
                           │
                     Tailscale VPN
                     (subnet router)
                           │
                    [自宅PC (Claude Code)]
                           │
                    [ダッシュボード]
                           │
                    [スマホのブラウザ] ◀── 操作
```

### セットアップ手順

#### 1. Tailscale をインストール

- Android: Google Play から [Tailscale](https://play.google.com/store/apps/details?id=com.tailscale.ipn) をインストール
- 自宅PC: `curl -fsSL https://tailscale.com/install.sh | sh`
- 両方とも同じアカウントでログイン

#### 2. Android でサブネットルーターを設定

スマホのテザリングで作られるローカルネットワーク（M5Stack が接続する）を、Tailscale 経由で自宅PCからアクセスできるようにする。

```
Android Tailscale アプリ → ⚙ 設定 → Subnet router
→ テザリングのサブネットを追加（例: 192.168.49.0/24）
```

テザリングのサブネットは機種によって異なる。M5Stack がテザリングに接続した後、M5Stack の IP を確認して `/24` を付ける。

#### 3. Tailscale Admin Console でサブネットを承認

https://login.tailscale.com/admin/machines でスマホのマシンを開き、サブネットルートを承認（Approve）する。

#### 4. 自宅PCからサブネットを受け入れる

```bash
sudo tailscale up --accept-routes
```

#### 5. 接続確認

M5Stack をスマホのテザリングに接続した状態で、自宅PCから:

```bash
ping <M5StackのIP>  # 例: ping 192.168.49.1
```

通ればOK。ダッシュボードからそのまま操作できる。

### 散歩時の操作

スマホのブラウザで `http://<自宅PCのTailscale IP>:8765` にアクセスしてダッシュボードから操作。

## ダッシュボードの常時起動（systemd）

PC再起動後も自動でダッシュボードが起動するようにする。

### 1. 環境設定ファイルを作成

`~/petit_claude/.env.dashboard` に環境固有の値を書く:

```bash
cat > ~/petit_claude/.env.dashboard <<'EOF'
PETIT_DATA_DIR=/home/yourname/petit_claude
DASHBOARD_HOST=0.0.0.0
DASHBOARD_PORT=8765
EOF
```

- `DASHBOARD_HOST`: `0.0.0.0` なら全インタフェースでリッスン。Tailscale IP を指定すると VPN 経由のみアクセス可能
- Tailscale IP の確認: `tailscale ip -4`

### 2. サービスを登録・起動

```bash
sudo cp dashboard/petit-dashboard.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable petit-dashboard
sudo systemctl start petit-dashboard

# 状態確認
sudo systemctl status petit-dashboard

# ログ確認
journalctl -u petit-dashboard -f
```

## 認証（オプション）

ダッシュボードに Basic 認証 + 7日間セッションを追加できる。

### ロール

| ロール | 閲覧 | チャット・操作 | 設定変更 |
|--------|------|---------------|---------|
| admin | OK | OK | OK |
| operator | OK | OK | NG |
| viewer | OK | NG | NG |

### 設定方法

`~/petit_claude/auth.json` を作成:

```bash
cp dashboard/auth.json.example ~/petit_claude/auth.json
vim ~/petit_claude/auth.json  # パスワードを設定
```

```json
{
  "users": {
    "arisan": {"password": "あなたのパスワード", "role": "admin"},
    "friend": {"password": "友達用パスワード", "role": "operator", "characters": ["puchiko"]},
    "guest": {"password": "ゲスト用パスワード", "role": "viewer"}
  }
}
```

ダッシュボードを再起動すると認証が有効になる。`auth.json` がなければ認証なし（従来通り）。

### キャラクター表示制限

`characters` フィールドで、ユーザーごとに閲覧・操作可能なキャラクターを制限できる。

- `characters` 未設定 or 空配列 → 全キャラ見える
- `characters: ["puchiko"]` → puchiko のみ見える（タブ・チャット・記憶・日記すべて）
- `admin` ロールは `characters` 設定を無視して常に全キャラ見える
- グループチャットも許可キャラのみに送信される

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

## API想定利用回数

2キャラ・デフォルト設定（`active_hours: [[7,8],[12,13],[18,24]]`）の場合:

| 種別 | 頻度 | 回数/日 | 備考 |
|------|------|---------|------|
| 自律行動（アクティブ時間帯） | 20分毎 | ~24回/キャラ | 8h × 3回/h |
| 自律行動（昼間非アクティブ） | 毎時:00、30%確率 | ~3回/キャラ | 9h × 0.3 |
| 自律行動（深夜） | 毎時:00、10%確率 | ~1回/キャラ | 7h × 0.1 |
| 日記生成 | 23:50 | 1回/キャラ | |
| desire_updater | 5分毎 | 0回 | SQLite直接読み、API不使用 |
| **合計（2キャラ）** | | **~58回/日** | |

### コスト目安（Sonnet 4）

| 期間 | 概算 |
|------|------|
| 1日 | ~$1.5（約230円） |
| 1ヶ月 | ~$45（約7,000円） |

ツール呼び出しが多いと膨らむため、実際は月1万〜1.5万円程度を見込む。

### 節約方法

- **`active_hours` を狭める**: `[[18,23]]` のみにすれば半分以下
- **非アクティブ確率を下げる**: `autonomous-action.sh` の昼間30%→10%、深夜10%→0% に変更
- **キャラ数を減らす**: 1キャラなら半額
- **Anthropic Console で上限設定**: https://console.anthropic.com/settings/usage

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
