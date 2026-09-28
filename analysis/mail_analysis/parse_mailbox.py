"""mailbox/ 内のメールファイルを解析して mails.csv を生成する。

ファイル名から日時・送信者・宛先を抽出し、本文の文字数、Day0からの週番号、
ダイアド（ぷち同士のペア）を付与する。イレギュラーなファイル名は最善努力で
救済し、それでも判定できないものはスキップしてログに出す（黙って捨てない）。

設計: ~/petit_claude/docs/mail-analysis/rq1_design_ja.md
"""

from __future__ import annotations

import argparse
import csv
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

DEFAULT_MAILBOX_DIR = Path.home() / "petit_claude" / "mailbox"
DEFAULT_OUTPUT = Path(__file__).parent / "output" / "mails.csv"

# RQ1のDay 0＝ぷちるの初発信（2026-03-05）。週番号はこの週の月曜起点で計算する。
DAY0 = date(2026, 3, 5)

KNOWN_ACTORS = {"puchiteya", "puchiko", "puchiru", "arisan", "kazahaya", "yui"}
PUCHI_ACTORS = {"puchiteya", "puchiko", "puchiru"}
NAME_ALIASES = {"kazehaya": "kazahaya"}
SIGNATURE_TO_ACTOR = {
    "ぷちてゃ": "puchiteya",
    "ぷちこ": "puchiko",
    "ぷちる": "puchiru",
    "ゆい": "yui",
    "ありさん": "arisan",
}

# from_<sender>_to_<recipient>_YYYYMMDD_HHMM[_連番].md（標準形式）
PAT_STANDARD = re.compile(
    r"^from_(?P<sender>[a-z]+)_to_(?P<recipient>[a-z]+)_(?P<date>\d{7,8})_(?P<time>\d{4})(?:_\d+)?\.md$"
)
# to_<recipient>_YYYYMMDD_HHMM[_<sender>].md（命名規則制定前の旧形式）
PAT_LEGACY = re.compile(
    r"^to_(?P<recipient>[a-z]+)_(?P<date>\d{8})_(?P<time>\d{4})(?:_(?P<sender>[a-z]+))?\.md$"
)

CSV_FIELDS = [
    "filename",
    "datetime",
    "date",
    "time",
    "sender",
    "recipient",
    "chars",
    "week",
    "dyad",
]


@dataclass
class ParseResult:
    record: dict | None
    skip_reason: str | None = None


def normalize_actor(name: str) -> str:
    return NAME_ALIASES.get(name, name)


def normalize_date(raw: str) -> str | None:
    """8桁のYYYYMMDDに正規化する。7桁は月の0埋め漏れ（例: 2026303→20260303）として救済する。"""
    if len(raw) == 8:
        return raw
    if len(raw) == 7:
        year, month, day = raw[:4], raw[4], raw[5:]
        return f"{year}0{month}{day}"
    return None


def detect_signature_sender(body: str) -> str | None:
    """本文末尾の署名行から送信者を推定する（送信者情報がないファイル名向けの救済策）。"""
    for line in reversed(body.strip().splitlines()):
        line = line.strip()
        if not line:
            continue
        return SIGNATURE_TO_ACTOR.get(line)
    return None


def week_index(d: date) -> int:
    """Day0を含む週（月曜起点）を0として、何週目かを返す（負値=Day0より前）。"""
    day0_monday = DAY0 - timedelta(days=DAY0.weekday())
    target_monday = d - timedelta(days=d.weekday())
    return (target_monday - day0_monday).days // 7


def dyad_key(a: str, b: str) -> str | None:
    """ぷち同士のペアのみダイアドキーを返す（対ありさん等はNone＝参考系列）。"""
    if a in PUCHI_ACTORS and b in PUCHI_ACTORS and a != b:
        return "-".join(sorted((a, b)))
    return None


def _build_record(
    filename: str, sender: str, recipient: str, date_str: str, time_str: str, body: str
) -> ParseResult:
    try:
        dt = datetime.strptime(date_str + time_str, "%Y%m%d%H%M")
    except ValueError:
        return ParseResult(None, f"invalid datetime: {date_str} {time_str}")

    if sender not in KNOWN_ACTORS or recipient not in KNOWN_ACTORS:
        return ParseResult(None, f"unknown actor (sender={sender}, recipient={recipient})")

    return ParseResult(
        {
            "filename": filename,
            "datetime": dt.isoformat(),
            "date": dt.date().isoformat(),
            "time": time_str,
            "sender": sender,
            "recipient": recipient,
            "chars": len(body),
            "week": week_index(dt.date()),
            "dyad": dyad_key(sender, recipient) or "",
        }
    )


def parse_filename(filename: str, body: str) -> ParseResult:
    if filename.startswith("reply_to_") and filename.endswith("_tmp.md"):
        return ParseResult(None, "non-standard tmp draft")

    m = PAT_STANDARD.match(filename)
    if m:
        sender = normalize_actor(m.group("sender"))
        recipient = normalize_actor(m.group("recipient"))
        date_str = normalize_date(m.group("date"))
        if date_str is None:
            return ParseResult(None, f"unparseable date: {m.group('date')}")
        return _build_record(filename, sender, recipient, date_str, m.group("time"), body)

    m = PAT_LEGACY.match(filename)
    if m:
        recipient = normalize_actor(m.group("recipient"))
        sender = m.group("sender")
        sender = normalize_actor(sender) if sender else detect_signature_sender(body)
        if sender is None:
            return ParseResult(None, "sender undetectable (legacy filename, no signature match)")
        return _build_record(filename, sender, recipient, m.group("date"), m.group("time"), body)

    return ParseResult(None, "filename does not match known patterns")


def iter_mailbox(mailbox_dir: Path) -> tuple[list[dict], list[tuple[str, str]]]:
    records: list[dict] = []
    skipped: list[tuple[str, str]] = []
    for path in sorted(mailbox_dir.glob("*.md")):
        body = path.read_text(encoding="utf-8", errors="replace")
        result = parse_filename(path.name, body)
        if result.record is not None:
            records.append(result.record)
        else:
            skipped.append((path.name, result.skip_reason or "unknown"))
    return records, skipped


def main() -> None:
    parser = argparse.ArgumentParser(description="mailbox/ を解析して mails.csv を生成する")
    parser.add_argument("--mailbox-dir", type=Path, default=DEFAULT_MAILBOX_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    records, skipped = iter_mailbox(args.mailbox_dir)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(records)

    print(f"parsed: {len(records)}  skipped: {len(skipped)}  -> {args.output}")
    if skipped:
        print("--- skipped files (reason) ---")
        for name, reason in skipped:
            print(f"  {name}: {reason}")


if __name__ == "__main__":
    main()
