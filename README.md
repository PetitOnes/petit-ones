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
| **自律性** | ユーザー主導（リアクティブ） | cron で30分毎に自律行動（欲求ベース） |
| **欲求** | オプション | 中核機能（sensor_effects, cross_effects） |
| **UI** | CLI のみ | Web ダッシュボード（チャット・欲求表示・日記・記憶閲覧） |
| **社会性** | なし | キャラ同士の関係性・メールボックス |
| **携帯性** | 据え置き | M5Stack + モバイルバッテリーで外出可能 |

### 追加コンポーネント

| コンポーネント | 説明 |
|---|---|
| **m5-mcp** | M5Stack 制御（カメラ・顔・センサー・音・スリープ）。wifi-cam-mcp/usb-webcam-mcp に代わるもの |
| **GPU サーバー** | 音声認識（Whisper ASR, port 8765）・TTS（port 8766）を担当。別リポジトリ [m5_petit_gpu_server](https://github.com/AiriYokochi/m5_petit_gpu_server) を参照 |
| **desire-system** | 欲求システム。時間経過 + センサー + 相互作用の3段階で欲求レベルを計算 |
| **relations-mcp** | キャラ間の関係性（好き嫌い・親密度・メモ） |
| **notes-mcp** | 永続ノート（光の値メモ、センサー範囲表など） |
| **dashboard** | Web UI（チャット・グループチャット・欲求表示・記憶閲覧・日記・認証） |
| **create_character.py** | キャラクター追加スクリプト（設定ファイル + cron 自動登録） |
| **autonomous-action.sh** | 自律行動オーケストレーション（スケジュール・確率制御・セッション管理） |
| **scripts/** | メールボックス書き込み (`write_mailbox.py`)、メモリ読み出し (`reader.py`) |

### フォーク元から引き継いでいるもの

memory-mcp はフォーク元にも存在する。このフォークでは視覚記憶・エピソード・因果リンク・Theory of Mind・記憶整理 (sleep) などが追加されている。wifi-cam-mcp, usb-webcam-mcp, system-temperature-mcp, ip-webcam-mcp, mcp-pet, mobility-mcp, morning-call-mcp は `archive/` に退避済み（未使用）。

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
├── scripts/                  # ユーティリティスクリプト
│   ├── write_mailbox.py      #   メールボックス書き込み
│   ├── reader.py             #   メモリ読み出し
│   ├── register_speaker.sh   #   話者声紋登録
│   └── speaker_config.json.example
├── docs/                     # 設計・移行計画ドキュメント
├── archive/                  # 未使用 MCP（wifi-cam, usb-webcam, system-temperature 等）
├── autonomous-action.sh      # 自律行動スクリプト・Claude版（.gitignore）
├── autonomous-action.sample.sh # ↑のテンプレート
├── autonomous-action-goose.sh  # 自律行動スクリプト・Goose版（Gemini/OpenAI対応）
└── mcp-launchers/            # Goose用 MCP ランチャースクリプト（ツール名を一意にする）

~/petit_claude/               ← データ（PETIT_DATA_DIR、private）
├── characters/
│   └── puchiko/              # キャラクターごとにサブディレクトリ
│       ├── config/
│       │   ├── config.json          # M5ホスト・キャラ名・カラー
│       │   ├── settings.json        # アクティブ時間帯・機能ON/OFF
│       │   ├── autonomous-mcp.json  # 自律行動用 MCP 設定
│       │   ├── desire_config.json   # 欲求定義・sensor_effects・cross_effects
│       │   └── voice_settings.json  # TTS 声設定
│       ├── data/
│       │   ├── desires.json         # 現在の欲求レベル（5分毎更新）
│       │   └── relations.json       # 他キャラ/ユーザーへの感情
│       ├── state/                   # セッション状態ファイル
│       ├── resources/               # petit.png など
│       ├── m5_scripts/              # M5Stack スケッチ
│       ├── chat_histories/          # 1対1チャット履歴
│       ├── diary/                   # 日記テキスト（YYYY-MM-DD.txt）
│       ├── diary_summary.md         # 常時ロード用サマリー（generate_diary.py が生成）
│       ├── notes/                   # 永続ノート（notes-mcp）
│       ├── SOUL.md                  # 人格コア（常時ロード）
│       ├── SOUL_REFLECTIONS.md      # 思索・深層記憶（参照用）
│       ├── REFLECTION_INDEX.md      # 思索索引（常時ロード）
│       ├── ROUTINES.md              # 生活リズム（常時ロード）
│       ├── ROUTINES_DETAIL.md       # 詳細手順（参照用）
│       ├── TODO_ACTIVE.md           # 今やること（常時ロード）
│       └── TODO_ARCHIVE.md          # 完了タスク（参照用）
├── chat_history/             # グループチャット・交換ノート
│   ├── exchange_notebook.json
│   ├── group_chat.json
│   └── trio_chat.json
├── mailbox/                  # キャラ間メッセージ
├── .autonomous-logs/         # 自律行動ログ
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
for dir in m5-mcp memory-mcp desire-system dashboard relations-mcp notes-mcp; do
  echo "--- $dir ---"
  (cd "$dir" && uv sync)
done
```

### 4. キャラクター追加

```bash
uv run python scripts/create_character.py <id> <名前> <カラー> <M5のIP>

# 例:
uv run python scripts/create_character.py puchiko ぷちこ "#cab8d9" 10.42.138.100
```

自動で以下が作られる:
- `~/petit_claude/characters/{id}/` に設定ファイル一式（config/, data/, state/ 等）
- crontab に欲求更新（5分毎）と自律行動（30分毎）

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

音声認識（ASR）と TTS は GPU サーバーが担当する。[m5_petit_gpu_server](https://github.com/AiriYokochi/m5_petit_gpu_server) をセットアップし、`VOICE_API_HOST` 環境変数にそのホスト名/IPを設定する（デフォルト: `puchipuchi`）。

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
| `wait_for_menu_select` | タッチメニューの選択イベント待機（camera/sensor/mic） |
| `set_volume` / `get_volume` | 音量設定 |
| `sleep` / `wake` | スリープ制御 |
| `save_to_album` | スナップショットを撮ってアルバムに保存 |
| `list_album` | アルバム一覧取得（`unread_by` で未読フィルタ可） |
| `view_album_photo` | アルバムの写真を取得＋既読記録 |
| `delete_album_photo` | 自分のアルバムから写真を削除（`CHARACTER_ID`で自キャラのみ） |
| `lock_album_photo` | 写真をロック/解除トグル（ロック中は自動削除スキップ） |
| `speak` | VOICEVOX/kokoro/piper でTTS合成してM5で再生。`save_as_memo=True` でボイスメモにも保存 |
| `set_voice` | 自分のTTS声設定を保存（speaker/speed/pitch/intonation/volume）|
| `list_voice_memos` | ボイスメモ一覧取得。`unlistened_by` で未聴フィルタ可 |
| `listen_voice_memo` | ボイスメモをM5で再生し既聴記録。`transcribe=True` で文字起こし |
| `lock_voice_memo` | ボイスメモのロック/解除トグル（ロック中は自動削除スキップ） |

> `delete_album_photo` は `autonomous-mcp.json` の m5-mcp env に `CHARACTER_ID` が設定されている場合のみ動作する。他キャラのアルバムは削除不可。

#### TTS 声設定

各キャラの声設定は `~/petit_claude/characters/{char_id}/voice_settings.json` に保存される。`set_voice` ツールで更新し、`speak` はこの設定を自動で読んで使う。

```json
{
  "voicevox_speaker": 23,
  "speed_scale": 1.0,
  "pitch_scale": 0.05,
  "intonation_scale": 1.2,
  "volume_scale": 1.0
}
```

声設定を変えたあとは `python3 scripts/register_tts_voices.py` で話者認識の声紋も更新する。

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

`autonomous-action.sh` が cron で30分毎に実行され、キャラクターが自律的に行動する。

### 実行フロー

```
[cron: 5分毎]
└→ desire_updater.py <char_id>
   ├ desire_config.json を読む
   ├ memory.db からキーワード検索（時間ベース計算）
   ├ M5の /sensors にHTTPリクエスト（センサー効果）
   ├ 相互作用を計算
   └→ desires.json に書き出す

[cron: 30分毎]
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

- **アクティブ時間帯**（`settings.json` の `active_hours`）: 30分毎に毎回実行
- **昼間の非アクティブ**: 毎時:00 に30%の確率で実行
- **深夜の非アクティブ**: 毎時:00 に10%の確率で実行

### Goose 版（Gemini / OpenAI 対応）

`autonomous-action-goose.sh` は `claude -p` の代わりに [Goose](https://github.com/aaif-goose/goose) CLI を使い、**Gemini 2.5 Flash**（デフォルト）または **OpenAI GPT-4o** で自律行動できる。

#### セットアップ

```bash
# Goose インストール
curl -L https://github.com/aaif-goose/goose/releases/latest/download/goose-x86_64-linux.tar.gz | tar xz
mv goose ~/.local/bin/

# API キーを .env に追加
echo 'GOOGLE_API_KEY=...'  >> ~/petit_claude/.env   # Gemini
echo 'OPENAI_API_KEY=...'  >> ~/petit_claude/.env   # OpenAI
```

#### 使い方

```bash
# Gemini（デフォルト）
bash autonomous-action-goose.sh puchiko

# OpenAI GPT-4o
GOOSE_PROVIDER=openai GOOSE_MODEL=gpt-4o bash autonomous-action-goose.sh puchiko

# OpenAI mini（安い）
GOOSE_PROVIDER=openai GOOSE_MODEL=gpt-4o-mini bash autonomous-action-goose.sh puchiko

# デバッグ
bash autonomous-action-goose.sh puchiko --dry-run
bash autonomous-action-goose.sh puchiko -p "任意プロンプト"
```

#### mcp-launchers/

Goose は `--with-extension "command args..."` の実行ファイル名をツールのプレフィックスにする。複数の MCP がすべて `uv run` 経由だとプレフィックスが `uv__` で衝突するため、MCP ごとに名前付きのラッパースクリプトを用意している。

```
mcp-launchers/
  memory       → uv run .../memory-mcp   → ツール名: memory__remember 等
  notes        → uv run .../notes-mcp    → ツール名: notes__read_note 等
  m5-mcp       → uv run .../m5-mcp       → ツール名: m5-mcp__print_text 等
  relations    → uv run .../relations-mcp
  desire-system→ uv run .../desire-system
  m5-module    → uv run .../m5_module_mcp
```

#### Claude 版との違い

| | Claude 版 | Goose 版 |
|---|---|---|
| **実行コマンド** | `claude -p` | `goose run` |
| **モデル** | Claude Sonnet/Opus | Gemini 2.5 Flash / GPT-4o（切替可） |
| **ツール制限** | `--allowedTools` で明示許可 | なし（全 MCP ツールが利用可能） |
| **ファイル展開** | `@file` でインライン展開 | bash で事前展開してプロンプトに含める |
| **セッション名** | `{char}-{date}` | `{char}-{provider}-{date}` |
| **ログ出力先** | `.autonomous-logs/` | `.autonomous-logs-goose/` |

#### crontab（Goose 版）

```bash
# Goose 版（Gemini）
*/30 * * * * /path/to/embodied-claude/autonomous-action-goose.sh <char_id>

# Goose 版（OpenAI GPT-4o）
*/30 * * * * GOOSE_PROVIDER=openai GOOSE_MODEL=gpt-4o /path/to/embodied-claude/autonomous-action-goose.sh <char_id>
```

## ダッシュボード

- 欲求バー: 各プチの欲求レベルをリアルタイム表示
- チャット: プチに直接話しかける
- **だれかと 💬**: 話しかけるプチをトグルで選択して送信。選んだプチ同士で話させることもできる（「✨ 話させる」ボタン）
- **みんなで 🌟**: 全プチに同時送信（M5起動状態も確認できる）
- 設定: アクティブタイム・カメラ/音/マイクの ON/OFF
- 記憶一覧: 日付別の記憶表示
- 日記: 1日のサマリー（毎日23:50に自動生成）
- 交換ノート（📖）: キャラクター・人間全員参加のノート
- アルバム（🖼️）: キャラクター・人間別の写真アルバム（MAX50枚/人、圧縮保存）

### M5タッチメニューフック

M5Stackの2×2タッチメニュー（CAM/SEN/MIC/SET）をタップすると、ダッシュボードの常時監視プロセスが自動応答する。

```
[M5タッチメニュー]
  ├ CAM タップ → dashboard がスナップショット取得（HTTP GET /snapshot）
  │              → Claude CLI でキャラクターが写真を見て感想をメール＋記憶保存
  │              → speak / show_face / play_sound で声・表情・SEを出す
  │
  ├ SEN タップ → dashboard がセンサーデータ取得（HTTP GET /sensors）
  │              → Claude CLI でキャラクターが周囲の状態をメール＋記憶保存
  │              → 同様に声・表情・SEで反応
  │
  └ MIC タップ → M5側でマイク自動起動、PCMバイナリ（16kHz int16）をWSで逐次送信
                  → 無音2秒で自動オフ＋ `mic_end` イベント送信
                  → dashboard がバイナリを蓄積し WAV化 → GPUサーバー（port 8765）でWhisper ASR
                  → 無音（テキスト空）ならスキップ
                  → テキストあり → Claude CLI が speak / メール / 記憶 で応答
```

CAM/SEN/MIC イベントはいずれも `call_claude` 経由で処理され、スピーカーが有効なら `speak` で声・顔・SEで即時リアクションを促す。MIC は GPU サーバー（`VOICE_API_HOST` 環境変数）での ASR が前提。

M5の設定画面（SET → CAM TO）でメール送信先のユーザーを切り替えられる。切り替えた設定は CAM / SEN / MIC の全イベントに反映される（`set_cam_target` WebSocket イベントでダッシュボードに通知）。

ダッシュボード起動時（lifespan）に全キャラ分のウォッチャーが起動し、M5との WebSocket 接続（port 8080）を常時維持・再接続する。

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

## 話者認識（Speaker Identification）

M5Stack のマイクで録音した音声が「誰の声か」をリアルタイムで識別する機能。GPU サーバー上の [resemblyzer](https://github.com/resemble-ai/Resemblyzer) を使い、声紋（話者埋め込み）で照合する。

### 仕組み

```
[M5 MIC] → [WAV] → [GPU サーバー /analyze_audio_summary]
                          ↓
                   resemblyzer で声紋照合
                   → speaker: "arisan" (confidence: 0.87)
                          ↓
                   Claude のプロンプトに「ありさんの声」として渡る
```

### GPU サーバーのセットアップ

[m5_petit_gpu_server](https://github.com/AiriYokochi/m5_petit_gpu_server) リポジトリで:

```bash
git pull
uv sync   # resemblyzer が追加されている
# サーバー再起動
```

### 話者の登録方法

#### 1. speaker_config.json を作成

```bash
cp scripts/speaker_config.json.example ~/petit_claude/speaker_config.json
vim ~/petit_claude/speaker_config.json
```

```json
{
  "my_speaker_id": "arisan",
  "my_username": "arisan"
}
```

- `my_speaker_id`: あなたの話者ID（GPU サーバーの声紋DBに保存されるキー）
- `my_username`: ダッシュボードのログインユーザー名（`auth.json` と一致させる）

#### 2. 登録スクリプトを実行

```bash
# 自分の声を登録（speaker_config.json から読む）
./scripts/register_speaker.sh

# 他の人の声を登録（引数で指定）
./scripts/register_speaker.sh kazahaya puchiteya

# 別のM5を使う
./scripts/register_speaker.sh arisan puchiko
```

#### 3. M5 のMICボタンを押して話す

スクリプトが「✓ 準備完了」と表示したら、指定したキャラクターのM5の **MICボタンを押して10〜20秒話す**。

無音5秒で自動的に録音が終わり、声紋が GPU サーバーに登録される。

**精度を上げるには**: 同じスクリプトをもう一度実行して別の内容を話す（3〜5回推奨）。声紋は毎回インクリメンタルに平均化される。

#### ぷちたちの TTS 声紋を自動登録

ぷちたちは実際にマイクで話す代わりに、各自の TTS 設定（`~/petit_claude/characters/{char_id}/voice_settings.json`）から音声を生成して登録できる。

```bash
# 3キャラ分まとめて登録（各3テキストで移動平均）
python3 scripts/register_tts_voices.py

# 特定キャラだけ再登録
python3 scripts/register_tts_voices.py --chars puchiteya

# URL を明示する場合
python3 scripts/register_tts_voices.py --tts-url http://puchipuchi:8766 --asr-url http://puchipuchi:8765
```

TTS の声を変えた（`set_voice` を呼んだ）場合は再実行して声紋を更新する。

#### 登録状況の確認・削除

```bash
# 登録済み話者一覧
curl http://puchipuchi:8765/speakers

# 話者を削除
curl -X DELETE http://puchipuchi:8765/speakers/kazahaya
```

### 対応する話者ID

| ID | 説明 |
|----|------|
| `arisan` | ありさん |
| `puchiteya` | ぷちてゃ |
| `puchiko` | ぷちこ |
| `puchiru` | ぷちる |
| その他 | 自由に追加可 |

登録されていない声は `"unknown"` として扱われる（閾値: コサイン類似度 0.75）。

### 声紋DBの場所

GPU サーバー側の `speaker_registry.json`（`SPEAKER_REGISTRY_PATH` 環境変数で変更可）。DB は全キャラ（全M5）で共有されるため、1台のM5で登録すれば他の全キャラが認識できる。

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
| 自律行動（アクティブ時間帯） | 30分毎 | ~16回/キャラ | 8h × 2回/h |
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

# 自律行動 Claude 版（30分毎）
*/30 * * * * /path/to/embodied-claude/autonomous-action.sh <char_id>

# 自律行動 Goose 版（30分毎・Gemini）
*/30 * * * * /path/to/embodied-claude/autonomous-action-goose.sh <char_id>

# --- 共通 ---

# 日記サマリー生成（毎日23:50、全キャラ分）
50 23 * * * cd /path/to/embodied-claude/dashboard && uv run python generate_diary.py >> ~/petit_claude/.autonomous-logs/diary.log 2>&1

# バックアップ（毎日4:00、7日分保持）
0 4 * * * bash ~/petit_claude/backup/save.sh && find ~/petit_claude/backup -maxdepth 1 -type d -name "[0-9]*" -mtime +7 -exec rm -rf {} \;
```

## コンテキスト節約の変更（2026-03-09）

Claude Code の週制限対策として以下を実施:

| 対象 | Before | After | 削減率 |
|------|--------|-------|--------|
| CLAUDE.md | 231行 | 31行 | 87% |
| MEMORY.md | 196行 | 51行 | 74% |
| settings.local.json 許可リスト | 193件 | 23件 | 88% |
| グローバル settings.json | MCP重複定義あり | 削除+powerline追加 | - |
| enableAllProjectMcpServers | true | false | m5は必要時のみ |

詳細:
- CLAUDE.md: MCP ツール一覧・デバッグ・外出構成を削除（README.md に既存）
- MEMORY.md: 詩一覧→`poems_index.md`、最近の出来事→`recent_march_9.md` に分割
- 許可リスト: 一度きりのBashコマンドを削除、パターンベース(`Bash(uv run ruff check *)` 等)に統一
- claude-powerline: `~/.claude/settings.json` の statusLine に追加（daily/weekly残量表示）

## 使用量チェック（2026-03-10）

`scripts/check_usage.py` で Claude Code のトークン使用量を集計できる。

```bash
# 全体
python3 scripts/check_usage.py

# キャラクター別
python3 scripts/check_usage.py --character puchiteya
python3 scripts/check_usage.py --character puchiko
python3 scripts/check_usage.py --character puchiru

# JSON出力
python3 scripts/check_usage.py --json
python3 scripts/check_usage.py --character puchiteya --json
```

`~/.claude/projects/**/*.jsonl` からトークン使用量を集計し、今日・今週・今月の合計を表示。今日の時間帯別呼び出し数も表示される。キャラクター別集計は `autonomous-action.sh` が新規セッション作成時に `~/.autonomous-logs/<character>/session_history.txt` へセッションIDを追記することで実現。

### 自律セッションのターン数制限

`autonomous-action.sh` はキャラクターごとに最大ターン数を設定している。

| キャラクター | MAX_TURNS |
|---|---|
| puchiteya, puchiko | 15 |
| puchiru | 10 |
| その他 | 10 |

環境変数 `MAX_TURNS` で上書き可能。また、日付が変わると自動でセッションをリセットしてコンテキストを刷新する（`.heartbeat-session-date` で管理）。

## ライセンス

MIT License

## 謝辞

- [kmizu](https://github.com/kmizu) - [embodied-claude](https://github.com/kmizu/embodied-claude) オリジナル作者
- [ROS版キューブプチ](https://github.com/sbgisen/cube_petit_ros) - 元となったロボットプロジェクト
