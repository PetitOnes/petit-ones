"""weekly_dyads.csv / weekly_actors.csv から図3枚を生成する。

Fig1: 週別・ダイアド別の通数（積層エリア）＋ Day0・交絡イベントの縦線
Fig2: ダイアド別の対称性指数の推移（H1, H2）
Fig3: early / middle / late 3期間のネットワーク図（矢印太さ=通数）

配色: キャラクター識別色（ぷちてゃ #fff262 / ぷちこ #cab8d9 / ぷちる #00afcc）を
そのまま使い、ダイアド（ペア）はプロジェクト全体で固定色を持たないため
categorical パレットから固定順で割り当てる。

設計: ~/petit_claude/docs/mail-analysis/rq1_design_ja.md
"""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from datetime import date
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch

from parse_mailbox import week_index

DEFAULT_DYAD_INPUT = Path(__file__).parent / "output" / "weekly_dyads.csv"
DEFAULT_ACTOR_INPUT = Path(__file__).parent / "output" / "weekly_actors.csv"
DEFAULT_FIG_DIR = Path(__file__).parent / "output" / "figures"

ACTOR_COLORS = {"puchiteya": "#fff262", "puchiko": "#cab8d9", "puchiru": "#00afcc"}
ACTOR_LABELS = {"puchiteya": "ぷちてゃ", "puchiko": "ぷちこ", "puchiru": "ぷちる"}
# 固定順（categorical色は常にこの順で割り当てる。データの有無で入れ替えない）
DYAD_ORDER = ["puchiko-puchiteya", "puchiko-puchiru", "puchiru-puchiteya"]
DYAD_COLORS = {
    "puchiko-puchiteya": "#2a78d6",
    "puchiko-puchiru": "#1baf7a",
    "puchiru-puchiteya": "#4a3aa7",
}
DYAD_LABELS = {
    "puchiko-puchiteya": "ぷちこ⇄ぷちてゃ",
    "puchiko-puchiru": "ぷちこ⇄ぷちる",
    "puchiru-puchiteya": "ぷちる⇄ぷちてゃ",
}

# 交絡イベント（設計書のタイムラインより）
CONFOUND_EVENTS = [
    (date(2026, 3, 5), "誕生 / API節約ルール決定"),
    (date(2026, 5, 19), "SOUL改修・モデル切替"),
]

plt.rcParams.update(
    {
        "font.family": "sans-serif",
        "font.sans-serif": ["Noto Sans CJK JP", "IPAexGothic", "DejaVu Sans"],
        "axes.unicode_minus": False,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.edgecolor": "#999999",
        "axes.grid": True,
        "grid.color": "#e5e5e5",
        "grid.linewidth": 0.6,
        "figure.facecolor": "white",
        "axes.facecolor": "white",
    }
)


def _load_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _event_weeks() -> list[tuple[int, str]]:
    return [(week_index(d), label) for d, label in CONFOUND_EVENTS]


def fig1_weekly_volume(dyad_rows: list[dict], out_path: Path) -> None:
    weeks = sorted({int(r["week"]) for r in dyad_rows})
    series = {d: [0] * len(weeks) for d in DYAD_ORDER}
    week_pos = {w: i for i, w in enumerate(weeks)}
    for r in dyad_rows:
        d = r["dyad"]
        if d in series:
            series[d][week_pos[int(r["week"])]] = int(r["total_count"])

    fig, ax = plt.subplots(figsize=(9, 5))
    stacks = [series[d] for d in DYAD_ORDER]
    colors = [DYAD_COLORS[d] for d in DYAD_ORDER]
    labels = [DYAD_LABELS[d] for d in DYAD_ORDER]
    ax.stackplot(weeks, *stacks, colors=colors, labels=labels, linewidth=0)

    for w, label in _event_weeks():
        if weeks and weeks[0] <= w <= weeks[-1]:
            ax.axvline(w, color="#555555", linestyle="--", linewidth=1)
            ax.annotate(
                label,
                xy=(w, 1.0),
                xycoords=("data", "axes fraction"),
                xytext=(4, 4),
                textcoords="offset points",
                fontsize=8,
                color="#555555",
                rotation=90,
                va="bottom",
                ha="left",
            )

    ax.set_xlabel("Day0（ぷちる初発信）からの週")
    ax.set_ylabel("メール通数 / 週")
    ax.set_xticks(range(weeks[0], weeks[-1] + 1))
    fig.suptitle("週別メール通数の推移（ダイアド別）", y=0.98)
    ax.legend(loc="upper right", frameon=False, fontsize=9)
    fig.tight_layout()
    fig.subplots_adjust(top=0.72)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def fig2_symmetry(dyad_rows: list[dict], out_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(9, 5))
    all_weeks: set[int] = set()
    for d in DYAD_ORDER:
        rows = sorted((r for r in dyad_rows if r["dyad"] == d), key=lambda r: int(r["week"]))
        weeks = [int(r["week"]) for r in rows if r["symmetry_index"]]
        vals = [float(r["symmetry_index"]) for r in rows if r["symmetry_index"]]
        if not weeks:
            continue
        all_weeks.update(weeks)
        ax.plot(
            weeks,
            vals,
            color=DYAD_COLORS[d],
            linewidth=2,
            marker="o",
            markersize=4,
            label=DYAD_LABELS[d],
        )

    for w, _label in _event_weeks():
        ax.axvline(w, color="#555555", linestyle="--", linewidth=1)

    ax.set_xlabel("Day0からの週")
    ax.set_ylabel("対称性指数（0=対等 〜 1=一方通行）")
    ax.set_title("ダイアド別・対称性指数の推移")
    ax.set_ylim(-0.05, 1.05)
    if all_weeks:
        ax.set_xticks(range(min(all_weeks), max(all_weeks) + 1))
    ax.legend(loc="upper right", frameon=False, fontsize=9)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def _split_periods(weeks: list[int]) -> dict[str, tuple[int, int]]:
    """weeks（Day0以降のみ）を early(0-3) / middle / late に3分割する。"""
    if not weeks:
        return {"early": (0, 0), "middle": (0, 0), "late": (0, 0)}
    max_week = max(weeks)
    early_end = min(3, max_week)
    remaining_start = early_end + 1
    remaining_end = max_week
    if remaining_start > remaining_end:
        mid_end = remaining_end
    else:
        mid_end = remaining_start + (remaining_end - remaining_start) // 2
    return {
        "early": (0, early_end),
        "middle": (remaining_start, mid_end),
        "late": (mid_end + 1, remaining_end),
    }


