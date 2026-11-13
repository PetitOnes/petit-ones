# ターミナル機能 セットアップ手順

ダッシュボード (`/terminal`) からブラウザでClaudeターミナルを使うための設定。

## 必要なパッケージ

```bash
sudo apt install -y ttyd tmux
```

| パッケージ | 用途 |
|---|---|
| `ttyd` | ターミナルをブラウザで表示 |
| `tmux` | セッション共有・チャット開始ボタンのコマンド送信に必要 |

## tmux 設定

マウス・タッチスクロールを有効にする:

```bash
echo 'set -g mouse on' >> ~/.tmux.conf
```

## systemd ユーザーサービス（ttyd）

`~/.config/systemd/user/ttyd-claude.service` を作成:

```ini
[Unit]
Description=ttyd Claude Code terminal
After=network.target

[Service]
WorkingDirectory=/home/USERNAME/work/embodied-claude
ExecStart=/usr/bin/ttyd -p 7682 -W -c USERNAME:PASSWORD /usr/bin/tmux new-session -A -s claude /home/USERNAME/.nvm/versions/node/v20.20.2/bin/claude
Restart=on-failure
RestartSec=5
Environment=HOME=/home/USERNAME
Environment=PATH=/home/USERNAME/.nvm/versions/node/v20.20.2/bin:/usr/local/bin:/usr/bin:/bin

[Install]
WantedBy=default.target
```

- `USERNAME` → 実際のユーザー名
- `PASSWORD` → ブラウザからアクセスするときのBasic認証パスワード
- `-W` → クライアントから入力可能にする
- `-c user:pass` → Basic認証（省略するとパスワードなしで誰でもアクセス可）
- tmux セッション名は `claude`（`/api/terminal/chat` のsend-keys先と合わせること）

有効化・起動:

```bash
systemctl --user daemon-reload
systemctl --user enable ttyd-claude
systemctl --user start ttyd-claude
```

## 動作確認

```bash
# ttyd が起動しているか
systemctl --user status ttyd-claude

# ポートが開いているか
curl -s -o /dev/null -w "%{http_code}" http://localhost:7682

# tmux セッションがあるか（ブラウザでターミナルを開いた後）
tmux list-sessions
```

## ダッシュボードとの連携

ダッシュボード（port 8765）の `/terminal` ページから:
- キャラアイコンをクリックして選択 → **チャット開始 ▶** で `/chat` コマンドが自動送信される
- **終了 ✕** で `/endchat` が送信される
- **⛶** ボタン → ttyd を別タブで直接開く（スマホでのスクロール用）

この連携には `tmux send-keys -t claude` を使っているため、tmux セッション名が `claude` である必要がある。

## チャットログ保存

`/chat` スキルは会話内容を `~/petit_claude/characters/<id>/chat_histories/chat_history.json` に保存する。  
保存スクリプト: `scripts/append_chat_log.py`

## ポート一覧

| ポート | サービス |
|---|---|
| 8765 | ダッシュボード（FastAPI） |
| 7682 | ttyd（Claudeターミナル） |
| 7681 | ttyd（ログインシェル、loopbackのみ） |

## system prompt の文面(2026-11-13)

`chat_startup.sh`(1 セッション、複数人可)と `chat_startup_3p.sh`(3 窓)は、どちらも `scripts/build_chat_prompt.py <id…>` で system prompt を作る。文面は `prompts/chat/system.md` 1 つ(1 人でも複数人でも同じテンプレート。複数人のときだけ「複数人チャットのルール」が付く)。
名前は `characters/<id>/config/config.json` の `name`、話しかける人は `.env` の `COMPANION_NAME`。家ごとの言い回しは `PETIT_DATA_DIR/prompts/chat/system.md` で上書き。

