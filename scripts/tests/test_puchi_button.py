"""ぷちボタン(scripts/puchi_button.py)"""

import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import puchi_button as pb  # noqa: E402

NOON = datetime(2026, 11, 18, 12, 0)
PLACE = {"town": "a1b2c3", "near": "0badf0", "here": "123456"}


def test_pair_then_key(tmp_path):
    code = pb.make_pair_code(tmp_path, NOON, owner="arisan", owner_name="ありさん")["code"]
    assert pb.redeem_pair("000000" if code != "000000" else "111111", tmp_path, NOON) is None
    key = pb.redeem_pair(code, tmp_path, NOON)
    assert key and pb.key_ok(key, tmp_path)
    assert pb.redeem_pair(code, tmp_path, NOON) is None   # 1 回で消える
    code2 = pb.make_pair_code(tmp_path, NOON)["code"]
    assert pb.redeem_pair(code2, tmp_path, NOON + timedelta(minutes=11)) is None   # 10 分まで


def test_receive_dedupe_and_line(tmp_path):
    pb.save_config({"owner_name": "ありさん"}, tmp_path)
    rep = {"boot": "b1", "fix": True, "presses": [
        {"seq": 1, "ago_s": 3600, "kind": "leave", "env": {"temp": 18.24, "humid": 61, "pressure": 1008.3}, "place": PLACE, "sats": 6},
        {"seq": 2, "ago_s": 5, "kind": "tell", "env": {"temp": 999}, "place": {"town": "a1b2c3", "near": "zzzz", "here": "876543"}}]}
    assert pb.receive(rep, tmp_path, NOON) == {"ok": [1, 2], "new": 2, "tells": ["b1:2"]}
    assert pb.receive(rep, tmp_path, NOON)["new"] == 0           # 送り直しは 2 度入れない
    s = pb.line("puchiru", tmp_path)
    assert "2 回" in s and "11:00 ありさんがぷちボタンを押した(おいておく)" in s and "あとから届いた" in s
    assert "18.2℃ 61% 1008.3hPa" in s and "まち a1b2c3(はじめて)" in s
    assert "知らせる" in s and "まち a1b2c3(前にも)" in s and "その場 876543(はじめて)" in s
    assert "999" not in s and "zzzz" not in s                    # おかしい値は捨てる
    assert pb.line("puchiru", tmp_path, mark=True) and pb.line("puchiru", tmp_path) == ""
    assert pb.line("puchiko", tmp_path)                          # ほかの子にはまだ


def test_no_place(tmp_path):
    pb.receive({"boot": "b2", "presses": [{"seq": 1, "kind": "leave"}]}, tmp_path, NOON)
    assert "場所の印なし" in pb.line("puchiteya", tmp_path)
    assert pb.line("puchiteya", tmp_path).count("(") >= 1


def test_epoch_and_unknown(tmp_path):
    ep = int(datetime(2026, 11, 18, 9, 30).timestamp())
    pb.receive({"boot": "d", "presses": [{"seq": 1, "epoch": ep}, {"seq": 2, "unknown": True}, {"seq": 3, "epoch": ep + 86400 * 400}]}, tmp_path, NOON)
    s = pb.line("puchiko", tmp_path)
    assert "09:30 家の人がぷちボタンを押した" in s and "あとから届いた" in s
    assert "押した時刻はわからない。11/18 12:00 に届いた" in s


def test_tell_now_then_not_in_line(tmp_path):
    res = pb.receive({"boot": "e", "presses": [{"seq": 1, "kind": "tell", "ago_s": 3, "place": PLACE},
                                                {"seq": 2, "kind": "tell", "ago_s": 3600}]}, tmp_path, NOON)
    assert res["tells"] == ["e:1"]                     # 外でためた分は、その場で起こさない
    t = pb.press_text("e:1", tmp_path)
    assert t.startswith("11/18 11:59") and "まち a1b2c3(はじめて)" in t and "ぷちボタン" not in t
    pb.mark_told("puchiko", res["tells"], tmp_path)
    s = pb.line("puchiko", tmp_path)
    assert "1 回" in s and "あとから届いた" in s


def _ble(key, seq=7, kind=1, age=4, place=True):
    import hashlib
    import hmac
    b = bytes([0xB0 | kind | 2 | (4 if place else 0), 0x4b, 0x00, seq >> 8, seq & 255, age >> 8, age & 255])
    b += (1825).to_bytes(2, "big") + bytes([61]) + (10083).to_bytes(2, "big") + (1234).to_bytes(2, "big")
    b += bytes.fromhex("a1b2c30badf0123456") if place else bytes(9)
    return (b + hmac.new(key.encode(), b, hashlib.sha256).digest()[:4]).hex()


def test_ble(tmp_path):
    key = pb.make_key(tmp_path)
    rep = pb.from_ble(_ble(key), tmp_path)
    assert rep["boot"] == "4b00" and rep["presses"][0] == {"seq": 7, "kind": "tell", "ago_s": 4,
        "env": {"temp": 18.25, "humid": 61, "pressure": 1008.3, "gas": 12340}, "place": PLACE}
    assert pb.from_ble(_ble("wrong"), tmp_path) is None and pb.from_ble("zz", tmp_path) is None
    assert pb.receive(rep, tmp_path, NOON, via="ble")["tells"] == ["4b00:7"]
    assert pb.status(tmp_path).get("ble_at") and not pb.status(tmp_path).get("at")
    # あとで Wi-Fi からも同じ押し → 1 回
    assert pb.receive({"boot": "4b00", "presses": [{"seq": 7, "kind": "tell"}]}, tmp_path, NOON)["new"] == 0
    assert "unknown" in pb.from_ble(_ble(key, age=65535, place=False), tmp_path)["presses"][0]
