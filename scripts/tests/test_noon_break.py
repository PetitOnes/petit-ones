"""noon_break.py / carry.py: お昼の区切り"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import carry  # noqa: E402
import noon_break as nb  # noqa: E402

JST = timezone(timedelta(hours=9))


def _at(h, m=0, d=17):
    return datetime(2026, 11, d, h, m, tzinfo=JST)


def test_before_noon_and_once_a_day(tmp_path):
    assert nb.decide(tmp_path, "ko", now=_at(11, 50)) == "no"
    assert nb.decide(tmp_path, "ko", now=_at(12, 0)) == "break"
    nb.done(tmp_path, "ko", now=_at(12, 1))
    assert nb.decide(tmp_path, "ko", now=_at(12, 30)) == "no"
    assert nb.decide(tmp_path, "ko", now=_at(12, 0, d=18)) == "break"   # 次の日はまた


def test_wait_while_talking_and_same_slot_for_all(tmp_path):
    ch = tmp_path / "characters" / "ko" / "chat_histories"
    ch.mkdir(parents=True)
    (ch / "chat_history.json").write_text(json.dumps([{"role": "user", "text": "やあ", "timestamp": "2026-11-17T02:55:00+00:00"}]))
    assert nb.decide(tmp_path, "teya", now=_at(12, 0)).startswith("wait: ダッシュボード")
    # 同じ枠(12:00〜12:29)の子は、話が終わっていても同じ答え(3 人そろう)
    (ch / "chat_history.json").write_text("[]")
    assert nb.decide(tmp_path, "ru", now=_at(12, 10)).startswith("wait")
    assert nb.decide(tmp_path, "teya", now=_at(12, 30)) == "break"


def test_wait_while_out(tmp_path):
    (tmp_path / "state").mkdir()
    (tmp_path / "state" / "whereabouts.json").write_text(json.dumps({"users": {"arisan": {"text": "お外", "since": "2026-11-17T10:00:00"}}}, ensure_ascii=False))
    assert nb.decide(tmp_path, "ko", "arisan", now=_at(12, 0)) == "wait: arisan のいまが「お外」"
    (tmp_path / "state" / "whereabouts.json").write_text(json.dumps({"users": {"arisan": {"text": "自室"}}}, ensure_ascii=False))
    assert nb.decide(tmp_path, "ko", "arisan", now=_at(12, 30)) == "break"


def test_carry_keeps_three_lines_of_today(tmp_path):
    for i in range(4):
        carry.write(tmp_path, "ko", f"行{i}", now=_at(11, i))
    assert [x["text"] for x in carry.load(tmp_path, "ko", now=_at(12))] == ["行1", "行2", "行3"]
    assert carry.load(tmp_path, "ko", now=_at(12, d=18)) == []


def test_intro_has_carry_and_last_words(tmp_path):
    carry.write(tmp_path, "ko", "静けさに起伏があった", now=_at(11, 59))
    logs = tmp_path / ".autonomous-logs" / "ko"
    logs.mkdir(parents=True)
    msg = {"type": "assistant", "message": {"content": [{"type": "text", "text": "窓の外が白い。"}]}}
    (logs / "20261117_113000_stream.jsonl").write_text(json.dumps(msg, ensure_ascii=False))
    (logs / "20261117_120000_carry_stream.jsonl").write_text(json.dumps({**msg, "message": {"content": [{"type": "text", "text": "書いたよ"}]}}, ensure_ascii=False))
    out = carry.intro(tmp_path, "ko", now=_at(12, 1))
    assert "- 静けさに起伏があった" in out and "[11:30] 窓の外が白い。" in out and "書いたよ" not in out
