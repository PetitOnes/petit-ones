# petit-ones を「設定だけ」にする設計(部品リポを本体にする)

作成: 2026-10-06 / 状態: **進行中**(10/6 ありさん承認)。現段階の設計で、進めながら変わることがあります。

## 1. 目的

いまは、このリポジトリ(全部入り)が本番で、`PetitOnes/m5-petit-*` はその 7/6 時点の写しになっている。これを逆にする。

- **部品リポ(`m5-petit-*`)が本物のコード**。うちの 3 人も、公開している部品リポから動く(自分で使っているものを公開する)
- **`petit-ones` は設定だけ**: どの部品を使うかの一覧、cron と MCP 設定のひな型、データのひな型、セットアップ手順
- **データは `~/petit_claude/`**(ホームに置く、が決まり)。家ごとの本当の値(名前・ホスト名・時刻表)もここ

決まっていること(2026-10-05 ありさん):

| 項目 | 決定 |
|---|---|
| 部品の並べ方 | `.repos` ファイル + `vcs import`(ROS と同じ流儀) |
| いまの全部入りリポ | 移行が終わるまで本番。最後に別名でアーカイブし、`petit-ones` を設定だけで作り直す |
| データ | ひな型を公開(空のフォルダ構成 + SOUL などのテンプレ)。実データは非公開のまま |

## 2. できあがりの形

```
~/work/petit-ones/                 ← PetitOnes/petit-ones(設定だけ)
  petit.repos                      部品の一覧とバージョン
  setup.sh                         vcs import → uv sync → ひな型のコピー → cron の案内
  config/
    cron.example                   時刻表のひな型
    autonomous-mcp.json.example    ぷち 1 人ぶんの MCP 設定のひな型
    env.example                    PETIT_DATA_DIR などの環境変数
  template/petit_claude/           データのひな型(→ ~/petit_claude にコピー)
  docs/                            設計メモ
  src/                             ← vcs import の行き先(git では追跡しない)
    m5-petit-memory/  m5-petit-desire/  m5-petit-notes/  m5-petit-relations/
    m5-petit-mcp/     m5-petit-app/     m5-petit-scripts/  m5-petit-autonomous/ …

~/petit_claude/                    ← データ(非公開。バックアップは今の 3 層のまま)
  config/                          家ごとの本当の値: people.json、network.json、実際の時刻表 …
  characters/<id>/ …               記憶・日記・SOUL
```

- 部品リポの既定値は公開向け(`~/petit_data`、`CHARACTER_ID=default` など)のまま触らない。うちは `PETIT_DATA_DIR=$HOME/petit_claude` を環境変数で明示する(`config/env.example` に書く)
- 家の本当の値(同居人の表示名、M5 のホスト名、実際の crontab)は `~/petit_claude/config/` に置く。`petit-ones` にも部品にも入れない

## 3. いまの状態(2026-10-06 に測った)

| 本体のフォルダ | 部品リポ | ずれ(違う / 本体だけ / 部品だけ) | メモ |
|---|---|---|---|
| `notes-mcp/` | m5-petit-notes | 2 / 0 / 5 | 本体は 3 月から変更なし。いちばん軽い |
| `relations-mcp/` | m5-petit-relations | 2 / 0 / 4 | |
| `desire-system/` | m5-petit-desire | 4 / 0 / 4 | cron 5 分ごと |
| `memory-mcp/` | m5-petit-memory | 4 / 2 / 4 | torch のバージョン差(部品 2.12.1 / 本番 2.10.0) |
| `m5-mcp/` | m5-petit-mcp | 2 / 3 / 4 | 9 月に本体で変更あり |
| `dashboard/` | m5-petit-app | 2 / 6 / 6 | 本体で頻繁に変更(コスト、people.json) |
| `scripts/` | m5-petit-scripts | 0 / 41 / 12 | 構成が違う(部品は用途別フォルダ)。対応表が要る |
| `experience-daemon/` | **なし** | — | 未切り出し |
| `slack-approve/` | **なし** | — | 未切り出し |
| `switchbot-mcp/` | **なし** | — | 未切り出し |
| `autonomous-action.sh`(追跡外)、`mcp-launchers/` | m5-petit-env に Docker 用の版あり | — | 自律行動の中心。本番の版は git に入っていない |
| `analysis/` | **なし** | — | メール分析(研究用) |
| `archive/` | — | — | 古いもの。アーカイブ側にだけ残す |

