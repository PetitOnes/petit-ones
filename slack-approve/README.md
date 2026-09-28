# slack-approve

tmux上で動いているClaude Codeの許可プロンプト（「Do you want to …?」＋「1. Yes / 2. Yes, and… / 3. No」）
をSlackのボタンで承認できるようにするボット。ダッシュボードのY/YS/Nボタン（tmux send-keysで数字を送る）
と同じ操作を、Slackからもできるようにする。

## 仕組み

1プロセス（`approve_bot.py`）が2つの役割を同時に持つ:

- **見張りスレッド**（バックグラウンドスレッド）: 5秒ごとに対象tmuxセッションそれぞれで
  `tmux capture-pane -pt <session>` を実行し、画面末尾に許可プロンプトが出ていないか確認する。
  検出したら、プロンプトに**実際に存在する選択肢だけ**をパースしてボタン化し
  （2択なら2つ、3択なら3つ。ラベルはSlackの75文字上限で切り詰め）、
  プロンプト内容をSlackチャンネル（`SLACK_APPROVE_CHANNEL`）にBlock Kitで投稿する
  （本文はコードブロック・末尾40行まで）。ボタンのvalueにはJSON
  （`session`/`choice`/`hash`/`label`）を埋め込む。
  新規出現したプロンプトはハッシュでdedupeし10分間は再通知しない
  （画面に残り続けている間の抑制は下記のアクティブ通知トラッキングが担当する）。
  さらに投稿済みの通知を継続的に見張り:
  - 画面から消えたことが2周連続（約10秒）で確認できたら、通知をSlackから自動削除する
    （承認済み＝✅などに更新済みのものは削除しない）。削除できたら再出現時に備えて
    dedupeキャッシュもクリアする。
  - 5分以上画面に残り続けて未応答なら、古い通知を削除して
    「⏰ まだ待っています」付きで再通知する。
- **Socket Modeハンドラ**（メインスレッド）: Slackのボタンが押されたら、まず同一
  message_tsの二重処理（連打・Slackの再送）をin-memoryで防ぎ、
  `body.user.id == SLACK_APPROVE_ALLOWED_USER`（ありさん）を確認したうえで、
  **送信前にそのセッションのpaneを再captureし、ボタンに埋め込まれたハッシュと
  一致するプロンプトがまだ画面にあるか照合する**。一致しなければ
  `tmux send-keys` は呼ばず「⌛ このプロンプトはもう画面にありません」に更新する。
  一致すれば `tmux send-keys -t <session> <数字>` で選択肢の番号だけを送る
  （**Enterは送らない**。Claude CodeのUIは数字キー単独で選択が確定するため）。
  他の人が押した場合はエフェメラルで「ありさんだけが押せます」と返す。
  処理後は元のSlackメッセージを「✅ Yes で承認 (日時)」のように更新し、ボタンを消す。

Anthropic/Claude APIは一切呼ばない。tmuxとSlackとだけやり取りする。

## 検出条件（正規表現）

- 行頭の枠線（`│`）やカーソル（`❯`）などの飾りを読み飛ばしつつ「N. Yes」「N. No」の行を拾う
  （`OPTION_RE` in `approve_bot.py`）。
- 「1. Yes」の行 **かつ** 「No」を含む選択肢の行、**かつ**「Do you want」という文言か
  カーソル `❯` のどちらかが存在する場合のみプロンプトとみなす。
  （単なる箇条書きに「1. Yes」「3. No idea…」のような文字列が偶然含まれても誤検出しないため）

## 対象セッション

環境変数 `SLACK_APPROVE_SESSIONS`（カンマ区切り）で指定する。**未設定時のデフォルトは
`claude,claude3,main`**。見張り対象（capture-paneするセッション）と、send-keysの送信先として
許可するセッションの両方に同じリストを使う。リストに無いセッション名へは、Slack経由であっても
tmux send-keysを送らない。

