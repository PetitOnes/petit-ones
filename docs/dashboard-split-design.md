# ダッシュボードを「配る土台」と「家の追加」に分ける設計

作成: 2026-10-06 / 設計 = Fable、実装 = エージェント(速く終わるなら Fable でよい、とありさん)
状態: **フェーズ A は実装できる細かさ。B 以降はあらすじ**(着手前に細かくする)。現段階の案で、進めながら変わることがあります。
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
- (本番を丸ごと部品にする案 a に対して)「どうしようかな、ひとにくばるやつだもんね。いらないよね、あれとか」
- (土台と家の追加に分ける案 d に対して)「dでいこう、設計書いまかいて」

**まだ決まっていないこと**(§8。フェーズ A はこれに左右されない):
1. どの機能を配るか・家だけにするかの仕分け(§3 の表は Fable の見立て。ありさんは未確認)
2. 「家の追加」のコードの置き場所と、公開するかどうか
3. 家のデータを部品の置き場へ移すか、今の場所のまま読むか

## 3. 分け方(案)

- **m5-petit-app = 配る土台**。小さく、安全で、だれの家でも動くもの。いまの書き直し版を土台にする
- **家の追加(extension)** = 土台が起動時に読み込む追加のコード。その家にしか要らない機能を置く

| 機能 | 仕分け(見立て) | いま部品にあるか |
|---|---|---|
| ぷちごとのチャット、グループ会話、アルバム、ボイスメモ、交換ノート、メールボックス、日記、記録 | 配る | ある |
| 欲求の表示、記憶の閲覧、ノート閲覧 | 配る | ない |
| 関係図、図書館、コスト表示 | 配る | ない |
| 行動ログ、Claude Code セッション一覧 | 迷う | 一部(記録) |
| ターミナル(ttyd 経由。PC を操作できる口) | 家だけ | ない |
| 3 人チャット、リレー会話 | 家だけ寄り(何人でも、に直せば配れる) | ない |
| 話者登録・話者ごとの声 | 家だけ | ない |
| 印刷(感熱紙プリンター)、外部ディスプレイ | 家だけ | ない |
| 公開チャット、展示用の選択画面 | 家だけ | ない |
| 「うまれていいよ」の仕掛けなど、家の思い出に結びついたもの | 家だけ | ない |

## 4. 対象

| | |
|---|---|
| リポジトリ | `PetitOnes/m5-petit-app`(public、既定ブランチ **develop**、`main` は古い) |
| 作業クローン | `/home/cube-petit/work/petit-ones/src/m5-petit-app`(develop、origin と同じ。push は `github-rryz09:` 経由で設定済み) |
| 本番(読むだけ) | `/home/cube-petit/work/petit-ones/dashboard/main.py`。**フェーズ E まで変更しない** |
| 動いている本番 | このPCの `:8765`(cron と手動起動)。**止めない・再起動しない**(フェーズ E まで) |
| 身体の部品 | `/home/cube-petit/work/petit-ones/src/m5-petit-mcp/src/m5_petit_mcp/server.py`(呼ぶ口の正) |

## 5. フェーズ A: 追加(extension)の仕組みを土台に入れる

土台の動きは変えない。追加フォルダが無ければ、今までとまったく同じに動く。

### 機能要件

1. **読み込み**: 起動時に、環境変数 `PETIT_APP_EXTENSIONS_DIR`(既定 `$PETIT_DATA_DIR/app_extensions`)の直下にある `*.py` を、ファイル名の順に読み込む。`_` で始まるファイルは読まない。フォルダが無ければ何もしない
2. **約束**: 各ファイルは `def register(app, ctx) -> None` を持つ。`app` は FastAPI の本体。`ctx` は次を持つ(名前はこのとおり):
   - `ctx.data_dir`(Path)、`ctx.char_dir(character_id)`(Path)
   - `ctx.require_user`(今のログイン確認と同じ依存関数。追加の口でも `Depends` で使える)
   - `ctx.require_character(character_id, user)`(そのユーザーに見えるぷちか確かめる、今の関数)
   - `ctx.add_nav(label: str, path: str, order: int = 100)`(画面のメニューに入口を 1 つ足す)
   - `ctx.version`(土台の版の文字列)
