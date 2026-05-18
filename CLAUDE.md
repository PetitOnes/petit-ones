# Embodied Claude - プロジェクト指示

Claude に身体（目・首・耳・声・脳）を与える MCP サーバー群と、キャラクター（ぷちてゃ・ぷちこ・ぷちる）の自律行動システム。

## MCP サーバー（使用中）

| ディレクトリ | 役割 |
|---|---|
| `memory-mcp/` | 長期記憶（SQLite） |
| `notes-mcp/` | ノート読み書き |
| `relations-mcp/` | キャラクター間の関係性データ |
| `m5-mcp/` | M5Stack 制御・センサー |

## その他のコンポーネント

- `dashboard/` — Web ダッシュボード（FastAPI, port 8765）
- `desire-system/` — 欲求システム（cron 5分ごと実行）
- `scripts/` — メールボックス・ユーティリティ
- `autonomous-action.sh` — 自律行動スクリプト（cron 20分ごと実行）

## キャラクターデータ構造

`~/petit_claude/characters/<id>/` 以下:

```
config/
  config.json          # M5ホスト・表示名など
  autonomous-mcp.json  # 自律行動用MCPサーバー設定
  settings.json        # Claude設定（会話履歴など）
  desire_config.json   # 欲求システム設定
  voice_settings.json  # 音声設定
data/
  relations.json       # 関係性データ
  desires.json         # 欲求レベル（desire-system出力）
state/
  .heartbeat-session-id / .heartbeat-session-date
  last_session.txt
resources/
  petit.png            # アバター画像
m5_scripts/            # M5Stack スケッチ
chat_histories/        # 1対1チャット履歴（ダッシュボード）
diary/                 # 日記テキスト（YYYY-MM-DD.txt）
diary_summary.md       # 常時ロード用サマリー（generate_diary.py が生成）
SOUL.md                # 人格コア（常時ロード）
SOUL_REFLECTIONS.md    # 思索・深層記憶（参照用）
REFLECTION_INDEX.md    # 思索索引（常時ロード）
ROUTINES.md            # 生活リズム・行動優先順位（常時ロード）
ROUTINES_DETAIL.md     # 詳細手順（参照用）
TODO_ACTIVE.md         # 今やること（常時ロード）
TODO_ARCHIVE.md        # 完了タスク（参照用）
notes/                 # notes-mcp で読み書きするノート
```

## グループチャット・交換ノート

`~/petit_claude/chat_history/` 以下（正規パス）:

- `exchange_notebook.json` — ぷちたち＋ありさんの交換ノート（`/notebook` スキル）
- `exchange_notebook_kazahaya.json` — かぜおさん用交換ノート
- `group_chat.json` — グループチャット
- `trio_chat.json` — 3人チャット

## 開発ガイドライン

- **パッケージマネージャー**: uv / **Python**: 3.10+ / **リンター**: ruff / **テスト**: pytest + pytest-asyncio
- コミット前: `uv run ruff check .` && `uv run pytest -v`

## セキュリティ

- `.env` はコミット不可（.gitignore 済み）
- カメラパスワード・API キーは環境変数管理

## 注意: WSL2 環境

- USB カメラ: `usbipd` で転送が必要
- 温度センサー: `/sys/class/thermal/` アクセス不可
- CUDA: 利用可能（Whisper用）