`main` はありさん本人の対話セッション用（`tmux new -s main` で動かす想定）。増やしたい場合は
`.env` の `SLACK_APPROVE_SESSIONS` を編集するだけでよい（コード変更不要）。

tmuxセッションが存在しない場合、そのセッションの見張りはスキップして待機する（エラーにしない）。

## 認証情報

`~/petit_claude/.env`（`PETIT_DATA_DIR`環境変数で場所を変更可）に以下を設定する:

```
SLACK_APPROVE_APP_TOKEN=xapp-...       # Socket Mode用
SLACK_APPROVE_BOT_TOKEN=xoxb-...       # chat:write
SLACK_APPROVE_CHANNEL=C0XXXXXXXXX      # 通知先チャンネル
SLACK_APPROVE_ALLOWED_USER=UCWJ8LJ3H   # ボタン操作を許可するSlackユーザーID
SLACK_APPROVE_SESSIONS=claude,claude3,main  # 省略可（省略時はこの値がデフォルト）
```

値はコードにハードコードしない・ログに出さない。

## 使い方

```bash
# 手動起動（フォアグラウンド、デバッグ用）
uv run python approve_bot.py

# バックグラウンド起動（多重起動防止つき。既に動いていれば何もしない）
./start_approve_bot.sh
```

## ログ・pid

- ログ: `~/petit_claude/.autonomous-logs/slack-approve.log`
  （起動ログ・見張りループの通知ログ・承認/拒否の操作ログすべてここに追記される）
- pidファイル: `~/petit_claude/.autonomous-logs/slack-approve.pid`（`start_approve_bot.sh`が管理）

操作ログの例:

```
2026-07-06 16:30:00 [OK] user=UCWJ8LJ3H session=claude choice=1 label=Yes
2026-07-06 16:31:00 [DENY-USER] user=U0OTHERPERSON session=claude choice=1
2026-07-06 16:32:00 [ERROR] user=UCWJ8LJ3H session=unknown-session choice=1 error=許可されていないセッション: unknown-session
2026-07-06 16:33:00 [STALE-SKIP] user=UCWJ8LJ3H session=claude choice=1 hash=09f0124c64d9
2026-07-06 16:34:00 [DUPLICATE-CLICK] message_ts=1234567.890 user=UCWJ8LJ3H
2026-07-06 16:40:00 [AUTO-DELETE] session=claude hash=09f0124c64d9 reason=vanished
2026-07-06 16:45:00 [STALE-RENOTIFY] session=claude hash=09f0124c64d9 elapsed=301s
```

## crontab への追加（提案・未反映）

このリポジトリからは crontab を直接編集しない。以下を手動で `crontab -e` に追加すること
（@reboot起動 + 5分ごとの見張り。`start_approve_bot.sh`は多重起動防止つきなので、
既に動いていれば5分ごとの呼び出しは何もしない）。

```cron
# slack-approve: 再起動時に自動起動 + 5分ごとに死んでいたら再起動
@reboot /home/cube-petit/work/embodied-claude/slack-approve/start_approve_bot.sh
*/5 * * * * /home/cube-petit/work/embodied-claude/slack-approve/start_approve_bot.sh
```

## テスト

```bash
uv sync --extra dev
uv run ruff check .
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run pytest -v
```

tmux・Slackはすべてモック。プロンプト検出の正規表現・dedupe・セッション名の許可判定・
Slackアクションハンドラ（本人確認・ボタン処理・メッセージ更新・操作ログ書き込み）を検証する。

## やらないこと

- `claude` / `claude3` 以外の未知のセッションへの送鍵（`SLACK_APPROVE_SESSIONS`に無い名前は拒否）
- Enterキーの送信（数字キー単独で選択させる。誤ってEnterまで送ると選択後の入力欄に
  意図しない空行が入るおそれがあるため）
- ボタンを押した人の検証をスキップすること（`SLACK_APPROVE_ALLOWED_USER`が空でない限り必ず確認する）
