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
    assert rl.line(tmp_path, T) == "家の空気: あり部屋 24.1℃・44%(明るさ 9)。ありさん机の動き: なし(最後は 18:05)。人感は、座ったまま動かないと更新されない(動きなし = いない、ではない)。あり部屋の電気 オフ(18:20 の読み)"
    assert rl.line(tmp_path, datetime(2026, 11, 14, 19, 0)) == ""   # 30 分より古い読みは渡さない
    assert rl.day_summary(tmp_path, "2026-11-13") == {"date": "2026-11-13", "reads": 0, "devices": {}}


def test_no_key(tmp_path, monkeypatch):
    monkeypatch.delenv("SWITCHBOT_TOKEN", raising=False)
    monkeypatch.delenv("SWITCHBOT_SECRET", raising=False)
    monkeypatch.setattr(rl, "omron_present", lambda cfg: False)   # この PC には本物の OMRON が差さっているので、無いことにする
    assert rl.read_all(tmp_path) is None and rl.record(tmp_path) is None and rl.line(tmp_path) == ""


def test_cfg_off_and_names(tmp_path):
    assert rl.load_cfg(tmp_path) == {"off": [], "names": {}, "omron": {"port": "/dev/omron-env", "name": "PC の OMRON"}}
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "room.json").write_text(json.dumps({"names": {"a": "あり部屋"}}), encoding="utf-8")
    assert rl.set_off(tmp_path, ["b", "a", "b"]) == {"off": ["a", "b"], "names": {"a": "あり部屋"}}   # omron は元のファイルに無ければ書かない
    assert rl.load_cfg(tmp_path)["off"] == ["a", "b"] and rl.load_cfg(tmp_path)["names"] == {"a": "あり部屋"}   # 言い換えは残る


def test_line_without_last_move(tmp_path):
    rows = [{"ts": "2026-11-14T18:20:00", "devices": {"m1": {"name": "ありさん机", "type": "Motion Sensor", "move": False}}}]
    rd = rl.room_dir(tmp_path); rd.mkdir(parents=True)
    (rd / "latest.json").write_text(json.dumps(rows[-1], ensure_ascii=False), encoding="utf-8")
    assert rl.line(tmp_path, T) == "家の空気: ありさん机の動き: なし(記録を始めてから、まだ動きなし)。人感は、座ったまま動かないと更新されない(動きなし = いない、ではない)(18:20 の読み)"


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


def test_latest_uses_presence_when_newer(tmp_path):
    """10 分ごとの読みが動きを見逃しても、1 分ごとの気配が覚えている最後の動きを使う"""
    rows = [{"ts": "2026-11-14T20:30:00", "devices": {"m1": {"name": "机", "type": "Motion Sensor", "move": False}}}]
    _write(tmp_path, rows)   # latest の last_move は 18:05
    (tmp_path / "state" / "presence_state.json").write_text(json.dumps({"m1": {"place": "机", "last_move": "2026-11-14T20:39:01"}}), encoding="utf-8")
    assert rl.latest(tmp_path)["last_move"]["m1"] == "2026-11-14T20:39:01"
    assert "最後は 20:39" in rl.line(tmp_path, datetime(2026, 11, 14, 20, 40))   # いまの時刻に依らないよう、時刻を決める
    # 気配のほうが古ければ、部屋の記録のまま
    (tmp_path / "state" / "presence_state.json").write_text(json.dumps({"m1": {"place": "机", "last_move": "2026-11-14T17:00:00"}}), encoding="utf-8")
    assert rl.latest(tmp_path)["last_move"]["m1"] == "2026-11-14T18:05:00"
    # 気配の記録が無くても困らない
    (tmp_path / "state" / "presence_state.json").unlink()
    assert rl.latest(tmp_path)["last_move"]["m1"] == "2026-11-14T18:05:00"


def test_omron_joins_the_record(tmp_path, monkeypatch):
    """PC に差した OMRON は、SwitchBot の鍵が無くても id omron-env の 1 台として記録に入る。まとめ・行・変化にも気圧が出る"""
    monkeypatch.delenv("SWITCHBOT_TOKEN", raising=False); monkeypatch.delenv("SWITCHBOT_SECRET", raising=False)
    monkeypatch.setattr(rl, "omron_present", lambda cfg: True)
    import omron_env
    monkeypatch.setattr(omron_env, "read", lambda port: {"temperature": 24.1, "humidity": 50.2, "light": 2, "pressure": 1015.6, "noise": 53.1, "eco2": 1349, "etvoc": 144})
    snap = rl.record(tmp_path)
    assert set(snap["devices"]) == {"omron-env"} and snap["devices"]["omron-env"]["pressure"] == 1015.6 and snap["devices"]["omron-env"]["name"] == "PC の OMRON"
    devs = rl.devices(tmp_path)
    assert devs == [{"id": "omron-env", "name": "PC の OMRON", "type": "OMRON 2JCIE-BU", "on": True}]
    day = rl.day_summary(tmp_path, snap["ts"][:10])
    assert day["devices"]["omron-env"]["pressure_min"] == 1015.6 and day["devices"]["omron-env"]["eco2_max"] == 1349
    assert "気圧 1015.6 hPa" in rl.line(tmp_path) and "CO2 1349 ppm" in rl.line(tmp_path)
    assert rl.change_line(tmp_path, "puchiko", mark=True) == ""   # はじめは覚えるだけ
    monkeypatch.setattr(omron_env, "read", lambda port: {"temperature": 24.1, "humidity": 50.2, "light": 2, "pressure": 1011.2, "noise": 53.1, "eco2": 1349, "etvoc": 144})
    rl.record(tmp_path)
    assert "気圧 1015.6 → 1011.2 hPa(下がってきた)" in rl.change_line(tmp_path, "puchiko", mark=True)
    # 切ったら入らない。名前は config の omron.name
    (tmp_path / "config").mkdir(exist_ok=True)
    (tmp_path / "config" / "room.json").write_text(json.dumps({"off": ["omron-env"], "omron": {"name": "机"}}), encoding="utf-8")
    assert rl.read_all(tmp_path) is None
    assert rl.devices(tmp_path)[0]["name"] == "机" and rl.devices(tmp_path)[0]["on"] is False


def test_omron_absent_without_key(tmp_path, monkeypatch):
    monkeypatch.delenv("SWITCHBOT_TOKEN", raising=False); monkeypatch.delenv("SWITCHBOT_SECRET", raising=False)
    monkeypatch.setattr(rl, "omron_present", lambda cfg: False)
    assert rl.read_all(tmp_path) is None and rl.devices(tmp_path) is None
