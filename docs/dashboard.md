# ダッシュボード

[README](../README.md) に戻る

## ダッシュボード

- 欲求バー: 各プチの欲求レベルをリアルタイム表示
- チャット: プチに直接話しかける（複数モデル対応: Claude / Gemini / ChatGPT）
- **ターミナル（🖥️）**: ブラウザから Claude Code ターミナル（ttyd）を開く。キャラアイコンを選択して「チャット開始」を押すと `/chat` スキルが自動起動し、プチと SOUL.md ベースのチャットができる。セットアップは [`terminal-setup.md`](terminal-setup.md) を参照
- **だれかと 💬**: 話しかけるプチをトグルで選択して送信。選んだプチ同士で話させることもできる（「✨ 話させる」ボタン）
- **みんなで 🌟**: 全プチに同時送信（M5起動状態も確認できる）
- 設定: アクティブタイム・カメラ/音/マイクの ON/OFF
- 記憶一覧: 日付別の記憶表示
- 日記: 1日のサマリー（毎日23:50に自動生成）。材料はその日の記憶と、ぷちログの出来事（持ち上げられた・置かれた・だれと何回話した・ひとりの時間に何をしたか。中身は写さない）
- 交換ノート（📖）: キャラクター・人間全員参加のノート
- アルバム（🖼️）: キャラクター・人間別の写真アルバム（ぷち 50 枚・ありさん 200 枚・かぜおさん 50 枚、圧縮保存。`_album_limit`）

### M5タッチメニューフック

M5Stackの2×2タッチメニュー（CAM/SEN/MIC/SET）をタップすると、ダッシュボードの常時監視プロセスが自動応答する。

```
[M5タッチメニュー]
  ├ CAM タップ → dashboard がスナップショット取得（HTTP GET /snapshot）
  │              → Claude CLI でキャラクターが写真を見て感想をメール＋記憶保存
  │              → speak / show_face / play_sound で声・表情・SEを出す
  │
  ├ SEN タップ → dashboard がセンサーデータ取得（HTTP GET /sensors）
  │              → Claude CLI でキャラクターが周囲の状態をメール＋記憶保存
  │              → 同様に声・表情・SEで反応
  │
  └ MIC タップ → M5側でマイク自動起動、PCMバイナリ（16kHz int16）をWSで逐次送信
                  → 無音2秒で自動オフ＋ `mic_end` イベント送信
                  → dashboard がバイナリを蓄積し WAV化 → GPUサーバー（port 8765）でWhisper ASR
                  → 無音（テキスト空）ならスキップ
                  → テキストあり → Claude CLI が speak / メール / 記憶 で応答
```

CAM/SEN/MIC イベントはいずれも `call_claude` 経由で処理され、スピーカーが有効なら `speak` で声・顔・SEで即時リアクションを促す。MIC は GPU サーバー（`VOICE_API_HOST` 環境変数）での ASR が前提。

M5の設定画面（SET → CAM TO）でメール送信先のユーザーを切り替えられる。切り替えた設定は CAM / SEN / MIC の全イベントに反映される（`set_cam_target` WebSocket イベントでダッシュボードに通知）。

ダッシュボード起動時（lifespan）に全キャラ分のウォッチャーが起動し、M5との WebSocket 接続（port 8080）を常時維持・再接続する。

## ダッシュボードの常時起動（systemd）

PC再起動後も自動でダッシュボードが起動するようにする。

### 1. 環境設定ファイルを作成

`~/petit_claude/.env.dashboard` に環境固有の値を書く:

```bash
cat > ~/petit_claude/.env.dashboard <<'EOF'
PETIT_DATA_DIR=/home/yourname/petit_claude
DASHBOARD_HOST=0.0.0.0
DASHBOARD_PORT=8765
EOF
```

- `DASHBOARD_HOST`: `0.0.0.0` なら全インタフェースでリッスン。Tailscale IP を指定すると VPN 経由のみアクセス可能
- Tailscale IP の確認: `tailscale ip -4`

### 2. サービスを登録・起動

