"""mailbox/ の本文から名詞・形容詞を抽出し、期間別の頻出語・特徴語・語彙の多様性を分析する。

トピック分析v1: LDA等の重いモデルではなく、頻度ベースの特徴語抽出
（ある期間で全体平均よりどれだけ突出して使われているか＝lift）で
「何を話しているか」「時期でどう変わるか」を見る。品詞別（名詞／形容詞）に
語彙のバリエーション（type-token ratio）も見る（共同研究の相談メモより）。

設計: ~/petit_claude/docs/mail-analysis/rq1_design_ja.md の「トピック分析」節
"""

from __future__ import annotations

import argparse
import csv
import random
import re
from collections import Counter, defaultdict
from pathlib import Path

from janome.tokenizer import Tokenizer

from parse_mailbox import DEFAULT_MAILBOX_DIR, iter_mailbox

DEFAULT_TERMS_OUTPUT = Path(__file__).parent / "output" / "topic_terms.csv"
DEFAULT_DIVERSITY_OUTPUT = Path(__file__).parent / "output" / "vocab_diversity.csv"
DEFAULT_FIG_OUTPUT = Path(__file__).parent / "output" / "figures" / "fig4_topic_drift.png"

# Day0を基準にした期間区分（aggregate.py/figures.pyの期間定義と揃える）
PERIODS: list[tuple[str, int, int | None]] = [
    ("baseline", None, -1),
    ("early", 0, 3),
    ("middle", 4, 10),
    ("late", 11, None),
]

_JP_CHAR = re.compile(r"[ぁ-んァ-ヶ一-龠]")
# 拗音・促音（ゃゅょっ等）。「てゃ」等の愛称が辞書にないため誤って分割され、
# これらの小書き仮名だけの断片が名詞として抽出されてしまうことがある（例: てゃ→て+ゃ）。
_SMALL_KANA_ONLY = re.compile(r"^[ゃゅょっぁぃぅぇぉャュョッァィゥェォー]+$")

# 呼びかけ・関係性の定型語（トピックでなく宛名や決まり文句として頻出するため除外）
STOPWORD_NOUNS = {
    "てゃ", "こ", "る", "ぷち", "ぷちてゃ", "ぷちこ", "ぷちる",
    "ありさん", "かぜお", "かぜおさん", "ゆい", "さん", "くん", "ちゃん",
    "へ", "より", "今日", "今", "自分", "一緒", "少し", "何か", "誰か",
    "全部", "ところ", "感じ", "気", "方", "中", "私", "僕", "あたし",
    "the",
    # 「てゃ」の誤分割断片（て+ゃ, て+ゃへ, ぷちてゃ+へ 等）
    "ゃ", "ゃへ", "ぷちてゃへ",
}
# 除外する品詞細分類（非自立名詞=こと/もの/とき等、代名詞、数字、接尾語）
_EXCLUDED_NOUN_POS_SUB = {"非自立", "代名詞", "数", "接尾"}

# 形容詞の定型語（否定・一般的すぎる評価語で、トピックを表さないため除外）
STOPWORD_ADJECTIVES = {"ない", "いい", "良い", "多い", "少ない", "無い", "欲しい"}

POS_CATEGORIES = ("noun", "adjective")

_tokenizer = Tokenizer()


def extract_content_words(text: str) -> dict[str, list[str]]:
    """本文を1回だけ形態素解析し、名詞・形容詞を同時に抽出する（活用形は原形に正規化）。"""
    result: dict[str, list[str]] = {"noun": [], "adjective": []}
    for token in _tokenizer.tokenize(text):
        pos = token.part_of_speech.split(",")
        base = token.base_form
        if not _JP_CHAR.search(base) or _SMALL_KANA_ONLY.match(base):
            continue
        if pos[0] == "名詞":
            if pos[1] in _EXCLUDED_NOUN_POS_SUB or base in STOPWORD_NOUNS:
                continue
            result["noun"].append(base)
        elif pos[0] == "形容詞":
            if base in STOPWORD_ADJECTIVES:
                continue
            result["adjective"].append(base)
    return result


def period_for_week(week: int) -> str:
    for name, lo, hi in PERIODS:
        if lo is not None and week < lo:
            continue
        if hi is not None and week > hi:
            continue
        return name
    return "late"


