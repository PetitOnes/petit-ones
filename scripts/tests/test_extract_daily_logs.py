"""extract_daily_logs.py のユニット/結合テスト。

実データには一切触れず、tmp_path 上にダミーデータを作って検証する。
実行: PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest scripts/tests/test_extract_daily_logs.py
"""

import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import extract_daily_logs as edl  # noqa: E402

# --- parse_mailbox_date -----------------------------------------------------


def test_mailbox_date_standard_pattern():
    # ありえない mtime を渡しておき、フォールバックが起きたらすぐ気づけるようにする
    mtime_jst = edl.datetime(2099, 1, 1, tzinfo=edl.JST)
    d, src = edl.parse_mailbox_date("from_puchiko_to_arisan_20260302_1004.md", mtime_jst)
    assert d == date(2026, 3, 2)
    assert src == "filename_datetime"


def test_mailbox_date_with_numeric_suffix():
    mtime_jst = edl.datetime(2099, 1, 1, tzinfo=edl.JST)
    d, src = edl.parse_mailbox_date("from_puchiko_to_arisan_20260430_1918_15.md", mtime_jst)
    assert d == date(2026, 4, 30)
    assert src == "filename_datetime"


def test_mailbox_date_no_from_prefix():
    mtime_jst = edl.datetime(2099, 1, 1, tzinfo=edl.JST)
    d, src = edl.parse_mailbox_date("to_arisan_20260228_0059.md", mtime_jst)
    assert d == date(2026, 2, 28)
    assert src == "filename_datetime"


def test_mailbox_date_trailing_name_suffix():
    mtime_jst = edl.datetime(2099, 1, 1, tzinfo=edl.JST)
    d, src = edl.parse_mailbox_date("to_arisan_20260301_0305_puchiteya.md", mtime_jst)
    assert d == date(2026, 3, 1)
    assert src == "filename_datetime"


def test_mailbox_date_non_numeric_time_falls_back_to_date_only():
    mtime_jst = edl.datetime(2099, 1, 1, tzinfo=edl.JST)
    d, src = edl.parse_mailbox_date("reply_to_teya_20260511_tmp.md", mtime_jst)
    assert d == date(2026, 5, 11)
    assert src == "filename_date_only"


def test_mailbox_date_malformed_digits_falls_back_to_mtime():
    # "2026303_1501" は 7桁+4桁で日付として解釈できないので mtime を使う
    mtime_jst = edl.datetime(2026, 3, 3, 16, 4, tzinfo=edl.JST)
    d, src = edl.parse_mailbox_date("from_yui_to_puchiteya_2026303_1501.md", mtime_jst)
    assert d == date(2026, 3, 3)
    assert src == "mtime_fallback"


# --- timestamp parsing / JST boundary ---------------------------------------


def test_parse_iso_to_jst_utc_offset_crosses_midnight():
    # UTC 15:30 の前日は JST では日付が変わって当日 00:30 になる
    dt = edl.parse_iso_to_jst("2026-07-05T15:30:00+00:00")
    assert dt.date() == date(2026, 7, 6)


def test_parse_iso_to_jst_naive_assumed_already_jst():
    dt = edl.parse_iso_to_jst("2026-07-06T23:59:00")
    assert dt.date() == date(2026, 7, 6)


def test_parse_iso_to_jst_explicit_jst_offset_noop():
    dt = edl.parse_iso_to_jst("2026-03-28T08:08:00+09:00")
    assert dt.date() == date(2026, 3, 28)


def test_parse_iso_to_jst_invalid_returns_none():
    assert edl.parse_iso_to_jst("not-a-date") is None


def test_parse_slash_date_to_jst():
    dt = edl.parse_slash_date_to_jst("2026/03/03 17:50")
    assert dt.date() == date(2026, 3, 3)
    assert dt.tzinfo == edl.JST


def test_parse_slash_date_to_jst_invalid_returns_none():
    assert edl.parse_slash_date_to_jst("garbage") is None


