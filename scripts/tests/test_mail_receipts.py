"""手紙が届いたことの知らせ(scripts/mail_receipts.py)のテスト"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import mail_receipts as mr

A = "from_puchi_to_arisan_20261113_0705.md"
B = "from_puchi_to_arisan_20261113_1205.md"
C = "from_puchi_to_other_20261113_1300.md"       # ぷち同士の手紙
D = "from_other_to_arisan_20261113_1400.md"      # ほかの子が書いた手紙


def house(tmp_path: Path, mails: dict) -> Path:
    for pid in ("puchi", "other"):
        (tmp_path / "characters" / pid / "config").mkdir(parents=True, exist_ok=True)
        (tmp_path / "characters" / pid / "config" / "config.json").write_text("{}", encoding="utf-8")
    (tmp_path / "config").mkdir(exist_ok=True)
    (tmp_path / "config" / "people.json").write_text(json.dumps({"arisan": {"name": "ありさん"}}), encoding="utf-8")
    (tmp_path / "mailbox").mkdir(exist_ok=True)
    (tmp_path / "mailbox" / ".metadata.json").write_text(json.dumps({"version": 1, "mails": mails}), encoding="utf-8")
    return tmp_path


def test_first_time_says_nothing_and_sets_baseline(tmp_path):
    """はじめての回は、昔の手紙をまとめて数えない"""
    base = house(tmp_path, {A: {"read_by": ["arisan"]}})
    assert mr.notice(base, "puchi", mark=True) == []
    assert mr.notice(base, "puchi", mark=True) == []


def test_read_and_stamp_are_told_once(tmp_path):
    base = house(tmp_path, {A: {"read_by": []}, B: {"read_by": []}, C: {"read_by": ["other"]}, D: {"read_by": ["arisan"]}})
    assert mr.notice(base, "puchi", mark=True) == []                      # 基準を作る
    house(tmp_path, {A: {"read_by": ["arisan"], "stamps": {"arisan": "💛"}}, B: {"read_by": ["arisan"]},
                     C: {"read_by": ["other"]}, D: {"read_by": ["arisan"], "stamps": {"arisan": "✨"}}})
    line = "（ちなみに、ありさんが、きみの手紙を 2 通読んだ。スタンプも付いていた: 11/13 07:05 の手紙に きみの色のハート）"
    assert mr.notice(base, "puchi") == [line]                              # --mark なしでは、残さない
    assert mr.notice(base, "puchi", mark=True) == [line]
    assert mr.notice(base, "puchi", mark=True) == []                      # 2 回目は言わない


def test_stamp_added_later_and_changed(tmp_path):
    base = house(tmp_path, {A: {"read_by": ["arisan"]}})
    mr.notice(base, "puchi", mark=True)
    house(tmp_path, {A: {"read_by": ["arisan"], "stamps": {"arisan": "🥹"}}})
    assert mr.notice(base, "puchi", mark=True) == ["（ちなみに、ありさんが、きみの手紙にスタンプを付けた: 11/13 07:05 の手紙に 🥹）"]
    house(tmp_path, {A: {"read_by": ["arisan"], "stamps": {"arisan": "x"}}})   # 決めた 5 つ以外は数えない
    assert mr.notice(base, "puchi", mark=True) == []


def test_only_read(tmp_path):
    base = house(tmp_path, {A: {"read_by": []}})
    mr.notice(base, "puchi", mark=True)
    house(tmp_path, {A: {"read_by": ["arisan"]}})
    assert mr.notice(base, "puchi", mark=True) == ["（ちなみに、ありさんが、きみの手紙を 1 通読んだ）"]