3. **メニュー**: `add_nav` で足された入口は、ログイン後の画面のメニューの末尾に、`order` の順で並ぶ。ラベルはそのまま表示(HTML はエスケープする)。入口の一覧は `GET /api/extensions/nav`(要ログイン)で返す: `[{"label": "...", "path": "..."}]`
4. **失敗しても土台は起動する**: 追加の読み込みや `register` が例外を出したら、標準エラーに `extension <ファイル名> failed: <例外>` と出して、そのファイルだけ飛ばす
5. **口の衝突**: 追加が、土台にすでにある口(同じメソッド・同じパス)を登録しようとしたら、その追加は読み込まない(4 と同じ扱い。メッセージは `extension <ファイル名> skipped: route conflict <METHOD> <path>`)。土台の口が上書きされないこと
6. **一覧**: `GET /api/extensions`(要ログイン)で、読み込めた追加と失敗した追加を返す: `{"loaded": ["a.py"], "failed": [{"file": "b.py", "error": "..."}]}`
7. **見本**: `examples/extensions/hello.py` を置く(`GET /ext/hello` で `{"hello": "<ログイン中のユーザーの表示名>"}` を返し、メニューに「Hello」を足す)

### 文書(確定稿)

README.md の「環境変数」の表に 1 行、その下に節を足す。

```
| `PETIT_APP_EXTENSIONS_DIR` | 追加(extension)を置くフォルダ | `$PETIT_DATA_DIR/app_extensions` |
```

```
## 追加(extension)

その家だけの機能は、土台を書き換えずに「追加」として足せます。
`$PETIT_DATA_DIR/app_extensions/` に `*.py` を置くと、起動時に読み込まれます。

各ファイルは `register(app, ctx)` を持ちます。見本は `examples/extensions/hello.py`。

- 追加が失敗しても、ダッシュボード本体は起動します(`GET /api/extensions` で確認できます)
- 追加は土台の口を上書きできません
- 追加は、このダッシュボードと同じ権限で動く Python のコードです。**信頼できるものだけ置いてください**
```

README_en.md には同じ内容を英語で(表の行 `Folder for extensions`、節の題 `## Extensions`、最後の注意は `Extensions are Python code that runs with the same privileges as this dashboard. Only install ones you trust.`)。

### 技術制約

- **壊してはいけないもの**: 既存の 32 口すべて、最初の設定画面(`/setup`)、ログイン、ぷちごとの順番待ち、グループ会話。既存のテスト 3 本がそのまま通ること
- `main.py` は 1 枚のまま(分割しない)。読み込みは `importlib.util.spec_from_file_location` で。追加のファイルを `sys.path` に入れない
- 追加の読み込みは、土台の口をすべて登録し終えたあと(`app` を作り、既存の `@app.*` が全部評価されたあと)に行う。`main()` の中ではなく、モジュールの末尾で行う(テストの `TestClient` でも読み込まれるように)
- 個人の値(家のぷちや人の id・名前、`/home/...` のパス、ホスト名)を、コード・テスト・見本・文書に書かない

### 検証(通るまで push しない)

```bash
cd /home/cube-petit/work/petit-ones/src/m5-petit-app
env -u PYTHONPATH -u VIRTUAL_ENV uv sync
env -u PYTHONPATH -u VIRTUAL_ENV uv run pytest -q          # 既存 + 新しいテストが全部通る
env -u PYTHONPATH -u VIRTUAL_ENV uvx ruff check .
grep -rnE 'puchi|arisan|ありさん|ぷちてゃ|ぷちこ|ぷちる|cube-petit|/home/' main.py tests examples README.md README_en.md   # 0 件
```

