"""よその家のぷちの名簿(scripts/known_petits.py): 手紙が通った子だけ・薄く・経路は消えない"""

import sys
from datetime import date, datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import known_petits  # noqa: E402
import sns_notice  # noqa: E402
from test_sns_notice import _house  # noqa: E402


def _letter(i: int, frm: str, to: str, day: str) -> dict:
    names = {"puchiko": "ぷちこ", "mio": "澪", "maru": "ぷちまる"}
    return {"id": f"L{i}", "from": frm, "from_name": names[frm], "to": to, "to_name": names[to],
            "body": "ないしょの本文", "created_at": f"{day}T09:00:00Z"}


LETTERS = [_letter(1, "mio", "puchiko", "2026-11-02"), _letter(2, "puchiko", "mio", "2026-11-03"),
           _letter(3, "mio", "puchiko", "2026-11-09"), _letter(4, "puchiko", "maru", "2026-11-16")]
PENPALS = [{"petit": "mio", "name": "澪", "state": "active"}, {"petit": "maru", "name": "ぷちまる", "state": "active"},
           {"petit": "yoso", "name": "まだの子", "state": "asked"}]


def test_only_those_a_letter_passed_with_and_no_body(tmp_path):
    book = known_petits.update(tmp_path, "puchiko", "puchiko", LETTERS, PENPALS)
    assert set(book) == {"mio", "maru"}   # 申し込み中の相手は載らない
    assert book["mio"]["first"] == {"at": "2026-11-02", "via": "手紙"} and book["mio"]["name"] == "澪"
    assert "ないしょ" not in known_petits.book_path(tmp_path, "puchiko").read_text(encoding="utf-8")
    assert known_petits.waiting(book["mio"]) == "theirs" and known_petits.waiting(book["maru"]) == "mine"
    # 新しい手紙だけ見えるようになっても、はじめの日は動かない
    book = known_petits.update(tmp_path, "puchiko", "puchiko", [_letter(5, "puchiko", "mio", "2026-11-16")], PENPALS)
    assert book["mio"]["first"]["at"] == "2026-11-02" and known_petits.waiting(book["mio"]) == "mine"


def test_notes_are_one_line_overwritten_and_fade(tmp_path):
    known_petits.update(tmp_path, "puchiko", "puchiko", LETTERS, PENPALS)
    known_petits.note(tmp_path, "puchiko", "澪", is_line="低い目線が好きな子", last_line="海の写真の話", today=date(2026, 11, 16))
    known_petits.note(tmp_path, "puchiko", "mio", last_line="貝がらの話", today=date(2026, 11, 16))
    assert known_petits.hint(tmp_path, "puchiko", "mio", date(2026, 11, 20)) == "低い目線が好きな子。前は: 貝がらの話"
    assert known_petits.hint(tmp_path, "puchiko", "mio", date(2027, 1, 20)) == "低い目線が好きな子"   # 古くなったら添えない
    row = [r for r in known_petits.rows(tmp_path, "puchiko", date(2027, 1, 20)) if r["id"] == "mio"][0]
    assert row["last"] == "貝がらの話" and row["faded"] and row["first_at"] == "2026-11-02"   # 名簿には残る。経路も
    with pytest.raises(ValueError):
        known_petits.note(tmp_path, "puchiko", "shiranai", is_line="x")
    with pytest.raises(ValueError):
        known_petits.note(tmp_path, "puchiko", "mio", is_line="あ" * 81)
    assert "澪(mio): 低い目線が好きな子" in known_petits.text(tmp_path, "puchiko")


def test_notice_line_carries_the_hint(tmp_path):
    _house(tmp_path)
    unread = [dict(_letter(3, "mio", "puchiko", "2026-11-09"))]

    def f(env, cid):
        return {"letters": unread, "events": [], "recent": LETTERS, "penpals": PENPALS}
    now = datetime(2026, 11, 16, 10, 0)
    assert sns_notice.line(tmp_path, "puchiko", now=now, fetcher=f).startswith("ぷちSNS のお知らせ: 澪から手紙が 1 通")
    known_petits.note(tmp_path, "puchiko", "mio", is_line="低い目線が好きな子", today=now.date())
    assert "澪(低い目線が好きな子)から手紙が 1 通" in sns_notice.line(tmp_path, "puchiko", now=now, fetcher=f)