```bash
sudo cp dashboard/petit-dashboard.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable petit-dashboard
sudo systemctl start petit-dashboard

# 状態確認
sudo systemctl status petit-dashboard

# ログ確認
journalctl -u petit-dashboard -f
```

## 認証（オプション）

ダッシュボードに Basic 認証 + 7日間セッションを追加できる。

### ロール

| ロール | 閲覧 | チャット・操作 | 設定変更 |
|--------|------|---------------|---------|
| admin | OK | OK | OK |
| operator | OK | OK | NG |
| viewer | OK | NG | NG |

### 設定方法

`~/petit_claude/auth.json` を作成:

```bash
cp dashboard/auth.json.example ~/petit_claude/auth.json
vim ~/petit_claude/auth.json  # パスワードを設定
```

```json
{
  "users": {
    "arisan": {"password": "あなたのパスワード", "role": "admin"},
    "friend": {"password": "友達用パスワード", "role": "operator", "characters": ["puchiko"]},
    "guest": {"password": "ゲスト用パスワード", "role": "viewer"}
  }
}
```

ダッシュボードを再起動すると認証が有効になる。`auth.json` がなければ認証なし（従来通り）。

### ログイン画面からのお願い(新規登録・パスワードの出し直し)

ログイン画面の箱の下に「新規登録をお願いする」「パスワードを忘れた」がある。送れるのは**お願いだけ**で、アカウントを作る・
パスワードを決めるのは、家の持ち主が `auth.json` を手で直す(2026-11-14。`scripts/account_request.py`、`POST /api/public/account_request`)。

- お願いは、家の手紙箱に、家の持ち主への手紙(`from_login_to_<家の持ち主>_…md`、差出人「ログイン画面」)として入り、「メール」に未読で出る。
  手紙には、ユーザー名・呼び名・ひとこと・送ってきた場所(IP)と、家の持ち主が次にやること(その名前がもう使われているか、いない人か)が書いてある
- **パスワードは受け取らない**(手紙箱に、パスワードを書いた手紙を残さない)
- パスワードの出し直しでは、そのユーザー名がいるかどうかを、送った人に教えない(いつも同じ返事)
- 送りすぎを止める: 同じ場所から 1 時間に 3 通まで、家ぜんたいで 1 日に 12 通まで(ダッシュボードを入れ直すと数え直し)

### キャラクター表示制限

`characters` フィールドで、ユーザーごとに閲覧・操作可能なキャラクターを制限できる。

- `characters` 未設定 or 空配列 → 全キャラ見える
- `characters: ["puchiko"]` → puchiko のみ見える（タブ・チャット・記憶・日記すべて）
- `admin` ロールは `characters` 設定を無視して常に全キャラ見える
- グループチャットも許可キャラのみに送信される

### 見られる子が決まっている人(`characters` を書いた人)にできること

家に 2 人目の世話人がいて、その人の子が決まっているとき(`"characters": ["<その人の子>"]`)の決まり(2026-11-14):

- **会話・記憶・設定**は、自分の子だけ
- **🌱 ようす**は、どの子の分も見える(体につながっているか・眠っているか・電池)。体の設定を変えられるのは自分の子だけ。ほかの子の欲求と記憶は渡さない
- **メール**の差出人の色は、どの子も、その子の色で出る
- **みんなの会話**は、自分がした会話だけが出る(記録は 1 つで、発言ごとに「だれの会話か」を残す。古い発言は、家の持ち主の会話)。ぷちどうしの会話は、だれにでも出る
- **アルバム・ボイスメモ**は、みんなの分を見られる。消せるのは自分の分だけ。ボイスメモを録れるのも自分の分だけ
- **画面の設定**(トップバーの題と色・道具の列・送信のしかた)は、人ごと(下)
- 子が 1 人だけの人は、開いたときにその子が選ばれていて、「みんな」「だれか」は出ない
- **からだ おやすみ・「ここにいるよ」・音**(体の音の一覧、送る・鳴らす)は、自分の子だけ
- **人のボイスメモ**(家の持ち主・ほかの子)は、聞くだけ(名前を変える・鍵・消す・声の登録は出ない)
- **記念日**を直す・消すのは、自分が足したものだけ

