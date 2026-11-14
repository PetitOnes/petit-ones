"""体の net(どの Wi-Fi か)と seen を state に書く(experienced.py)のテスト"""

import json
from datetime import datetime

import experienced as ex

T0 = datetime(2026, 11, 14, 12, 30, 0)
T1 = datetime(2026, 11, 14, 12, 55, 0)


def test_net_of():
    status = {"wifi": 2, "ip": "192.168.1.214", "is_sleeping": False}
    assert ex._net_of(status, "192.168.1.214") == {
        "wifi": 2, "ip": "192.168.1.214", "host": "192.168.1.214",
    }
    # 古いファーム(wifi 無し)は、つないだ先だけ
    assert ex._net_of({"is_sleeping": False}, "100.88.72.95") == {"host": "100.88.72.95"}
    assert ex._net_of(None, "x") == {}


def test_write_state_has_net_and_seen(tmp_path, monkeypatch):
    monkeypatch.setattr(ex, "DATA_DIR", tmp_path)
    ex._write_state("puchiko", "awake", T0, {"wifi": 1, "host": "h"}, T0, T1)
    st = json.loads(ex._state_path("puchiko").read_text(encoding="utf-8"))
    assert st == {
        "state": "awake", "since": "2026-11-14T12:30:00",
        "net": {"wifi": 1, "host": "h", "since": "2026-11-14T12:30:00"},
        "seen": "2026-11-14T12:55:00",
    }
    ex._write_state("puchiko", "offline", T0)   # 昔の呼び方でも壊れない
    st = json.loads(ex._state_path("puchiko").read_text(encoding="utf-8"))
    assert st == {"state": "offline", "since": "2026-11-14T12:30:00"}


def test_wifi_sample_keeps_strongest_per_name():
    from datetime import datetime

    import experienced as ex

    now = datetime(2026, 11, 14, 21, 0)
    near = {"now": {"s": "home", "r": -56},
            "list": [{"s": "bea", "r": -42}, {"s": "bea", "r": -37}, {"s": "", "r": -30},
                     {"s": "x"}]}
    want = {"ts": "2026-11-14T21:00:00", "now": -56, "marks": {"bea": -37}}
    assert ex._wifi_sample(near, now) == want
    assert ex._wifi_sample(None, now) is None and ex._wifi_sample({"list": []}, now) is None
