# ダッシュボードを「配る土台」と「家の追加」に分ける設計

作成: 2026-10-06 / 設計 = Fable、実装 = エージェント(速く終わるなら Fable でよい、とありさん)
状態: **フェーズ A は実装できる細かさ。B 以降はあらすじ**(着手前に細かくする)。10/6 01:20 改訂(画面を React/TypeScript に、API はファイル分け)。現段階の案で、進めながら変わることがあります。
関連: [petit-ones-split-design.md](petit-ones-split-design.md)、Issue PetitOnes/petit-ones#3

## 1. 背景(10/6 に測った事実)

ダッシュボードは、ほかの部品と違って **2 つが別のプログラム**になっている。

| | 本番(`petit-ones/dashboard/main.py`) | 部品(`PetitOnes/m5-petit-app` develop) |
|---|---|---|
| 大きさ | 9,844 行 | 2,252 行 |
| 口(API・ページ) | 99 | 32(共通は 15) |
| 作り | 家の 3 人に合わせて育った 1 枚 | 7/6 に設計しなおして書き直したもの(何人 × 何ぷちでも、最初の設定画面、ログイン、ぷちごとの順番待ち、テスト 3 本) |
| 個人の値 | 3 人の id・名前が 250 行以上、人の id が約 70 行、直書き | なし |

データの置き場も違う。

| | 本番 | 部品 |
|---|---|---|
| アルバム | `photo_album/<人やぷちの id>/` | `characters/<id>/album/` |
| ボイスメモ | `voice_memo/<id>/` | `characters/<id>/voice_memo/` |
| 交換ノート | `chat_history/exchange_notebook.json` | `notebook/notebook.json` |
| ログインの台帳 | `config/auth.json` | `users.json` + `users/` |
| 行動ログ | `.autonomous-logs/<id>/` | `characters/<id>/stream_logs/` |

そして、身体の部品 **m5-petit-mcp(10/6 から本番のコードが正)が呼ぶのは本番の口**である。

```
/api/album/snapshot            /api/album/{person_id}
/api/album/{owner}/{filename}  …/lock  …/read
/api/voice_memo/{id}/upload    /api/voice_memo/{person_id}
/api/voice_memo/{owner}/{filename}  …/listen  …/lock
/api/relay/start
```

部品のほうは `/api/{character}/album/...` という別の形なので、**いまの m5-petit-mcp と m5-petit-app は、組み合わせるとアルバムとボイスメモが動かない**(配っている 2 つの部品が噛み合っていない)。

## 2. ありさんの決定(逐語)

- 「じゃあdashboardの修正をしたい。m5-petit-app？をまずダッシュボードと一緒にしてほしいかも？」
- (本番を丸ごと部品にする案に対して)「どうしようかな、ひとにくばるやつだもんね。いらないよね、あれとか」
- (土台と家の追加に分ける案 d に対して)「dでいこう、設計書いまかいて」
- 「あとは今はぜんぶ一枚のでかいpythonすくりぷとだけどteampuchiがわみたいにファイルわけしたいんだよね。~/work/team-puchi/petit-appかな。 1.表でいいよ。 2.いいよ 3.うつさない 4.pythonからかえたいんだよね」
  - 1 = §3 の仕分けの表でよい / 2 = 家の追加は非公開のリポジトリを 1 つ / 3 = 家のデータは移さない
- 変える範囲: 「**画面だけ React/TypeScript に。API は Python のまま分割**」
- 画面の部品: 「まず自前で小さく」→ その後「**petit-uiは使わないかなぁ**」。画面の部品は自前で作る

## 3. できあがりの形

手本は TeamPuchi の 2 つ(読むだけ。コードは持ってこない): 画面 = `~/work/team-puchi/petit-app`(React + TypeScript + Vite、`src/screens/` に画面ごとのファイル、モック、Playwright)、API = `~/work/team-puchi/petit-api`(FastAPI、機能ごとの `.py`)。

