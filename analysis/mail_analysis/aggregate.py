"""mails.csv を週次集計して weekly_dyads.csv / weekly_actors.csv を作る。

weekly_dyads.csv: ダイアド毎・週毎の方向別通数・本文長中央値・対称性指数（H1, H2用）
weekly_actors.csv: 各キャラの週毎の送信シェア＝ハブ度の推移（H3の補助）

設計: ~/petit_claude/docs/mail-analysis/rq1_design_ja.md
"""

from __future__ import annotations

import argparse
import csv
import statistics
from collections import defaultdict
from pathlib import Path

DEFAULT_INPUT = Path(__file__).parent / "output" / "mails.csv"
DEFAULT_DYAD_OUTPUT = Path(__file__).parent / "output" / "weekly_dyads.csv"
DEFAULT_ACTOR_OUTPUT = Path(__file__).parent / "output" / "weekly_actors.csv"

DYAD_FIELDS = [
    "week",
    "dyad",
    "a",
    "b",
    "a_to_b_count",
    "b_to_a_count",
    "a_to_b_chars_median",
    "b_to_a_chars_median",
    "total_count",
    "symmetry_index",
]
ACTOR_FIELDS = ["week", "actor", "out_count", "out_share"]


def load_mails(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def aggregate_dyads(mails: list[dict]) -> list[dict]:
    buckets: dict[tuple[int, str], dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
    for m in mails:
        if not m["dyad"]:
            continue
        key = (int(m["week"]), m["dyad"])
        buckets[key][m["sender"]].append(int(m["chars"]))

    rows = []
    for (week, dyad), by_sender in sorted(buckets.items()):
        a, b = dyad.split("-")
        a_to_b = by_sender.get(a, [])
        b_to_a = by_sender.get(b, [])
        total = len(a_to_b) + len(b_to_a)
        symmetry = abs(len(a_to_b) - len(b_to_a)) / total if total else None
        rows.append(
            {
                "week": week,
                "dyad": dyad,
                "a": a,
                "b": b,
                "a_to_b_count": len(a_to_b),
                "b_to_a_count": len(b_to_a),
                "a_to_b_chars_median": statistics.median(a_to_b) if a_to_b else "",
                "b_to_a_chars_median": statistics.median(b_to_a) if b_to_a else "",
                "total_count": total,
                "symmetry_index": f"{symmetry:.4f}" if symmetry is not None else "",
            }
        )
    return rows


def aggregate_actors(mails: list[dict]) -> list[dict]:
    week_out: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for m in mails:
        week_out[int(m["week"])][m["sender"]] += 1

    rows = []
    for week, counts in sorted(week_out.items()):
        total = sum(counts.values())
        for actor, count in sorted(counts.items()):
            rows.append(
                {
                    "week": week,
                    "actor": actor,
                    "out_count": count,
                    "out_share": f"{count / total:.4f}" if total else "",
                }
            )
    return rows


def write_csv(rows: list[dict], path: Path, fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="mails.csv を週次集計する")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--dyad-output", type=Path, default=DEFAULT_DYAD_OUTPUT)
    parser.add_argument("--actor-output", type=Path, default=DEFAULT_ACTOR_OUTPUT)
    args = parser.parse_args()

    mails = load_mails(args.input)

    dyad_rows = aggregate_dyads(mails)
    write_csv(dyad_rows, args.dyad_output, DYAD_FIELDS)

    actor_rows = aggregate_actors(mails)
    write_csv(actor_rows, args.actor_output, ACTOR_FIELDS)

    print(f"weekly_dyads: {len(dyad_rows)} rows -> {args.dyad_output}")
    print(f"weekly_actors: {len(actor_rows)} rows -> {args.actor_output}")


if __name__ == "__main__":
    main()
