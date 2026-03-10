---
description: "ダッシュボードを再起動する。コード変更後に使う。"
allowed-tools: Bash(pgrep *), Bash(kill *), Bash(cd ~/work/embodied-claude/dashboard && uv run python main.py *)
---

ダッシュボード（port 8765）を再起動する。

## 手順

1. 現在のダッシュボードプロセスを探して停止する:
   ```bash
   pgrep -af "uvicorn|dashboard/main"
   ```
2. PIDを確認してkillする（プロセスがあれば）
3. バックグラウンドで再起動する:
   ```bash
   cd ~/work/embodied-claude/dashboard && uv run python main.py &
   ```
4. 起動確認（数秒待ってからcurlで確認）
5. ありさんに「再起動した、port 8765」と伝える
