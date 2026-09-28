#!/usr/bin/env python3
"""失われた会話履歴(1:1チャット・グループ・トリオ)を過去のバックアップから回収し、
`~/petit_claude/recovered_chat/` にマスターとして保存した上で、
`~/petit_claude/daily_logs/YYYY-MM-DD/` へ追記マージする。

背景:
    - `characters/*/chat_histories/*.json` (1:1チャット) は直近200件、
      `chat_history/group_chat.json` は直近500件のローリングバッファで、
      古い分は本体からすでに消えている。
    - `chat_history/exchange_notebook*.json` と `chat_history/trio_chat.json` は
      追記型(non-rolling)で、調査の結果すでに現在のライブファイルが全期間を
      カバーしていることを確認済み(trio_chat は2026-03-21で更新停止のまま
      frozen、exchange_notebook は2026-03-03から単調増加)。そのためこの
      スクリプトは notebook/trio を積極的な復元対象にはしない
      (念のためソースとしては読み込むが、通常は新規追加0件になるはず)。

回収元(すべて読み取り専用。1バイトも変更しない):
    A. `~/petit_claude/backup/` の現存スナップショット(直近7日 + 毎月1日)。
       現行と同じネストレイアウト(`characters/*/chat_histories/*.json`)。
    B. `~/Downloads/petit_claude_202603011604/`, `~/Downloads/petit_backup_20260423/`,
       `~/Downloads/backup/` -- 過去のフルバックアップ(入れ子スナップショット込み)。
       いずれも旧・フラットレイアウト(`characters/<name>/chat_history*.json` が
       直下、`chat_history/` はそのまま)。
    C. `docs/ro-man/data/chats_all.csv` -- 2026-06-09時点で研究用に一度
       バックアップ統合済みのCSV(individual/group/trioチャンネル、
       2026-02-27〜2026-06-09)。唯一 2026-03-02〜2026-04-07 の
       個別/グループチャットをカバーする情報源(当時のバックアップが
       存在しないため)。ただしCSVは `type`/`name`/`color` を持たないため、
       group/trio 由来のエントリはこれらのフィールドを既知の対応表から
       再構成する(`type` は元の値を区別できないため "group"/"trio" 固定)。

    調査の結果、以下のzipファイルは事前にmd5で内容確認し、上記A/Bのディレクトリと
    完全に重複、または無関係(`~/.claude` 設定バックアップで petit_claude データを
    含まない)と判明したため、本スクリプトのソースには含めていない:
        - petit_claude.zip                    (= A/backup/20260227_191126 と同一)
        - petit_claude_202603011604.zip        (= petit_claude_202603011604/ と同一)
        - petit_claude1.zip                    (= petit_backup_20260423/ と同一)
        - claude_backup.zip                    (~/.claude のバックアップ、無関係)

設計原則:
    - ソースは読み取り専用(一切変更しない)
    - 冪等: 同じデータに対して複数回実行しても daily_logs 側に重複が増えない
    - --dry-run で実行計画のみ表示

Usage:
    python3 recover_chat_history.py --dry-run     # 実行計画・件数だけ表示
    python3 recover_chat_history.py                # マスター保存 + daily_logs へ統合
    python3 recover_chat_history.py --master-only   # daily_logsへは統合せずマスターのみ更新
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import extract_daily_logs as edl  # noqa: E402

JST = edl.JST
UTC = timezone.utc

PETIT_DATA_DIR = Path(os.environ.get("PETIT_DATA_DIR", str(Path.home() / "petit_claude")))
DAILY_LOGS_DIR = PETIT_DATA_DIR / "daily_logs"
RECOVERED_DIR = PETIT_DATA_DIR / "recovered_chat"
CHATS_ALL_CSV = PETIT_DATA_DIR / "docs" / "ro-man" / "data" / "chats_all.csv"

DOWNLOADS_DIR = Path.home() / "Downloads"
DOWNLOADS_BACKUP_BASES = [
    DOWNLOADS_DIR / "petit_claude_202603011604",
    DOWNLOADS_DIR / "petit_backup_20260423",
    DOWNLOADS_DIR / "backup",
]
LOCAL_BACKUP_ROOT = PETIT_DATA_DIR / "backup"
LOCAL_BACKUP_EXCLUDE_NAMES = {"github-mirror", "cc_sessions_mirror"}

# 優先度: 数字が小さいほど「そのソースの生データをそのまま採用する」優先順位が高い。
# 同じ(character, partner, role, text, timestamp)の重複が複数ソースから見つかった場合、
# 優先度が最も高いソースのrawレコード(type/name/color等のフィールドが完全なもの)を
# 採用しつつ、貢献したソース全部を recovered_from として記録する。
PRIORITY_LIVE = 0
PRIORITY_LOCAL_BACKUP = 1
PRIORITY_DOWNLOADS_BACKUP = 2
PRIORITY_CSV = 9

CHARACTER_META = {
    "puchiteya": {"name": "ぷちてゃ", "color": "#fff262"},
    "puchiko": {"name": "ぷちこ", "color": "#cab8d9"},
    "puchiru": {"name": "ぷちる", "color": "#00afcc"},
    "puchiku": {"name": "ぷちく", "color": "#cccccc"},
    "arisan": {"name": "ありさん", "color": "#aaaaaa"},
    "user": {"name": "ありさん", "color": "#aaaaaa"},
}


def log(msg: str) -> None:
    print(msg, file=sys.stderr)


# -- normalized entry --------------------------------------------------------


@dataclass(frozen=True)
class Entry:
    kind: str  # "chat" | "group" | "trio"
    character: str | None  # kind=="chat" のときの所有キャラクター
    partner: str | None  # kind=="chat" のときの相手 (arisan/kazahaya/visitor)
    dt_utc: datetime  # aware, UTC に正規化済み
    role: str
    text: str
    raw: dict[str, Any]  # 出力にそのまま書き戻す生レコード
    source: str  # 由来ソースのラベル(報告用)
    priority: int

    def bucket_key(self) -> tuple[str, str | None, str | None]:
        return (self.kind, self.character, self.partner)

    def dedup_key(self) -> tuple[Any, ...]:
        # 秒精度に丸めることで、ソース間のわずかなタイムスタンプ表記差
        # (マイクロ秒の欠落・オフセット表記の違い等)を吸収する。
        # text は空白正規化してから比較する: docs/ro-man/data/chats_all.csv は
        # CSVエクスポート時に改行が空白に置き換えられており、生JSONソースの
        # 改行付きテキストと素の文字列比較では一致しないため。
        return (
            self.kind,
            self.character,
            self.partner,
            self.role,
            _normalize_text(self.text),
            self.dt_utc.replace(microsecond=0).isoformat(),
        )

    def jst_date(self) -> date:
        return self.dt_utc.astimezone(JST).date()


def _normalize_text(text: str) -> str:
    """空白(改行・タブ・連続スペース含む)を単一スペースに畳んで比較用に正規化する。"""
    return " ".join(text.split())


def _partner_from_filename(name: str) -> str:
    stem = name[: -len(".json")] if name.endswith(".json") else name
    if stem == "chat_history":
        return "arisan"
    prefix = "chat_history_"
    if stem.startswith(prefix):
        return stem[len(prefix) :]
    return stem


def _to_utc(dt: datetime) -> datetime:
    return dt.astimezone(UTC)


def _normalize_chat_raw(
    character: str, partner: str, raw: Any, label: str, priority: int
) -> Entry | None:
    if not isinstance(raw, dict):
        return None
    ts = raw.get("timestamp")
    role = raw.get("role")
    text = raw.get("text")
    if not ts or role is None or text is None:
        return None
    dt = edl.parse_iso_to_jst(str(ts))
    if dt is None:
        return None
    return Entry(
        kind="chat",
        character=character,
        partner=partner,
        dt_utc=_to_utc(dt),
        role=str(role),
        text=str(text),
        raw=dict(raw),
        source=label,
        priority=priority,
    )


def _normalize_group_raw(kind: str, raw: Any, label: str, priority: int) -> Entry | None:
    if not isinstance(raw, dict):
        return None
    ts = raw.get("timestamp")
    role = raw.get("role")
    text = raw.get("text")
    if not ts or role is None or text is None:
        return None
    dt = edl.parse_iso_to_jst(str(ts))
    if dt is None:
        return None
    return Entry(
        kind=kind,
        character=None,
        partner=None,
        dt_utc=_to_utc(dt),
        role=str(role),
        text=str(text),
        raw=dict(raw),
        source=label,
        priority=priority,
    )


# -- source discovery ---------------------------------------------------------


def find_petit_claude_roots(base: Path) -> list[Path]:
    """base 以下を再帰的に走査し、petit_claude データルート
    (characters/ または chat_history/ を含む "petit_claude" という名前のディレクトリ)
    を探す。フルバックアップは `<snapshot>/petit_claude/` という形で入れ子に
    なっていることがあるため、深さを問わず探索する。"""
    if not base.is_dir():
        return []
    roots = []
    for p in sorted(base.rglob("petit_claude")):
        if not p.is_dir():
            continue
        parts = set(p.relative_to(base).parts)
        if parts & LOCAL_BACKUP_EXCLUDE_NAMES:
            continue
        if (p / "characters").is_dir() or (p / "chat_history").is_dir():
            roots.append(p)
    return roots


def label_for_root(base_label: str, base: Path, root: Path) -> str:
    try:
        rel = root.relative_to(base)
        rel_str = str(rel)
    except ValueError:
        rel_str = root.name
    if rel_str in (".", "petit_claude"):
        return base_label
    return f"{base_label}/{rel_str}"


def discover_sources() -> list[tuple[str, Path, int]]:
    """(label, petit_claude_root, priority) のリストを返す。"""
    sources: list[tuple[str, Path, int]] = [("live", PETIT_DATA_DIR, PRIORITY_LIVE)]

    if LOCAL_BACKUP_ROOT.is_dir():
        for snap in sorted(LOCAL_BACKUP_ROOT.iterdir()):
            if not snap.is_dir() or snap.name in LOCAL_BACKUP_EXCLUDE_NAMES:
                continue
            for root in find_petit_claude_roots(snap):
                sources.append(
                    (
                        label_for_root(f"local_backup/{snap.name}", snap, root),
                        root,
                        PRIORITY_LOCAL_BACKUP,
                    )
                )

    for base in DOWNLOADS_BACKUP_BASES:
        for root in find_petit_claude_roots(base):
            sources.append(
                (
                    label_for_root(f"downloads/{base.name}", base, root),
                    root,
                    PRIORITY_DOWNLOADS_BACKUP,
                )
            )

    return sources


# -- loading --------------------------------------------------------------


def load_entries_from_root(label: str, root: Path, priority: int) -> list[Entry]:
    entries: list[Entry] = []

    chars_dir = root / "characters"
    if chars_dir.is_dir():
        for char_dir in sorted(chars_dir.iterdir()):
            if not char_dir.is_dir():
                continue
            character = char_dir.name
            nested = char_dir / "chat_histories"
            files = sorted(nested.glob("*.json")) if nested.is_dir() else []
            if not files:
                # 旧・フラットレイアウト: characters/<name>/chat_history*.json が直下
                files = sorted(char_dir.glob("chat_history*.json"))
            for jf in files:
                partner = _partner_from_filename(jf.name)
                try:
                    data = json.loads(jf.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                if not isinstance(data, list):
                    continue
                for raw in data:
                    e = _normalize_chat_raw(character, partner, raw, label, priority)
                    if e:
                        entries.append(e)

    chat_hist_dir = root / "chat_history"
    if chat_hist_dir.is_dir():
        for fname, kind in (("group_chat.json", "group"), ("trio_chat.json", "trio")):
            f = chat_hist_dir / fname
            if not f.is_file():
                continue
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(data, list):
                continue
            for raw in data:
                e = _normalize_group_raw(kind, raw, label, priority)
                if e:
                    entries.append(e)

    return entries


def load_entries_from_csv(csv_path: Path, label: str) -> list[Entry]:
    if not csv_path.is_file():
        return []
    entries: list[Entry] = []
    with csv_path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            channel = row.get("channel")
            character = (row.get("character") or "").strip() or None
            speaker = row.get("speaker")
            ts = row.get("timestamp")
            text = row.get("text")
            if not ts or text is None or speaker is None:
                continue
            dt = edl.parse_iso_to_jst(ts)
            if dt is None:
                continue
            dt_utc = _to_utc(dt)
            if channel == "individual":
                if not character:
                    continue
                raw = {"role": speaker, "text": text, "timestamp": ts}
                entries.append(
                    Entry(
                        kind="chat",
                        character=character,
                        partner="arisan",
                        dt_utc=dt_utc,
                        role=speaker,
                        text=text,
                        raw=raw,
                        source=label,
                        priority=PRIORITY_CSV,
                    )
                )
            elif channel in ("group", "trio"):
                meta = CHARACTER_META.get(speaker, {})
                raw = {
                    "type": channel,
                    "role": speaker,
                    "name": meta.get("name", speaker),
                    "color": meta.get("color", "#888888"),
                    "text": text,
                    "timestamp": ts,
                }
                entries.append(
                    Entry(
                        kind=channel,
                        character=None,
                        partner=None,
                        dt_utc=dt_utc,
                        role=speaker,
                        text=text,
                        raw=raw,
                        source=label,
                        priority=PRIORITY_CSV,
                    )
                )
    return entries


def load_all_entries() -> tuple[list[Entry], list[dict[str, Any]]]:
    """全ソースからエントリを読み込む。(entries, source_report) を返す。"""
    all_entries: list[Entry] = []
    report: list[dict[str, Any]] = []

    for label, root, priority in discover_sources():
        es = load_entries_from_root(label, root, priority)
        report.append({"label": label, "path": str(root), "kind": "petit_claude_root", "count": len(es)})
        all_entries.extend(es)

    csv_entries = load_entries_from_csv(CHATS_ALL_CSV, "ro_man_chats_all_csv")
    report.append(
        {
            "label": "ro_man_chats_all_csv",
            "path": str(CHATS_ALL_CSV),
            "kind": "csv",
            "count": len(csv_entries),
        }
    )
    all_entries.extend(csv_entries)

    return all_entries, report


# -- merge / dedup ----------------------------------------------------------


def build_master(entries: list[Entry]) -> dict[tuple[str, str | None, str | None], list[Entry]]:
    """kind/character/partner ごとにバケット分けし、重複排除・時系列ソートする。"""
    buckets: dict[tuple[str, str | None, str | None], dict[tuple[Any, ...], Entry]] = {}

    for e in entries:
        bucket = buckets.setdefault(e.bucket_key(), {})
        key = e.dedup_key()
        existing = bucket.get(key)
        if existing is None or e.priority < existing.priority:
            bucket[key] = e

    result: dict[tuple[str, str | None, str | None], list[Entry]] = {}
    for bucket_key, by_dedup in buckets.items():
        result[bucket_key] = sorted(by_dedup.values(), key=lambda e: e.dt_utc)
    return result


# -- master output ------------------------------------------------------------


def bucket_filename(bucket_key: tuple[str, str | None, str | None]) -> tuple[str, str]:
    """(サブディレクトリ, ファイル名) を返す。"""
    kind, character, partner = bucket_key
    if kind == "chat":
        return "chat", f"{character}_{partner}.json"
    if kind == "group":
        return ".", "group_chat.json"
    if kind == "trio":
        return ".", "trio_chat.json"
    raise ValueError(f"unknown kind: {kind}")


def write_master(
    master: dict[tuple[str, str | None, str | None], list[Entry]],
    all_source_report: list[dict[str, Any]],
    dry_run: bool,
) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for bucket_key, es in sorted(master.items()):
        subdir, fname = bucket_filename(bucket_key)
        out_path = RECOVERED_DIR / subdir / fname if subdir != "." else RECOVERED_DIR / fname
        raws = [e.raw for e in es]
        sources_used = sorted({e.source for e in es})
        kind, character, partner = bucket_key
        bucket_label = kind if character is None else f"{kind}:{character}:{partner}"
        summary[bucket_label] = {
            "path": str(out_path),
            "count": len(es),
            "date_min": es[0].jst_date().isoformat() if es else None,
            "date_max": es[-1].jst_date().isoformat() if es else None,
            "sources": sources_used,
        }
        if not dry_run:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(raws, ensure_ascii=False, indent=2), encoding="utf-8")

    if not dry_run:
        RECOVERED_DIR.mkdir(parents=True, exist_ok=True)
        readme = _render_master_readme(summary, all_source_report)
        (RECOVERED_DIR / "README.md").write_text(readme, encoding="utf-8")

    return summary


def _render_master_readme(
    summary: dict[str, Any], all_source_report: list[dict[str, Any]]
) -> str:
    lines = [
        "# recovered_chat — 復元済み全期間マスター",
        "",
        "`scripts/recover_chat_history.py` が過去のバックアップ・研究用CSVから",
        "1:1チャット・グループチャット・トリオチャットを統合し、重複排除・時系列",
        "ソートした「その時点でのフルヒストリー」。ソースは読み取り専用のまま、",
        "このディレクトリにのみ新しいファイルとして書き出している。",
        "",
        "## 生成元ソース(このマスターに使われた素材の内訳)",
        "",
        "| ラベル | パス | 種別 | エントリ数 |",
        "|---|---|---|---|",
    ]
    for s in all_source_report:
        lines.append(f"| {s['label']} | `{s['path']}` | {s['kind']} | {s['count']} |")
    lines += [
        "",
        "## 統合後バケット別サマリー",
        "",
        "| バケット | 件数 | 期間(JST) | 出力ファイル |",
        "|---|---|---|---|",
    ]
    for key, info in sorted(summary.items()):
        date_range = f"{info['date_min']} 〜 {info['date_max']}" if info["count"] else "(0件)"
        lines.append(f"| {key} | {info['count']} | {date_range} | `{info['path']}` |")
    lines += [
        "",
        "## 既知の制約",
        "",
        "- `group`/`trio` チャンネルのうち `docs/ro-man/data/chats_all.csv` 由来のエントリは",
        "  元の `type` フィールド(`select` / `group` 等の区別)を復元できないため",
        "  `\"group\"`/`\"trio\"` 固定で再構成している。`name`/`color` も既知の対応表からの",
        "  再構成であり、当時の実際の値と異なる可能性がある。",
        "- `characters/puchiku/` は puchiko/puchiru/puchiteya のいずれとも異なる、",
        "  2026-05-25〜05-29 のみ存在した短命の別キャラクター(ノート参照)。",
        "  誤って統合しないよう、独立したバケット(`chat:puchiku:arisan`)として扱っている。",
        "- `exchange_notebook*.json` と `trio_chat.json` は調査の結果すでに現在の",
        "  ライブファイルが全期間をカバーしていた(非ローリング)ため、このマスターの",
        "  対象に含めていない(1:1チャットとgroup_chatのみがローリングバッファで",
        "  過去データを喪失していた)。",
    ]
    return "\n".join(lines) + "\n"


# -- daily_logs integration --------------------------------------------------


def _load_existing_entries(
    path: Path, kind: str, character: str | None, partner: str | None
) -> tuple[list[dict], list[Entry]]:
    if not path.is_file():
        return [], []
    try:
        raws = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return [], []
    if not isinstance(raws, list):
        return [], []
    normalized = []
    for raw in raws:
        if kind == "chat":
            e = _normalize_chat_raw(character, partner, raw, "existing_daily_log", -1)
        else:
            e = _normalize_group_raw(kind, raw, "existing_daily_log", -1)
        if e:
            normalized.append(e)
    return raws, normalized


def integrate_into_daily_logs(
    master: dict[tuple[str, str | None, str | None], list[Entry]], dry_run: bool
) -> dict[str, Any]:
    """master の内容を daily_logs/YYYY-MM-DD/{chat,group}/*.json に追記マージする。
    既存日付フォルダのみを対象にする(新しい日付フォルダは作らない)。
    manifest.json は sources.{chat,group}.count / files を更新しつつ、
    新規に manifest["recovery"] を追加して「何をどこから復元したか」を記録する。
    """
    if not DAILY_LOGS_DIR.is_dir():
        log(f"daily_logs が見つかりません: {DAILY_LOGS_DIR}")
        return {}

    # bucket_key -> date -> [Entry]
    by_date: dict[tuple[str, str | None, str | None], dict[date, list[Entry]]] = {}
    for bucket_key, es in master.items():
        d: dict[date, list[Entry]] = {}
        for e in es:
            d.setdefault(e.jst_date(), []).append(e)
        by_date[bucket_key] = d

    day_reports: dict[str, Any] = {}

    for day_dir in sorted(DAILY_LOGS_DIR.iterdir()):
        if not day_dir.is_dir():
            continue
        try:
            target_date = datetime.strptime(day_dir.name, "%Y-%m-%d").date()
        except ValueError:
            continue

        manifest_path = day_dir / "manifest.json"
        manifest: dict[str, Any] | None = None
        if manifest_path.is_file():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                manifest = None

        recovery_report: dict[str, Any] = {"chat": {}, "group": {}}
        touched = False

        for bucket_key, dates in by_date.items():
            kind, character, partner = bucket_key
            candidates = dates.get(target_date, [])
            if not candidates:
                continue

            subdir, fname = bucket_filename(bucket_key)
            out_dir = day_dir / ("chat" if kind == "chat" else "group")
            out_path = out_dir / fname

            _, existing_entries = _load_existing_entries(out_path, kind, character, partner)
            existing_keys = {e.dedup_key() for e in existing_entries}

            new_entries = [e for e in candidates if e.dedup_key() not in existing_keys]
            if not new_entries:
                continue

            merged_entries = existing_entries + new_entries
            merged_entries.sort(key=lambda e: e.dt_utc)
            merged_raws = [e.raw for e in merged_entries]

            if not dry_run:
                out_dir.mkdir(parents=True, exist_ok=True)
                out_path.write_text(
                    json.dumps(merged_raws, ensure_ascii=False, indent=2), encoding="utf-8"
                )

            sources_used = sorted({e.source for e in new_entries})
            recovery_report[kind if kind == "chat" else "group"][fname] = {
                "added": len(new_entries),
                "total_after": len(merged_raws),
                "sources": sources_used,
            }
            touched = True

        if touched:
            day_reports[day_dir.name] = recovery_report
            if manifest is not None and not dry_run:
                _update_manifest_counts(manifest, recovery_report)
                manifest.setdefault("recovery", {})
                manifest["recovery"] = {
                    "recovered_at": datetime.now(tz=JST).isoformat(),
                    "script": "scripts/recover_chat_history.py",
                    **recovery_report,
                }
                manifest_path.write_text(
                    json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
                )

    return day_reports


def _update_manifest_counts(manifest: dict[str, Any], recovery_report: dict[str, Any]) -> None:
    sources = manifest.setdefault("sources", {})

    chat_report = sources.setdefault(
        "chat",
        {"condition": "recover_chat_history.py により追加", "source_paths": [], "count": 0, "files": {}},
    )
    for fname, info in recovery_report.get("chat", {}).items():
        chat_report["files"][fname] = info["total_after"]
    chat_report["count"] = sum(chat_report["files"].values())

    group_report = sources.setdefault(
        "group",
        {
            "condition": "recover_chat_history.py により追加",
            "source_paths": [],
            "count": 0,
            "files": {},
        },
    )
    for fname, info in recovery_report.get("group", {}).items():
        entry = group_report["files"].setdefault(fname, {"count": 0, "unparseable": 0})
        entry["count"] = info["total_after"]
    group_report["count"] = sum(f["count"] for f in group_report["files"].values())


# -- CLI ----------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="失われた会話履歴の回収・統合")
    parser.add_argument("--dry-run", action="store_true", help="実行せず計画・件数のみ表示")
    parser.add_argument(
        "--master-only", action="store_true", help="recovered_chat/ の更新のみ行い daily_logs へは統合しない"
    )
    args = parser.parse_args()

    log("=== 会話履歴の棚卸し ===")
    entries, source_report = load_all_entries()
    for s in source_report:
        log(f"  {s['label']}: {s['count']} 件")
    log(f"合計 {len(entries)} 件のエントリを読み込み")

    log("=== マージ・重複排除 ===")
    master = build_master(entries)
    for bucket_key, es in sorted(master.items()):
        log(f"  {bucket_key}: {len(es)} 件 (重複排除後)")

    log("=== recovered_chat/ マスター保存 ===")
    write_master(master, source_report, dry_run=args.dry_run)

    if not args.master_only:
        log("=== daily_logs への統合 ===")
        day_reports = integrate_into_daily_logs(master, dry_run=args.dry_run)
        total_added = sum(
            info["added"]
            for report in day_reports.values()
            for kind_report in ("chat", "group")
            for info in report.get(kind_report, {}).values()
        )
        log(f"  {len(day_reports)} 日分に新規追加あり、合計 {total_added} 件{'(dry-run)' if args.dry_run else ''}")
        for day, report in sorted(day_reports.items()):
            parts = []
            for kind_report in ("chat", "group"):
                for fname, info in report.get(kind_report, {}).items():
                    parts.append(f"{fname}:+{info['added']}")
            if parts:
                log(f"    {day}: {', '.join(parts)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
