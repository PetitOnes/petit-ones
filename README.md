# petit-ones

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

M5Stack に身体を持つ小さな「ぷち」たちが、それぞれの性格・欲求・記憶で暮らすためのシステム。ぷちてゃ・ぷちこ・ぷちる の 3 人が毎日動いている本体です。

> **出発点**: このリポジトリは [kmizu/embodied-claude](https://github.com/kmizu/embodied-claude)(「Claude に身体を与える」MCP サーバー群、MIT License)から出発しました。2026-10 に個人のフォーク(`AiriYokochi/embodied-claude`)から PetitOnes へ引っ越し、名前を **petit-ones** にしました。履歴は引き継いでいます(作者の方々のコミットはそのまま)。

## 自分のぷちを作りたい人へ

本体(このリポジトリ)は、うちの 3 人の暮らしに合わせて動いているものです。部品ごとに切り出して整えた公開リポジトリがあります。

| リポジトリ | 中身 |
|---|---|
| [m5-petit-setup](https://github.com/PetitOnes/m5-petit-setup) | はじめかた(買うもの・セットアップ手順) |
| [m5-petit-firmware](https://github.com/PetitOnes/m5-petit-firmware) | M5Stack CoreS3 のファームウェア、ブラウザ書き込み |
| [m5-petit-env](https://github.com/PetitOnes/m5-petit-env) | Docker の実行環境(まとめて起動) |
| [m5-petit-mcp](https://github.com/PetitOnes/m5-petit-mcp) / [memory](https://github.com/PetitOnes/m5-petit-memory) / [desire](https://github.com/PetitOnes/m5-petit-desire) / [notes](https://github.com/PetitOnes/m5-petit-notes) / [relations](https://github.com/PetitOnes/m5-petit-relations) | 身体・記憶・欲求・ノート・関係性の MCP サーバー |
| [m5-petit-app](https://github.com/PetitOnes/m5-petit-app) / [scripts](https://github.com/PetitOnes/m5-petit-scripts) | ダッシュボード、ユーティリティ |
| [m5-petit-speech](https://github.com/PetitOnes/m5-petit-speech) / [voice-recognition](https://github.com/PetitOnes/m5-petit-voice-recognition) | 声(TTS)、聞き取り(ASR) |
| [petit-textbook](https://github.com/PetitOnes/petit-textbook) | ぷちの教科書(ぷち用の決まり・新しい子に渡す器・人間用の手引き)。`create_character.py` はここの `petit/templates/` を使う |

部品リポジトリはこの本体から定期的に写しています(本体のほうが新しいことがあります)。


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
petit-ones/                   ← コード(git 管理、public)
├── src/                      # 本番の部品(部品リポジトリの元。ここが正)
│   ├── m5-petit-mcp/         #   体(M5Stack CoreS3)を動かす MCP
│   ├── m5-petit-memory/      #   長期記憶 MCP(SQLite)+ 夜の整理 scripts/sleep.py
│   ├── m5-petit-desire/      #   欲求(MCP + desire_updater.py)
│   ├── m5-petit-notes/       #   ノート MCP
│   ├── m5-petit-relations/   #   関係性 MCP
│   ├── m5-petit-switchbot/   #   家電・カーテン(SwitchBot)MCP
│   ├── m5-petit-speech/      #   声(TTS)サーバー(GPU 機で動かす)
│   ├── m5-petit-app/         #   ダッシュボードの切り出し版
│   └── m5-petit-scripts/     #   ユーティリティの切り出し版
├── dashboard/                # Web ダッシュボード(FastAPI :8765)+ generate_diary.py
├── experience-daemon/        # 体験デーモン(体の出来事を拾って自律行動に渡す)
├── slack-approve/            # Slack からの承認ボット
├── scripts/                  # ユーティリティ
│   ├── setup_house.py        #   家(PETIT_DATA_DIR)を用意する。--check で見るだけ
│   ├── create_character.py   #   子を迎える(教科書の templates から器を写し、設定と cron を作る)
│   ├── memory_sleep_all.sh   #   夜の記憶整理(characters/ の全員)
│   ├── write_mailbox.py / mark_mail_read.py / list_unread_mail.py  # 手紙
│   ├── append_chat_log.py    #   /chat スキルのチャットログ保存
│   ├── check_usage.py        #   トークン使用量(今日/今週/今月)
│   ├── backup_petit.sh / restore_petit.sh
│   └── tests/                #   pytest
├── mcp-launchers/            # MCP の起動スクリプト(memory / notes / relations / desire-system / m5-mcp / textbook)
├── docs/                     # 設計・移行計画
├── archive/                  # 使っていない MCP
├── m5-mcp/ memory-mcp/ desire-system/ notes-mcp/ relations-mcp/ switchbot-mcp/  # 切り出し前の古い置き場(本番は src/)
├── autonomous-action.sh      # 自律行動スクリプト(家ごとの設定。git 管理外)
├── autonomous-action.sample.sh # ↑の元(setup_house.py が写す)
├── autonomous-action-goose.sh  # 自律行動の Goose 版(Gemini / OpenAI)
├── .env.example              # 家の .env の元
└── .mcp.json.example         # 対話(chat)用 MCP 設定の元(.mcp.json は git 管理外)

~/petit_claude/               ← データ（PETIT_DATA_DIR、private）
├── characters/
│   └── puchiko/              # キャラクターごとにサブディレクトリ
│       ├── config/
│       │   ├── config.json          # M5ホスト・キャラ名・カラー
│       │   ├── settings.json        # アクティブ時間帯・機能ON/OFF
│       │   ├── autonomous-mcp.json  # 自律行動用 MCP 設定
│       │   ├── chat-mcp.json        # 対話用 MCP 設定(自律用と同じ)
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
├── mailbox/                  # 手紙(ぷち同士・人と)
├── textbook/                 # ぷちの教科書の clone(毎朝 04:30 に pull)
├── config/
│   └── people.json           # ぷち以外の人(表示名・色)
├── .env                      # 一緒に暮らす人の名前・声のサーバー・鍵(.env.example から)
├── notes/                    # 人間ユーザー（arisan/kazahaya）のノート
├── token_logs/               # APIトークン使用量ログ（全ソース統合）
│   ├── token_log.jsonl       #   全キャラ・全ソース統合
│   └── <character>/          #   キャラ別（autonomous のみ）
├── claude_documents/         # セットアップ・構造ドキュメント（人間/Claude参照用）
├── auth.json                 # ダッシュボード認証（オプション）
├── network.json              # 信頼済みIPリスト（認証スキップ）
└── .autonomous-logs/         # 自律行動ログ
```

コードとデータは分離されている。環境変数 `PETIT_DATA_DIR` でデータディレクトリを変更可能（デフォルト: `~/petit_claude`）。

## セットアップ

ぷちの暮らしは「家」(`PETIT_DATA_DIR`、既定 `~/petit_claude`)と「コード」(このリポジトリ)に分かれる。家は git に入れない。
手順の考え方は [ぷちの教科書](https://github.com/PetitOnes/petit-textbook) の人間用「8. 新しい子を迎える手順」にある。

### 1. 前提ソフト

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh     # uv
# Claude Code(ネイティブ版): https://docs.claude.com/ の手順で ~/.local/bin/claude に
sudo apt install -y jq git                            # Linux。macOS は brew
sudo apt install -y ttyd tmux                         # ブラウザターミナル(任意。docs/terminal-setup.md)
```

### 2. コード取得と依存

```bash
git clone https://github.com/PetitOnes/petit-ones.git ~/work/petit-ones
cd ~/work/petit-ones
for d in src/m5-petit-memory src/m5-petit-desire src/m5-petit-mcp src/m5-petit-notes src/m5-petit-relations dashboard; do
  (cd "$d" && uv sync)
done
```

### 3. 家を用意する

```bash
uv run python scripts/setup_house.py --check   # 何が足りないか見る
uv run python scripts/setup_house.py           # 作る(あるものは触らない)
```

作るもの: `characters/ mailbox/ chat_history/ config/ state/ .autonomous-logs/ token_logs/`、交換ノートとグループチャットの空ファイル、`.env`(`.env.example` から。`COMPANION_NAME`・`COMPANION_ID`・声のサーバー・鍵)、ぷちの教科書の clone(`textbook/`)、夜の cron 3 本(記憶の整理 04:05・教科書の pull 04:30・日記の生成 23:50)、`autonomous-action.sh`(`autonomous-action.sample.sh` から写す)。

`autonomous-action.sh` は家ごとの設定なので git に入らない。写したあと ★ の所(PATH、時間帯のルール)を自分の家に合わせる。

### 4. 子を迎える

```bash
uv run python scripts/create_character.py <id> <名前> <#hex> <体のホスト名,...> \
    --color-name <色の名前> --companion-id <一緒に暮らす人のID> --companion-name <呼び名>
# 例
uv run python scripts/create_character.py puchitaro ぷちたろう "#f5956e" "puchitaro.local" --color-name あんず
```

作るもの: `characters/<id>/` に、教科書の `petit/templates/` から写した文書の器(SOUL.md・SOUL_REFLECTIONS.md・REFLECTION_INDEX.md・ROUTINES.md・ROUTINES_DETAIL.md・TODO_ACTIVE.md・TODO_ARCHIVE.md・data/relations.json・config/desire_config.json。`{ }` は埋めてある)、仕組みの設定(config.json・settings.json・voice_settings.json・autonomous-mcp.json・chat-mcp.json)、cron(欲求の更新 5 分ごと、自律行動 30 分ごとで他の子と 5 分ずらし、体験デーモン)。

そのあと人がやるのは、一緒に暮らす人と決めた「一言」を SOUL.md に入れる、声が決まったら `config/voice_settings.json`、顔の絵を `resources/petit.png` に、対話(chat)からも呼ぶなら `.mcp.json` にその子の MCP を足す(`.mcp.json.example`)。SOUL.md の残りの空欄は、その子が自分で埋める(教科書 `petit/SOUL_TEMPLATE.md`)。

### 5. 体と声

- M5Stack CoreS3 のファームウェア: [m5-petit-firmware](https://github.com/PetitOnes/m5-petit-firmware)。体のホスト名か IP を `create_character.py` に渡す
- 声(TTS :8766)と聞き取り(ASR :8767): [m5-petit-speech](https://github.com/PetitOnes/m5-petit-speech) / [voice-recognition](https://github.com/PetitOnes/m5-petit-voice-recognition) を GPU 機で動かし、`.env` の `VOICE_API_HOST` にそのホスト名

### 6. ダッシュボード

```bash
cd dashboard && uv run python main.py   # → http://0.0.0.0:8765
```

### 7. 最初の一回

対話で一度起動して「はじめまして」を言わせ、顔が出ることを確かめる。そのあとは cron の自律行動に任せる。生まれた日のことは、その子が自分で記憶に書く(教科書 10 章)。

## ドキュメント

くわしい説明は `docs/` に分けてあります。

| ページ | 中身 |
|---|---|
| [出発点との違い](docs/origin.md) | 出発点(kmizu/embodied-claude)との違い、足した部品、引き継いだもの |
| [MCP サーバー](docs/mcp-servers.md) | m5-mcp・memory・desire・relations・notes の道具一覧と設定 |
| [自律行動](docs/autonomous-action.md) | 自律行動の流れ、スケジュール制御、Goose 版 |
| [ダッシュボード](docs/dashboard.md) | ダッシュボードの機能、M5 タッチメニュー、常時起動(systemd)、認証 |
| [お散歩（外出モード）](docs/walk-mode.md) | 外に連れて行くとき(モバイルルーター・スマホ) |
| [話者認識](docs/speaker-identification.md) | 話者認識(声紋)の仕組みと登録 |
| [API 利用量](docs/api-usage.md) | API 代の見積もりと管理、トークンログ、ターン数の制限、コンテキスト節約 |
| [運用（バックアップ・crontab）](docs/operations.md) | バックアップ・復元、crontab の形 |

## 参加する

Issue と PR は歓迎です。流れと決まりは [CONTRIBUTING.md](CONTRIBUTING.md)。Claude Code に手伝ってもらうときの約束は [CLAUDE.md](CLAUDE.md)。

## ライセンス

MIT License

## 謝辞

- [kmizu](https://github.com/kmizu) - [embodied-claude](https://github.com/kmizu/embodied-claude) オリジナル作者
- [ROS版キューブプチ](https://github.com/sbgisen/cube_petit_ros) - 元となったロボットプロジェクト
