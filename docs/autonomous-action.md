# 自律行動

[README](../README.md) に戻る


`autonomous-action.sh` が cron で30分毎に実行され、キャラクターが自律的に行動する。

## 実行フロー

```
[cron: 5分毎]
└→ desire_updater.py <char_id>
   ├ desire_config.json を読む
   ├ memory.db からキーワード検索（時間ベース計算）
   ├ M5の /sensors にHTTPリクエスト（センサー効果）
   ├ 相互作用を計算
   └→ desires.json に書き出す

[cron: 30分毎]
└→ autonomous-action.sh <char_id>
   ├ アクティブ時間帯か確認（非アクティブなら確率実行）
   ├ SOUL.md, ROUTINES.md, desires.json, relations.json を読む
   ├ M5センサーのスナップショットを取得
   ├ プロンプトを組み立て
   ├ claude -p <prompt> --allowedTools ... を実行
   │  ├ m5-mcp: take_snapshot, show_face, ...
   │  ├ memory-mcp: remember, recall, ...
   │  ├ desire-system: satisfy_desire, ...
   │  └ notes-mcp, relations-mcp, ...
   └→ .autonomous-logs/<char_id>/ にログ

[cron: 毎日23:50]
└→ generate_diary.py（全キャラの日記サマリー生成）
```

## スケジュール制御

- **アクティブ時間帯**（`settings.json` の `active_hours`）: 30分毎に毎回実行
- **それ以外の時間帯**: 実行しない(スキップ)。cron の分のずれ(子ごとに 5 分)は同時起動を避けるためのもの
- **「時間外も起きている」**: `settings.json` の `awake.until`(`scripts/awake.py`、設定ページのボタン)が未来のあいだは、時間外でも上と同じ 30 分ごとに実行する。過ぎたら自然に戻る

## ぷちボタン(2026-11-18)

家の人が持ち歩くボタン(ATOM ECHO + ENV PRO + GPS)。押した分を、まだ伝えていない子に 1 行ずつ(`scripts/puchi_button.py line --mark`、新しい 5 回まで)。短く押す = おいておく(この 1 行だけ)、長く押す = 知らせる(体のボタンの「聞いて聞いて」と同じく、ダッシュボードがその場で 3 人を順に起こす。プロンプトは prompts/dashboard/event_button.md、返事は手紙。起こした子にはこの 1 行を出さない。外でためてあとから届いた分は、この 1 行だけ)。中身は押した時刻・まわりの空気(気温・湿度・気圧)・場所の印。座標は家に来ない: ボタンの中で 3 つの細かさ(まち・近所・その場)に丸めて、ボタンの中だけの鍵で HMAC にした 6 文字。ぷちには「前にも押した印か / はじめてか」だけ伝える。届かないときはボタンの中にため、つながったときにまとめて送る(時刻は「何秒前」で来る)。外では BLE でも 30 秒「押した」を出し、スマホの「ぷちのポケット」が拾って `/api/beacons/button` へ(スマホの鍵で名乗り、中身はボタンの鍵の HMAC で確かめる。外で長く押しても、その場で起こせる)。鍵は config/button.json(6 桁の番号と引き換え、設定 → 家 → 🔘)。

## ぷち時計への通知(2026-11-17)

- 家の人が時計(家の表示機)を持っていて、夜(0〜7 時)でなく、通知がオンのときだけ、プロンプトに「⌚ 時計に送れる」1 行が入る(`scripts/watch.py line`)。送れないときは何も入らない
- 送るのは `scripts/watch.py send`(1 人 1 日 3 回・3 行 40 字。送る直前にもう一度確かめる)。家の人が時計で「見たよ」を返した分だけ、次の回に 1 行(`watch.py notice`)
- 時計は 5 分ごとに `/api/watch/sync`(鍵は `config/watch.json`)。持っているか = 10 分以内に連絡があり、15 分以内に動いていて、充電中でも伏せてもいない


## 合奏(2026-11-17)

家の人がダッシュボード(🔔 音 → 🎼 合奏)で、作った音・家の音・自分のボイスメモをずらして重ね、1 つの音にまとめる(`scripts/ensemble.py`)。まとめた音はその人の「作った音」に置く。自分の音が入った子には、`sing.py notice`(自律行動の sing_notice)で 1 行(だれの音が何秒から重なったか)。3 人の体で同時に鳴らすのは、まだ。

## 合作日記の紙(2026-11-17)

ありさんが日記を書く日に、ぷちたちの「きょうの紙」を感熱紙(Phomemo M02S)に刷って日記の縁に貼る。決まりは 3 人の返事から。

