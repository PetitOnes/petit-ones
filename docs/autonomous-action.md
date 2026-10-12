# 自律行動

[README](../README.md) に戻る


`autonomous-action.sh` が cron で30分毎に実行され、キャラクターが自律的に行動する。

## 実行フロー

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

## スケジュール制御

- **アクティブ時間帯**（`settings.json` の `active_hours`）: 30分毎に毎回実行
- **昼間の非アクティブ**: 毎時:00 に30%の確率で実行
- **深夜の非アクティブ**: 毎時:00 に10%の確率で実行

## Goose 版（Gemini / OpenAI 対応）

`autonomous-action-goose.sh` は `claude -p` の代わりに [Goose](https://github.com/aaif-goose/goose) CLI を使い、**Gemini 2.5 Flash**（デフォルト）または **OpenAI GPT-4o** で自律行動できる。

### セットアップ

```bash
# Goose インストール
curl -L https://github.com/aaif-goose/goose/releases/latest/download/goose-x86_64-linux.tar.gz | tar xz
mv goose ~/.local/bin/

# API キーを .env に追加
echo 'GOOGLE_API_KEY=...'  >> ~/petit_claude/.env   # Gemini
echo 'OPENAI_API_KEY=...'  >> ~/petit_claude/.env   # OpenAI
```

### 使い方

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

### mcp-launchers/

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

### Claude 版との違い

| | Claude 版 | Goose 版 |
|---|---|---|
| **実行コマンド** | `claude -p` | `goose run` |
| **モデル** | Claude Sonnet/Opus | Gemini 2.5 Flash / GPT-4o（切替可） |
| **ツール制限** | `--allowedTools` で明示許可 | なし（全 MCP ツールが利用可能） |
| **ファイル展開** | `@file` でインライン展開 | bash で事前展開してプロンプトに含める |
| **セッション名** | `{char}-{date}` | `{char}-{provider}-{date}` |
| **ログ出力先** | `.autonomous-logs/` | `.autonomous-logs-goose/` |

### crontab（Goose 版）

```bash
# Goose 版（Gemini）
*/30 * * * * /path/to/petit-ones/autonomous-action-goose.sh <char_id>

# Goose 版（OpenAI GPT-4o）
*/30 * * * * GOOSE_PROVIDER=openai GOOSE_MODEL=gpt-4o /path/to/petit-ones/autonomous-action-goose.sh <char_id>
```