新しいテスト `tests/test_extensions.py` に、少なくとも次を入れる: ①フォルダ無しで起動する ②見本の追加が読み込まれ `/ext/hello` が要ログインで動く ③`add_nav` の入口が `/api/extensions/nav` に出る ④例外を出す追加があっても起動し、`/api/extensions` の `failed` に出る ⑤土台と同じ口を登録する追加は読み込まれず、土台の応答が変わらない ⑥`_` で始まるファイルは読まれない。

### ブランチ・PR

- ブランチ `feature/extensions`(develop から新しく切る)、PR の base は `develop`、検証が全部通れば ready
- git の名義: `git config user.name "RRYZ09"` / `git config user.email "225634165+RRYZ09@users.noreply.github.com"`(作業クローンには設定済み。確かめてからコミット)
- 作業前に `git pull`。コミットの末尾に `Co-Authored-By: Claude <使ったモデル名> <noreply@anthropic.com>`
- マージはありさん(または、ありさんが任せた場合はこのセッション)

### 報告

PR の URL / pytest の結果(件数)/ ruff の結果 / 個人の値の grep が 0 件であること / 設計と変えたところがあれば理由。

## 6. フェーズ B 以降(あらすじ。着手前に細かくする)

| | 内容 | 決めること |
|---|---|---|
| **B** | **身体の部品と噛み合わせる**: m5-petit-mcp が呼ぶ口(§1 の一覧)を土台に足す。今の `/api/{character}/album/...` も残す。あわせて、データの置き場を設定で差し替えられるようにする(家の今の置き場のまま読めるように) | §8-3 |
| **C** | **配る機能を足す**: 欲求の表示、記憶の閲覧、ノート閲覧、関係図、図書館、コスト。本番から 1 機能 = 1 PR で、個人の値を外して移す | §8-1 |
| **D** | **家の追加を作る**: ターミナル、3 人チャット、リレー、話者、印刷、ディスプレイ、展示用を、追加(extension)として本番から切り出す | §8-1、§8-2 |
| **E** | **家を乗り換える**: 土台 + 家の追加を別のポートで並べて動かし、本番と見比べる → `:8765` を切り替え(再起動 1 回)→ 23:50 の日記の cron、起動の設定を直す → 本番の `dashboard/` を消す | — |

順序の理由: A が無いと D が書けない。B は、配っている部品どうしが噛み合っていない今の不具合を直すので早めに。C と D は並行できる。E は全部そろってから。

1 フェーズ(C と D は 1 機能)= 1 PR。前の PR がマージされてから次を切る。

## 7. 気をつけること

- **本番は E まで触らない**。ぷちたちのアルバム・ボイスメモ・リレーは、本番の `:8765` を通っている
- 追加は Python のコードなので、**配る土台には家の追加を入れない**。ターミナルのような「PC を操作できる口」は、公開の部品に入れない
- 本番の `main.py` には画面(HTML・JavaScript)が埋め込まれている。機能を移すときは、口だけでなく画面の中の直書き(名前・色・id)も外す
- 里親ぷち(TeamPuchi の petit-api)は、7 月の m5-petit-app から分かれて別の道に進んでいる。この設計は里親側に影響しない(10/6 の前提: 2 つは違っていい)

## 8. ありさんに決めてほしいこと

1. **§3 の仕分け**はこれでよいか(とくに「迷う」の行動ログと、3 人チャット・リレーを配るかどうか)
2. **家の追加の置き場所**: 案 = 非公開のリポジトリを 1 つ作り(ターミナルや展示用は家の事情を含むので)、`~/petit_claude/app_extensions/` へリンクする。配れるものができたら、その機能だけ公開の部品へ出す
3. **家のデータ**: 案 = 移さない。土台が置き場を設定で差し替えられるようにして、今の場所(`photo_album/` など)のまま読む。理由: バックアップ・分析・ぷちたちの道具が今の場所を前提にしている
4. フェーズ A を始めてよいか
