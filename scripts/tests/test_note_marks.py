"""ノートの ★・既読と、ぷちへの知らせ(scripts/note_marks.py)のテスト"""

import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import note_marks as nm  # noqa: E402

T1 = datetime(2026, 11, 14, 17, 20)
T2 = datetime(2026, 11, 14, 18, 0)


def _house(tmp_path: Path) -> Path:
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "people.json").write_text(json.dumps({"arisan": {"name": "ありさん"}}), encoding="utf-8")
    return tmp_path


def test_star_read_and_notice(tmp_path):
    base = _house(tmp_path)
    assert nm.notice(base, "puchiko", mark=True) == []                    # はじめての回は何も言わず、いまを覚える
    nm.set_star(base, "puchiko", "20261114_070000_あさ.md", True, "arisan", T1)
    nm.set_read(base, "arisan", "puchiko", "20261114_070000_あさ.md", T1)
    nm.set_read(base, "arisan", "puchiko", "20261114_220000_よる.md", T1)
    assert nm.load_stars(base)["puchiko"]["20261114_070000_あさ.md"] == {"by": "arisan", "at": "2026-11-14T17:20"}
    lines = nm.notice(base, "puchiko", mark=True)
    assert lines == ["（ちなみに、ありさんが、きみのノート 「あさ」、「よる」 を読んだ。「あさ」 には ★ を付けた）"]
    assert nm.notice(base, "puchiko", mark=True) == []                    # 伝えたら、もう言わない
    nm.set_read(base, "arisan", "puchiko", "20261114_070000_あさ.md", T2)   # 読み直したら、また伝える
    assert nm.notice(base, "puchiko") == ["（ちなみに、ありさんが、きみのノート 「あさ」 を読んだ）"]
    nm.set_star(base, "puchiko", "20261114_070000_あさ.md", False, "arisan")
    assert "20261114_070000_あさ.md" not in nm.load_stars(base)["puchiko"]   # 外したら消える(知らせない)


def test_old_star_format(tmp_path):
    (tmp_path / "state").mkdir()
    (tmp_path / "state" / "note_stars.json").write_text(json.dumps({"x": ["a.md"]}), encoding="utf-8")
    assert nm.load_stars(tmp_path) == {"x": {"a.md": {"by": "", "at": ""}}}
    assert nm.notice(tmp_path, "x") == []   # だれが付けたか分からない古い ★ は知らせない


def test_valid_name_and_title():
    assert nm.valid_name("20261114_070000_あさ.md") and not nm.valid_name("../x.md") and not nm.valid_name(".stars.md")
    assert nm.note_title("20261114_070000_あさ.md") == "あさ" and nm.note_title("poem_1.md") == "poem_1"


def test_pins_are_private(tmp_path):
    nm.set_pin(tmp_path, "arisan", "puchiko", "a.md", True)
    nm.set_pin(tmp_path, "arisan", "puchiko", "b.md", True)
    assert nm.load_pins(tmp_path)["arisan"]["puchiko"] == ["a.md", "b.md"]
    nm.set_pin(tmp_path, "arisan", "puchiko", "a.md", False)
    assert nm.load_pins(tmp_path)["arisan"]["puchiko"] == ["b.md"]
    assert nm.notice(tmp_path, "puchiko") == []   # ピン留めは知らせない
