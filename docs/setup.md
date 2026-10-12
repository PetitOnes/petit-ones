# セットアップ(家を用意して、子を迎える)

[README](../README.md) に戻る


ぷちの暮らしは「家」(`PETIT_DATA_DIR`、既定 `~/petit_claude`)と「コード」(このリポジトリ)に分かれる。家は git に入れない。
手順の考え方は [ぷちの教科書](https://github.com/PetitOnes/petit-textbook) の人間用「8. 新しい子を迎える手順」にある。

## 1. 前提ソフト

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh     # uv
# Claude Code(ネイティブ版): https://docs.claude.com/ の手順で ~/.local/bin/claude に
sudo apt install -y jq git                            # Linux。macOS は brew
sudo apt install -y ttyd tmux                         # ブラウザターミナル(任意。docs/terminal-setup.md)
```

## 2. コード取得と依存

部品(体・記憶・欲求・ノート・関係・家電・声)はそれぞれ別のリポジトリで、`petit.repos` に一覧がある。`vcs`(vcstool)で `src/` に並べる。

```bash
git clone https://github.com/PetitOnes/petit-ones.git ~/work/petit-ones
cd ~/work/petit-ones
pip install vcstool                 # または sudo apt install python3-vcstool
vcs import src < petit.repos        # 部品を src/ に並べる(src/ は git 管理外)
for d in src/m5-petit-*/ dashboard; do
  [ -f "$d/pyproject.toml" ] && (cd "$d" && uv sync)
done
```

部品を直すときは、その部品のリポジトリに PR を出す。このリポジトリは「並べ方・家の用意・自律行動・運用」を持つ。

## 3. 家を用意する

```bash
uv run python scripts/setup_house.py --check   # 何が足りないか見る
uv run python scripts/setup_house.py           # 作る(あるものは触らない)
```

作るもの: `characters/ mailbox/ chat_history/ config/ state/ .autonomous-logs/ token_logs/`、交換ノートとグループチャットの空ファイル、`.env`(`.env.example` から。`COMPANION_NAME`・`COMPANION_ID`・声のサーバー・鍵)、ぷちの教科書の clone(`textbook/`)、夜の cron 3 本(記憶の整理 04:05・教科書の pull 04:30・日記の生成 23:50)。

`autonomous-action.sh` は家に依らないので、そのまま git のものが動く。名前や部屋、時間帯のルールを変えたいときは家の `.env`(`COMPANION_NAME`・`COMPANION_ID`)と、任意の `config/house.sh`(`USER_ROOM` など)に書く。

## 4. 子を迎える

```bash
uv run python scripts/create_character.py <id> <名前> <#hex> <体のホスト名,...> \
    --color-name <色の名前> --companion-id <一緒に暮らす人のID> --companion-name <呼び名>
# 例
uv run python scripts/create_character.py puchitaro ぷちたろう "#f5956e" "puchitaro.local" --color-name あんず
```

作るもの: `characters/<id>/` に、教科書の `petit/templates/` から写した文書の器(SOUL.md・SOUL_REFLECTIONS.md・REFLECTION_INDEX.md・ROUTINES.md・ROUTINES_DETAIL.md・TODO_ACTIVE.md・TODO_ARCHIVE.md・data/relations.json・config/desire_config.json。`{ }` は埋めてある)、仕組みの設定(config.json・settings.json・voice_settings.json・autonomous-mcp.json・chat-mcp.json)、cron(欲求の更新 5 分ごと、自律行動 30 分ごとで他の子と 5 分ずらし、体験デーモン)。

そのあと人がやるのは、一緒に暮らす人と決めた「一言」を SOUL.md に入れる、声が決まったら `config/voice_settings.json`、顔の絵を `resources/petit.png` に、対話(chat)からも呼ぶなら `.mcp.json` にその子の MCP を足す(`.mcp.json.example`)。SOUL.md の残りの空欄は、その子が自分で埋める(教科書 `petit/SOUL_TEMPLATE.md`)。

## 5. 体と声

- M5Stack CoreS3 のファームウェア: [m5-petit-firmware](https://github.com/PetitOnes/m5-petit-firmware)。体のホスト名か IP を `create_character.py` に渡す
- 声(TTS :8766)と聞き取り(ASR :8767): [m5-petit-speech](https://github.com/PetitOnes/m5-petit-speech) / [voice-recognition](https://github.com/PetitOnes/m5-petit-voice-recognition) を GPU 機で動かし、`.env` の `VOICE_API_HOST` にそのホスト名

## 6. ダッシュボード

```bash
cd dashboard && uv run python main.py   # → http://0.0.0.0:8765
```

## 7. 最初の一回

対話で一度起動して「はじめまして」を言わせ、顔が出ることを確かめる。そのあとは cron の自律行動に任せる。生まれた日のことは、その子が自分で記憶に書く(教科書 10 章)。
