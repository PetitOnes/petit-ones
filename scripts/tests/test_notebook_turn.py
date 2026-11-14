"""交換ノートの順番(scripts/notebook_turn.py)のテスト"""

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import notebook_turn as nt  # noqa: E402

NOW = datetime(2026, 11, 14, 17, 0)


def e(author, date):
    return {"author": author, "date": date, "content": "x"}


def test_empty():
    t = nt.compute([], "ありさん", NOW)
    assert t["next"] == "ぷちてゃ" and t["last"] is None and t["skippable"] and not t["my_turn"]


def test_next_and_skippable():
    t = nt.compute([e("ぷちてゃ", "2026/11/14 07:00"), e("ぷちこ", "2026/11/14 12:05")], "ありさん", NOW)
    assert t["next"] == "ぷちる" and t["last"]["author"] == "ぷちこ" and t["hours_since"] == 4.9 and not t["skippable"]
    t = nt.compute([e("ぷちる", "2026/11/13 07:10")], "ありさん", NOW)
    assert t["next"] == "ぷちてゃ" and t["skippable"]          # 20 時間すぎた
    t = nt.compute([e("puchiru", "2026/11/13 07:10"), e("--help", "2026/11/13 08:00")], "ありさん", NOW)
    assert t["next"] == "ぷちてゃ"                              # 古い id 表記は読み替え、混入は数えない


def test_my_turn_after_a_round():
    log = [e("ありさん", "2026/11/10 20:00"), e("ぷちてゃ", "2026/11/11 07:00"), e("ぷちこ", "2026/11/11 12:05")]
    t = nt.compute(log, "ありさん", NOW)
    assert not t["my_turn"] and t["wrote_since_mine"] == ["ぷちてゃ", "ぷちこ"]
    log.append(e("ぷちる", "2026/11/11 22:10"))
    t = nt.compute(log, "ありさん", NOW)
    assert t["my_turn"] and t["wrote_since_mine"] == ["ぷちてゃ", "ぷちこ", "ぷちる"]
    log.append(e("ありさん", "2026/11/12 20:00"))
    assert not nt.compute(log, "ありさん", NOW)["my_turn"]      # 書いたら消える
    assert nt.compute(log, "風早さん", NOW)["my_turn"]          # 人ごと(風早さんはまだ書いていない)
