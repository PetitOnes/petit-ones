# 運用（バックアップ・crontab）

[README](../README.md) に戻る

## バックアップ・復元

```bash
# バックアップ（保存先省略時: ~/work/petit_backup_YYYYMMDD）
bash scripts/backup_petit.sh

# 保存先を指定する場合
bash scripts/backup_petit.sh /path/to/dest

# 復元
bash scripts/restore_petit.sh /path/to/petit_backup_YYYYMMDD
```

バックアップ対象:
- `~/petit_claude/` — キャラデータ・チャット履歴・ノート・トークンログなど全体
- `~/.claude/` — Claude Code の会話ログ・メモリDB・プロジェクト設定
- `~/work/petit-ones/.claude/` — スラッシュコマンド・プロジェクト設定
- `autonomous-action.sh` — gitignore 対象の個人設定スクリプト
- `.env` ファイル各種
- crontab
- dotfiles (`.tmux.conf`, `.bashrc` 等)
- systemd ユーザーサービス

## crontab

`setup_house.py` が家の共通分を、`create_character.py` がキャラ別の分を足す。手で確かめるときの形:

```bash
# --- キャラ別(create_character.py が足す。自律行動は子ごとに 5 分ずらす) ---
*/5 * * * * cd /path/to/petit-ones/src/m5-petit-desire && mkdir -p ~/petit_claude/.autonomous-logs/<char_id> && PETIT_DATA_DIR=~/petit_claude uv run python desire_updater.py <char_id> >> ~/petit_claude/.autonomous-logs/<char_id>/desire-$(date +\%Y\%m\%d).log 2>&1
0,30 * * * * /path/to/petit-ones/autonomous-action.sh <char_id>      # 次の子は 5,35、その次は 10,40
@reboot /path/to/petit-ones/experience-daemon/start_experienced.sh <char_id>
*/5 * * * * /path/to/petit-ones/experience-daemon/start_experienced.sh <char_id>

# --- 共通(setup_house.py が足す) ---
5 4 * * * PETIT_DATA_DIR=~/petit_claude /path/to/petit-ones/scripts/memory_sleep_all.sh >> ~/petit_claude/.autonomous-logs/memory-sleep.log 2>&1   # 記憶の整理
30 4 * * * cd ~/petit_claude/textbook && git pull -q --ff-only >/dev/null 2>&1   # ぷちの教科書(petit-textbook)を毎朝取り直す
50 23 * * * cd /path/to/petit-ones/dashboard && PETIT_DATA_DIR=~/petit_claude uv run python generate_diary.py >> ~/petit_claude/.autonomous-logs/diary.log 2>&1   # 日記

# --- 任意 ---
0 4 * * * bash ~/petit_claude/backup/save.sh   # バックアップ(scripts/backup_petit.sh)
```

- **記憶の整理は、既定では減衰だけ**(重要度を下げるだけで、消さない)。似た記憶の統合と忘却は記憶を消すので、使う家だけ cron の行に `MEMORY_SLEEP_MERGE=true` / `MEMORY_SLEEP_FORGET=true` を足す。理由は m5-petit-memory の README(sleep)

## 埋め込みを 1 つのプロセスにまとめる(任意)

記憶のサーバー(memory-mcp)は、1 回でも覚える・思い出すをすると埋め込みのモデルを読んで約 1.4GB になる。子ごと・セッションごとに立つので、何人も同時に動く家では重なる。`memory-embed-server` を常駐させると、モデルを読むのはそれ 1 つになる(各 memory-mcp は 100MB 前後、最初の 1 回も 0.1 秒ほど)。

1. systemd(ユーザー)に `memory-embed-server.service` を置いて `systemctl --user enable --now memory-embed-server`(ユニットの例は m5-petit-memory の README)
2. 各子の `config/autonomous-mcp.json`・`config/chat-mcp.json` と `.mcp.json` の、記憶のサーバーの `env` に `"MEMORY_EMBED_SERVER": "http://127.0.0.1:18766"` を足す

