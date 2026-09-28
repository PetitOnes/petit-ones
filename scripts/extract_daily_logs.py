#!/usr/bin/env python3
"""日別ログ抽出システム。

`~/petit_claude/` 配下に散らばっている研究データ（メール・日記・チャット・
交換ノート・体験バッファ・トークン使用量・写真・ボイスメモ）から、
「その日（JST）に発生した分だけ」を重複なく切り出して
`~/petit_claude/daily_logs/YYYY-MM-DD/` に集める。

設計原則:
    - ソースは読み取り専用（一切変更しない）
    - 日付境界は JST（Asia/Tokyo）
    - 冪等: 同じ日を再実行すると出力ディレクトリを作り直す（上書き再生成）
    - 各日フォルダに manifest.json を残し、何をどの条件で抽出したかを記録する

Usage:
    python3 extract_daily_logs.py                    # 昨日分（JST）を抽出
    python3 extract_daily_logs.py --date 2026-07-05   # 指定日を抽出
    python3 extract_daily_logs.py --backfill          # データが存在する最古の日〜昨日まで一括生成
    python3 extract_daily_logs.py --dry-run --date 2026-07-05  # 実行せず計画のみ表示
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

JST = timezone(timedelta(hours=9))

PETIT_DATA_DIR = Path(os.environ.get("PETIT_DATA_DIR", str(Path.home() / "petit_claude")))
OUTPUT_ROOT = PETIT_DATA_DIR / "daily_logs"

MAILBOX_DIR = PETIT_DATA_DIR / "mailbox"
CHARACTERS_DIR = PETIT_DATA_DIR / "characters"
CHAT_HISTORY_DIR = PETIT_DATA_DIR / "chat_history"
TOKEN_LOG_FILE = PETIT_DATA_DIR / "token_logs" / "token_log.jsonl"
PHOTO_ALBUM_DIR = PETIT_DATA_DIR / "photo_album"
VOICE_MEMO_DIR = PETIT_DATA_DIR / "voice_memo"

# 除外したデータソースとその理由（再現性のため manifest ではなく README 側に記す）。
# extract_daily_logs.py の docstring 兼メモとしてここにも残す:
#   - mailbox/.metadata.json: 既読/アーカイブ状態の可変インデックス。日付を持たず
#     将来にわたって更新され続けるため「その日に発生した」データとして切り出せない。
#   - characters/*/data/{relations,desires}.json: ある時点のスナップショットであり
#     ログ（追記型）ではない。
#   - .autonomous-logs/**: Claude Code の生セッションストリーム（100MB超、継続増加）。
#     デバッグ用の生トレースであり、研究用の「その日のコンテンツ」データではないため対象外。
#   - cost_summary/*.md: 会計サイクル単位（26日始まり）の集計レポートで、usage.json
#     (token_log.jsonl から日次抽出)と重複する派生データのため対象外。

MAILBOX_DT_RE = re.compile(r"(?<!\d)(\d{8})_(\d{4})(?!\d)")
MAILBOX_DATE_RE = re.compile(r"(?<!\d)(\d{8})(?!\d)")


def log(msg: str) -> None:
    print(msg, file=sys.stderr)


def to_jst(dt: datetime) -> datetime:
    """timezone-aware / naive な datetime を JST に正規化する。

    naive な文字列(offsetなし)は、このシステムのローカル時刻が常に JST であるため
    「すでに JST である」とみなす。
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=JST)
    return dt.astimezone(JST)


