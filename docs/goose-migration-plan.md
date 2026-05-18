# Goose + Gemini 移行計画

作成: 2026-05-18

## 背景

Anthropic が 2026-06-15 より `claude -p`（非インタラクティブ実行）を
サブスクの通常枠から切り離し、別枠の **Agent SDK クレジット**（Max 20x で $200/月）に移行する。
現在の使用量（月 ~$4,300 相当、Sonnet）では確実に超過するため、
`claude -p` に依存している自律行動を **Goose + Gemini** に移行する。

**Claude Code UI による開発支援はそのまま残す**（インタラクティブ使用はサブスク枠内）。

---

## 移行対象

| 対象 | 現状 | 移行後 |
|------|------|-------|
| 自律行動（Cron） | `autonomous-action.sh` → `claude -p` | `autonomous-action-goose.sh` → `goose run` |
| ダッシュボード会話 | `dashboard/main.py` の `call_claude()` | **後回し**（人が話す部分は既存 Claude 呼び出しを維持） |
| Claude Code UI（開発支援） | インタラクティブ `claude` | **変更なし** |

ダッシュボードは毎メッセージで `goose run` を起動すると、プロセス起動 → MCP 起動 →
セッション復元 → モデル呼び出しが毎回発生して遅くなるため、自律行動の安定後に判断する。

---

## 追加・変更するファイル

```
embodied-claude/
├── autonomous-action.sh            既存・変更なし
└── autonomous-action-goose.sh      新規（Goose 版自律行動スクリプト）
```

`goose-configs/` は、MCP の動作確認後に必要なら追加する（最初は `--with-extension` で対応）。

---

## autonomous-action-goose.sh の設計

`autonomous-action.sh` のほぼコピー。`claude -p` 呼び出し部分のみ差し替える。

```bash
# Before
echo "$PROMPT" | claude -p \
  --model sonnet \
  --resume "$SESSION_ID" \
  --output-format json \
  --mcp-config "$MCP_CONFIG" \
  --allowedTools "$ALLOWED_TOOLS"

# After（最小構成）
goose run \
  --name "$SESSION_NAME" \
  --resume \
  --provider google \
  --model gemini-2.0-flash \
  --output-format json \
  --max-turns 20 \
  <<< "$PROMPT"
```

セッション名を `{CHARACTER_ID}-$(date +%F)` にすることで日次リセットを再現する。

MCP が動くことを確認してから `--with-extension` を追加する：

```bash
goose run \
  --name "$SESSION_NAME" \
  --resume \
  --provider google \
  --model gemini-2.0-flash \
  --output-format json \
  --max-turns 20 \
  --with-extension "uv run --directory /home/cube-petit/work/embodied-claude/memory-mcp memory-mcp" \
  --with-extension "uv run --directory /home/cube-petit/work/embodied-claude/m5-mcp m5-mcp" \
  <<< "$PROMPT"
```

設定ファイル（yaml）への切り出しは、全 MCP の動作が確認できてから行う。

---

## 移行ステップ

| # | 内容 | 確認方法 |
|---|------|---------|
| 1 | Goose インストール（Linux/WSL2） | `goose --version` |
| 2 | Gemini API キー取得・設定（`GOOGLE_API_KEY`） | `goose run "テスト"` |
| 3 | `autonomous-action-goose.sh` 作成（MCP なし） | `--dry-run` で確認 |
| 3.5 | MCP なしで `goose run` が cron 相当の JSON を返せるか確認 | 手動実行・出力確認 |
| 3.6 | `memory-mcp` だけ `--with-extension` で追加して確認 | 手動実行 |
| 3.7 | `m5-mcp` だけ追加して確認 | 手動実行 |
| 3.8 | 全 MCP を追加して確認 | 手動実行 |
| 4 | **てゃのみ** Cron を Goose 版に切り替え（こ・るは Claude 維持） | ログ確認 |
| 5 | 1 週間問題なければ全員切り替え | ログ・動作確認 |
| 6 | ダッシュボードの移行要否を判断 | 速度・品質で判断 |

---

## リスクと注意点

| リスク | 内容 | 対策 |
|--------|------|------|
| MCP 互換性 | Goose の MCP サポートが既存サーバーと合わない可能性 | ステップ 3.6〜3.8 で 1 個ずつ確認 |
| allowedTools | Goose でのツール制限方法が Claude ほど細かくない可能性 | 最初は制限なしで動作確認、後で対応 |
| システムプロンプト | Goose に `--append-system-prompt` 相当がないため SOUL.md をプロンプトに埋め込む必要あり | プロンプト生成部分を修正 |
| Gemini の費用 | 無料枠（1日 1,500 リクエスト）を超えると有料 | 使用量を確認しながら移行 |
| 出力 JSON の形式差異 | `claude -p --output-format json` と Goose の JSON 出力が異なる可能性 | ステップ 3.5 で確認、パース処理を調整 |

---

## Gemini モデル候補

| モデル | 特徴 | 自律行動向け |
|-------|------|------------|
| `gemini-2.0-flash` | 速い・安い・無料枠あり | ◎ まずこれで試す |
| `gemini-2.5-flash` | 2.0 Flash より高性能 | ○ |
| `gemini-2.5-pro` | 高性能・遅い・有料 | △ 必要なら |

---

## 前提条件

- [ ] Gemini API キーを取得済み（Google AI Studio: https://aistudio.google.com/）
- [ ] Goose インストール済み