# --- end-to-end extraction on dummy data ------------------------------------


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _build_dummy_petit_dir(root: Path) -> None:
    # mailbox: 対象日1通 + 前日1通 + 翌日1通
    mailbox = root / "mailbox"
    mailbox.mkdir(parents=True)
    (mailbox / "from_puchiko_to_arisan_20260706_0900.md").write_text("today mail", encoding="utf-8")
    (mailbox / "from_puchiko_to_arisan_20260705_0900.md").write_text("yesterday mail", encoding="utf-8")
    (mailbox / "from_puchiko_to_arisan_20260707_0900.md").write_text("tomorrow mail", encoding="utf-8")

    # diary
    diary_dir = root / "characters" / "puchiko" / "diary"
    diary_dir.mkdir(parents=True)
    (diary_dir / "2026-07-06.txt").write_text("today diary", encoding="utf-8")
    (diary_dir / "2026-07-05.txt").write_text("yesterday diary", encoding="utf-8")

    # 1:1 chat history (UTC timestamps)
    chat_dir = root / "characters" / "puchiko" / "chat_histories"
    chat_dir.mkdir(parents=True)
    _write_json(
        chat_dir / "chat_history.json",
        [
            {
                "role": "user",
                "text": "in-day (UTC前日23:30 = JST当日08:30)",
                "timestamp": "2026-07-05T23:30:00+00:00",
            },
            {
                "role": "puchiko",
                "text": "same day reply",
                "timestamp": "2026-07-06T01:00:00+00:00",
            },
            {
                "role": "user",
                "text": "next day, should NOT be included",
                "timestamp": "2026-07-06T20:00:00+00:00",
            },
        ],
    )

    # group chat
    chat_history_dir = root / "chat_history"
    chat_history_dir.mkdir(parents=True)
    _write_json(
        chat_history_dir / "group_chat.json",
        [
            {"role": "puchiteya", "text": "target day", "timestamp": "2026-07-06T03:00:00+00:00"},
            {"role": "puchiko", "text": "other day", "timestamp": "2026-07-04T03:00:00+00:00"},
        ],
    )
    _write_json(chat_history_dir / "trio_chat.json", [])

    # notebook (mixed date/timestamp fields)
    _write_json(
        chat_history_dir / "exchange_notebook.json",
        [
            {"author": "arisan", "date": "2026/07/06 08:00", "content": "target day, date field"},
            {
                "author": "puchiko",
                "timestamp": "2026-07-06T09:00:00+09:00",
                "content": "target day, ts field",
            },
            {"author": "puchiko", "date": "2026/07/05 08:00", "content": "wrong day"},
        ],
    )
    _write_json(chat_history_dir / "exchange_notebook_kazahaya.json", [])

    # experience buffer (already per-day filename)
    exp_dir = root / "characters" / "puchiko" / "state" / "experience"
    exp_dir.mkdir(parents=True)
    exp_dir_lines = [
        json.dumps({"ts": "2026-07-06T10:00:00", "type": "touch", "detail": {}}, ensure_ascii=False),
    ]
    (exp_dir / "20260706.jsonl").write_text("\n".join(exp_dir_lines) + "\n", encoding="utf-8")

    # token usage log
    token_dir = root / "token_logs"
    token_dir.mkdir(parents=True)
    with (token_dir / "token_log.jsonl").open("w", encoding="utf-8") as f:
        f.write(json.dumps({"timestamp": "2026-07-06T12:00:00+09:00", "character": "puchiko"}) + "\n")
        f.write(json.dumps({"timestamp": "2026-07-05T12:00:00+09:00", "character": "puchiko"}) + "\n")

    # photos / voice_memo (dated filenames)
    photo_dir = root / "photo_album" / "puchiko"
    photo_dir.mkdir(parents=True)
    (photo_dir / "20260706_120000_puchiko_test.jpg").write_bytes(b"fake")
    (photo_dir / "20260705_120000_puchiko_test.jpg").write_bytes(b"fake")

    voice_dir = root / "voice_memo" / "puchiko"
    voice_dir.mkdir(parents=True)
    (voice_dir / "20260706_120000_puchiko_test.wav").write_bytes(b"fake")


def _patch_paths(monkeypatch, root: Path) -> None:
    monkeypatch.setattr(edl, "PETIT_DATA_DIR", root)
    monkeypatch.setattr(edl, "OUTPUT_ROOT", root / "daily_logs")
    monkeypatch.setattr(edl, "MAILBOX_DIR", root / "mailbox")
    monkeypatch.setattr(edl, "CHARACTERS_DIR", root / "characters")
    monkeypatch.setattr(edl, "CHAT_HISTORY_DIR", root / "chat_history")
    monkeypatch.setattr(edl, "TOKEN_LOG_FILE", root / "token_logs" / "token_log.jsonl")
    monkeypatch.setattr(edl, "PHOTO_ALBUM_DIR", root / "photo_album")
    monkeypatch.setattr(edl, "VOICE_MEMO_DIR", root / "voice_memo")