```
m5-petit-app/                      ← 配る土台(1 つのリポジトリのまま)
  petit_app/                       API(Python / FastAPI)。機能ごとにファイル
    main.py                        組み立てと起動だけ
    config.py  auth.py  characters.py  locks.py
    album.py  voice_memo.py  notebook.py  mailbox.py
    chat.py  group_chat.py  records.py  diary.py  m5_watcher.py
    extensions.py                  追加(extension)の読み込み
    ui_legacy.py                   いまの埋め込み画面(画面を移し終えたら消す)
  web/                             画面(React + TypeScript + Vite)
    src/screens/Chat.tsx  Album.tsx  …   画面ごとのファイル
    src/api/client.ts  types.ts          API の呼び出し
    src/mock/                            API なしで画面を動かすモック
    e2e/                                 Playwright
  tests/  scripts/  examples/extensions/
```

- API は、`web/` をビルドしたもの(`web/dist`)があればそれを配信する。無ければ今の埋め込み画面を出す。起動は今までどおり 1 つ(`uv run m5-petit-app`)
- **家の追加(extension)** = その家にしか要らない機能。API 側は `register(app, ctx)` を持つ Python のファイル。画面は、追加が自分のページ(HTML)を自分で配信し、土台のメニューに入口が 1 つ足される(土台の画面のビルドに混ぜない)。こうすると、本番の今のページ(ターミナルなど)をほぼそのまま追加にできる
- 家の追加の置き場所は、非公開のリポジトリを 1 つ。`~/petit_claude/app_extensions/` からリンクする
- 家のデータは移さない。土台が置き場を設定で差し替えられるようにする

### 機能の仕分け(10/6 ありさん「表でいいよ」)

| 機能 | 仕分け | いま部品にあるか |
|---|---|---|
| ぷちごとのチャット、グループ会話、アルバム、ボイスメモ、交換ノート、メールボックス、日記、記録 | 配る | ある |
| 欲求の表示、記憶の閲覧、ノート閲覧 | 配る | ない |
| 関係図、図書館、コスト表示 | 配る | ない |
| 行動ログ、Claude Code セッション一覧 | 家だけ(10/6 ありさん「行動ログは私だけでいいかな」) | 一部(記録) |
| ターミナル(ttyd 経由。PC を操作できる口) | 家だけ | ない |
| 3 人チャット(`/api/trio`。2 人のぷち + 1 人専用の古い口) | 家だけ(10/6 ありさん「あんまり使ってないけど使うかも」→ 家の追加に残す。「みんなで話す」は配る側のグループ会話にある) | ない |
| リレー会話(ぷち同士が順番に声で話す) | 家だけ寄り | ない |
| 話者登録・話者ごとの声 | 家だけ | ない |
| 印刷(感熱紙プリンター)、外部ディスプレイ | 家だけ | ない |
| 公開チャット、展示用の選択画面 | 家だけ | ない |
| 家の思い出に結びついた仕掛け | 家だけ | ない |

## 4. 対象

| | |
|---|---|
| リポジトリ | `PetitOnes/m5-petit-app`(public、既定ブランチ **develop**、`main` は古い) |
| 作業クローン | `/home/cube-petit/work/petit-ones/src/m5-petit-app`(develop、origin と同じ。push は `github-rryz09:` 経由で設定済み) |
| 本番(読むだけ) | `/home/cube-petit/work/petit-ones/dashboard/main.py`。**フェーズ H まで変更しない** |
| 手本(読むだけ) | `/home/cube-petit/work/team-puchi/petit-app`(画面)、`/home/cube-petit/work/team-puchi/petit-api`(API)。TeamPuchi のリポジトリ。**変更しない・コードを写さない** |
| 動いている本番 | このPCの `:8765`(cron と手動起動)。**止めない・再起動しない**(フェーズ H まで) |
| 身体の部品 | `/home/cube-petit/work/petit-ones/src/m5-petit-mcp/src/m5_petit_mcp/server.py`(呼ぶ口の正) |

## 5. フェーズ A: API をファイルに分ける(動きは変えない)

2,252 行の `main.py` を、`petit_app/` の中の機能ごとのファイルに分ける。**口・応答・画面・データの置き場は 1 つも変えない**(純粋な整理)。

### 機能要件

