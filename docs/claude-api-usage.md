# Claude API 使用箇所まとめ

システム内で `claude -p` を呼び出している場所を全列挙する。
代替手段の検討や API 使用量の把握に使う。

---

## 一覧

| # | 用途 | ファイル | トリガー | モデル | 頻度 |
|---|------|----------|---------|--------|------|
| 1 | 自律行動 | `autonomous-action.sh` | cron | sonnet | 30分毎（アクティブ帯は毎回） |
| 2 | チャット応答 | `dashboard/main.py` `call_claude()` | ユーザー操作 | sonnet | 操作のたびに |
| 3 | M5 CAM タップ応答 | `dashboard/main.py` `call_claude()` | M5 ボタン | sonnet | ボタンを押すたびに |
| 4 | M5 SEN タップ応答 | `dashboard/main.py` `call_claude()` | M5 ボタン | sonnet | ボタンを押すたびに |
| 5 | M5 MIC タップ応答 | `dashboard/main.py` `call_claude()` | M5 ボタン | sonnet | ボタンを押すたびに |
| 6 | 日記生成 | `dashboard/main.py` `generate_diary_summary()` | cron / 手動 | sonnet | 1日1回 |
| 7 | 欲求バー一言表示 | `dashboard/main.py` `_generate_display_phrase()` | ダッシュボード更新 | haiku-4-5 | 更新のたびに |

---

## 詳細

### 1. 自律行動（`autonomous-action.sh`）

**消費量: 最大。全体の大部分を占める。**

```bash
echo "$PROMPT" | claude -p \
  --model sonnet \
  --resume "$SESSION_ID" \
  --max-turns 20 \
  --output-format json \
  --mcp-config "$MCP_CONFIG" \
  --allowedTools "$ALLOWED_TOOLS"
```

- cron で 30 分毎に全キャラ分実行（3キャラ × 30分 = 最大6回/時）
- アクティブ時間帯は毎回実行、非アクティブ帯は確率制御でスキップ
- `--resume` でセッションを日内継続（日付が変わるとリセット）
- ログ: `~/petit_claude/.autonomous-logs/<char_id>/`
- **代替済み**: `autonomous-action-goose.sh`（Gemini 2.5 Flash / GPT-4o）

---

### 2〜5. ダッシュボード応答（`dashboard/main.py` `call_claude()`）

**呼ばれる場面:**

| 呼び出し元 | 説明 | 関数内の行 |
|---|---|---|
| チャット送信 | ユーザーがプチに話しかける（1対1・グループ・選択チャット） | L3997, L3834, L3865, L3898 |
| 「話させる」ボタン | プチ同士を会話させる | L4257, L4273 |
| 会話リレー開始 | MCP の `conversation_relay` から呼ばれる | L4323 |
| 「話しかけて」ボタン | 任意のプチに一言しゃべらせる | L4346, L4363 |
| M5 CAM タップ | スナップショット取得後に感想を生成 | L83 |
| M5 SEN タップ | センサー値を読んで感想を生成 | L116 |
| M5 MIC タップ | 音声認識結果に返答 | L232 |
| `/relay` エンドポイント | MCP からの会話リレー中継 | L3225 |

```python
cmd = ["claude", "-p", "--model", model,
       "--resume", sid,               # セッション継続
       "--append-system-prompt", system_prompt,
       "--mcp-config", mcp_config,
       "--allowedTools", allowed_tools,
       "--dangerously-skip-permissions",
       "--output-format", "json", "--verbose"]
```

- セッションファイル: `~/petit_claude/characters/<id>/chat_histories/<username>.session`
- タイムアウト: 120 秒
- モデル: 環境変数 `CLAUDE_MODEL`（デフォルト: `sonnet`）、チャット画面から上書き可

---

### 6. 日記生成（`generate_diary_summary()`）

```python
proc = await asyncio.create_subprocess_exec(
    "claude", "-p", "--model", diary_model, prompt, ...
)
```

- cron で毎日 23:50 に全キャラ分（`generate_diary.py`）
- ダッシュボードの「日記」タブから手動実行も可
- 1日の記憶一覧を渡して 2〜3 文にまとめる
- 過去日のキャッシュあり（`diary/YYYY-MM-DD.txt`）、今日分は毎回生成
- 生成後に `diary_summary.md` も更新（次回の自律行動プロンプトに含まれる）
- **代替可能**: テンプレートやルールベースで十分かもしれない

---

### 7. 欲求バー一言表示（`_generate_display_phrase()`）

```python
proc = await asyncio.create_subprocess_exec(
    "claude", "-p", prompt,
    "--model", "claude-haiku-4-5-20251001", ...
)
```

- ダッシュボードのトップ画面でキャラアイコン横に表示される一言
- センサー値 + 欲求上位 3 件から「今感じていることを15字以内」を生成
- haiku-4-5 直呼び（セッションなし、MCP なし）
- **代替可能**: 欲求レベルをルールで文字列に変換するだけで代替できる（Claude 不要）

---

## 代替可否まとめ

| 用途 | Claude 必須か | 代替案 |
|------|--------------|--------|
| 自律行動 | 要推論モデル | Goose + Gemini/OpenAI（実装済み） |
| チャット応答 | ほぼ必須（対話品質） | Gemini/GPT-4o に切り替え可（未実装） |
| M5 タップ応答 | ほぼ必須 | 同上 |
| 日記生成 | 不要 | ルールベース or テンプレートで代替可 |
| 欲求バー一言 | 不要 | 欲求→テキストのルールマップで代替可 |

---

## 現在の API 使用量の確認方法

```bash
# 全体
python3 /home/cube-petit/work/embodied-claude/scripts/check_usage.py

# キャラクター別
python3 /home/cube-petit/work/embodied-claude/scripts/check_usage.py --character puchiko
```