#### 何を見せるかを、家の持ち主が決める(⚙️ 設定 → 👪 ひと)

家の持ち主(`characters` の無い admin。ログインの要らない家では、だれでも)の設定に「👪 ひと」が出る。見られる子が決まっている人ごとに、3 つを決める:

1. **だれの分を、見せるか・してよいか**(表。行 = 見せるもの、列 = ぷちたち + ほかの人)
   - **子**: その人の子。会話・記憶・設定・体の設定まで見られる。子にすると、下の行は自動で入る。`auth.json` の `characters` は、はじめの値(ここで決め直すと、こちらが効く)
   - **会話**: 子でなくても、話してよい子。話す・これまでの会話を読むことだけできる。話せる子が 2 人以上なら「みんな」「だれか」も出る
   - **メール受信**・**メール送信**: その子からの手紙を「メール」に出すか、その子に手紙を送れるか
   - **ぷちログ表示**・**日記表示**・**ノート表示**: その子の分を、見られるか
   - **アルバム表示**・**ボイスメモ表示**: その子・その人(家の持ち主など)の分を、見られるか。自分の分は、いつでも見られる
   - 決めていないとき: メール・アルバム・ボイスメモは、だれの分でも。ほかは、子だけ(いままでと同じ)
2. **見せるページ**: 道具を全部(設定を除く)。外すと、道具の列に出ず、ページも入口も開けない(403)。毎日の暮らしで使うものに「おすすめ」の印が付き、上に並ぶ。「おすすめにそろえる」「ぜんぶ見せる」で、まとめて決められる
3. **してよいこと**(たたんである。13 個): その人の子に「ここにいるよ」を送る / からだ おやすみ を使う / ようす から体の設定を変える / 自分のアルバムの写真・ボイスメモ・ノートを消す / 交換日記に書く / 記念日を足す・直す・消す / 音を取り込む・消す・体へ送る / 設定の アクティブタイム・自律行動・からだの使い方・くわしい設定 を変える。
   外すと、その人の画面から押すところが消え(ようす の「からだの設定」はカードごと、設定の段は薄くなって押せない)、入口でも断る(403)。はじめは全部「してよい」

使い方のページ(`/help`)は、見られる子が決まっている人には、できないこと・見せないページの行を出さない(行の頭の太字で見分ける。`dashboard/ui/help.html` の `CANNOT_LINES`)。

**お願いの口**: 見られる子が決まっている人の ⚙️ 設定 → 🏠 家 に「<家の持ち主>にお願いする」の欄が出る。送ると、家の手紙箱に
その人から家の持ち主への手紙(`from_<その人>_to_<家の持ち主>_…md`、頭に【お願い】)として入り、家の持ち主の「メール」に未読で出る(`POST /api/request`)。

決めた中身は `PETIT_DATA_DIR/config/access.json`(`{"<ユーザー名>": {"children": [...], "chat": [...], "mail_in": [...], "mail_out": [...], "petitlog": [...], "diary": [...], "notes": [...], "album": [...], "voice": [...], "hide_tools": [...], "can": {"rest": false, …}}}`)。入口は `GET` / `POST /api/access`(家の持ち主だけ)。

## ライブラリ(📚)

棚は 2 つ。**じぶんの本**は `PETIT_DATA_DIR/library/<ユーザー名>/`、**みんなの本**は `PETIT_DATA_DIR/library/` の直下(ぷちたちが読む本と同じ棚)。
どこまで読んだか(しおり・読了)は、どちらの本も人ごとに `library/<ユーザー名>/.bookmarks.json` に持つ(みんなの本は `shared/<ファイル名>` の名前で)。

## タブの印(favicon)

3 つの点。色は、その家のぷちたちの色(一覧の順に 3 人まで。足りない分は薄い紫)。絵のファイルは置かず、家の設定から描く
(`/favicon.svg`、SVG を出せないブラウザ用に `/favicon.ico`(中身は PNG)、ホーム画面用に `/apple-touch-icon.png`)。ログインの前でも読める。

