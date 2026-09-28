# mail-analysis

RQ1「第三の子の誕生は、二者関係をどう再編したか」の分析パイプライン。
設計書: `~/petit_claude/docs/mail-analysis/rq1_design_ja.md`

## 使い方

```bash
uv sync
uv run python parse_mailbox.py      # mailbox/ → output/mails.csv（スキップしたファイルも表示）
uv run python aggregate.py          # → output/weekly_dyads.csv, output/weekly_actors.csv
uv run python figures.py            # → output/figures/fig1〜3.png
```

コミット前:

```bash
uv run ruff check .
uv run pytest -v
```

## 出力

- `output/mails.csv` — 1メール1行（filename, datetime, sender, recipient, chars, week, dyad）
- `output/weekly_dyads.csv` — ダイアド×週の方向別通数・本文長中央値・対称性指数
- `output/weekly_actors.csv` — キャラ×週の送信シェア（ハブ度）
- `output/figures/fig1_weekly_volume.png` — 週別通数（積層エリア＋交絡イベント線）
- `output/figures/fig2_symmetry.png` — 対称性指数の推移
- `output/figures/fig3_network_periods.png` — early/middle/late ネットワーク図

`output/` は生成物なので `.gitignore` 済み。