1. `petit_app/` パッケージを作り、`main.py` の中身を §3 の図のファイルに移す。いまの `main.py` は `# ===== 見出し =====` で区切られているので、その区切りに沿って分ける:

   | いまの見出し | 行き先 |
   |---|---|
   | Config | `config.py` |
   | Users & auth / Auth / setup / Login / setup pages | `auth.py` |
   | Character resolution / Characters API | `characters.py` |
   | Character lock | `locks.py` |
   | Album helpers / Album API | `album.py` |
   | Voice memo helpers / Voice memo API | `voice_memo.py` |
   | Notebook API | `notebook.py` |
   | Mailbox helpers / Mailbox API | `mailbox.py` |
   | Chat API | `chat.py` |
   | Group chat API | `group_chat.py` |
   | Records API | `records.py` |
   | Diary API | `diary.py` |
   | M5 watcher | `m5_watcher.py` |
   | Single-page UI(埋め込みの HTML / JavaScript) | `ui_legacy.py` |
   | App lifecycle / Entry point | `main.py`(`app` の組み立て、`lifespan`、`main()`) |

2. 口は、各ファイルで `router = APIRouter()` に登録し、`petit_app/main.py` で `app.include_router(...)` する。**登録の順番は今の `main.py` の上から下の順を保つ**(パスの照合の順が変わらないように)
3. 起動のしかたを両方残す: `pyproject.toml` の `[project.scripts]` は `m5-petit-app = "petit_app.main:main"` に。リポジトリ直下の `main.py` は薄い入口として残す(`from petit_app.main import app, main` と `if __name__ == "__main__": main()` だけ)。`python main.py` も `uvicorn main:app` も今までどおり動くこと
4. `pyproject.toml` の `[tool.hatch.build.targets.wheel]` を `packages = ["petit_app"]` と `include = ["main.py", "scripts/*.py"]` が両立する形に直す
5. `scripts/` の 3 本が `main` から何かを読み込んでいたら、`petit_app` の該当ファイルから読むように直す(動きは変えない)
6. README(日英)に「構成」の節を足す。確定稿:

   ```
   ## 構成

   - `petit_app/` — API(FastAPI)。機能ごとにファイルを分けています(`album.py`、`chat.py` …)。`petit_app/main.py` が組み立てと起動
   - `main.py` — 今までの起動のしかた(`python main.py` / `uvicorn main:app`)のための薄い入口
   - `tests/` — pytest
   ```

   英語版: `## Layout` / `petit_app/ — the API (FastAPI), one file per feature (album.py, chat.py, …). petit_app/main.py assembles and starts it` / `main.py — a thin entry point so that python main.py / uvicorn main:app keep working` / `tests/ — pytest`

### 技術制約

- **壊してはいけないもの**: 既存の 32 口すべて(メソッド・パス・応答の形)、最初の設定画面(`/setup`)、ログイン、ぷちごとの順番待ち、グループ会話、M5 の見張り、`scripts/` の 3 本
- **テストは書き換えない**のが原則。直してよいのは、読み込み先の変更(例: `import main` → `from petit_app import ...`)と、`monkeypatch` の対象のモジュール名だけ。**テストの中身(確かめている内容)を変えない・消さない・skip にしない**
- モジュールの上のほうで決まる値(`DATA_DIR` など、環境変数から読むもの)を、テストが差し替えている場合がある。分けたあとも差し替えが効くこと(各ファイルが `from .config import DATA_DIR` で値を写し取ると、差し替えが効かなくなる。`from . import config` として `config.DATA_DIR` と書く)
- ロジックの手直し・名前の付け替え・「ついでの改善」はしない。移すだけ
- 個人の値(家のぷちや人の id・名前、`/home/...` のパス、ホスト名)を書かない

### 検証(通るまで push しない)