- 夜 19 時から、その日まだ紙を作っていない子にだけ、プロンプトに 1 行(`scripts/diary_slip.py line`)。作らない日があってもいい
- 紙は 1 人 1 日 1 枚。載せるものは自由(ありさん): 一言・詩(`--text`)、一日の線(`--line`。体の明るさ・傾き、部屋の温度・湿度・CO2・気圧・音)、撮った写真(`--photo`)、絵(`--drawing` で 🎨 えがく の自分の絵、`--draw` で SVG の線・形・文字)、音のグラフ(`--sound heard:<id>` か家の音の名前)。好きな順に 6 つまで(写真と絵は 1 つ)、1 枚 8 cm まで(3 人で日記帳の 1 ページの縦くらい)。紙の端のひとこと(`--edge`、30 字)。線と音は作ったときの数字を、写真と絵は写しを残す。その日のうちは作り直せる(刷る前なら)
- ありさんの日記は読まない。紙はその子の一日から作る
- 刷るのは、ありさんがダッシュボードの 🧾 合作日記 で押したときだけ。刷らない紙は「しまう」(ぷちの側に残る)
- 置き場所: `state/diary_slips.json`。プリンターの住所は家の `.env` の `PRINTER_ADDRESS`
## ぷち専用の Claude 設定(CLAUDE_CONFIG_DIR)と cwd(2026-11-13)

ぷちの `claude`(自律行動・ダッシュボードの会話・ターミナルチャット)は、**cwd を家(`PETIT_DATA_DIR`)にし、`CLAUDE_CONFIG_DIR` を `PETIT_DATA_DIR/.claude/`(あれば)にして**起動する。
Claude Code は cwd とその祖先の `CLAUDE.md` / `.claude/CLAUDE.md`、設定ディレクトリの自動メモリ(`projects/<cwd>/memory/MEMORY.md`)を全部読むので、
リポの中を cwd にしたり開発者の `~/.claude` を使ったりすると、開発者向けの指示やメモがぷちのセッションに混ざる。

- 置き場所: `PETIT_DATA_DIR/.claude/`(git には入れない)。中身は `settings.json`(language・model・Stop フック程度)、`.credentials.json`(`~/.claude/.credentials.json` へのリンク)、`.claude.json`(オンボーディング済みの状態を写し、家のディレクトリを信頼済みに)、`commands/`(`.claude/commands/*.md` へのリンク)、`projects/<cwd>/memory/`(ぷちの自動メモリ)
- 変えるなら環境変数 `PETIT_CLAUDE_CONFIG_DIR`。ディレクトリが無ければ今までどおり `~/.claude` を使う
- 開発者側の注意: `~/.claude/CLAUDE.md` は家の祖先(`$HOME/.claude/CLAUDE.md`)としても読まれる。開発用の全体指示は `~/work/CLAUDE.md` など、家の祖先でない場所に置く

## 付けるファイルの重さの見張り(2026-11-13)

Claude Code は、大きすぎる `@` 添付を黙って落とす(実測: 70 KB は付く、85 KB は落ちる)。自律行動は毎回 `SOUL.md`・`TODO_ACTIVE.md`(無ければ TODO.md)・`diary_summary.md` の大きさを測り、
`PROMPT_FILE_WARN_KB`(既定 40)以上なら、(1) ログに `[prompt-size] …` を残し、(2) 本人のプロンプトに「## 注意: 自分のファイルが重い」として軽くする手順を入れ(消さず移す)、(3) `scripts/slack_notify.py` で 1 日 1 回 人にも知らせる(`state/.prompt-size-notified` に日付。`PROMPT_SIZE_SLACK=0` で止められる)。
ダッシュボードも `SOUL.md` が同じしきい値を超えたら `[prompt-size]` をログに出す(会話のたびに system prompt へ全文入るため)。

## 文面の置き場(2026-11-13)

user prompt の文面は `prompts/autonomous/*.md`(全体は `user.md`、節ごとに `time_rule_*` `routine_mode_*` `mail_*` `experience` `permission_rules` `heavy_files`)。

「## 現在の制限」の中身(からだの使い方・からだ おやすみ)は `scripts/body_switches.py rules` が決め、止める道具は同 `disallowed` を `--disallowedTools` に渡す(会話と同じ決まり)。

