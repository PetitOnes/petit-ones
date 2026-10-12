# API 利用量

[README](../README.md) に戻る

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

### claude -p のトークンログ

`autonomous-action.sh` とダッシュボードの `claude -p` 呼び出しは、実行ごとに JSON 形式のトークンログを `~/petit_claude/token_logs/` に保存する。

```bash
# ログを確認（最新5件）
tail -5 ~/petit_claude/token_logs/token_log.jsonl | python3 -m json.tool

# キャラ別（autonomousのみ）
cat ~/petit_claude/token_logs/puchiteya/token_log.jsonl
```

ログの1行フォーマット:

```json
{"timestamp":"2026-05-19T11:20:00+00:00","source":"chat","character":"puchiko","turns":5,"input":100,"output":800,"cache_creation":12000,"cache_read":50000,"cost_usd":0.12}
```

`source` の種類: `autonomous`（自律行動）, `chat`（ダッシュボード会話）, `display_phrase`（M5一言生成）, `diary`（日記サマリー生成）

### 自律セッションのターン数制限

`autonomous-action.sh` はキャラクターごとに最大ターン数を設定している。

| キャラクター | MAX_TURNS |
|---|---|
| puchiteya, puchiko | 15 |
| puchiru | 10 |
| その他 | 10 |

環境変数 `MAX_TURNS` で上書き可能。また、日付が変わると自動でセッションをリセットしてコンテキストを刷新する（`.heartbeat-session-date` で管理）。