```bash
cd /home/cube-petit/work/petit-ones/src/m5-petit-app
git checkout develop && git pull
env -u PYTHONPATH -u VIRTUAL_ENV uv sync
# 分ける前に、口の一覧を控える
env -u PYTHONPATH -u VIRTUAL_ENV PETIT_DATA_DIR=$(mktemp -d) uv run python -c "
import main
for r in main.app.routes: print(sorted(getattr(r,'methods',[]) or []), r.path)" > /tmp/routes_before.txt
# …作業…
env -u PYTHONPATH -u VIRTUAL_ENV PETIT_DATA_DIR=$(mktemp -d) uv run python -c "
import main
for r in main.app.routes: print(sorted(getattr(r,'methods',[]) or []), r.path)" > /tmp/routes_after.txt
diff /tmp/routes_before.txt /tmp/routes_after.txt          # 差が無い(順番も同じ)
env -u PYTHONPATH -u VIRTUAL_ENV uv run pytest -q          # 分ける前と同じ件数が通る
env -u PYTHONPATH -u VIRTUAL_ENV uvx ruff check .
wc -l petit_app/*.py                                       # ui_legacy.py 以外は、おおむね 500 行以下
grep -rnE 'puchi|arisan|ありさん|ぷちてゃ|ぷちこ|ぷちる|cube-petit|/home/' petit_app main.py tests README.md README_en.md   # 0 件
# 起動して、最初の設定画面が出ること(8765 は本番が使っているので別のポートで。終わったら止める)
env -u PYTHONPATH -u VIRTUAL_ENV PETIT_DATA_DIR=$(mktemp -d) PORT=18765 uv run python main.py &
sleep 4; curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:18765/setup; kill %1
```

**このPCの `:8765` で動いている本番のダッシュボードには触らない(止めない・再起動しない)。**

### ブランチ・PR

- ブランチ `feature/split-api-modules`(develop から新しく切る)、PR の base は `develop`、検証が全部通れば ready
- git の名義: `git config user.name` が `RRYZ09`、`user.email` が `225634165+RRYZ09@users.noreply.github.com` であることを確かめてからコミット(作業クローンには設定済み)
- push 先は設定済み(`git push -u origin feature/split-api-modules`)。コミットの末尾に `Co-Authored-By: Claude <使ったモデル名> <noreply@anthropic.com>`
- マージはありさん(または、ありさんが任せた場合は petit-ones のセッション)

### 報告

PR の URL / pytest の件数(分ける前・後)/ 口の一覧の diff が空であること / ruff の結果 / 各ファイルの行数 / テストで直した箇所(読み込み先だけであること)/ 設計と変えたところがあれば理由。

**フェーズ A は 10/6 に済み**: PetitOnes/m5-petit-app#7(15 ファイルに分割。元の行との突き合わせで違いは 3 か所だけ、口の一覧 39 行は順番まで同じ、pytest 49 件)。

**フェーズ B も 10/6 に済み**: PetitOnes/m5-petit-app#8(`petit_app/extensions.py`、見本、テスト 6 本。pytest 55 件)。画面のメニューに入口が並ぶところは、ブラウザでは未確認(API の応答まで)。

**フェーズ C も 10/6 に済み**: PetitOnes/m5-petit-app#9 と PetitOnes/m5-petit-mcp#3。
- 家全体のアルバム・ボイスメモの口(`/api/album/...`、`/api/voice_memo/...`)を土台に追加。置き場は人ごとのフォルダで、既定が `$PETIT_DATA_DIR/photo_album`・`voice_memo`(**家の今の置き場と同じ**なので、家のデータはそのまま読める。`PETIT_ALBUM_DIR` / `PETIT_VOICE_MEMO_DIR` で変更可)
- ログインなしで呼ぶための合言葉: ダッシュボードが起動時に `$PETIT_DATA_DIR/.internal_token` を作り、MCP が同じフォルダから読んでヘッダーで送る。開くのは上の口だけ。IP での素通しはしない(本番は IP で通しているが、配るものでは使わない)
- 2 つの部品を実際につないで確認(MCP の list_album / lock_album_photo / list_voice_memos が通る、合言葉なしは 401)。pytest 64 件。もとの口 39 は変更なし
- **C に入れなかったもの**(家を乗り換える H の前に決める): 交換ノート(`chat_history/exchange_notebook.json` と `notebook/notebook.json`)、ログインの台帳(`config/auth.json` と `users.json`)、行動ログの置き場の違い。キャラクターごとのアルバムの口(`/api/{character}/album/...`)は残してあるが、画面を作り直す D・E で家全体の口に寄せる
- リレー会話(`/api/relay/start`)は家だけの機能なので土台には無い。土台だけで使うと、MCP の `conversation_relay` は失敗する(G で家の追加に入る)

