"""スマホの居場所(scripts/phone_place.py)のテスト"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import phone_place as pp  # noqa: E402
import whereabouts as wa  # noqa: E402

T = datetime(2026, 11, 14, 21, 0)


def _house(tmp_path: Path) -> Path:
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "spots.json").write_text(json.dumps({"spots": [
        {"id": "a1", "room": "あり部屋", "spot": "ソファ", "devices": ["DFE455C969D7", "84F703B4BB6A"]},
        {"id": "a2", "room": "あり部屋", "spot": "机", "devices": ["DFE455C969D7"]},
        {"id": "b1", "room": "寝室", "spot": "窓際", "devices": ["70041D7E07AE"]},
    ]}), encoding="utf-8")
    pp.make_key("arisan", "ありさんのスマホ", tmp_path)
    return tmp_path


def test_key_and_macs(tmp_path):
    base = _house(tmp_path)
    key = json.loads(pp.config_path(base).read_text(encoding="utf-8"))["phones"]["arisan"]["key"]
    assert len(key) > 30 and pp.person_for_key(key, base) == "arisan"
    assert pp.person_for_key("x", base) is None and pp.person_for_key(None, base) is None
    assert pp.macs(base) == ["70041D7E07AE", "84F703B4BB6A", "DFE455C969D7"]
    assert pp.rooms_from_seen({"df:e4:55:c9:69:d7": -60, "84F703B4BB6A": -55, "70041D7E07AE": -99, "FFFFFFFFFFFF": -10}, base) == {"あり部屋": -55}


def test_report_hysteresis_and_lines(tmp_path):
    base = _house(tmp_path)
    r = pp.report("arisan", {"DFE455C969D7": -60}, base, T)
    assert r["room"] == "あり部屋" and r["since"] == T.isoformat()
    # 寝室が 3 dB だけ強くても、まだ動かない(6 dB の決まり)
    r = pp.report("arisan", {"DFE455C969D7": -60, "70041D7E07AE": -57}, base, T + timedelta(seconds=30))
    r = pp.report("arisan", {"DFE455C969D7": -60, "70041D7E07AE": -57}, base, T + timedelta(seconds=60))
    assert r["room"] == "あり部屋"
    # 寝室がはっきり強い報告が続けば(まんなかが寝室)、移る
    for i in range(3, 6):
        r = pp.report("arisan", {"DFE455C969D7": -80, "70041D7E07AE": -50}, base, T + timedelta(seconds=30 * i))
    assert r["room"] == "寝室" and r["since"] == (T + timedelta(seconds=30 * 4)).isoformat()
    label = lambda u: {"arisan": "ありさん"}.get(u, u)  # noqa: E731
    assert pp.lines(base, label, T + timedelta(seconds=160)) == ["ありさんのスマホ: 家(寝室)"]
    assert wa.lines(base, label=label, now=T + timedelta(seconds=160)) == []   # 毎回は渡さない(見に行けるもの)
    # 古くなれば、何も言わない
    assert pp.where("arisan", base, T + timedelta(seconds=150 + 300)) is None
    assert pp.lines(base, label, T + timedelta(seconds=150 + 300)) == []


def test_no_beacon_seen(tmp_path):
    base = _house(tmp_path)
    for i in range(3):
        r = pp.report("arisan", {}, base, T + timedelta(seconds=30 * i))
    assert r["room"] is None
    assert pp.lines(base, lambda u: "ありさん", T + timedelta(seconds=70)) == ["ありさんのスマホ: 家の印が見えない(お外か、印の無い部屋)"]


def test_no_config(tmp_path):
    assert pp.config(tmp_path)["phones"] == {}
    assert pp.lines(tmp_path) == []
    assert wa.lines(tmp_path, now=T) == []


def test_first_sighting_after_empty_reports_does_not_pick_a_room_by_tie(tmp_path):
    """空の報告 2 回のあとに初めて印が見えても、まんなかが -100 同士の引き分けで部屋を決めない(2026-11-14 実機)"""
    base = _house(tmp_path)
    pp.report("arisan", {}, base, T)
    pp.report("arisan", {}, base, T + timedelta(seconds=30))
    r = pp.report("arisan", {"DFE455C969D7": -44, "70041D7E07AE": -52}, base, T + timedelta(seconds=60))
    assert r["room"] is None
    r = pp.report("arisan", {"DFE455C969D7": -44, "70041D7E07AE": -52}, base, T + timedelta(seconds=90))
    assert r["room"] == "あり部屋"
    assert pp.decide(None, {"寝室": -100, "あり部屋": -100}, 6) is None


def test_change_line_only_when_moved(tmp_path):
    base = _house(tmp_path)
    for i in range(3):
        pp.report("arisan", {"DFE455C969D7": -50}, base, T + timedelta(seconds=30 * i))
    t = T + timedelta(seconds=70)
    assert pp.change_line(base, "puchiko", mark=True, now=t) == ""          # はじめては覚えるだけ
    assert pp.change_line(base, "puchiko", mark=True, now=t) == ""          # 変わっていない
    for i in range(3, 6):
        pp.report("arisan", {"70041D7E07AE": -45}, base, T + timedelta(seconds=30 * i))
    t = T + timedelta(seconds=160)
    assert pp.change_line(base, "puchiko", mark=False, now=t) == "ありさんのスマホ: あり部屋 → 寝室 に動いた"
    assert pp.change_line(base, "puchiko", mark=True, now=t) == "ありさんのスマホ: あり部屋 → 寝室 に動いた"   # mark 無しでは覚えない
    assert pp.change_line(base, "puchiko", mark=True, now=t) == ""
    assert pp.change_line(base, "puchiteya", mark=True, now=t) == ""        # 子ごとに別
    for i in range(6, 9):
        pp.report("arisan", {}, base, T + timedelta(seconds=30 * i))
    t = T + timedelta(seconds=250)
    assert pp.change_line(base, "puchiko", mark=True, now=t) == "ありさんのスマホ: 家の印が見えなくなった(お外に出たか、印の無い部屋)"
    for i in range(9, 12):
        pp.report("arisan", {"DFE455C969D7": -50}, base, T + timedelta(seconds=30 * i))
    t = T + timedelta(seconds=340)
    assert pp.change_line(base, "puchiko", mark=True, now=t) == "ありさんのスマホ: 家(あり部屋)に戻ってきた"
    # 報告が古くなったら、分からないので何も言わず、覚えも変えない
    assert pp.change_line(base, "puchiko", mark=True, now=t + timedelta(seconds=600)) == ""
