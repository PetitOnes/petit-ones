"""変わったときの一言を受け取るか(scripts/notices.py)と、空・家の空気・スマホの部屋の各部品がそれを見ること"""

import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import notices  # noqa: E402
import phone_place as pp  # noqa: E402
import room_log as rl  # noqa: E402
import sky  # noqa: E402


def _set(base: Path, cid: str, d: dict):
    p = base / "characters" / cid / "config" / "settings.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"notices": d}), encoding="utf-8")


def test_defaults_and_clean(tmp_path):
    assert notices.enabled("puchiko", tmp_path) == {k: True for k in notices.KINDS}
    _set(tmp_path, "puchiko", {"pressure": False, "unknown": False})
    e = notices.enabled("puchiko", tmp_path)
    assert e["pressure"] is False and e["temperature"] is True and "unknown" not in e
    assert notices.wants("puchiko", "pressure", tmp_path) is False and notices.wants("puchiru", "pressure", tmp_path) is True
    assert notices.clean({"sky": 0, "x": 1, "phone": "yes"}) == {"sky": False, "phone": True}
    assert notices.clean("nope") == {}


def test_room_log_respects_kinds(tmp_path):
    rd = rl.room_dir(tmp_path); rd.mkdir(parents=True)
    def snap(temp, press):
        rd.joinpath("latest.json").write_text(json.dumps({"ts": datetime.now().replace(microsecond=0).isoformat(), "devices": {"o": {"name": "机", "temperature": temp, "pressure": press}}}), encoding="utf-8")
    snap(20.0, 1015.0)
    _set(tmp_path, "puchiko", {"pressure": False})
    assert rl.change_line(tmp_path, "puchiko", mark=True) == ""
    snap(20.0, 1010.0)
    assert rl.change_line(tmp_path, "puchiko", mark=True) == ""        # 気圧は受け取らない
    snap(23.0, 1010.0)
    assert "20.0℃ → 23.0℃" in rl.change_line(tmp_path, "puchiko", mark=True) and "気圧" not in rl.change_line(tmp_path, "puchiko")


def test_sky_and_phone_respect_kinds(tmp_path):
    _set(tmp_path, "puchiko", {"sky": False, "phone": False})
    assert sky.wants_sky("puchiko", tmp_path) is False and sky.wants_sky("puchiru", tmp_path) is True and sky.wants_sky(None) is True
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "spots.json").write_text(json.dumps({"spots": [{"id": "a", "room": "あり部屋", "spot": "机", "devices": ["AA"]}, {"id": "b", "room": "寝室", "spot": "窓", "devices": ["BB"]}]}), encoding="utf-8")
    pp.make_key("arisan", "ありさんのスマホ", tmp_path)
    T = datetime(2026, 11, 14, 21, 0)
    for i in range(3):
        pp.report("arisan", {"AA": -50}, tmp_path, T + timedelta(seconds=30 * i))
    pp.change_line(tmp_path, "puchiko", mark=True, now=T + timedelta(seconds=70))
    pp.change_line(tmp_path, "puchiru", mark=True, now=T + timedelta(seconds=70))
    for i in range(3, 6):
        pp.report("arisan", {"BB": -45}, tmp_path, T + timedelta(seconds=30 * i))
    t = T + timedelta(seconds=160)
    assert pp.change_line(tmp_path, "puchiko", mark=True, now=t) == ""                                  # 受け取らない(覚えは進む)
    assert pp.change_line(tmp_path, "puchiru", mark=True, now=t) == "ありさんのスマホ: あり部屋 → 寝室 に動いた"
    assert json.loads((tmp_path / "characters" / "puchiko" / "state" / "phone_told.json").read_text())["arisan"] == "寝室"
    assert isinstance(date.today(), date)


def test_set_kind_touches_only_notices(tmp_path):
    p = tmp_path / "characters" / "puchiko" / "config" / "settings.json"
    p.parent.mkdir(parents=True)
    p.write_text(json.dumps({"max_turns": 7, "notices": {"sky": False}}), encoding="utf-8")
    now = notices.set_kind("puchiko", "pressure", False, tmp_path)
    assert now["pressure"] is False and now["sky"] is False and now["temperature"] is True
    d = json.loads(p.read_text(encoding="utf-8"))
    assert d["max_turns"] == 7 and d["notices"] == {"sky": False, "pressure": False}
    notices.set_kind("puchiko", "sky", True, tmp_path)
    assert notices.wants("puchiko", "sky", tmp_path) is True
    try:
        notices.set_kind("puchiko", "moon", True, tmp_path); raise AssertionError("知らない種類が通った")
    except ValueError:
        pass