## 家の設定（`config/ui.json`）

**人ごとに持つ**: ログインなしで開いたとき(この PC から、など)と家の持ち主(`arisan`)は `config/ui.json`。ほかの人は `config/ui.<ユーザー名>.json`。
まだ自分の設定が無い人は、家の持ち主の設定から始まる(トップバーの色だけは引き継がず、ぷちの色になる)。
**📍 の候補**(`now_presets`): 「自室・お外・会社」を、自分の言葉に変えられる(4 つまで、5 字まで。空にすると、はじめの候補に戻る)。
**📍 から送る相手**(`hello_to` / `rest_to`): 右上の 📍 の「ここにいるよ」「からだ おやすみ」を、だれに届けるか。子ごとの粒を押して選ぶ。みんな選んであれば「みんな」(あとから迎えた子にも届く)。
トップバーの色は、1 色だけ取っておける(`topbar_saved`)。「ぷちの色に戻す」のあとでも、取っておいた色に戻せる。


家ぜんたいの見た目と使い方の設定。置き場所は `PETIT_DATA_DIR/config/ui.json`（git には入れない）。ダッシュボードの道具の列「⚙️ 設定」（はじめは「ほか」の中。`/settings`、中身は `dashboard/ui/settings.html`）の「🏠 家」から変えられる。

道具の列「⚙️ 設定」は 1 ページ（`/settings`。アルバムと同じく会話の場所に出る）。上の粒で 家 / 各ぷち を切り替える（1 人を選んでいればその子、「みんな」「だれか」なら家が最初に出る）。その子の `characters/<id>/config/settings.json`（アクティブタイム・今日のスケジュール・頻度・1 回の最大ターン数 `max_turns`・からだの使い方 `body`・からだ おやすみ `rest`）と、「くわしい設定」に体のアドレス（`config.json` の `m5_hosts`）。cron で動き出す時刻は crontab を読んで見せるだけ（`GET /api/<id>/cron`。画面からは変えない）。

| 項目 | 中身 |
|---|---|
| `topbar_color` | トップバーの色（`#rrggbb`）。無ければ、選んでいるぷちの色 |
| `house_title` | トップバーの題。無ければ「`<COMPANION_NAME>`ち」 |
| `notebook_dot` | 交換日記: 自分の番(3 人が一周)のときに 📖 へピンクの点を出すか。既定 true |
| `tools` | 道具の列の並び。`[{"id": "album", "show": true, "off": false}, …]` の順。`show: true` は最初から列に、`show: false` は「ほか」を押したら、`off: true` は出さない |
| `send_key` | 話しかける欄の送り方。`enter`（Enter で送信）か `ctrl_enter`（Ctrl+Enter で送信、Enter は改行） |

## 部品とページ（`dashboard/ui/`）

見た目の部品は `dashboard/ui/` に分けて置く。新しいページはここに 1 ページ 1 ファイルで足し、`main.py` には経路だけを書く。