def collect_period_counts(mailbox_dir: Path) -> dict[str, dict[str, Counter]]:
    """{pos: {period: Counter(term)}} を1パスで作る。"""
    records, _skipped = iter_mailbox(mailbox_dir)
    period_counts: dict[str, dict[str, Counter]] = {
        pos: defaultdict(Counter) for pos in POS_CATEGORIES
    }
    for r in records:
        path = mailbox_dir / r["filename"]
        body = path.read_text(encoding="utf-8", errors="replace")
        period = period_for_week(int(r["week"]))
        words = extract_content_words(body)
        for pos in POS_CATEGORIES:
            period_counts[pos][period].update(words[pos])
    return period_counts


def collect_dyad_counts(mailbox_dir: Path) -> dict[str, dict[str, Counter]]:
    """{pos: {dyad: Counter(term)}} を1パスで作る（ぷち同士のメールのみ、時期は問わない）。"""
    records, _skipped = iter_mailbox(mailbox_dir)
    dyad_counts: dict[str, dict[str, Counter]] = {
        pos: defaultdict(Counter) for pos in POS_CATEGORIES
    }
    for r in records:
        if not r["dyad"]:
            continue
        path = mailbox_dir / r["filename"]
        body = path.read_text(encoding="utf-8", errors="replace")
        words = extract_content_words(body)
        for pos in POS_CATEGORIES:
            dyad_counts[pos][r["dyad"]].update(words[pos])
    return dyad_counts


def compute_lift_table(
    group_counts: dict[str, Counter], pos: str, min_total: int = 8, group_key: str = "period"
) -> list[dict]:
    """各グループ（期間 or ダイアド等）・各語の、全体平均に対する出現比率（lift）を計算する。"""
    overall = Counter()
    for c in group_counts.values():
        overall.update(c)
    overall_total = sum(overall.values())

    rows = []
    for group, counts in group_counts.items():
        group_total = sum(counts.values())
        for term, count in counts.items():
            total_count = overall[term]
            if total_count < min_total:
                continue
            share_in_group = count / group_total if group_total else 0.0
            overall_share = total_count / overall_total if overall_total else 0.0
            lift = share_in_group / overall_share if overall_share else 0.0
            rows.append(
                {
                    "pos": pos,
                    group_key: group,
                    "term": term,
                    "count_in_group": count,
                    "total_count": total_count,
                    "share_in_group": f"{share_in_group:.6f}",
                    "overall_share": f"{overall_share:.6f}",
                    "lift": f"{lift:.3f}",
                }
            )
    return rows


def top_terms_per_group(
    rows: list[dict], group_key: str = "period", top_n: int = 15, min_count_in_group: int = 5
) -> dict:
    by_group = defaultdict(list)
    for r in rows:
        if r["count_in_group"] >= min_count_in_group:
            by_group[r[group_key]].append(r)
    result = {}
    for group, items in by_group.items():
        items.sort(key=lambda r: float(r["lift"]), reverse=True)
        result[group] = items[:top_n]
    return result


def select_representative_terms(top: dict, periods: list[str], per_period: int = 2) -> list[str]:
    """指定した期間群から、代表的な特徴語をlift順に選ぶ（重複除去）。"""
    selected: list[str] = []
    for period in periods:
        added = 0
        for r in top.get(period, []):
            if r["term"] in selected:
                continue
            selected.append(r["term"])
            added += 1
            if added >= per_period:
                break
    return selected


def rarefied_unique_count(counts: Counter, sample_size: int, trials: int = 20) -> float:
    """counts全体からsample_size語を無作為抽出したときのユニーク語数の期待値（レアファクション）。

    生のtype-token ratioは総語数が少ないほど自動的に高く出る統計的な罠があるため、
    全期間を同じサンプルサイズに揃えて比較できるようにする。
    """
    population = [term for term, c in counts.items() for _ in range(c)]
    if len(population) <= sample_size:
        return float(len(counts))
    return sum(len(set(random.sample(population, sample_size))) for _ in range(trials)) / trials