def test_end_to_end_extraction_only_target_day(tmp_path, monkeypatch):
    root = tmp_path / "petit_claude"
    _build_dummy_petit_dir(root)
    _patch_paths(monkeypatch, root)

    extractor = edl.DailyExtractor(date(2026, 7, 6))
    manifest = extractor.run()

    out_dir = root / "daily_logs" / "2026-07-06"
    assert out_dir.is_dir()

    # mailbox: only the target-day file copied
    mailbox_files = sorted(p.name for p in (out_dir / "mailbox").iterdir())
    assert mailbox_files == ["from_puchiko_to_arisan_20260706_0900.md"]

    # diary
    assert (out_dir / "diary" / "puchiko.txt").read_text(encoding="utf-8") == "today diary"

    # chat: only 2 of 3 entries match JST day boundary
    chat_data = json.loads((out_dir / "chat" / "puchiko_arisan.json").read_text(encoding="utf-8"))
    assert len(chat_data) == 2
    assert all("target" not in "" for _ in chat_data)  # sanity no-op

    # group
    group_data = json.loads((out_dir / "group" / "group_chat.json").read_text(encoding="utf-8"))
    assert len(group_data) == 1
    assert group_data[0]["text"] == "target day"
    assert not (out_dir / "group" / "trio_chat.json").exists()  # empty match -> no file

    # notebook: 2 of 3 entries match
    notebook_data = json.loads(
        (out_dir / "notebook" / "exchange_notebook.json").read_text(encoding="utf-8")
    )
    assert len(notebook_data) == 2

    # experience
    exp_lines = (out_dir / "experience" / "puchiko.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(exp_lines) == 1

    # usage
    usage_data = json.loads((out_dir / "usage.json").read_text(encoding="utf-8"))
    assert len(usage_data) == 1

    # photos / voice_memo
    assert (out_dir / "photos" / "puchiko" / "20260706_120000_puchiko_test.jpg").exists()
    assert not (out_dir / "photos" / "puchiko" / "20260705_120000_puchiko_test.jpg").exists()
    assert (out_dir / "voice_memo" / "puchiko" / "20260706_120000_puchiko_test.wav").exists()

    # manifest exists and records counts
    manifest_on_disk = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest_on_disk["date"] == "2026-07-06"
    assert manifest_on_disk["sources"]["mailbox"]["count"] == 1
    assert manifest == manifest_on_disk


def test_extraction_is_idempotent(tmp_path, monkeypatch):
    root = tmp_path / "petit_claude"
    _build_dummy_petit_dir(root)
    _patch_paths(monkeypatch, root)

    edl.DailyExtractor(date(2026, 7, 6)).run()
    out_dir = root / "daily_logs" / "2026-07-06"
    first_run_files = sorted(str(p.relative_to(out_dir)) for p in out_dir.rglob("*") if p.is_file())

    # 元データを変える前にもう一度実行 -> 同じ内容
    edl.DailyExtractor(date(2026, 7, 6)).run()
    second_run_files = sorted(str(p.relative_to(out_dir)) for p in out_dir.rglob("*") if p.is_file())
    assert first_run_files == second_run_files

    # ソース側のメールを1通消してから再実行すると、出力側からも消える(=作り直し)
    (root / "mailbox" / "from_puchiko_to_arisan_20260706_0900.md").unlink()
    edl.DailyExtractor(date(2026, 7, 6)).run()
    # マッチするメールが無くなったので mailbox/ サブフォルダごと作られない
    assert not (out_dir / "mailbox").exists()


def test_dry_run_writes_nothing(tmp_path, monkeypatch):
    root = tmp_path / "petit_claude"
    _build_dummy_petit_dir(root)
    _patch_paths(monkeypatch, root)

    manifest = edl.DailyExtractor(date(2026, 7, 6), dry_run=True).run()
    out_dir = root / "daily_logs" / "2026-07-06"
    assert not out_dir.exists()
    # それでも集計上は件数が分かる
    assert manifest["sources"]["mailbox"]["count"] == 1


def test_sources_never_modified(tmp_path, monkeypatch):
    root = tmp_path / "petit_claude"
    _build_dummy_petit_dir(root)
    _patch_paths(monkeypatch, root)

    mail_file = root / "mailbox" / "from_puchiko_to_arisan_20260706_0900.md"
    before = mail_file.read_bytes()
    before_mtime = mail_file.stat().st_mtime

    edl.DailyExtractor(date(2026, 7, 6)).run()

    assert mail_file.read_bytes() == before
    assert mail_file.stat().st_mtime == before_mtime


def test_find_earliest_date(tmp_path, monkeypatch):
    root = tmp_path / "petit_claude"
    _build_dummy_petit_dir(root)
    _patch_paths(monkeypatch, root)

    earliest = edl.find_earliest_date()
    assert earliest == date(2026, 7, 5)