def parse_iso_to_jst(ts: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        return None
    return to_jst(dt)


def parse_slash_date_to_jst(s: str) -> datetime | None:
    """"YYYY/MM/DD HH:MM" 形式 (exchange_notebook.json の "date" フィールド)。"""
    try:
        dt = datetime.strptime(s, "%Y/%m/%d %H:%M")
    except (ValueError, TypeError):
        return None
    return dt.replace(tzinfo=JST)


def parse_mailbox_date(filename: str, mtime_jst: datetime) -> tuple[date, str]:
    """メールファイル名から日付を推定する。

    観測されたファイル名パターン:
        from_{sender}_to_{recipient}_{YYYYMMDD}_{HHMM}.md          (標準形)
        from_{sender}_to_{recipient}_{YYYYMMDD}_{HHMM}_{N}.md      (同一分内の複数通)
        to_{recipient}_{YYYYMMDD}_{HHMM}.md                        (初期の命名規則)
        to_{recipient}_{YYYYMMDD}_{HHMM}_{name}.md                 (末尾に送信者名)
        reply_to_teya_{YYYYMMDD}_tmp.md                            (時刻部分が非数値)
        from_yui_to_puchiteya_2026303_1501.md                      (日付が7桁の誤記)

    優先順位: 「8桁日付+4桁時刻」 > 「8桁日付のみ」 > ファイルの mtime (JST)。
    """
    m = MAILBOX_DT_RE.search(filename)
    if m:
        try:
            dt = datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M")
            return dt.date(), "filename_datetime"
        except ValueError:
            pass
    m2 = MAILBOX_DATE_RE.search(filename)
    if m2:
        try:
            d = datetime.strptime(m2.group(1), "%Y%m%d").date()
            return d, "filename_date_only"
        except ValueError:
            pass
    return mtime_jst.date(), "mtime_fallback"


def file_mtime_jst(path: Path) -> datetime:
    ts = path.stat().st_mtime
    return datetime.fromtimestamp(ts, tz=JST)


@dataclass
class SourceReport:
    """1つのデータソースについて、抽出条件と結果件数を記録する。"""

    name: str
    condition: str
    sources: list[str] = field(default_factory=list)
    count: int = 0
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = {"condition": self.condition, "source_paths": self.sources, "count": self.count}
        d.update(self.details)
        return d


class DailyExtractor:
    def __init__(self, target_date: date, dry_run: bool = False):
        self.date = target_date
        self.dry_run = dry_run
        self.out_dir = OUTPUT_ROOT / target_date.isoformat()
        self.reports: dict[str, SourceReport] = {}

    # -- io helpers -----------------------------------------------------
    def _ensure_dir(self, p: Path) -> None:
        if not self.dry_run:
            p.mkdir(parents=True, exist_ok=True)

    def _copy(self, src: Path, dst: Path) -> None:
        if not self.dry_run:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

    def _write_json(self, dst: Path, data: Any) -> None:
        if not self.dry_run:
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _write_jsonl(self, dst: Path, lines: list[str]) -> None:
        if not self.dry_run:
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")

    def reset_output_dir(self) -> None:
        """冪等性のため、出力先を作り直す（既存データがあれば消してから再生成）。"""
        if self.dry_run:
            return
        if self.out_dir.exists():
            shutil.rmtree(self.out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)

    # -- sources ----------------------------------------------------------
    def extract_mailbox(self) -> None:
        report = SourceReport(
            name="mailbox",
            condition=(
                "mailbox/*.md のうちファイル名から抽出した日付(JST)が対象日と一致するもの。"
                "ファイル名から日付が読み取れない場合は"
                "ファイルの mtime(JST) の日付にフォールバック。"
            ),
            sources=[str(MAILBOX_DIR)],
        )
        date_source_counts: dict[str, int] = {}
        if MAILBOX_DIR.is_dir():
            for f in sorted(MAILBOX_DIR.glob("*.md")):
                mtime_jst = file_mtime_jst(f)
                d, src = parse_mailbox_date(f.name, mtime_jst)
                if d == self.date:
                    self._copy(f, self.out_dir / "mailbox" / f.name)
                    report.count += 1
                    date_source_counts[src] = date_source_counts.get(src, 0) + 1
        report.details["date_source_breakdown"] = date_source_counts
        self.reports["mailbox"] = report

    def extract_diary(self) -> None:
        report = SourceReport(
            name="diary",
            condition="characters/*/diary/{date}.txt が存在すればそのままコピー。",
            sources=[str(CHARACTERS_DIR / "*" / "diary" / f"{self.date.isoformat()}.txt")],
        )
        characters = []
        if CHARACTERS_DIR.is_dir():
            for char_dir in sorted(CHARACTERS_DIR.iterdir()):
                if not char_dir.is_dir():
                    continue
                src = char_dir / "diary" / f"{self.date.isoformat()}.txt"
                if src.is_file():
                    self._copy(src, self.out_dir / "diary" / f"{char_dir.name}.txt")
                    report.count += 1
                    characters.append(char_dir.name)
        report.details["characters"] = characters
        self.reports["diary"] = report

    @staticmethod
    def _chat_partner_name(basename: str) -> str:
        # chat_history.json -> arisan (ダッシュボードの既定1対1チャット相手)
        # chat_history_kazahaya.json -> kazahaya / chat_history_visitor.json -> visitor
        stem = basename[: -len(".json")]
        if stem == "chat_history":
            return "arisan"
        prefix = "chat_history_"
        if stem.startswith(prefix):
            return stem[len(prefix) :]
        return stem

    def extract_chat_histories(self) -> None:
        report = SourceReport(
            name="chat",
            condition=(
                "characters/*/chat_histories/*.json (1対1チャット, ロール切り替え式) の"
                "各エントリのうち timestamp(UTC ISO8601) をJSTに変換して対象日と一致するものだけを"
                "元の配列構造のまま抽出。"
            ),
            sources=[str(CHARACTERS_DIR / "*" / "chat_histories" / "*.json")],
        )
        per_file: dict[str, int] = {}
        if CHARACTERS_DIR.is_dir():
            for char_dir in sorted(CHARACTERS_DIR.iterdir()):
                chat_dir = char_dir / "chat_histories"
                if not chat_dir.is_dir():
                    continue
                for jf in sorted(chat_dir.glob("*.json")):
                    try:
                        entries = json.loads(jf.read_text(encoding="utf-8"))
                    except (json.JSONDecodeError, OSError):
                        continue
                    if not isinstance(entries, list):
                        continue
                    matched = [
                        e
                        for e in entries
                        if isinstance(e, dict)
                        and (dt := parse_iso_to_jst(e.get("timestamp", "")))
                        and dt.date() == self.date
                    ]
                    if matched:
                        partner = self._chat_partner_name(jf.name)
                        out_name = f"{char_dir.name}_{partner}.json"
                        self._write_json(self.out_dir / "chat" / out_name, matched)
                        per_file[out_name] = len(matched)
                        report.count += len(matched)
        report.details["files"] = per_file
        self.reports["chat"] = report

    def _extract_list_json_by_date(
        self, src: Path, out_subdir: str, condition: str
    ) -> tuple[int, int]:
        """timestamp(ISO) または date("YYYY/MM/DD HH:MM") フィールドを持つ
        リスト形式JSONを対象日でフィルタして書き出す。(件数, 未解析件数) を返す。
        """
        if not src.is_file():
            return 0, 0
        try:
            entries = json.loads(src.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return 0, 0
        if not isinstance(entries, list):
            return 0, 0
        matched = []
        unparseable = 0
        for e in entries:
            if not isinstance(e, dict):
                continue
            dt = None
            if "timestamp" in e:
                dt = parse_iso_to_jst(str(e["timestamp"]))
            elif "date" in e:
                dt = parse_slash_date_to_jst(str(e["date"]))
            if dt is None:
                unparseable += 1
                continue
            if dt.date() == self.date:
                matched.append(e)
        if matched:
            self._write_json(self.out_dir / out_subdir / src.name, matched)
        return len(matched), unparseable

    def extract_group(self) -> None:
        report = SourceReport(
            name="group",
            condition=(
                "chat_history/{group_chat,trio_chat}.json の各エントリのうち "
                "timestamp(JSTへ変換) が対象日と一致するものを元の配列構造のまま抽出。"
            ),
            sources=[
                str(CHAT_HISTORY_DIR / "group_chat.json"),
                str(CHAT_HISTORY_DIR / "trio_chat.json"),
            ],
        )
        per_file = {}
        for fname in ("group_chat.json", "trio_chat.json"):
            n, unparsed = self._extract_list_json_by_date(
                CHAT_HISTORY_DIR / fname, "group", report.condition
            )
            per_file[fname] = {"count": n, "unparseable": unparsed}
            report.count += n
        report.details["files"] = per_file
        self.reports["group"] = report

    def extract_notebook(self) -> None:
        report = SourceReport(
            name="notebook",
            condition=(
                "chat_history/{exchange_notebook,exchange_notebook_kazahaya}.json の"
                "各エントリのうち "
                "'timestamp'(ISO) または 'date'(\"YYYY/MM/DD HH:MM\", JST) を"
                "JSTの日付に変換し、対象日と一致するものを元の配列構造のまま抽出。"
            ),
            sources=[
                str(CHAT_HISTORY_DIR / "exchange_notebook.json"),
                str(CHAT_HISTORY_DIR / "exchange_notebook_kazahaya.json"),
            ],
        )
        per_file = {}
        for fname in ("exchange_notebook.json", "exchange_notebook_kazahaya.json"):
            n, unparsed = self._extract_list_json_by_date(
                CHAT_HISTORY_DIR / fname, "notebook", report.condition
            )
            per_file[fname] = {"count": n, "unparseable": unparsed}
            report.count += n
        report.details["files"] = per_file
        self.reports["notebook"] = report

    def extract_experience(self) -> None:
        report = SourceReport(
            name="experience",
            condition=(
                "characters/*/state/experience/{YYYYMMDD}.jsonl (日別ファイル) が"
                "対象日のものであれば、"
                "念のため各行の 'ts' の日付(JST, naive=JST前提)を検証しつつ抽出。"
            ),
            sources=[
                str(
                    CHARACTERS_DIR
                    / "*"
                    / "state"
                    / "experience"
                    / f"{self.date.strftime('%Y%m%d')}.jsonl"
                )
            ],
        )
        per_char = {}
        if CHARACTERS_DIR.is_dir():
            date_str = self.date.strftime("%Y%m%d")
            for char_dir in sorted(CHARACTERS_DIR.iterdir()):
                src = char_dir / "state" / "experience" / f"{date_str}.jsonl"
                if not src.is_file():
                    continue
                lines_out = []
                for line in src.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    ts = rec.get("ts")
                    dt = parse_iso_to_jst(ts) if ts else None
                    if dt is not None and dt.date() != self.date:
                        continue  # 念のため: 日別ファイルの取り違え防止
                    lines_out.append(line)
                if lines_out:
                    out_path = self.out_dir / "experience" / f"{char_dir.name}.jsonl"
                    self._write_jsonl(out_path, lines_out)
                    per_char[char_dir.name] = len(lines_out)
                    report.count += len(lines_out)
        report.details["characters"] = per_char
        self.reports["experience"] = report

    def extract_usage(self) -> None:
        report = SourceReport(
            name="usage",
            condition=(
                "token_logs/token_log.jsonl (全ソース・全キャラクター統合ログ) のうち "
                "timestamp をJSTに変換して対象日と一致するレコードを抽出。"
                "token_logs/{character}/token_log.jsonl はこのファイルの"
                "autonomous分の部分集合のため使用しない。"
            ),
            sources=[str(TOKEN_LOG_FILE)],
        )
        matched = []
        if TOKEN_LOG_FILE.is_file():
            with TOKEN_LOG_FILE.open(encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    dt = parse_iso_to_jst(str(rec.get("timestamp", "")))
                    if dt is not None and dt.date() == self.date:
                        matched.append(rec)
        if matched:
            self._write_json(self.out_dir / "usage.json", matched)
        report.count = len(matched)
        self.reports["usage"] = report

    def _extract_dated_media(self, root: Path, out_subdir: str, source_name: str) -> None:
        report = SourceReport(
            name=source_name,
            condition=(
                f"{root.name}/*/YYYYMMDD_HHMMSS_*.* のファイル名冒頭8桁が"
                "対象日と一致するものをコピー（.json のメタデータファイルは対象外）。"
            ),
            sources=[str(root)],
        )
        per_person: dict[str, int] = {}
        date_str = self.date.strftime("%Y%m%d")
        if root.is_dir():
            for person_dir in sorted(root.iterdir()):
                if not person_dir.is_dir():
                    continue
                for f in sorted(person_dir.iterdir()):
                    if not f.is_file() or f.name.startswith("."):
                        continue
                    if f.name[:8] == date_str and f.name[8:9] == "_":
                        self._copy(f, self.out_dir / out_subdir / person_dir.name / f.name)
                        per_person[person_dir.name] = per_person.get(person_dir.name, 0) + 1
                        report.count += 1
        report.details["by_person"] = per_person
        self.reports[source_name] = report

    def extract_photos(self) -> None:
        self._extract_dated_media(PHOTO_ALBUM_DIR, "photos", "photos")

    def extract_voice_memo(self) -> None:
        self._extract_dated_media(VOICE_MEMO_DIR, "voice_memo", "voice_memo")

    # -- orchestration ----------------------------------------------------
    def run(self) -> dict[str, Any]:
        self.reset_output_dir()
        self.extract_mailbox()
        self.extract_diary()
        self.extract_chat_histories()
        self.extract_group()
        self.extract_notebook()
        self.extract_experience()
        self.extract_usage()
        self.extract_photos()
        self.extract_voice_memo()

        manifest = {
            "date": self.date.isoformat(),
            "timezone": "Asia/Tokyo",
            "generated_at": datetime.now(tz=JST).isoformat(),
            "dry_run": self.dry_run,
            "sources": {name: r.to_dict() for name, r in self.reports.items()},
            "excluded_sources": {
                "mailbox/.metadata.json": (
                    "既読/アーカイブ状態の可変インデックス。"
                    "日付を持たず将来も更新され続けるため対象外。"
                ),
                "characters/*/data/{relations,desires}.json": (
                    "ある時点のスナップショットでありログ(追記型)ではないため対象外。"
                ),
                ".autonomous-logs/**": (
                    "Claude Codeの生セッションストリーム(100MB超・継続増加)。"
                    "デバッグ用の生トレースで研究用コンテンツではないため対象外。"
                ),
                "cost_summary/*.md": (
                    "会計サイクル単位の集計レポート。"
                    "usage.jsonと重複する派生データのため対象外。"
                ),
            },
        }
        if not self.dry_run:
            (self.out_dir / "manifest.json").write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        return manifest


# -- date discovery ---------------------------------------------------------


def find_earliest_date() -> date:
    """全ソースを走査して、データが存在する最古の日付(JST)を返す。"""
    candidates: list[date] = []

    if MAILBOX_DIR.is_dir():
        for f in MAILBOX_DIR.glob("*.md"):
            d, _ = parse_mailbox_date(f.name, file_mtime_jst(f))
            candidates.append(d)

    if CHARACTERS_DIR.is_dir():
        for char_dir in CHARACTERS_DIR.iterdir():
            diary_dir = char_dir / "diary"
            if diary_dir.is_dir():
                for f in diary_dir.glob("*.txt"):
                    try:
                        candidates.append(datetime.strptime(f.stem, "%Y-%m-%d").date())
                    except ValueError:
                        pass

    if not candidates:
        # フォールバック: 昨日のみ
        return (datetime.now(tz=JST) - timedelta(days=1)).date()
    return min(candidates)


def yesterday() -> date:
    return (datetime.now(tz=JST) - timedelta(days=1)).date()


# -- CLI ----------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="日別ログ抽出システム")
    parser.add_argument("--date", type=str, help="対象日 YYYY-MM-DD (省略時=昨日, JST)")
    parser.add_argument(
        "--backfill",
        action="store_true",
        help="データが存在する最古の日から昨日まで全日分を一括生成",
    )
    parser.add_argument("--dry-run", action="store_true", help="実行せず計画のみ表示")
    args = parser.parse_args()

    if args.backfill:
        start = find_earliest_date()
        end = yesterday()
        if start > end:
            log(f"バックフィル対象日がありません (start={start} > end={end})")
            return 0
        log(f"バックフィル: {start} 〜 {end} ({(end - start).days + 1} 日分)")
        d = start
        total_files = 0
        while d <= end:
            extractor = DailyExtractor(d, dry_run=args.dry_run)
            manifest = extractor.run()
            n = sum(r["count"] for r in manifest["sources"].values())
            total_files += n
            log(f"  {d.isoformat()}: {n} 件")
            d += timedelta(days=1)
        log(f"完了: {total_files} 件（{(end - start).days + 1} 日分）")
        return 0

    if args.date:
        try:
            target = datetime.strptime(args.date, "%Y-%m-%d").date()
        except ValueError:
            log(f"日付の形式が不正です: {args.date} (YYYY-MM-DD で指定してください)")
            return 1
    else:
        target = yesterday()

    extractor = DailyExtractor(target, dry_run=args.dry_run)
    manifest = extractor.run()
    n = sum(r["count"] for r in manifest["sources"].values())
    log(f"{target.isoformat()}: {n} 件を抽出{'（dry-run）' if args.dry_run else ''}")
    for name, r in manifest["sources"].items():
        log(f"  - {name}: {r['count']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
