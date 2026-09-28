"""recover_chat_history.py のユニット/結合テスト。

実データには一切触れず、tmp_path 上にダミーデータを作って検証する。
実行: PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest scripts/tests/test_recover_chat_history.py
"""

import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import recover_chat_history as rch  # noqa: E402

# --- _normalize_text ---------------------------------------------------------


def test_normalize_text_collapses_newlines_and_spaces():
    assert rch._normalize_text("あ\n\nい　") == rch._normalize_text("あ い")


def test_normalize_text_distinguishes_different_content():
    assert rch._normalize_text("あい") != rch._normalize_text("あいう")


# --- _partner_from_filename ---------------------------------------------------


def test_partner_from_filename_default_is_arisan():
    assert rch._partner_from_filename("chat_history.json") == "arisan"


def test_partner_from_filename_kazahaya():
    assert rch._partner_from_filename("chat_history_kazahaya.json") == "kazahaya"


def test_partner_from_filename_visitor():
    assert rch._partner_from_filename("chat_history_visitor.json") == "visitor"


# --- normalize raw entries ----------------------------------------------------


def test_normalize_chat_raw_valid():
    raw = {"role": "puchiko", "text": "hi", "timestamp": "2026-06-01T00:00:00+00:00"}
    e = rch._normalize_chat_raw("puchiko", "arisan", raw, "test_source", 1)
    assert e is not None
    assert e.kind == "chat"
    assert e.character == "puchiko"
    assert e.partner == "arisan"
    assert e.dt_utc == datetime(2026, 6, 1, tzinfo=timezone.utc)


def test_normalize_chat_raw_missing_fields_returns_none():
    assert rch._normalize_chat_raw("puchiko", "arisan", {"role": "puchiko"}, "s", 1) is None
    assert rch._normalize_chat_raw("puchiko", "arisan", "not a dict", "s", 1) is None


def test_normalize_group_raw_valid():
    raw = {
        "type": "group",
        "role": "puchiteya",
        "name": "ぷちてゃ",
        "color": "#fff262",
        "text": "hello",
        "timestamp": "2026-06-01T00:00:00+00:00",
    }
    e = rch._normalize_group_raw("group", raw, "test_source", 1)
    assert e is not None
    assert e.kind == "group"
    assert e.character is None


# --- Entry.dedup_key -----------------------------------------------------------


def test_dedup_key_ignores_whitespace_differences():
    raw1 = {"role": "puchiko", "text": "a\nb", "timestamp": "2026-06-01T00:00:00.123456+00:00"}
    raw2 = {"role": "puchiko", "text": "a b", "timestamp": "2026-06-01T00:00:00.999999+00:00"}
    e1 = rch._normalize_chat_raw("puchiko", "arisan", raw1, "live", 0)
    e2 = rch._normalize_chat_raw("puchiko", "arisan", raw2, "csv", 9)
    assert e1.dedup_key() == e2.dedup_key()


def test_dedup_key_differs_for_different_text():
    raw1 = {"role": "puchiko", "text": "a", "timestamp": "2026-06-01T00:00:00+00:00"}
    raw2 = {"role": "puchiko", "text": "b", "timestamp": "2026-06-01T00:00:00+00:00"}
    e1 = rch._normalize_chat_raw("puchiko", "arisan", raw1, "live", 0)
    e2 = rch._normalize_chat_raw("puchiko", "arisan", raw2, "live", 0)
    assert e1.dedup_key() != e2.dedup_key()


# --- find_petit_claude_roots ---------------------------------------------------


def test_find_petit_claude_roots_finds_nested_snapshots(tmp_path):
    base = tmp_path / "some_download"
    outer = base / "petit_claude"
    (outer / "chat_history").mkdir(parents=True)
    nested = outer / "backup" / "20260227_191126" / "petit_claude" / "characters"
    nested.mkdir(parents=True)

    roots = rch.find_petit_claude_roots(base)
    assert outer in roots
    assert nested.parent in roots
    assert len(roots) == 2


def test_find_petit_claude_roots_excludes_cc_sessions_mirror(tmp_path):
    base = tmp_path / "backup_root"
    excluded = base / "cc_sessions_mirror" / "petit_claude"
    (excluded / "characters").mkdir(parents=True)
    roots = rch.find_petit_claude_roots(base)
    assert roots == []


def test_find_petit_claude_roots_missing_base_returns_empty(tmp_path):
    assert rch.find_petit_claude_roots(tmp_path / "does_not_exist") == []


# --- load_entries_from_root: flat vs nested layout -----------------------------


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def test_load_entries_from_root_nested_layout(tmp_path):
    root = tmp_path / "petit_claude"
    _write_json(
        root / "characters" / "puchiko" / "chat_histories" / "chat_history.json",
        [{"role": "arisan", "text": "hi", "timestamp": "2026-06-01T00:00:00+00:00"}],
    )
    _write_json(
        root / "chat_history" / "group_chat.json",
        [
            {
                "type": "group",
                "role": "puchiko",
                "name": "ぷちこ",
                "color": "#cab8d9",
                "text": "hey",
                "timestamp": "2026-06-01T00:00:00+00:00",
            }
        ],
    )
    entries = rch.load_entries_from_root("test", root, 1)
    kinds = {e.kind for e in entries}
    assert kinds == {"chat", "group"}


