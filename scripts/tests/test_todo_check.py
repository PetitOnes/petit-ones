"""todo_check.py: 知らせは 1 行、片付けるのは本人"""
import json
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import todo_check as tc  # noqa: E402

TODO = """# TODO_ACTIVE
## 返事待ち(催促はしない)
- [ ] 波長か hex か(ありさん・9/24から)
## 次にやること
- [x] 終わったこと
- [ ] 古いこと(8/1 に始めた)
- [ ] 新しいこと(11/16)
- [ ] 日付のないこと
- [ ] """ + "長" * 320 + """
"""


def _house(tmp_path: Path, rules: dict | None = None) -> Path:
    d = tmp_path / "characters" / "ko"
    (d / "config").mkdir(parents=True)
    (d / "TODO_ACTIVE.md").write_text(TODO, encoding="utf-8")
    (d / "config" / "settings.json").write_text(json.dumps({"todo_check": rules or {}}), encoding="utf-8")
    return tmp_path


def test_scan_groups(tmp_path):
    s = tc.scan(_house(tmp_path, {"stale_min": 1}), "ko", date(2026, 11, 17))
    assert [i["n"] for i in s["done"]] == [5]
    assert [i["n"] for i in s["stale"]] == [6]          # 返事待ちの 9/24 と日付のない行は数えない
    assert [i["n"] for i in s["long"]] == [9]
    assert s["waiting"][0]["who"] == "ありさん" and s["waiting"][0]["since"] == "9/24"


def test_latest_date_wraps_year():
    assert tc.latest_date("12/30 と 2026-01-02", date(2026, 1, 5)) == date(2026, 1, 2)
    assert tc.latest_date("12/30 だけ", date(2026, 1, 5)) == date(2025, 12, 30)


def test_notice_once_a_day_and_rules(tmp_path):
    base = _house(tmp_path, {"stale_days": 0})
    now = datetime(2026, 11, 17, 12, 0)
    line = tc.notice(base, "ko", mark=True, now=now)
    assert len(line) == 1 and "終わった印の行 1" in line[0] and "動いていない" not in line[0] and "返事待ち 1" in line[0]
    assert tc.notice(base, "ko", now=now) == []
    assert tc.notice(base, "ko", now=datetime(2026, 11, 18, 3, 0)) == []   # 静かな時間


def test_archive_moves_and_backs_up(tmp_path):
    base = _house(tmp_path)
    r = tc.archive(base, "ko", [8], done=True, now=datetime(2026, 11, 17, 22, 0))
    assert r["moved"] == 2
    d = base / "characters" / "ko"
    assert "終わったこと" not in (d / "TODO_ACTIVE.md").read_text(encoding="utf-8")
    assert "日付のないこと" in (d / "TODO_ARCHIVE.md").read_text(encoding="utf-8")
    assert (d / "TODO_ACTIVE.md.bak_2026-11-17_2200").read_text(encoding="utf-8") == TODO


def test_archive_refuses_headings(tmp_path):
    base = _house(tmp_path)
    try:
        tc.archive(base, "ko", [1])
    except ValueError:
        return
    raise AssertionError("見出しは移さない")


def test_set_rule_keeps_other_settings(tmp_path):
    base = _house(tmp_path)
    p = base / "characters" / "ko" / "config" / "settings.json"
    p.write_text(json.dumps({"notices": {"todo": False}}), encoding="utf-8")
    assert tc.set_rule(base, "ko", "stale_days", 14)["stale_days"] == 14
    assert json.loads(p.read_text(encoding="utf-8"))["notices"] == {"todo": False}


def test_waiting_all_only_waiting_section(tmp_path):
    rows = tc.waiting_all(_house(tmp_path))
    assert [r["character"] for r in rows] == ["ko"] and "波長" in rows[0]["text"]
