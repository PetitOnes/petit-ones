"""部屋の記録(scripts/room_log.py)のテスト(SwitchBot には行かない)"""

import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import room_log as rl  # noqa: E402

T = datetime(2026, 11, 14, 18, 30)


def test_pick():
    assert rl.pick({"temperature": 23.9, "lightLevel": 11, "humidity": 43, "deviceType": "Hub 2", "version": "x"}) == {"temperature": 23.9, "humidity": 43, "light": 11}
    assert rl.pick({"battery": 100, "moveDetected": False, "brightness": "bright"}) == {"move": False, "light_word": "bright"}
    assert rl.pick({"power": "on", "brightness": 99, "color": "0:0:0"}) == {"power": "on", "brightness": 99}


def _write(base: Path, rows):
    rd = rl.room_dir(base)
    rd.mkdir(parents=True)
    (rd / "20261114.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    (rd / "latest.json").write_text(json.dumps({**rows[-1], "last_move": {"m1": "2026-11-14T18:05:00"}}, ensure_ascii=False), encoding="utf-8")


def test_summary_and_line(tmp_path):
    rows = [
        {"ts": "2026-11-14T18:00:00", "devices": {"h2": {"name": "あり部屋", "type": "Hub 2", "temperature": 23.0, "humidity": 40, "light": 11},
                                                  "m1": {"name": "ありさん机", "type": "Motion Sensor", "move": True}, "b1": {"name": "あり部屋の電気", "type": "Color Bulb", "power": "on"}}},
        {"ts": "2026-11-14T18:20:00", "devices": {"h2": {"name": "あり部屋", "type": "Hub 2", "temperature": 24.1, "humidity": 44, "light": 9},
                                                  "m1": {"name": "ありさん机", "type": "Motion Sensor", "move": False}, "b1": {"name": "あり部屋の電気", "type": "Color Bulb", "power": "off"}}},
    ]
    _write(tmp_path, rows)
    s = rl.day_summary(tmp_path, "2026-11-14")
    assert s["reads"] == 2 and s["devices"]["h2"]["temperature_min"] == 23.0 and s["devices"]["h2"]["temperature_max"] == 24.1
    assert s["devices"]["m1"]["moves"] == 1 and s["devices"]["b1"]["on"] == 1
    assert rl.line(tmp_path, T) == "家の空気: あり部屋 24.1℃・44%(明るさ 9)。ありさん机の動き: なし(最後は 18:05)。あり部屋の電気 オフ(18:20 の読み)"
    assert rl.line(tmp_path, datetime(2026, 11, 14, 19, 0)) == ""   # 30 分より古い読みは渡さない
    assert rl.day_summary(tmp_path, "2026-11-13") == {"date": "2026-11-13", "reads": 0, "devices": {}}


def test_no_key(tmp_path, monkeypatch):
    monkeypatch.delenv("SWITCHBOT_TOKEN", raising=False)
    monkeypatch.delenv("SWITCHBOT_SECRET", raising=False)
    assert rl.read_all(tmp_path) is None and rl.record(tmp_path) is None and rl.line(tmp_path) == ""


def test_cfg_off_and_names(tmp_path):
    assert rl.load_cfg(tmp_path) == {"off": [], "names": {}}
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "room.json").write_text(json.dumps({"names": {"a": "あり部屋"}}), encoding="utf-8")
    assert rl.set_off(tmp_path, ["b", "a", "b"]) == {"off": ["a", "b"], "names": {"a": "あり部屋"}}
    assert rl.load_cfg(tmp_path)["off"] == ["a", "b"] and rl.load_cfg(tmp_path)["names"] == {"a": "あり部屋"}   # 言い換えは残る


def test_line_without_last_move(tmp_path):
    rows = [{"ts": "2026-11-14T18:20:00", "devices": {"m1": {"name": "ありさん机", "type": "Motion Sensor", "move": False}}}]
    rd = rl.room_dir(tmp_path); rd.mkdir(parents=True)
    (rd / "latest.json").write_text(json.dumps(rows[-1], ensure_ascii=False), encoding="utf-8")
    assert rl.line(tmp_path, T) == "家の空気: ありさん机の動き: なし(記録を始めてから、まだ動きなし)(18:20 の読み)"


def test_change_line(tmp_path):
    rd = rl.room_dir(tmp_path); rd.mkdir(parents=True)
    def snap(temp, hum, ts="2026-11-14T18:20:00"):
        (rd / "latest.json").write_text(json.dumps({"ts": ts, "devices": {"h2": {"name": "あり部屋", "type": "Hub 2", "temperature": temp, "humidity": hum}}}), encoding="utf-8")
    snap(23.9, 43)
    assert rl.change_line(tmp_path, "puchiko", mark=True, now=T) == ""          # はじめては覚えるだけ
    snap(24.5, 45)
    assert rl.change_line(tmp_path, "puchiko", mark=True, now=T) == ""          # 小さな動きは言わない
    snap(21.0, 46)
    assert rl.change_line(tmp_path, "puchiko", mark=True, now=T) == "家の空気が変わった: あり部屋 23.9℃ → 21.0℃(18:20 の読み)"
    assert rl.change_line(tmp_path, "puchiko", mark=True, now=T) == ""          # 伝えたら、次は言わない
    snap(21.5, 58)
    assert rl.change_line(tmp_path, "puchiru", now=T) == ""                     # 別の子は、まだ覚えていない(mark 無しでは覚えもしない)
    assert rl.change_line(tmp_path, "puchiko", now=T) == "家の空気が変わった: あり部屋 湿度 46% → 58%(18:20 の読み)"
    assert rl.change_line(tmp_path, "puchiko", now=datetime(2026, 11, 14, 19, 30)) == ""   # 古い読みでは言わない


def test_line_with_my_room(tmp_path):
    import spots as sp
    rows = [{"ts": "2026-11-14T18:20:00", "devices": {"h2": {"name": "あり部屋のハブ２", "type": "Hub 2", "temperature": 23.9, "humidity": 43},
                                                      "e3": {"name": "寝室の温湿度計", "type": "Meter", "temperature": 20.0, "humidity": 50}}}]
    rd = rl.room_dir(tmp_path); rd.mkdir(parents=True)
    (rd / "latest.json").write_text(json.dumps(rows[-1], ensure_ascii=False), encoding="utf-8")
    items = sp.save([{"room": "寝室", "spot": "窓際", "devices": ["e3"]}], tmp_path)
    sp.set_body_spot(tmp_path, "puchiru", items[0]["id"])
    assert rl.line(tmp_path, T, "puchiru") == "家の空気(いる部屋は 寝室): 寝室の温湿度計(いる部屋) 20.0℃・50%、あり部屋のハブ２ 23.9℃・43%(18:20 の読み)"
    assert rl.line(tmp_path, T, "puchiko").startswith("家の空気: あり部屋のハブ２ 23.9℃")   # 場所を決めていない子は、いつもの順
