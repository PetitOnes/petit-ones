# Embodied Claude - プロジェクト指示

Claude に身体（目・首・耳・声・脳）を与える MCP サーバー群。

## ディレクトリ構造

- `usb-webcam-mcp/` — USB ウェブカメラ制御
- `wifi-cam-mcp/` — Wi-Fi PTZ カメラ制御（Tapo/ONVIF）
- `tts-mcp/` — TTS 統合（ElevenLabs + VOICEVOX）
- `memory-mcp/` — 長期記憶（ChromaDB）
- `system-temperature-mcp/` — 体温感覚
- `m5-mcp/` — M5Stack 制御
- `dashboard/` — Web ダッシュボード（FastAPI, port 8765）
- `desire-system/` — 欲求システム
- `scripts/` — メールボックス・ユーティリティ

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