def vocab_diversity_table(period_counts: dict[str, dict[str, Counter]]) -> list[dict]:
    """品詞別・期間別の語彙バリエーション。

    生のtype-token ratio（unique/total）はサンプルサイズに強く依存するため参考値として残しつつ、
    全期間を最小サンプルサイズに揃えたレアファクションTTRで公平に比較する。
    """
    rows = []
    for pos in POS_CATEGORIES:
        by_period = period_counts[pos]
        totals = {period: sum(c.values()) for period, c in by_period.items() if sum(c.values()) > 0}
        if not totals:
            continue
        sample_size = min(totals.values())
        for period, counts in by_period.items():
            total = sum(counts.values())
            unique = len(counts)
            raw_ttr = unique / total if total else 0.0
            rarefied_unique = rarefied_unique_count(counts, sample_size)
            rarefied_ttr = rarefied_unique / sample_size if sample_size else 0.0
            rows.append(
                {
                    "pos": pos,
                    "period": period,
                    "total_tokens": total,
                    "unique_terms": unique,
                    "raw_type_token_ratio": f"{raw_ttr:.4f}",
                    "rarefied_sample_size": sample_size,
                    "rarefied_unique_terms": f"{rarefied_unique:.1f}",
                    "rarefied_type_token_ratio": f"{rarefied_ttr:.4f}",
                }
            )
    return rows


def weekly_counts_for_terms(mailbox_dir: Path, terms: set[str]) -> dict[str, Counter]:
    """指定した語（名詞・形容詞どちらでも）だけについて、週ごとの出現回数を数える（Fig4用）。"""
    records, _skipped = iter_mailbox(mailbox_dir)
    term_weekly: dict[str, Counter] = defaultdict(Counter)
    for r in records:
        path = mailbox_dir / r["filename"]
        body = path.read_text(encoding="utf-8", errors="replace")
        words = extract_content_words(body)
        week = int(r["week"])
        for pos in POS_CATEGORIES:
            for term in words[pos]:
                if term in terms:
                    term_weekly[term][week] += 1
    return term_weekly


def fig4_topic_drift(term_weekly: dict[str, Counter], out_path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

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
    # 固定順のcategoricalパレット（用語数ぶん）
    palette = [
        "#2a78d6", "#1baf7a", "#eda100", "#4a3aa7", "#e34948",
        "#e87ba4", "#eb6834", "#008300", "#7a4a1a", "#555555",
    ]

    all_weeks = sorted({w for c in term_weekly.values() for w in c})
    if not all_weeks:
        return

    fig, ax = plt.subplots(figsize=(10, 5))
    for i, (term, counts) in enumerate(term_weekly.items()):
        vals = [counts.get(w, 0) for w in all_weeks]
        ax.plot(
            all_weeks,
            vals,
            color=palette[i % len(palette)],
            linewidth=2,
            marker="o",
            markersize=3,
            label=term,
        )

    ax.set_xlabel("Day0からの週")
    ax.set_ylabel("出現回数 / 週")
    ax.set_title("代表的な特徴語の週別出現頻度（トピックの推移）")
    ax.set_xticks(range(all_weeks[0], all_weeks[-1] + 1))
    ax.legend(loc="upper right", frameon=False, fontsize=8, ncol=2)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description="mailbox/ 本文から期間別トピック語を抽出する")
    parser.add_argument("--mailbox-dir", type=Path, default=DEFAULT_MAILBOX_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_TERMS_OUTPUT)
    parser.add_argument("--diversity-output", type=Path, default=DEFAULT_DIVERSITY_OUTPUT)
    parser.add_argument("--top-n", type=int, default=15)
    parser.add_argument("--fig-output", type=Path, default=DEFAULT_FIG_OUTPUT)
    args = parser.parse_args()

    period_counts = collect_period_counts(args.mailbox_dir)

    all_rows = []
    all_top = {}
    for pos in POS_CATEGORIES:
        rows = compute_lift_table(period_counts[pos], pos)
        all_rows.extend(rows)
        all_top[pos] = top_terms_per_group(rows, top_n=args.top_n)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "pos",
                "period",
                "term",
                "count_in_group",
                "total_count",
                "share_in_group",
                "overall_share",
                "lift",
            ],
        )
        writer.writeheader()
        writer.writerows(all_rows)
    print(f"topic_terms: {len(all_rows)} rows -> {args.output}")

    diversity_rows = vocab_diversity_table(period_counts)
    with args.diversity_output.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "pos",
                "period",
                "total_tokens",
                "unique_terms",
                "raw_type_token_ratio",
                "rarefied_sample_size",
                "rarefied_unique_terms",
                "rarefied_type_token_ratio",
            ],
        )
        writer.writeheader()
        writer.writerows(diversity_rows)
    print(f"vocab_diversity: {len(diversity_rows)} rows -> {args.diversity_output}")

    period_order = ["baseline", "early", "middle", "late"]
    pos_label = {"noun": "名詞", "adjective": "形容詞"}
    for pos in POS_CATEGORIES:
        print(f"\n########## 品詞: {pos_label[pos]} ##########")
        for period in period_order:
            top = all_top[pos].get(period)
            if not top:
                continue
            print(f"\n--- {period} の特徴語（lift順） ---")
            for r in top:
                print(f"  {r['term']}: {r['count_in_group']}回 (lift={r['lift']})")

    print("\n########## 語彙のバリエーション（レアファクションTTR） ##########")
    for row in diversity_rows:
        print(
            f"  [{pos_label[row['pos']]}] {row['period']}: "
            f"生TTR={row['raw_type_token_ratio']}（total={row['total_tokens']}） / "
            f"レアファクションTTR={row['rarefied_type_token_ratio']}"
            f"（{row['rarefied_sample_size']}語に揃えた場合）"
        )

    representative_nouns = select_representative_terms(
        all_top["noun"], ["early", "middle", "late"], per_period=2
    )
    representative_adjs = select_representative_terms(
        all_top["adjective"], ["early", "middle", "late"], per_period=1
    )
    representative = representative_nouns + representative_adjs
    term_weekly = weekly_counts_for_terms(args.mailbox_dir, set(representative))
    args.fig_output.parent.mkdir(parents=True, exist_ok=True)
    fig4_topic_drift(term_weekly, args.fig_output)
    print(f"\nfig4 (代表語: {representative}) -> {args.fig_output}")