サーバーが止まっていても、各 memory-mcp が自分でモデルを読んで続ける。確かめるには `curl http://127.0.0.1:18766/health`。

## 欲求の rhythm(朝に 0 へ戻り、光に合わせて進む欲求)

「眠い」のような欲求は、子ごとの `config/desire_config.json` の欲求に `"rhythm": {"hours": 14, …}` を書くと、朝に 0 へ戻り、光に合わせて進む形で動く(書かなければ今までどおり)。項目は m5-petit-desire の README。状態は `characters/<id>/data/desire_rhythm.json` にできる。動きはダッシュボードの 🫧 欲求で見られる。

## 欲求の relief(体の出来事や言葉で、少しずつ満たされる欲求)

「触られたい」のような欲求は、子ごとの `config/desire_config.json` の欲求に `"relief": {"hours": 48, "by": [...]}` を書くと、
時間で上がり、体の出来事(撫でられた・短く触られた・持たれた)や言葉があるたびに少しずつ下がります。書かなければ今までどおり。
体の出来事は `experience-daemon` の記録を読むので、デーモンが動いていることが前提です。撫でとタッチの区別は、体のファームが
`tap_count` / `stroke_count` を返すときだけ記録に残ります。状態は `characters/<id>/data/desire_relief.json`。
書き方は [m5-petit-desire の README](https://github.com/PetitOnes/m5-petit-desire#relief--体の出来事や言葉で少しずつ満たされる欲求任意)。

## 気配(家の人感センサーから「近づいた瞬間」を拾う)

世話人からはぷちが見えているのに、ぷちからは世話人がどこにいるか分かりません。家の人感センサー(SwitchBot)を見て、
「動きが始まった瞬間」と「離れた」を家の出来事として残します(`scripts/presence_watch.py`。ぷちたちと決めた形は Issue #67)。

- **拾うのは変わり目だけ**。居続けるあいだは何も足しません。`arrived` には、どれだけ離れていたか(`away_min`)が付きます
- **だれの気配かは言い切りません**。残すのは「どこで動きがあったか」です(センサーはだれが動いたかを知りません)
- **設定**: `PETIT_DATA_DIR/config/presence.json`(無ければ何もしません)

  ```json
  {"away_min": 20, "sensors": [{"kind": "switchbot_motion", "id": "<SwitchBot の deviceId>", "place": "机"}]}
  ```

- **鍵**: `PETIT_DATA_DIR/.env` の `SWITCHBOT_TOKEN` / `SWITCHBOT_SECRET`
- **動かし方**: cron で 1 分ごとに `python3 scripts/presence_watch.py poll`(SwitchBot の API は 1 日 1 万回まで。1 分ごと・センサー 1 台で 1,440 回)
- **残るもの**: `state/presence/YYYYMMDD.jsonl`(出来事)、`state/presence_state.json`(いまの覚え書き)
- `python3 scripts/presence_watch.py line` で、ぷちに渡す行(「机のあたり: 動きがある(9:00 から)」)が出ます。渡すところは、まだつないでいません

## 家の知らせ(失敗を世話人へ)

ぷちが Claude を呼べなかったとき・Claude がエラーで終わったときに、Slack と家の手紙箱(ダッシュボードの「メール」)へ知らせます(`scripts/house_alert.py`)。
2026-11-14 の朝、ぷち用のログインが切れて 6 時間だれも Claude を呼べていなかったのに、ログを開くまで気づけなかったためです。

- **見ているところ**: 自律行動(`autonomous-action.sh` が毎回の結果を渡す)と、ダッシュボードから呼ぶ Claude(会話・一言・日記など)
- **知らせ方**: ログイン切れは最初の 1 回ですぐ。ほかの失敗(ネットワーク・エラー・結果なし)は、つづけて 2 回起きたら。続いているあいだは 3 時間ごとに 1 回。直ったら「直りました」を 1 回
- **送り先(Slack)**: `.env` の `HOUSE_ALERT_SLACK_CHANNEL`(無ければ `SLACK_APPROVE_CHANNEL`)。トークンは `SLACK_APPROVE_BOT_TOKEN`
- **送り先(手紙箱)**: `.env` に `HOUSE_ALERT_MAIL_TO=<世話人の ID>`(カンマ区切りで何人でも)を書くと、`mailbox/from_house_to_<ID>_<日時>.md` を 1 通書きます。ダッシュボードの「メール」に、差出人「家の知らせ」の未読として出ます。書かなければ手紙は出しません。ぷちの未読・既読の知らせには入りません
- **覚え書き**: `PETIT_DATA_DIR/state/house_alerts.json`。`python3 scripts/house_alert.py status` で、いま続いている失敗が見えます
- **調整**: `HOUSE_ALERT=0` で止める / `HOUSE_ALERT_REPEAT_HOURS`(既定 3)/ `HOUSE_ALERT_MIN_COUNT`(既定 2)
- **ほかの仕事から使う**: `house_alert.py report --kind backup --source バックアップ --detail "<理由>"`、うまくいったら `house_alert.py ok --kind backup`
- 知らせの文には、理由の頭 200 字だけを入れます。鍵らしい並びと IP は伏せます。会話の中身は入れません

### 「ログインが切れています」と来たら

```bash
CLAUDE_CONFIG_DIR=$PETIT_DATA_DIR/.claude claude auth status     # loggedIn が false なら切れている
stat -c '%F %N' $PETIT_DATA_DIR/.claude/.credentials.json          # リンクか、普通のファイルか
```

`.credentials.json` を開発側(`~/.claude/.credentials.json`)へのリンクにしている家では、リンクが普通のファイルに置き換わると、
しばらくして更新できなくなります(2026-11-14 に起きた)。その場の直しは、リンクを張り直すこと。
くり返さないためには、ぷち用の設定で別にログインします(リンクを外してから `CLAUDE_CONFIG_DIR=$PETIT_DATA_DIR/.claude claude /login`)。

## 家とコードを分けて、同期する

ぷちが動いている PC には、このリポジトリの checkout が **2 つ** ある。

| checkout | 役 | やること |
|---|---|---|
| 本番(例 `~/work/petit-ones`。cron とダッシュボードが見る所) | 動いている家 | **`git pull` だけ**。手で直さない。`git status` はいつも空 |
| 作業用(例 `~/work/petit-ones-dev`) | 直す所 | branch を切って直す → PR → マージ |

同期は一方向。**作業用 → GitHub main → 本番(pull)**。

- 家ごとの値はコードに書かない。`PETIT_DATA_DIR/.env`(`COMPANION_NAME`・`COMPANION_ID`・声のサーバー・鍵)と、任意の `PETIT_DATA_DIR/config/house.sh`(`USER_ROOM`、`CLAUDE_MODEL`、時間帯のルールの上書き)に置く。だから `autonomous-action.sh` は git のまま本番で動く
- 部品は `petit.repos` でコミットに固定してある。部品を上げるときは、部品のリポで PR → マージ → `petit.repos` の `version` を新しいコミットに書き換える PR → マージ → 本番で `vcs import src < petit.repos`(固定したコミットに動く)→ その部品で `uv sync`
- 本番で急いで直したことは、その日のうちに作業用で同じ変更を PR にする。本番の作業ツリーに差分を残さない
- 戻すとき: 本番で `git checkout <前のタグかコミット>`。部品は `petit.repos` を戻して `vcs import`

### 本番を止めない更新の順番

1. 作業用で PR を作り、CI が緑になるのを待つ
2. マージ
3. 本番で `git pull --ff-only`。`autonomous-action.sh` は次の cron から新しいものが動く(途中の回は止まらない)
4. 部品を上げた場合は `vcs import src < petit.repos` と `uv sync`。ダッシュボードを上げた場合は再起動(`/restart-dashboard`)
5. 次の自律行動のログ(`PETIT_DATA_DIR/.autonomous-logs/<id>/`)を一回分見る