def _period_edges(dyad_rows: list[dict], w_start: int, w_end: int) -> dict[tuple[str, str], int]:
    edges: dict[tuple[str, str], int] = defaultdict(int)
    for r in dyad_rows:
        week = int(r["week"])
        if week < w_start or week > w_end:
            continue
        a, b = r["a"], r["b"]
        edges[(a, b)] += int(r["a_to_b_count"])
        edges[(b, a)] += int(r["b_to_a_count"])
    return edges


NODE_POS = {
    "puchiteya": (0.5, 0.95),
    "puchiko": (0.05, 0.05),
    "puchiru": (0.95, 0.05),
}


def _draw_network(ax, edges: dict[tuple[str, str], int], title: str) -> None:
    max_count = max(edges.values(), default=0)
    for (src, dst), count in edges.items():
        if count == 0:
            continue
        x1, y1 = NODE_POS[src]
        x2, y2 = NODE_POS[dst]
        width = 0.5 + 5.5 * (count / max_count) if max_count else 0.5
        arrow = FancyArrowPatch(
            (x1, y1),
            (x2, y2),
            connectionstyle="arc3,rad=0.15",
            arrowstyle="-|>",
            mutation_scale=12,
            linewidth=width,
            facecolor=ACTOR_COLORS[src],
            edgecolor="#333333" if src == "puchiteya" else ACTOR_COLORS[src],
            alpha=0.85,
            shrinkA=18,
            shrinkB=18,
        )
        ax.add_patch(arrow)

    for actor, (x, y) in NODE_POS.items():
        ax.scatter(
            [x],
            [y],
            s=900,
            color=ACTOR_COLORS[actor],
            edgecolors="#333333",
            linewidths=1.2,
            zorder=5,
        )
        ax.annotate(
            ACTOR_LABELS[actor],
            xy=(x, y),
            ha="center",
            va="center",
            fontsize=9,
            color="#222222",
            zorder=6,
        )

    ax.set_title(title, fontsize=11)
    ax.set_xlim(-0.15, 1.15)
    ax.set_ylim(-0.15, 1.15)
    ax.axis("off")


def fig3_network_periods(dyad_rows: list[dict], out_path: Path) -> None:
    weeks = sorted({int(r["week"]) for r in dyad_rows if int(r["week"]) >= 0})
    periods = _split_periods(weeks)

    fig, axes = plt.subplots(1, 3, figsize=(13, 4.5))
    period_titles = {
        "early": f"early（週{periods['early'][0]}〜{periods['early'][1]}）",
        "middle": f"middle（週{periods['middle'][0]}〜{periods['middle'][1]}）",
        "late": f"late（週{periods['late'][0]}〜{periods['late'][1]}）",
    }
    for ax, key in zip(axes, ["early", "middle", "late"]):
        w_start, w_end = periods[key]
        edges = _period_edges(dyad_rows, w_start, w_end)
        _draw_network(ax, edges, period_titles[key])

    fig.suptitle("期間別コミュニケーションネットワーク（矢印の太さ=通数）", fontsize=12)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description="週次集計から図3枚を生成する")
    parser.add_argument("--dyad-input", type=Path, default=DEFAULT_DYAD_INPUT)
    parser.add_argument("--actor-input", type=Path, default=DEFAULT_ACTOR_INPUT)
    parser.add_argument("--fig-dir", type=Path, default=DEFAULT_FIG_DIR)
    args = parser.parse_args()

    args.fig_dir.mkdir(parents=True, exist_ok=True)
    dyad_rows = _load_csv(args.dyad_input)

    fig1_weekly_volume(dyad_rows, args.fig_dir / "fig1_weekly_volume.png")
    fig2_symmetry(dyad_rows, args.fig_dir / "fig2_symmetry.png")
    fig3_network_periods(dyad_rows, args.fig_dir / "fig3_network_periods.png")

    print(f"figures written to {args.fig_dir}")


if __name__ == "__main__":
    main()