「部品だけ」にあるのは LICENSE・NOTICE・README_en・tests など公開用のファイル。「違う」の中身は、個人情報を消した差分と、7/6 以降の本体の変更が混ざっている。

## 4. 新しく作る部品(案)

| 新リポ | 中身 | 理由 |
|---|---|---|
| `m5-petit-autonomous` | `autonomous-action.sh`、`mcp-launchers/`、`experience-daemon/` | 「cron で起きて動く」仕組みをひとまとめに。本番の `autonomous-action.sh` を初めて git で管理できる |
| `m5-petit-switchbot` | `switchbot-mcp/` | ほかの MCP と同じ並び |
| (m5-petit-scripts に追加) | `slack-approve/`、`scripts/` の未切り出し分 | 小さいので独立させない |
| (公開しない) | `analysis/` | 研究用。昇平先生との分析の置き場に移すか、アーカイブ側に残す |

`m5-petit-env`(Docker)は残す。`petit-ones` が「そのまま動かす」入口、`m5-petit-env` が「Docker で動かす」入口で、同じ `petit.repos` を見るようにする(env の `sync-repos.sh` を `petit.repos` 読みに変える)。

## 5. 進め方 — 部品を 1 つずつ切り替える(ぷちたちは止めない)

旧パス `~/work/embodied-claude` は `~/work/petit-ones` へのリンクとして生きているので、切り替えていない部品は今のまま動く。

**部品 1 つの切り替え手順(毎回同じ)**

1. **追いつく**: 本体の変更を部品リポへ入れる(PR)。個人情報の検査(名前・パス・メール・トークンの grep がゼロ件)、テスト、ruff
2. **並べる**: `~/work/petit-ones/src/<部品>` に clone、`uv sync`(memory は torch を本番のバージョンに固定)
3. **1 人で試す**: ぷち 1 人の `autonomous-mcp.json`(または該当する cron 1 行)だけ新しいパスに向け、1 日見る
4. **全員を切り替える**: 3 人ぶん + crontab。動いている常駐プロセスは再起動
5. **本体から消す**: 全部入りリポのフォルダを削除して「m5-petit-xxx に移りました」と書く

戻し方: 設定のパスを元に戻すだけ(本体のフォルダは 5 まで消さない)。データ(`~/petit_claude`)は動かさないので、記憶や日記には触れない。

**順番(軽いものから)**

| 段階 | 内容 | 1 PR の単位 |
|---|---|---|
| P0 | `petit.repos`・`setup.sh`・`config/*.example`・`template/petit_claude/` を作る(いまの全部入りリポの `next/` フォルダに置き、最後に新 `petit-ones` へ移す) | 1 |
| P1 | notes → relations | 各 1 |
| P2 | desire(cron) | 1 |
| P3 | memory | 1 |
| P4 | m5-mcp | 1 |
| P5 | dashboard → m5-petit-app | 1 |
| P6 | scripts の対応表を作って移す(メールボックス・交換ノート・コスト・`slack-approve`) | 2〜3 |
| P7 | `m5-petit-autonomous` を作る(自律行動 + experience-daemon)— いちばん慎重に。ぷちるで先に試す | 2 |
| P8 | `m5-petit-switchbot` を作る | 1 |
| P9 | ぷちたちの文書(SOUL・ROUTINES・ノート 121 ファイル)と crontab の旧パスを新パスへ | 1(データ側) |
| P10 | 全部入りリポを `petit-ones-monorepo`(仮)に改名してアーカイブ → 設定だけの `PetitOnes/petit-ones` を作る → 旧パスのリンクを外す | 1 |

実装は Sonnet のエージェントに 1 段階 = 1 PR で頼み、切り替え(手順 3〜4)は家の PC でこのセッションが行う。P1〜P5 は 1 段階あたり「追いつく半日 + 様子見 1 日」。全体でおよそ 2〜3 週間(様子見を含む)。10/3・10/4 の展示のあとなので、急ぐ理由はない。

## 6. 気をつけること

