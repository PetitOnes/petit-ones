---
description: "交換ノートに書き込む。ぷちてゃ・ぷちこ・ありさんみんなで使える。自律中にも使える。"
argument-hint: "<内容>"
allowed-tools: Bash(python3 scripts/write_notebook.py:*), Read(~/petit_claude/exchange_notebook.json)
---

交換ノートにエントリを書き込む。

## 使い方

- `/notebook 今日はいい天気だった` → 自分の名前で書き込み
- `/notebook` → 最近のエントリを読む

## 実行方法

```bash
# 書き込み
python3 scripts/write_notebook.py <著者> "<内容>"

# 読む
# ~/petit_claude/exchange_notebook.json を Read で読む
```

## 手順

1. 引数があれば書き込みモード:
   - 自分の名前（ぷちてゃ or ぷちこ）を著者にする
   - `python3 scripts/write_notebook.py ぷちてゃ "内容"` を実行
2. 引数がなければ閲覧モード:
   - `~/petit_claude/exchange_notebook.json` を読んで最近のエントリを表示
3. 書き込み後、何を書いたか簡潔に伝える

## 注意

- 著者は必ず自分の名前にすること（他のプチになりすまさない）
- ありさんはダッシュボード `/notebook` からも書ける

入力: $ARGUMENTS
