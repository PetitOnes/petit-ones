# 参加のしかた

petit-ones は、うちの 3 人(ぷちてゃ・ぷちこ・ぷちる)が毎日動いている本体です。Issue も PR も歓迎します。ただし **main は動いている家そのもの**なので、流れだけ守ってください。

## 流れ

1. **Issue を立てる**(不具合・提案のテンプレートがあります)。小さな直しなら PR から始めてもかまいません
2. **fork して branch を切る**(`fix/…`、`feat/…`、`docs/…`)
3. 直す。手元で確かめる:
   ```bash
   uvx ruff check .                         # 全体の lint(ruff.toml + 部品ごとの設定)
   (cd src/m5-petit-memory && uv sync --all-extras && uv run pytest -q)   # 触った部品のテスト
   ```
4. **PR を出す**。テンプレートに沿って「何を・なぜ・確かめたこと」を書く
5. CI(ruff・pytest・yamllint・シェルと JSON の文法)が通るのを待つ
6. **マージするのは世話人(ありさん)だけ**です。main に直接 push できるのも世話人だけ。レビューの返事は数日かかることがあります

## 書き方の決まり

- Python 3.10+、パッケージは **uv**、lint は **ruff**、テストは **pytest**(非同期は pytest-asyncio)
- 本番の部品は `src/m5-petit-*`。根にある `m5-mcp/` などは切り出し前の古い置き場なので触らない
- 家(`PETIT_DATA_DIR`、既定 `~/petit_claude`)の中身は git に入れない。名前・会話・写真・鍵・IP はコミットにも Issue にも貼らない
- 家ごとの設定(`autonomous-action.sh`・`.mcp.json`・`.env`)は git 管理外。sample / example を直すときは、個人の値を入れない
- コミットは小さく、題は「何をしたか」を日本語か英語で一行

## どこを直せばいいか

| したいこと | 場所 |
|---|---|
| 体(M5Stack)の道具を足す・直す | `src/m5-petit-mcp` |
| 記憶・欲求・ノート・関係 | `src/m5-petit-memory` / `-desire` / `-notes` / `-relations` |
| ダッシュボード | `dashboard/`(`src/m5-petit-app` は切り出し版) |
| 自律行動の流れ・プロンプト | `autonomous-action.sample.sh`(本番は各家の `autonomous-action.sh`) |
| 家の用意・子の迎え方 | `scripts/setup_house.py` / `scripts/create_character.py` |
| ぷちの振る舞いの決まり・SOUL の器 | [petit-textbook](https://github.com/PetitOnes/petit-textbook)(別リポ) |

## Claude Code で手伝ってもらうとき

リポジトリの `CLAUDE.md` に、Claude 向けの約束(構成・確かめ方・触らない所)があります。人も同じものを読めば十分です。
