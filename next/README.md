# next/ — 設定だけの petit-ones(準備中)

このフォルダが、移行のあと `PetitOnes/petit-ones` の中身になります(設計: `../docs/petit-ones-split-design.md`)。

- `petit.repos` — 部品の一覧。`vcs import src < petit.repos`
- `setup.sh` — 部品を並べる → uv sync → データのひな型を `~/petit_data` に置く
- `config/` — 環境変数・MCP 設定・時刻表のひな型
- `template/petit_data/` — データのひな型(`~/petit_data` にコピーされる)
