"""しずかな時間(scripts/quiet_time.py)のテスト"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import quiet_time as qt


def stream(tmp_path: Path, tools: list[tuple[str, dict]], result: str = "部屋は静かで、だれもいなかった。", error: bool = False,
           name: str = "20261113_130501_stream.jsonl") -> Path:
    lines = [{"type": "assistant", "message": {"content": [{"type": "tool_use", "name": n, "input": a}]}} for n, a in tools]
    lines.append({"type": "result", "subtype": "success", "is_error": error, "result": result})
    p = tmp_path / name
    p.write_text("\n".join(json.dumps(line, ensure_ascii=False) for line in lines), encoding="utf-8")
    return p


def test_quiet_run_is_recorded_in_own_words(tmp_path):
    s = stream(tmp_path, [("mcp__m5-mcp__get_sensor_data", {}), ("Bash", {"command": "ls mailbox"}), ("mcp__m5-mcp__sleep", {})],
               result="13:05 の確認では、\n部屋は静かで、だれもいなかった。")
    line = qt.record(tmp_path, "puchi", s)
    assert line == "- 11/13 13:05 — 13:05 の確認では、 部屋は静かで、だれもいなかった。"
    note = tmp_path / "characters" / "puchi" / "notes" / "しずかな時間_2026-11.md"
    assert note.read_text(encoding="utf-8").endswith(line + "\n")
    assert qt.record(tmp_path, "puchi", s) is None                      # 同じ回は 2 度足さない
    assert note.read_text(encoding="utf-8").count("13:05 —") == 1


def test_runs_that_left_something_are_not_recorded(tmp_path):
    for tools in (
        [("mcp__memory__remember", {"content": "x"})],
        [("mcp__notes-puchi__append_note", {})],
        [("Bash", {"command": "python3 /repo/scripts/write_mailbox.py puchi arisan 'やあ'"})],
        [("Write", {"file_path": "/h/characters/puchi/notes/詩.md"})],
        [("mcp__m5-mcp__save_to_album", {})],
    ):
        assert qt.record(tmp_path, "puchi", stream(tmp_path, tools)) is None
    assert not (tmp_path / "characters").exists()


def test_failed_or_empty_runs_are_not_recorded(tmp_path):
    assert qt.record(tmp_path, "puchi", stream(tmp_path, [], error=True)) is None
    assert qt.record(tmp_path, "puchi", stream(tmp_path, [], result="  ")) is None
    assert qt.record(tmp_path, "puchi", tmp_path / "20261113_130501_none.jsonl") is None
    assert qt.record(tmp_path, "puchi", stream(tmp_path, [], name="chat_stream.jsonl")) is None   # 時刻が読めない名前


def test_long_text_is_cut_and_dry_run_writes_nothing(tmp_path):
    s = stream(tmp_path, [], result="あ" * 500)
    line = qt.record(tmp_path, "puchi", s, dry_run=True)
    assert line.endswith("…") and len(line) < 330
    assert not (tmp_path / "characters").exists()