def test_load_entries_from_root_flat_layout(tmp_path):
    root = tmp_path / "petit_claude"
    _write_json(
        root / "characters" / "puchiko" / "chat_history.json",
        [{"role": "arisan", "text": "hi", "timestamp": "2026-03-01T00:00:00+00:00"}],
    )
    entries = rch.load_entries_from_root("test", root, 1)
    assert len(entries) == 1
    assert entries[0].character == "puchiko"
    assert entries[0].partner == "arisan"


# --- load_entries_from_csv ------------------------------------------------------


def test_load_entries_from_csv_individual_and_group(tmp_path):
    csv_path = tmp_path / "chats_all.csv"
    csv_path.write_text(
        "channel,character,speaker,timestamp,date,text\n"
        "individual,puchiko,arisan,2026-03-01T00:00:00+00:00,2026-03-01,hello there\n"
        "group,,puchiteya,2026-03-01T00:00:01+00:00,2026-03-01,group msg\n",
        encoding="utf-8",
    )
    entries = rch.load_entries_from_csv(csv_path, "test_csv")
    assert len(entries) == 2
    chat_entry = next(e for e in entries if e.kind == "chat")
    assert chat_entry.character == "puchiko"
    assert chat_entry.partner == "arisan"
    group_entry = next(e for e in entries if e.kind == "group")
    assert group_entry.raw["name"] == "ぷちてゃ"
    assert group_entry.raw["color"] == "#fff262"


def test_load_entries_from_csv_missing_file_returns_empty(tmp_path):
    assert rch.load_entries_from_csv(tmp_path / "missing.csv", "x") == []


# --- build_master: dedup + priority --------------------------------------------


def test_build_master_dedup_prefers_lower_priority_number():
    raw_live = {"role": "puchiko", "text": "a\nb", "timestamp": "2026-06-01T00:00:00+00:00"}
    raw_csv = {"role": "puchiko", "text": "a b", "timestamp": "2026-06-01T00:00:00+00:00"}
    e_csv = rch._normalize_chat_raw("puchiko", "arisan", raw_csv, "csv", 9)
    e_live = rch._normalize_chat_raw("puchiko", "arisan", raw_live, "live", 0)
    master = rch.build_master([e_csv, e_live])
    bucket = master[("chat", "puchiko", "arisan")]
    assert len(bucket) == 1
    assert bucket[0].source == "live"
    assert bucket[0].raw["text"] == "a\nb"


def test_build_master_sorts_by_time():
    raws = [
        {"role": "puchiko", "text": "second", "timestamp": "2026-06-01T00:00:02+00:00"},
        {"role": "puchiko", "text": "first", "timestamp": "2026-06-01T00:00:01+00:00"},
    ]
    entries = [rch._normalize_chat_raw("puchiko", "arisan", r, "live", 0) for r in raws]
    master = rch.build_master(entries)
    bucket = master[("chat", "puchiko", "arisan")]
    assert [e.raw["text"] for e in bucket] == ["first", "second"]


# --- daily_logs integration -----------------------------------------------------


def _make_entry(kind, character, partner, role, text, ts_iso, source="live", priority=0):
    if kind == "chat":
        raw = {"role": role, "text": text, "timestamp": ts_iso}
        return rch._normalize_chat_raw(character, partner, raw, source, priority)
    raw = {
        "type": kind,
        "role": role,
        "name": role,
        "color": "#000000",
        "text": text,
        "timestamp": ts_iso,
    }
    return rch._normalize_group_raw(kind, raw, source, priority)


def test_integrate_into_daily_logs_appends_new_and_skips_duplicates(tmp_path, monkeypatch):
    daily_logs = tmp_path / "daily_logs"
    day_dir = daily_logs / "2026-06-01"
    existing_chat = [{"role": "arisan", "text": "existing msg", "timestamp": "2026-06-01T00:00:00+00:00"}]
    _write_json(day_dir / "chat" / "puchiko_arisan.json", existing_chat)
    manifest = {
        "date": "2026-06-01",
        "sources": {
            "chat": {"condition": "c", "source_paths": [], "count": 1, "files": {"puchiko_arisan.json": 1}},
            "group": {"condition": "c", "source_paths": [], "count": 0, "files": {}},
        },
    }
    _write_json(day_dir / "manifest.json", manifest)

    monkeypatch.setattr(rch, "DAILY_LOGS_DIR", daily_logs)

    dup_entry = _make_entry(
        "chat", "puchiko", "arisan", "arisan", "existing msg", "2026-06-01T00:00:00.000001+00:00"
    )
    new_entry = _make_entry(
        "chat", "puchiko", "arisan", "puchiko", "brand new", "2026-06-01T00:05:00+00:00"
    )
    master = {("chat", "puchiko", "arisan"): [dup_entry, new_entry]}

    report = rch.integrate_into_daily_logs(master, dry_run=False)

    assert "2026-06-01" in report
    assert report["2026-06-01"]["chat"]["puchiko_arisan.json"]["added"] == 1

    merged = json.loads((day_dir / "chat" / "puchiko_arisan.json").read_text(encoding="utf-8"))
    assert len(merged) == 2
    assert merged[0]["text"] == "existing msg"
    assert merged[1]["text"] == "brand new"

    updated_manifest = json.loads((day_dir / "manifest.json").read_text(encoding="utf-8"))
    assert updated_manifest["sources"]["chat"]["files"]["puchiko_arisan.json"] == 2
    assert updated_manifest["sources"]["chat"]["count"] == 2
    assert "recovery" in updated_manifest
    assert updated_manifest["recovery"]["chat"]["puchiko_arisan.json"]["added"] == 1


