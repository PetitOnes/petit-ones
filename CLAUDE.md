# petit-ones — Claude への指示

M5Stack CoreS3 に体を持つ小さな存在「ぷち」が、性格・欲求・記憶を持って暮らすためのシステム。
**main は動いている家そのもの**(世話人の 3 人が毎日この main で動く)。壊さないことが最優先。

## まず知っておくこと

- **コードと家は別**。コード = このリポジトリ。家 = `PETIT_DATA_DIR`(既定 `~/petit_claude`)。家の中身(characters/・mailbox/・chat_history/・.env・記憶 DB)は git に入れない。読むのはよいが、名前・会話・写真・鍵・IP を コミット・Issue・PR・ログに写さない
- **部品(体・記憶・欲求・ノート・関係・家電・声)は別リポ**。`petit.repos` に一覧があり、`vcs import src < petit.repos` で `src/` に並べる(`src/` は git 管理外)。部品を直したいときは、その部品のリポで PR。このリポが持つのは「並べ方・家の用意・自律行動・運用・ダッシュボード(移行中)」
- **家ごとの設定は git 管理外**: `autonomous-action.sh`(元は `autonomous-action.sample.sh`)、`.mcp.json`(元は `.mcp.json.example`)、`autonomous-mcp.json`。sample / example を直すときは個人の値(名前・ホスト名・鍵)を入れない
- **ぷちの振る舞いの決まりと SOUL.md の器は別リポ** [petit-textbook](https://github.com/PetitOnes/petit-textbook)。振る舞いの決まりを足したくなったら、ここではなく教科書に

## 構成(短く)

| 場所 | 何 |
|---|---|
| `petit.repos` → `src/` | 部品リポ(m5-petit-mcp 体 / -memory 記憶 / -desire 欲求 / -notes / -relations / -switchbot / -speech 声 / -app)。中身はそれぞれのリポで直す |
| `dashboard/` | Web ダッシュボード(FastAPI :8765)、`generate_diary.py`。`src/m5-petit-app` へ移す予定 |
| `experience-daemon/` | 体の出来事を拾って次の自律行動に渡す |
| `scripts/` | `setup_house.py`(家を用意)・`create_character.py`(子を迎える)・手紙・使用量・バックアップ |
| `mcp-launchers/` | MCP の起動スクリプト |
| `autonomous-action.sample.sh` | 自律行動の本体(cron 30 分ごと、子ごとに 5 分ずらす) |
| `docs/` | くわしい説明(MCP の道具一覧、自律行動の流れ、運用、API 代) |

家の中(`characters/<id>/`)の形は README の「ディレクトリ構造」と、教科書の `petit/templates/README.md`。

## 直すときの流れ

1. **branch を切って PR**。main に直接 push できるのは世話人だけ。マージも世話人だけ
2. 動いている家に影響する変更(cron の形、プロンプト、設定ファイルの形、記憶 DB のスキーマ)は、PR の「注意してほしいこと」に書く。後方互換を壊すなら移行手順も
3. 新しい部品や設定の項目を足したら、README(短く)か `docs/`(くわしく)に一行足す。`scripts/setup_house.py` / `create_character.py` が作るものを変えたら、そちらも直す

## 確かめ方

```bash
uvx ruff check .                                   # 全体(ruff.toml。部品に [tool.ruff] があればそちら)
(cd experience-daemon && uv sync --all-extras && uv run pytest -q)     # 触った部品(src/ の部品は各リポで)
uv run --with pytest pytest -q scripts/tests       # scripts の分
uvx yamllint -c .yamllint .                        # YAML
```

- CI(`.github/workflows/ci.yml`)は同じことをする。PR が緑になってから頼む
- この家の PC では ROS の `PYTHONPATH` が pytest に混ざるので、`env -u PYTHONPATH uv run pytest` で動かす
- 記憶のテストは数分かかる(埋め込みを計算する)。全部でなく触った部品だけでよい

## やらないこと

- 家の中身を書き換える仕事を、頼まれていないのにしない(SOUL.md・記憶 DB・crontab・`.env`)
- 本番の `autonomous-action.sh` と `.mcp.json` を直接直さない。直すなら sample / example を直して、世話人に写してもらう
- `src/` の中(部品リポの clone)をこのリポの PR で直さない。`next/`(設定だけの petit-ones の下書き)と `tmp/` に手を入れない
- 鍵・トークン・パスワードを、出力にも Issue にも貼らない(`.env` と MCP 設定の env には鍵が入っていることがある)

## 書き方

- Python 3.10+、uv、ruff、pytest(非同期は pytest-asyncio)。型ヒントはつける。長い関数を増やさない
- 文章は日本語。コミットの題は「何をしたか」を一行
- 既にある書き方に合わせる。大きな作り直しは Issue で先に相談