| ファイル | 中身 |
|---|---|
| `tokens.css` | 色・角丸・余白・文字（デザイントークン）。部品はこの名前だけを使う |
| `atoms.css` / `molecules.css` | 原子（ボタン・入力欄・スイッチなど、`a-`）と分子（カード・設定の行など、`m-`） |
| `pages.css` / `page.js` | `ui/` のページの枠組みと共通の下ごしらえ |
| `embed.css` | 古いページ（アルバム・ボイスメモ・ノート・交換日記・ライブラリ）を、トップページの会話の場所に出すときの配色 |
| `md.js` | markdown を HTML にしたあとの後始末 |
| （家の中の場所） | `PETIT_DATA_DIR/config/spots.json`（部屋・場所・その部屋の SwitchBot の機体。設定ページ「家の中の場所」、`GET/POST /api/spots`）と、体の場所 `characters/<id>/state/spot.json`（ようす の「いる場所」、`POST /api/<id>/spot`。`scripts/spots.py`）。📍 の体の居場所に「家(あり部屋:ソファ)」、家の空気の 1 行はいる部屋の機体が先 |
| （場所の「かも」） | 体のまわりの Wi-Fi の強さからの見立て。体のファームに `/wifi_near` がある子だけ。体験デーモンが家の `config/spot_guess.json`(子ごとの `ch`・`every_s`・`rules`)を見て体に聞き、`characters/<id>/state/wifi_near.json` に残す。決まりに合えば、人が押していなくても 📍 に「あり部屋:ソファかも」。決まりの書き方は `scripts/spots.py` の頭。設定が無ければ何もしない |
| （手紙の Slack 通知） | 自分あての手紙が届いたら、Slack に「だれから、何通」だけ(本文は送らない)。人ごとの設定は家の `config/mail_notify.json`(設定ページ「🔔 Slack 通知」、`GET/POST /api/mail_notify`、ためしは `POST /api/mail_notify/test`)。送るのは `scripts/mail_notify.py run`(cron で 5 分ごと。`*/5 * * * * python3 <このリポ>/scripts/mail_notify.py run`)。出さない時間のあいだは送らず、明けてからまとめて 1 回。ボットの鍵は `.env` の `SLACK_APPROVE_BOT_TOKEN` |
| （部屋） | SwitchBot のハブ 2・温湿度計・人感・電気を `scripts/room_log.py record` が 10 分ごと(cron)に家の `state/room/YYYYMMDD.jsonl` と `latest.json` に残す(鍵は家の `.env` の `SWITCHBOT_TOKEN/SECRET`。機器は種類で自動。`config/room.json` の `off` で機体ごとに切る(設定ページ「SwitchBot 連携」、`GET/POST /api/room/devices`)・`names` で言い換え)。PC に差した OMRON 2JCIE-BU01 は `scripts/omron_env.py` で読み、ポート `/dev/omron-env`(udev の決まり `99-omron-2jcie-bu.rules` が作る。家の PC には 11/14 に置いた)があれば id `omron-env` の 1 台として同じ記録に入る(気温・湿度・明るさ・気圧・騒音・eCO2・eTVOC。`config/room.json` の `omron` で port と名前)。ようす の「部屋」カード(`/api/room/latest`)、📅 の日の欄(`/api/room/day`、カレンダーの `room`)、ぷちへは、その子に前に伝えた値から 2℃ / 10% / 3 hPa 以上動いたときだけ「家の空気が変わった: …」(`room_log.py changes --character --mark`、`characters/<id>/state/room_told.json`)。ふだんは `room_log.py line` で見に行く |
| （からだ） | からだの使い方 = 見る(カメラ)・話す(声)・鳴らす(効果音)・聞く(マイク)。`settings.json` の `body`（無ければ古い `allow_camera` など）。からだ おやすみ = 見る・話す・鳴らす を止める（`rest.until` = 📍 や設定ページの「いまから n 分」、`rest.hours` = 毎日この時間）。決まりは `scripts/body_switches.py` 1 か所で、会話・体のイベント・自律行動とも同じ。止める道具は `--disallowedTools` で本当に使えなくし、文でも伝える（`prompts/autonomous/permission_rules.md`）。📍 の「からだ おやすみ」は 3 人まとめて（`/api/switches/rest`） |
| （アクティブタイム） | 始まり ≦ いま < 終わり。終わりの時刻そのものは入らない（`autonomous-action.sh` の `check_entry`）。3 人の cron は 0・5・10 分とずれているので、終わりは cron の分より後ろ（:20 など）に。設定ページが「1 日に動く予定」を数え、終わりが cron の分と重なっていれば注意を出す |
| `help.html` + `help.md` | 使い方（`/help`、道具の列の「📖 使い方」。はじめは「ほか」の中）。本文は `help.md`（「〜したいとき」の形、仕組みは書かない）。見出しの `{#id}` が飛び先で、設定ページの「？」はそこへ飛ぶ。検索欄で絞り込める |
| （ノートの印） | ★・既読・ピン留めは人が付ける印で、家の `state/note_stars.json`・`state/note_reads.json`・`state/note_pins.json`（ピン留めは自分だけ、ぷちに知らせない。`GET /api/notes/pins` `POST /api/notes/pin`）（ぷちのノートは触らない。`scripts/note_marks.py`）。`GET /api/notes/stars` `POST /api/notes/star`、`GET /api/notes/reads` `POST /api/notes/read`。読まれた・★ が付いたことは、手紙の受け取りと同じ形で、次の会話か自律行動で 1 回だけその子に伝わる（`note_marks.py notice --mark`、`prompts/autonomous/user.md` の `note_mark_notice`） |
| `settings.html` | 設定（`/settings`）。家（トップバーの色・送信のしかた・道具の列 = `/api/ui`）と、ぷちごと（アクティブタイム・自律行動・からだの使い方・からだ おやすみ・体のアドレス = `/api/<id>/settings` `/api/<id>/switches` `/api/<id>/switches/rest` `/api/<id>/config/m5_hosts` `/api/<id>/cron`）。家の設定を変えたら親ページに `petit-ui-changed` を送る |
| `petitlog.html` / `diary.html` | ぷちログ（1 日のタイムライン）と日記の一覧。データの組み立ては `dashboard/petit_log.py`（読むだけ） |
| 右上の 📍 | いま どこ。わたしのいま（自室・お外・会社 など）を決めると `PETIT_DATA_DIR/state/whereabouts.json` に、ログインの人ごとの一言と、決めた時刻(since)・いつまでか(until。1・3・8 時間か「消すまで」)が入る。過ぎたら無いものとして扱う。ぷちの体の居場所（家 / お外）は、体験デーモンが `characters/<id>/state/experience_state.json` に書く体の Wi-Fi（何番目か）から決める。どの番号がどこかは `PETIT_DATA_DIR/config/places.json`（無ければ 1・2 = 家、3 = お外）。計算と保存は `scripts/whereabouts.py`。会話の system prompt と自律行動の冒頭に「ありさんのいま: 会社(9:02 から)」「あなたの体のいま: 家(家の Wi-Fi)」と伝わる。**スマホがどの部屋にあるか**は、Android の Garmin BLE Bridge アプリが家の SwitchBot の機体(機体 ID = BLE の MAC)の電波を聞いて `POST /api/beacons/report` に 30 秒ごとに送り、`scripts/phone_place.py` が `config/spots.json` の部屋に直して `state/phone_place.json` に覚える(直近 3 回の中央値、6 dB の差があるときだけ移る、4 分で古くなる)。アプリは `config/beacons.json` の鍵(`phone_place.py key <ユーザー名>` で作る)を `X-Petit-Key` で名乗り、聞く MAC は `GET /api/beacons/config` で受け取る。ぷちには毎回は渡さず、「見に行けるもの」の入口(`phone_place.py line`)と、部屋が変わった・帰ってきた・出たときだけの 1 行(`phone_place.py changes --character <id> --mark`、伝えたことは `characters/<id>/state/phone_told.json`) |
| `calendar.html` | 📅 よてい（`/calendar`）。月のカレンダーに 日本の祝日（`scripts/jp_holidays.py`、計算で出す）・空の暦（`scripts/sky.py`: 新月/上弦/満月/下弦の日の印、二十四節気、日の出入り。場所は家の `config/place.json` の lat/lon。ぷちには満月・新月・節気の境目の日だけ 1 行(`sky.py changes`。ふだんは `sky.py line` で見に行く。ぷちたちの希望、2026-11-14)）・予定（`PETIT_DATA_DIR/config/events.json`、`scripts/events.py`。題・日〜終わりの日・時間・場所・行く人や子 `who`・ひとこと）と 記念日 を一緒に出し、日を押して足す・直す・消す（`/api/events`、`/api/calendar?month=`）。🎂 記念日の道具はここに吸収（ページ `/anniversaries` は残る）。7 日以内の予定が、会話の system prompt と自律行動の冒頭に「近い予定:」として入る（`events.py lines --character`。行く子でなければ「自分は留守番」）。当日はぷちログのその日のいちばん上に 📅 で出る |
| `anniversaries.html` | 記念日（`/anniversaries`）。家の設定 `PETIT_DATA_DIR/config/anniversaries.json` に、名前・最初の日・くり返し（毎年・毎月・その日だけ）・ひとことを足す。計算と保存は `scripts/anniversaries.py`。当日は、ぷちログのその日のいちばん上に出る。ぷちたちには、前の日の自律行動で 1 回だけ「あしたは○○の日」と伝わる（`anniversaries.py notice`。前の日に動かなかった子には当日に）。ぷちも `anniversaries.py add` で足せる |
| `desires.html` | 欲求の様子（`/desires`）。その子の欲求ごとに、この数日の強さの線・上限にいた時間・いちばん強かった時間・満たした記憶の回数と、その欲求の決まり（満たすまでの時間・満たしたことになる言葉）を出す。データの組み立ては `dashboard/desire_history.py`（読むだけ） |
| `sounds.html` | 音（`/sounds`）。家の音のライブラリ `PETIT_DATA_DIR/sounds/` に音を取り込む（WAV・MP3 などを、体が鳴らせるモノラル・16 kHz・16 bit の WAV に変換。20 秒まで）、ブラウザで聞く、ぷちの体（SD）へ送る、消す。ぷちそれぞれの体にある音の一覧も出て、押すとその子の体で 1 回鳴る。体は音を取り出す・消すができないので、元になる音は家に置く。置き方と変換は `scripts/sounds.py`（ffmpeg が要る） |
| `kairanban.html` | 回覧板（`/kairanban`）。ぷちたちへの知らせ（`PETIT_DATA_DIR/kairanban/<yyyy-mm-dd>_<hhmm>_<話題>.md`。時刻と話題は無くてもよい）を、新しい順に 1 号 1 枚のカードで。題を押すと開く。本文は markdown。題の横に日付と時刻、ぷち 1 人に 1 つの点（読んだ = 塗る / 届いたがまだ = 輪 / 届けていない = 点線）。届いたか・読まれたかは、同じ本文の手紙をメールボックスから探して決める（`scripts/kairanban.py`、`GET /api/kairanban`）。号を開くと「届ける」（`POST /api/kairanban/send`。まだ届いていない子へ、押した人の名前で手紙として置く。号の日付の 2 日前〜7 日後だけ） |
| `costs.html` | おかね（`/costs`）。API 代。上に 今日・今月・残り、その下に 今月の予算（色と言葉で ゆとり / そろそろ / 上限に近い）、だれが・何に・どの日に の内訳。数字は `/api/costs` |
| `himitsu.html` | ひみつ（`/kankei`）。手紙を読む。「ぷちどうし / みんなのメール」の切り替え、だれから・だれあて の絞り込み、1 通は差出人の色の 1 枚、本文は markdown（HTML のタグは文字として出す）。手紙は `/api/secret_mails` から少しずつ。関係の図は `/relations`（🤝 関係） |
| `styleguide.html` | 部品の見本（`/ui`） |

Web フォント・markdown の変換・会話の画像化は、外の CDN（Google Fonts・jsDelivr）から部品を読む。届かないときは、端末のフォントと素の文字で出る。

## ぷちに渡す文(2026-11-13)

会話の system prompt、写真・声の前置き、来場者、ぷち同士、体のイベント(カメラ・センサー・マイク)、展示の一言、日記の文は `prompts/dashboard/*.md`(一覧は `prompts/README.md`)。`main.py` は `_prompt("<名前>", **値)` で組み立てるだけで日本語の文を持たない。
家ごとの言い回しは `PETIT_DATA_DIR/prompts/dashboard/<同名>.md` を置けば上書き(ダッシュボードの再起動は不要。毎回読む)。展示用の固定の紹介文は `prompts/dashboard/display_char_info.json`(同じく家で上書き可)。