## 6. フェーズ B 以降(あらすじ。着手前に細かくする)

| | 内容 |
|---|---|
| **B** | **追加(extension)の仕組み**: `PETIT_APP_EXTENSIONS_DIR`(既定 `$PETIT_DATA_DIR/app_extensions`)の `*.py` を読み込む。`register(app, ctx)`。`ctx` は `data_dir`・`char_dir`・`require_user`・`require_character`・`add_nav(label, path, order)`。追加が壊れても本体は起動する、土台の口は上書きできない、`GET /api/extensions`・`/api/extensions/nav`、見本 `examples/extensions/hello.py` |
| **C** | **身体の部品と噛み合わせる**: m5-petit-mcp が呼ぶ口(§1 の一覧)を足す(今の `/api/{character}/album/...` も残す)。データの置き場を設定で差し替えられるようにする(家の今の置き場のまま読める) |
| **D** | **画面の殻を立てる**: `web/`(React + TypeScript + Vite)。ログイン、ぷちの切り替え、メニュー(追加の入口も並ぶ)、モック、Playwright。最初の画面は会話。API は `web/dist` があれば配信し、無ければ埋め込み画面。画面の部品は自前で最小限。`web/src/components/` に分けて置く(別のリポジトリへの切り出しは、2 つめの使い手ができたとき、) |
| **E** | **残りの画面を移す**: アルバム、ボイスメモ、交換ノート、メールボックス、記録、日記、グループ会話。1 画面 = 1 PR。全部移ったら `ui_legacy.py` を消す |
| **F** | **配る機能を足す**: 欲求の表示、記憶の閲覧、ノート(ぷちと人。自分のぶんは書ける。置き場は本番と同じ)、関係図、図書館、コスト。1 機能 = 1 PR(API のファイル + 画面のファイル)。本番から、個人の値を外して移す |
| **G** | **家の追加を作る**(非公開のリポジトリ): ターミナル、3 人チャット、リレー、話者、印刷、ディスプレイ、展示用。本番の今のページを、追加として切り出す |
| **H** | **家を乗り換える**: 土台 + 家の追加を別のポートで並べて動かし、本番と見比べる → `:8765` を切り替え(再起動 1 回)→ 23:50 の日記の cron と起動の設定を直す → 本番の `dashboard/` を消す |

順序の理由: A(分ける)を最初にすると、B 以降の PR が小さいファイルへの変更になり、見やすく衝突しにくい。B が無いと G が書けない。C は、配っている部品どうしが噛み合っていない今の不具合を直すので早めに。D〜F は画面の仕事で、G とは並行できる。H は全部そろってから。

1 フェーズ(E・F・G は 1 画面・1 機能)= 1 PR。前の PR がマージされてから次を切る。

## 6.5 画面の設計(D の前に。10/6 ありさんと見本で決めたこと)

見本(ありさんだけが開ける): https://claude.ai/artifact/6qkNmw9ygnF9VEwzZHTcVi