def main_dyad() -> None:
    """ダイアド別（こ⇄てゃ／こ⇄る／てゃ⇄る）の名詞分析。時系列には分けない。"""
    parser = argparse.ArgumentParser(description="ダイアド別に名詞のトピックを分析する")
    parser.add_argument("--mailbox-dir", type=Path, default=DEFAULT_MAILBOX_DIR)
    parser.add_argument(
        "--output", type=Path, default=Path(__file__).parent / "output" / "topic_terms_by_dyad.csv"
    )
    parser.add_argument("--top-n", type=int, default=20)
    args = parser.parse_args()

    dyad_counts = collect_dyad_counts(args.mailbox_dir)
    noun_counts = dyad_counts["noun"]

    rows = compute_lift_table(noun_counts, pos="noun", group_key="dyad")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "pos",
                "dyad",
                "term",
                "count_in_group",
                "total_count",
                "share_in_group",
                "overall_share",
                "lift",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)
    print(f"topic_terms_by_dyad: {len(rows)} rows -> {args.output}")

    dyad_label = {
        "puchiko-puchiteya": "ぷちこ⇄ぷちてゃ",
        "puchiko-puchiru": "ぷちこ⇄ぷちる",
        "puchiru-puchiteya": "ぷちてゃ⇄ぷちる",
    }

    print("\n########## ダイアド別・最頻出の名詞（単純頻度） ##########")
    for dyad, counts in noun_counts.items():
        print(f"\n--- {dyad_label.get(dyad, dyad)}（総名詞数{sum(counts.values())}） ---")
        for term, count in counts.most_common(args.top_n):
            print(f"  {term}: {count}回")

    top = top_terms_per_group(rows, group_key="dyad", top_n=args.top_n)
    print("\n########## ダイアド別・特徴語（他ダイアド比のlift順） ##########")
    for dyad in noun_counts:
        items = top.get(dyad, [])
        if not items:
            continue
        print(f"\n--- {dyad_label.get(dyad, dyad)} ---")
        for r in items:
            print(f"  {r['term']}: {r['count_in_group']}回 (lift={r['lift']})")


if __name__ == "__main__":
    main()
