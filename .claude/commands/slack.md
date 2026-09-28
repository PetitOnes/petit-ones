---
description: "Slackの#099_embnodied-claudeにメッセージを送る（petitclaudeボットとして）。作業完了通知や、ありさんへの連絡に使う。自律中にも使える。"
argument-hint: "<メッセージ>"
allowed-tools: Bash(python3 /home/cube-petit/work/embodied-claude/scripts/slack_notify.py *)
---

Slackにメッセージを投稿する。

## 使い方

```bash
python3 /home/cube-petit/work/embodied-claude/scripts/slack_notify.py "メッセージ"
```

## ルール

- 投稿者は自分（ぷち or Claude）だと分かるように、必要なら名乗る
- **完了通知は、ありさんが「通知して」と言ったタスクだけ**。頼まれていないタスクの完了をいちいち流さない
- 深夜帯（0-7時）は緊急でない限り送らない
- 長文は送らない（3行以内目安。詳細はダッシュボードやノートへ）

入力: $ARGUMENTS
