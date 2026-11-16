"""🔒 ひみつ の「わたしている文」(dashboard/prompt_view.py)のテスト"""

import json
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "dashboard"))

import prompt_view as pv  # noqa: E402


def _house(tmp_path: Path) -> Path:
    char = tmp_path / "characters" / "puchiko"
    char.mkdir(parents=True)
    (char / "SOUL.md").write_text("# たましい\n", encoding="utf-8")
    (char / "TODO.md").write_text("古い TODO\n", encoding="utf-8")
    (char / "TODO_ACTIVE.md").write_text("x" * (50 * 1024), encoding="utf-8")
    (char / "TODO_ARCHIVE.md").write_text("y" * (120 * 1024), encoding="utf-8")
    (tmp_path / "ROUTINES.md").write_text("家のルーチン\n", encoding="utf-8")
    mailbox = tmp_path / "mailbox"
    mailbox.mkdir()
    (mailbox / "from_puchiru_to_puchiko_20261113_1200.md").write_text("a", encoding="utf-8")
    (mailbox / "from_puchiru_to_puchiko_20261113_1300.md").write_text("b", encoding="utf-8")
    (mailbox / "from_puchiko_to_puchiru_20261113_1400.md").write_text("c", encoding="utf-8")
    (mailbox / ".metadata.json").write_text(json.dumps({"mails": {"from_puchiru_to_puchiko_20261113_1200.md": {"read_by": ["puchiko"]}}}), encoding="utf-8")
    return tmp_path


def test_file_rows_follow_autonomous_rules(tmp_path: Path):
    rows = {r["key"]: r for r in pv.file_rows(_house(tmp_path), "puchiko", warn_kb=40)}
    assert rows["todo"]["name"] == "TODO_ACTIVE.md"          # TODO.md より TODO_ACTIVE.md
    assert rows["todo"]["heavy"] == "warn" and rows["soul"]["heavy"] == ""
    assert rows["todo_archive"]["heavy"] == ""                # 自分で読みに行くファイルは、重くても印を付けない
    assert rows["routines"]["when"] == "self"                 # その子のものが無ければ、家の ROUTINES.md
    assert "diary_summary" not in rows                        # 無いファイルは出さない
    assert all("content" not in r for r in rows.values())


def test_heavy_drop_and_read(tmp_path: Path):
    house = _house(tmp_path)
    (house / "characters" / "puchiko" / "SOUL.md").write_text("z" * (90 * 1024), encoding="utf-8")
    rows = {r["key"]: r for r in pv.file_rows(house, "puchiko")}
    assert rows["soul"]["heavy"] == "drop"
    assert pv.read_file(house, "puchiko", "routines") == "家のルーチン\n"
    assert pv.read_file(house, "puchiko", "nope") is None
    assert pv.read_file(house, "puchiko", "diary_summary") is None


def test_desire_rows_sorted():
    d = pv.desire_rows({"desires": {"a": 0.2, "b": 0.9}, "labels": {"b": "書きたい"}, "colors": {"a": "#fff"}, "dominant": "b"})
    assert [r["key"] for r in d["rows"]] == ["b", "a"]
    assert d["rows"][0]["label"] == "書きたい" and d["rows"][1]["label"] == "a"
    assert pv.desire_rows({}) == {"rows": [], "dominant": "", "updated_at": ""}


def test_autonomous_preview_writes_nothing(tmp_path: Path):
    house = _house(tmp_path)
    before = sorted((str(p), p.stat().st_mtime_ns) for p in house.rglob("*"))
    text = pv.autonomous_preview(house, REPO, "puchiko", now=datetime(2026, 11, 16, 14, 0), user_name="あなた",
                                 mail_targets="puchiru, owner", permission_rules="- カメラは使わない", whereabouts="いま: 家")
    assert pv.unread_count(house, "puchiko") == 1
    assert f"@{house}/characters/puchiko/SOUL.md" in text
    assert f"@{house}/characters/puchiko/TODO_ACTIVE.md" in text
    assert "現在の日時: 2026-11-16 14:00:00 (JST)" in text
    assert "TODO_ACTIVE.md が 50 KB" in text                   # 重いファイルの注意も、本番と同じに入る
    assert "## 現在の制限\n- カメラは使わない" in text and "いま: 家" in text
    assert "{{" not in text
    assert before == sorted((str(p), p.stat().st_mtime_ns) for p in house.rglob("*"))


def test_sidecar_roundtrip(tmp_path: Path):
    chat = tmp_path / "20261116_150000_chat_stream.jsonl"
    assert pv.sidecar_events(chat) == []                       # 残す前の記録は、空
    pv.save_sidecar(chat, "あなたは…", "こんにちは")
    assert (tmp_path / "20261116_150000_chat_prompt.json").is_file()
    assert pv.sidecar_events(chat) == [{"kind": "system_prompt", "text": "あなたは…"}, {"kind": "user_text", "text": "こんにちは"}]
    alone = tmp_path / "20261116_153000_stream.jsonl"
    (tmp_path / "20261116_153000_prompt.md").write_text("自律行動タイム\n", encoding="utf-8")   # autonomous-action.sh が置く形
    assert pv.sidecar_events(alone) == [{"kind": "user_text", "text": "自律行動タイム"}]
    pv.save_sidecar(tmp_path / "no_such_dir" / "x_stream.jsonl", "a", "b")   # 書けなくても落ちない