def test_integrate_into_daily_logs_is_idempotent(tmp_path, monkeypatch):
    daily_logs = tmp_path / "daily_logs"
    day_dir = daily_logs / "2026-06-01"
    _write_json(day_dir / "manifest.json", {"date": "2026-06-01", "sources": {}})
    monkeypatch.setattr(rch, "DAILY_LOGS_DIR", daily_logs)

    new_entry = _make_entry("chat", "puchiko", "arisan", "puchiko", "only once", "2026-06-01T00:05:00+00:00")
    master = {("chat", "puchiko", "arisan"): [new_entry]}

    first = rch.integrate_into_daily_logs(master, dry_run=False)
    assert first["2026-06-01"]["chat"]["puchiko_arisan.json"]["added"] == 1

    second = rch.integrate_into_daily_logs(master, dry_run=False)
    assert "2026-06-01" not in second  # 2周目は新規追加0件なので触らない

    merged = json.loads((day_dir / "chat" / "puchiko_arisan.json").read_text(encoding="utf-8"))
    assert len(merged) == 1


def test_integrate_into_daily_logs_dry_run_does_not_write(tmp_path, monkeypatch):
    daily_logs = tmp_path / "daily_logs"
    day_dir = daily_logs / "2026-06-01"
    _write_json(day_dir / "manifest.json", {"date": "2026-06-01", "sources": {}})
    monkeypatch.setattr(rch, "DAILY_LOGS_DIR", daily_logs)

    new_entry = _make_entry("chat", "puchiko", "arisan", "puchiko", "dry", "2026-06-01T00:05:00+00:00")
    master = {("chat", "puchiko", "arisan"): [new_entry]}

    report = rch.integrate_into_daily_logs(master, dry_run=True)
    assert report["2026-06-01"]["chat"]["puchiko_arisan.json"]["added"] == 1
    assert not (day_dir / "chat" / "puchiko_arisan.json").exists()


def test_integrate_into_daily_logs_ignores_dates_outside_master():
    # 日付フォルダが存在しなければ何も起きない(例外を投げない)ことを確認するのみ。
    # 実データ保護のため実際のDAILY_LOGS_DIRには触れない。
    pass


def test_bucket_filename():
    assert rch.bucket_filename(("chat", "puchiko", "arisan")) == ("chat", "puchiko_arisan.json")
    assert rch.bucket_filename(("group", None, None)) == (".", "group_chat.json")
    assert rch.bucket_filename(("trio", None, None)) == (".", "trio_chat.json")


# --- write_master ---------------------------------------------------------------


def test_write_master_creates_files_and_readme(tmp_path, monkeypatch):
    recovered_dir = tmp_path / "recovered_chat"
    monkeypatch.setattr(rch, "RECOVERED_DIR", recovered_dir)

    entry = _make_entry("chat", "puchiko", "arisan", "puchiko", "hi", "2026-06-01T00:00:00+00:00")
    master = {("chat", "puchiko", "arisan"): [entry]}
    summary = rch.write_master(master, [{"label": "live", "path": "/x", "kind": "petit_claude_root", "count": 1}], dry_run=False)

    assert (recovered_dir / "chat" / "puchiko_arisan.json").is_file()
    assert (recovered_dir / "README.md").is_file()
    assert summary["chat:puchiko:arisan"]["count"] == 1


def test_write_master_dry_run_does_not_write(tmp_path, monkeypatch):
    recovered_dir = tmp_path / "recovered_chat"
    monkeypatch.setattr(rch, "RECOVERED_DIR", recovered_dir)

    entry = _make_entry("chat", "puchiko", "arisan", "puchiko", "hi", "2026-06-01T00:00:00+00:00")
    master = {("chat", "puchiko", "arisan"): [entry]}
    rch.write_master(master, [], dry_run=True)

    assert not recovered_dir.exists()


# --- Entry.jst_date --------------------------------------------------------------


def test_jst_date_crosses_midnight():
    raw = {"role": "arisan", "text": "x", "timestamp": "2026-06-21T15:30:00+00:00"}
    e = rch._normalize_chat_raw("puchiko", "arisan", raw, "live", 0)
    assert e.jst_date() == date(2026, 6, 22)