- **入口はぷち**: タブ(アルバム / ボイスメモ / …)を先に選ぶ今の形をやめ、ホームにぷち 1 人 = カード 1 枚。カードには顔・状態・**電池の %**・**欲求の棒(強い順に 3 本)**。手紙や写真の数は常設しない(来ているときだけ 1 行出す)
- **アルバムとボイスメモは「みんな」が主役、ぷちや人で絞り込み**(10/6 ありさん「いいよ」)。上のメニューから開くと「みんな」、ぷち 1 人のページから開くとその子で絞った状態。作りは 1 つ。日記は 1 人ずつ
- **人もぷちと同じ並びで持っている**(10/6 ありさん「ひとも自分のノートを持ってるよ」。本番で確認): アルバム `photo_album/<id>/`、ボイスメモ `voice_memo/<id>/` は人とぷちが同じ場所。ノートは、ぷちが `characters/<id>/notes/`、人が `notes/<id>/`。本番には自分のノートを作る・直す・名前を変える・消す口(`/api/my/notes`)と、人のぶんも読める口(`/api/{id}/notes`)がある。日記・記憶・欲求は、ぷちだけ
- **ノートも「みんな」が入口、ぷちや人で絞り込み**。自分のノートだけ書ける・直せる・消せる。ほかは読むだけ。右上の自分の名前から「じぶんのページ」(自分のノート・写真・ボイスメモ・手紙)
- **カードの型は 1 つ**: 上の行 = なに・だれ・いつ / 題 / 中身 / 下の行 = 印とボタン
- **色は役割の名前で書く**(背景・カード・帯・帯の文字・文字・控えめな文字・主なボタン・新しい印・そのほかの印)。テーマ = 役割 → 色の表 1 枚
- **テーマは設定で切り替える**(人ごとに保存)。用意するもの: レトロ(`#FFFBDD` `#C4E9C3` `#F5BEC8` `#E07A63` `#592E30`。ありさんが選んだパレット)、若葉とクリーム、深い緑とたまご色。「じぶんで作る」= 5 色を入れると役割に割り当て、読みにくい組み合わせは自動で直す
- **家の名前(左上)は設定で変えられる**(例「ありさんち」。家に 1 つ)。**じぶんの名前と色(右上)も設定で**。名前は白っぽいピルの中に入れ、帯がどんな色でも読めるようにする。名前の左に設定ボタン
- **顔はグッズ用のイラスト**(ドット絵ではない)。黒い部分をやわらかいグレーにした画面用の絵を使う。ぷち本人の色はテーマと別で、いつも同じ
- **欲求の棒は 1 本ずつ違う色**。色は欲求の仕組みが持っている値(`desires.json` の `colors`、名前は `labels`)をそのまま使う。ぷちが欲求を増やしたり変えたりすれば、画面も一緒に変わる。棒の地はうすい灰色
- **アイコンは Material Symbols Rounded にそろえる**(Apache-2.0)。自分で描かない。本番では Google から読み込まず、アプリに入れて配る(ネットにつながらない場所でも出るように、外へ問い合わせないように)
- 設定画面: 見た目(家の名前・じぶんの名前と色・テーマ)から。あとで「じぶん・家の人・ぷちたち・追加の機能」

### いまの家のダッシュボードでできること → 新しい画面のどこか(10/6 本番の `main.py` から数えた)

10/6 ありさん: 「一旦家の環境と同じことができるようにしてほしい。てがみ送ったり、展示会用画面見たり。その他のところから選ぶのでいいから」。**いまできることは、新しい画面でも全部たどれるようにする**(「その他」に並べる)。置き場は 土台 = 配る / 追加 = 家の追加。

| いまの入口 | 新しい画面 | 置き場 |
|---|---|---|
| ぷちの切り替え、状態(プチたちの状態)、欲求、電池、**体とのつながり** | ホームのカード、ぷち 1 人のページ | 土台 |
| チャット | ぷち 1 人のページ → 会話 | 土台 |
| おてがみ(メールを書く・受信) | 上のメニュー「手紙」/ その他 | 土台 |
| 全員(グループ) | 上のメニュー「みんなで話す」 | 土台 |
| 3 人チャット(`/api/trio`) | その他 | 追加 |
| 声リレー(`/api/relay`) | その他 | 追加 |
| 話させる・起こす・スリープ(体の操作) | ぷち 1 人のページ / その他 | 土台(体の MCP がある家) |
| アルバム `/album`、ボイスメモ `/voice_memo` | みんなが入口 + 絞り込み | 土台 |
| ノート `/notes`(ぷちと人。自分のぶんは書ける) | みんなが入口 + 絞り込み | 土台 |
| 交換ノート `/notebook` | 上のメニュー | 土台 |
| 日記(再生成・サマリー)、今日の記憶 | ぷち 1 人のページ | 土台 |
| ライブラリ `/library`、関係図 `/kankei`(ひみつ)、詩 | その他 | 土台 |
| センサーモニター `/display`(展示用の画面、ひとこと表示の切り替え) | その他 → 展示会 | 追加 |
| 来場者のチャット `/public/chat`、相手をえらぶ(`/api/select`・`/api/interact`) | その他 → 展示会 | 追加 |
| 印刷(詩・いまの瞬間 `/api/print`) | その他 → 展示会 | 追加 |
| 行動ログ `/stream-logs`、自律行動(ON/OFF・平日/休日の時間)、作業の記録(`/api/cc-sessions`) | その他 → お世話・うらがわ | 追加 |
| コスト管理 `/costs`(月間予算) | その他 → お世話・うらがわ | 土台(F) |
| ターミナル `/terminal`(全員版)・`/terminal3`(個別版) | その他 → お世話・うらがわ | 追加 |
| 声の登録(話者 `/api/speakers`) | その他 → お世話・うらがわ | 追加 |