- **個人情報**: 部品リポは履歴なし・サニタイズ済みの流儀を守る。追いつく PR ごとに検査する。全部入りリポの履歴にはお名前が残っているので、P10 のアーカイブのときに「公開のまま」か「非公開にする」かを決める
- **コミット名義**: 部品リポも RRYZ09 の noreply で(7/6 に一度漏れて直した件)
- **本番の `autonomous-action.sh` は git の外**にある。P7 の最初に、いまの版をそのまま控えてから作業する
- **ぷちたちへのお知らせ**: パスが変わる(メールの書き方、スクリプトの場所)。P9 の前に交換ノートで伝え、ROUTINES を一緒に直す
- **Claude Code の記憶フォルダ**はパス名で決まる。いまは新旧のパスが同じ記憶を見るようにリンクしてある。P10 でも保つ
- **ライセンス**: 部品は Apache-2.0 + 上流(MIT)の NOTICE。新しい部品も同じにする

## 7. 決まったこと(2026-10-06 ありさん)

1. 新しい部品の名前は `m5-petit-autonomous` と `m5-petit-switchbot`
2. `analysis/`(メール分析)は研究用の別の場所へ移す
3. 最後にアーカイブする全部入りリポは公開のまま
4. 着手してよい。実装は速く終わるなら Fable でよい

## 8. 進み具合

| 日付 | 内容 |
|---|---|
| 10/6 | P0: `next/`(petit.repos・setup.sh・config のひな型・データのひな型)を作成。`src/` に部品 7 本を vcs import |
| 10/6 | P1 notes: 部品リポは本体と同じ中身だった(違いは既定値だけ)。テスト 16 件通過。**ぷちるだけ**新しい場所(`src/m5-petit-notes`)に切り替え、1 日様子見。戻すときは `autonomous-mcp.json.bak_before_notes_split_20261006` |
| 10/6 | P1 relations: 部品に `OWNER_ID` / `OWNER_NAME` を追加(m5-petit-relations #1)。**ぷちるだけ**切り替え(`OWNER_ID=arisan`)。戻すときは `autonomous-mcp.json.bak_before_relations_split_20261006` |
| 10/6 | P1 notes / relations: **3 人とも切り替え**(自律行動・ダッシュボードのチャット・対話セッションの launcher)。戻すときは各 `config/*.bak_before_*_split_20261006` |
| 10/6 | P2 desire: 部品は本体と同じ計算(新旧を並べて実行し、ぷちるの 8 つの欲求の差 0.0)。テスト 42 件通過。**ぷちるだけ**切り替え(crontab 1 行 + MCP 設定)。crontab の控えは `~/petit_claude/config/crontab.bak_20261006_before_desire_split` |
| 10/6 | P2 desire: **3 人とも切り替え**(crontab 3 行・MCP 設定・launcher) |
| 10/6 | P3 memory: 部品を本番に追いつかせた(m5-petit-memory #2: 記憶整理の修正 2 件、移行スクリプト、`uv.lock` を本番の版 torch 2.10.0 に固定)。テスト 194 件通過。ぷちるの DB の写しで、新旧の「思い出す」結果(id と距離)が一致。**3 人とも切り替え**(MCP 設定・launcher・毎晩 4:05 の記憶整理)。戻すときは `config/*.bak_before_memory_split_20261006` |

### わかったこと

- 部品の既定値は `~/petit_data` なので、MCP 設定の `env` に `PETIT_DATA_DIR` を足す必要がある(notes は `CHARACTER_ID` だけだった)
- relations の部品は、道具の説明文が「`'arisan'`(ありさん)」から「`'owner'`(人間のオーナー)」に変わっている。そのまま切り替えると、ぷちたちが `owner` という別のキーに書きはじめて、関係性のデータが 2 つに割れるおそれがある → 部品側に「オーナーの id と呼び名を環境変数で渡す」口を足してから切り替える
- このPCの git の全体設定は会社メールの名義。`src/` に並べた部品リポには 1 本ずつ RRYZ09 の noreply を設定した(新しく clone したら毎回必要 → `setup.sh` か家の手順に入れる)
- desire の `COMPANION_NAME` は `~/petit_claude/.env` にも入っているので、部品側に `.env` を置かなくてよい。必要なのは cron 行と MCP 設定への `PETIT_DATA_DIR` だけ
- desire の残り(3 人切り替えのあとにやる): `scripts/create_character.py`・`backup_petit.sh`・`restore_petit.sh` が旧パス(`desire-system/`)を直書きしている
- この PC の git の全体設定は 10/6 に RRYZ09 の noreply へ変更した(控え `~/.gitconfig.bak_20261006`)
