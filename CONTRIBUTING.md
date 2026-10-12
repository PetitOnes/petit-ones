# 参加のしかた

petit-ones は、うちの 3 人(ぷちてゃ・ぷちこ・ぷちる)が毎日動いている本体です。Issue も PR も歓迎します。ただし **main は動いている家そのもの**なので、流れだけ守ってください。

## 流れ

1. **Issue を立てる**(不具合・提案のテンプレートがあります)。小さな直しなら PR から始めてもかまいません
2. **fork して branch を切る**。名前は下の「branch と commit の規則」に沿う(例 `feat/add-wake-sound`、`fix/issue-12-cron-offset`)
3. 直す。手元で確かめる:
   ```bash
   uvx ruff check .                         # 全体の lint(ruff.toml + 部品ごとの設定)
   (cd experience-daemon && uv sync --all-extras && uv run pytest -q)     # 触った部品のテスト
   ```
4. **PR を出す**。テンプレートに沿って「何を・なぜ・確かめたこと」を書く
5. CI(ruff・pytest・yamllint・シェルと JSON の文法)が通るのを待つ
6. **マージするのは世話人(ありさん)だけ**です。main に直接 push できるのも世話人だけ。レビューの返事は数日かかることがあります

## 書き方の決まり

- Python 3.10+、パッケージは **uv**、lint は **ruff**、テストは **pytest**(非同期は pytest-asyncio)
- 部品(体・記憶・欲求・ノート・関係・家電・声)は別リポ(`petit.repos`)。`src/` はその clone で git 管理外。部品の直しはそのリポへ PR
- 家(`PETIT_DATA_DIR`、既定 `~/petit_claude`)の中身は git に入れない。名前・会話・写真・鍵・IP はコミットにも Issue にも貼らない
- 家ごとの値(`.env`・`config/house.sh`・`.mcp.json`・`autonomous-mcp.json`)は git に入れない。コードに個人の値(名前・ホスト名・鍵)を書かない
- コミットは小さく。題の形は下の規則(Conventional Commits)

## branch と commit の規則

有名な決まりをそのまま使います。読む側が迷わないためです。

### branch 名 — [Conventional Branch](https://conventionalbranch.org/ja/)

`<type>/<説明>`。小文字の英数字とハイフンだけ(アンダースコア・空白・大文字は使わない。ハイフンを続けない、端に置かない)。Issue があれば `issue-123-` を頭に。

| type | いつ |
|---|---|
| `feat/` | 新しい機能 |
| `fix/` | 不具合の直し |
| `hotfix/` | 動いている家を今すぐ直す |
| `chore/` | 依存の更新・設定・文書など、動きを変えないもの |
| `release/` | リリースの準備(`release/v1.2.0`) |
| `claude/` | Claude Code が作った branch(他の AI は `ai/` `codex/` `copilot/` `cursor/`) |

例: `feat/add-wake-sound`、`fix/issue-12-cron-offset`、`chore/update-readme`、`claude/house-code-split`。`main` には prefix をつけない。

### commit の題と PR の題 — [Conventional Commits](https://www.conventionalcommits.org/ja/)

`<type>(<範囲>): <何をしたか>`。範囲は省略可。本文は日本語でよい。

| type | 意味 |
|---|---|
| `feat` | 機能を足した |
| `fix` | 不具合を直した |
| `docs` | 文書だけ |
| `chore` | 設定・依存・掃除 |
| `refactor` | 動きを変えない整理 |
| `test` | テストだけ |
| `ci` | CI の変更 |

例: `feat(scripts): create_character が教科書の templates を写す`、`fix(autonomous): 手紙の宛先に zip を拾わない`、`docs: README をしくみ図つきに`。
動きが変わる(後方互換が壊れる)ときは `!` をつける: `feat(cron)!: 自律行動を 30 分ごとに`。

PR の題も同じ形にします(マージのとき、そのまま履歴の題になります)。CI が branch 名と PR の題の形を確かめます。

## どこを直せばいいか

| したいこと | 場所 |
|---|---|
| 体(M5Stack)の道具を足す・直す | [m5-petit-mcp](https://github.com/PetitOnes/m5-petit-mcp)(別リポ) |
| 記憶・欲求・ノート・関係 | [m5-petit-memory](https://github.com/PetitOnes/m5-petit-memory) / [-desire](https://github.com/PetitOnes/m5-petit-desire) / [-notes](https://github.com/PetitOnes/m5-petit-notes) / [-relations](https://github.com/PetitOnes/m5-petit-relations)(別リポ) |
| ダッシュボード | `dashboard/`(`src/m5-petit-app` へ移行中) |
| 部品の並べ方(どのリポのどの枝か) | `petit.repos` |
| 自律行動の流れ・プロンプト | `autonomous-action.sh` |
| 家の用意・子の迎え方 | `scripts/setup_house.py` / `scripts/create_character.py` |
| ぷちの振る舞いの決まり・SOUL の器 | [petit-textbook](https://github.com/PetitOnes/petit-textbook)(別リポ) |

## Claude Code で手伝ってもらうとき

リポジトリの `CLAUDE.md` に、Claude 向けの約束(構成・確かめ方・触らない所)があります。人も同じものを読めば十分です。