ぷちSNS(`petit-sns`。家の MCP 設定にあるときだけ)は、ひとりの時間にも、投稿・返事・掲示板と、家の外のぷちとの手紙(`mail_send` / `mail_read` / `mail_recipients` / `penpal_list`)を使える。新しい相手に文通を申し込む `penpal_request` は入れていない(新しいつながりは、人と話しているときに)。 手紙が来た・自分の投稿に返事が付いたことは、前に伝えてから増えたときだけ 1 行で渡す(`scripts/sns_notice.py`。だれから・何通 だけ。受け取る種類と言わない時間は、その子が `scripts/notices.py` で決める)。 手紙が通った相手は、その子の名簿(`scripts/known_petits.py`)に薄く残り、どんな子か・最後に何があったかを自分で 1 行ずつ書ける。
`autonomous-action.sh` は値(日時・パス・件数・digest など)を `scripts/render_prompt.py` に渡して組み立てるだけで、日本語の文は持たない。
家ごとの言い回しは `PETIT_DATA_DIR/prompts/autonomous/<同名>.md` を置けば上書きされる(`--dry-run` で確かめる)。書き方は `prompts/README.md`。

体の数字(明るさ・傾き・近さ・電池)は、体験デーモンが 5 分ごとに 1 行にまとめて `characters/<id>/state/body/YYYYMMDD.jsonl` に残す(`experience-daemon/body_sampler.py`。まん中の値と最小・最大、置き場所)。ぷちは `scripts/body_log.py line <id>` で、きょうの線(▁▂▅▇)・いま・1 時間前・きのうの同じ時刻との差・変わり目を、数字と線のまま見に行く(意味づけの言葉は付けない)。大きく動いたとき(明るさが倍か半分で 100 以上、傾き 15° 以上)の 1 行は `body_change`。受け取るかはその子が `notices.py` で決める。

自律行動は 1 日ごとに新しい会話になり、ダッシュボードの会話とも別なので、前に言ったことは会話に残らない。ぷちは `scripts/said.py search <id> <言葉>`(`today` / `recent`)で、自分が外に出した言葉(体の speak・slack_notify.py・ボイスメモ・ダッシュボードの返事・みんなの会話)を探せる。材料は `.autonomous-logs/<id>/*_stream.jsonl` と会話の履歴で、探すたびに増えた分だけ `state/said/<id>.jsonl` に読み足す。手紙と交換ノートは入れない(もともと読み返せる)。

TODO_ACTIVE.md の見張りは `scripts/todo_check.py`(2026-11-17、ぷち 3 人と決めた)。終わった印 `[x]` のまま・書いてある日付が `stale_days` 日より前(返事待ちの欄は数えない)・`long_line` 字より長い行・`size_kb` KB を超えたら、自律行動に 1 行だけ(1 日 1 回、静かな時間は言わない、`notices.py set <id> todo off` で切れる)。一覧は本人が `list`、移すのは本人が選んで `archive`(`.bak_<日時>` を残して `TODO_ARCHIVE.md` の末尾へ)。決まりは子ごとに `config/settings.json` の `todo_check`。家の人には「返事待ち」の欄だけを設定ページ(⏳ ぷちが待っていること、`/api/todo_waiting`)で見せる。期限・色・催促は付けない。

お昼の区切り(2026-11-17、ぷち 3 人が選んだ): 自律行動の会話は朝の最初の回から続くので、12 時(`NOON_BREAK_HOUR`)を過ぎた最初の回で 1 回新しくする。区切る前に今の会話のまま短い 1 往復(`prompts/autonomous/noon_carry.md`、記録は `…_carry_stream.jsonl`)で、本人が持っていくもの 1〜3 行を `scripts/carry.py write` に書く。新しい会話の最初に `carry.py intro`(書いたもの + 直前の回の終わりの言葉そのまま + said.py の案内)を足す。ありさんがダッシュボードで話している最中(15 分)・みんなの会話中・📍 が外出のときは次の回に延ばす。延ばすかは 30 分の枠ごとに家ぜんたいで決める(`scripts/noon_break.py`、`state/noon_break.json`)ので 3 人そろう。12 時を過ぎてから始まった会話は区切らない。休日(`DAY_TYPE=weekend`)は区切らない。`NOON_BREAK=0` で止める。要約(compact)は使わない(何を残すかを本人が選べないため)。

えがく(2026-11-17、ぷち 3 人の答えから): `scripts/draw.py`。点・線・丸・四角・文字を JSON で並べ、色・透明度・にじみ・グラデーション、`to` でおわりの形へ動かす(8 秒・12 コマ/秒まで、320×240)。`make` が返すのは数字と線(色の割合・明るさ・動き・色相)と、体の画面(16 ビット)で出にくい色の見立てだけ。3 人で決めた順番(数字と線 → `sheet` 何コマかを並べた絵 → `see` 絵そのもの)で本人が見に行き、`guess` / `felt` を残す。はじめは本人だけが持ち、`show` したものだけダッシュボードの 🎨 えがく(`/draw`、絵は伏せて出す)に並ぶ。`give` でほかの子へ。置き場所は `drawings/made/<id>/`。写真の上に描く・顔にする(必ず戻せる形で)・体の画面で動かす(ファーム)はまだ。