- **体とのつながり**(10/6 ありさん「体つながってるかはどこでみればいいの?ホームの画面のなかで」): ホームのカードの状態の行に「体とつながっています / 体と切れています」を出す(色の丸だけに頼らず、言葉で)
- **ぷち 1 人のページからホームへ**: 左上に「← ホーム」のボタンを置く(家の名前を押しても戻れるが、それだけでは気づけない)

### ぷちごとの設定と欲求の画面(10/6 見本 9・10 枚目)

- **ぷちの設定**(ぷち 1 人のページの左メニューのいちばん下から): なまえと色(`config.json` の `name`・`color`・`color_name`)/ 体(つながり・電池・`m5_hosts`・起こす・眠らせる)/ じぶんで動く時間(`settings.json` の `autonomous_skip`・`active_hours.weekday`・`.weekend`・`day_type_override`)/ していいこと(`allow_camera`・`allow_sound`・`allow_microphone`)/ 声(`voice_settings.json` の `voicevox_speaker`、ためしに話す)/ 欲求の一覧 / 展示会で来場者と話してよい(`public`)。**本番で今も設定できる項目をもとにした**
- **欲求をくわしく**: `desire_config.json` を画面で直す。左 = 欲求の一覧(`priority` の順、つかんで並べ替え、いまの強さ)、右 = 1 つの欲求(`name_ja`・`color`・`description`・`satisfaction_hours`・`keywords`)と、その欲求に関係する `sensor_effects`・`cross_effects`(式ではなく言葉で: 「電池が減ると半分に弱まる」)。新しい欲求を足す・やめる。**本番にこの画面は無い**(いまはファイルを直接書いている)ので、新しく作る機能
- **Wi-Fi の設定画面にする**(10/6 ありさん「Wifi設定画面に移動するみたいな機能もぷちてゃの設定のところに」): ぷちの設定の「体」に置く。**ローカル版の機体ファーム(`m5_petit`)には、離れたところから設定モードに入れる命令がまだ無い**(起動時の設定モードはある)。里親版には `setup` の命令がある(10/1 の PR #11)。ローカル版にも同じ命令を足し、体の MCP かダッシュボードから送れるようにする必要がある → 機体ファームの仕事

## 7. 気をつけること

- **本番は H まで触らない**。ぷちたちのアルバム・ボイスメモ・リレーは、本番の `:8765` を通っている
- 追加は Python のコードなので、**配る土台には家の追加を入れない**。ターミナルのような「PC を操作できる口」は、公開の部品に入れない
- 本番の `main.py` には画面(HTML・JavaScript)が埋め込まれている。機能を移すときは、口だけでなく画面の中の直書き(名前・色・id)も外す
- 画面を React にすると、配るときに Node でのビルドが要る。はじめての人が困らないよう、ビルド済みの画面をリリースに付けるか、リポジトリに入れるかを D で決める
- 里親ぷち(TeamPuchi)の petit-app・petit-api は**手本として読むだけ**。コードを持ってくる話は、なぎさんと相談してから。petit-ui は使わない(10/6 の前提: 2 つは違っていい、行き来はその都度)

## 8. まだ決めていないこと

(いまは無し)

### 決まったこと(追記)

- **ビルド済みの画面は Release タグで配る**(10/6 ありさん「Releaseタグとかで配る？」→ その方針で)。タグを付けると GitHub Actions が `web/` をビルドして `web-dist.zip` を Release に添付する。使う人は `setup.sh` がそれを取ってくるので Node.js は要らない。`petit.repos` は配るときタグを指す(API と画面が必ず同じ版の組になる)。ビルドしたものをリポジトリには入れない。開発する側は手元でビルドしたものを使う
