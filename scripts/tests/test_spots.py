"""家の中の場所(scripts/spots.py)のテスト"""

import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import spots as sp  # noqa: E402


def test_save_load_and_body(tmp_path):
    items = sp.save([{"room": "あり部屋", "spot": "ソファ", "devices": ["H2"]}, {"room": "あり部屋", "spot": "机", "devices": ["M1"]}, {"room": "寝室", "spot": "窓際"}], tmp_path)
    assert [sp.label(s) for s in items] == ["あり部屋:ソファ", "あり部屋:机", "寝室:窓際"]
    assert sp.room_devices(tmp_path, "あり部屋") == ["H2", "M1"] and sp.room_devices(tmp_path, "リビング") == []
    assert sp.body_spot(tmp_path, "puchiko") is None
    sp.set_body_spot(tmp_path, "puchiko", items[0]["id"], "arisan", datetime(2026, 11, 14, 19, 0))
    b = sp.body_spot(tmp_path, "puchiko")
    assert b["label"] == "あり部屋:ソファ" and b["since"] == "2026-11-14T19:00:00" and b["devices"] == ["H2"]
    sp.set_body_spot(tmp_path, "puchiko", None)
    assert sp.body_spot(tmp_path, "puchiko") is None
    with pytest.raises(ValueError):
        sp.set_body_spot(tmp_path, "puchiko", "nope")
    with pytest.raises(ValueError):
        sp.clean({"room": "", "spot": "x"})


def _near(tmp_path, cid, rows):
    import json
    d = tmp_path / "characters" / cid / "state"
    d.mkdir(parents=True, exist_ok=True)
    (d / "wifi_near.json").write_text(json.dumps({"samples": [{"ts": ts, "now": now, "marks": {"bea": bea}} for ts, now, bea in rows]}), encoding="utf-8")


def test_guess_and_effective(tmp_path):
    import json
    now = datetime(2026, 11, 14, 21, 0)
    sofa, desk, bed = sp.save([{"room": "あり部屋", "spot": "ソファ"}, {"room": "あり部屋", "spot": "机"}, {"room": "寝室", "spot": "窓際"}], tmp_path)
    assert sp.guess(tmp_path, "t", now) == (False, None) and sp.effective(tmp_path, "t", now) is None   # 決まりが無い
    (tmp_path / "config" / "spot_guess.json").write_text(json.dumps({"t": {"ch": 13, "rules": [
        {"spot_id": sofa["id"], "min": {"now": -38}},
        {"spot_id": desk["id"], "min": {"bea": -41}, "max": {"now": -50}}]}}), encoding="utf-8")
    assert sp.guess(tmp_path, "t", now) == (False, None)   # 記録が無い
    _near(tmp_path, "t", [("2026-11-14T20:58:00", -56, -42), ("2026-11-14T20:59:00", -55, -37), ("2026-11-14T20:59:30", -57, -32)])
    assert sp.guess(tmp_path, "t", now) == (True, desk["id"])   # まんなか(-37)で決まる
    e = sp.effective(tmp_path, "t", now)
    assert e["label"] == "あり部屋:机" and e["guess"] is True
    assert sp.guess(tmp_path, "t", datetime(2026, 11, 14, 21, 30)) == (False, None)   # 古い記録は使わない
    # 人が同じ場所を押せば「かも」が取れる。違う場所を押せば、見立てが変わらないあいだは押した場所
    sp.set_body_spot(tmp_path, "t", desk["id"], "a", now)
    assert sp.effective(tmp_path, "t", now)["guess"] is False
    sp.set_body_spot(tmp_path, "t", bed["id"], "a", now)
    e = sp.effective(tmp_path, "t", now)
    assert e["label"] == "寝室:窓際" and e["guess"] is False
    # ソファへ動いた → ソファかも(押した寝室より、変わった見立てが先)
    _near(tmp_path, "t", [("2026-11-14T20:59:00", -35, -45), ("2026-11-14T20:59:30", -33, -46)])
    e = sp.effective(tmp_path, "t", now)
    assert e["label"] == "あり部屋:ソファ" and e["guess"] is True
    # 机と押したあと、どの決まりにも合わない所へ動いた → 分からない。寝室と押していたなら、そのまま
    _near(tmp_path, "t", [("2026-11-14T20:59:00", -56, -37), ("2026-11-14T20:59:30", -56, -37)])
    sp.set_body_spot(tmp_path, "t", desk["id"], "a", now)
    _near(tmp_path, "t", [("2026-11-14T20:59:00", -47, -47), ("2026-11-14T20:59:30", -47, -47)])
    assert sp.guess(tmp_path, "t", now) == (True, None) and sp.effective(tmp_path, "t", now) is None
    sp.set_body_spot(tmp_path, "t", bed["id"], "a", now)
    assert sp.effective(tmp_path, "t", now)["label"] == "寝室:窓際"


def test_change_line_only_when_place_changes(tmp_path):
    now = datetime(2026, 11, 14, 22, 0)
    sofa, desk = sp.save([{"room": "あり部屋", "spot": "ソファ"}, {"room": "あり部屋", "spot": "机"}], tmp_path)
    told = tmp_path / "characters" / "t" / "state" / "spot_told.json"
    sp.set_body_spot(tmp_path, "t", sofa["id"], "a", now)
    assert sp.change_line(tmp_path, "t", now=now) == "" and not told.exists()     # mark なしでは覚えない
    assert sp.change_line(tmp_path, "t", mark=True, now=now) == "" and told.exists()   # はじめての回は、覚えるだけ
    assert sp.change_line(tmp_path, "t", mark=True, now=now) == ""                 # 変わっていなければ言わない
    sp.set_body_spot(tmp_path, "t", desk["id"], "a", now)
    assert sp.change_line(tmp_path, "t", mark=True, now=now) == "あなたの体の場所が変わった: あり部屋:ソファ → あり部屋:机"
    assert sp.change_line(tmp_path, "t", mark=True, now=now) == ""                 # 伝えたら、もう言わない
    sp.set_body_spot(tmp_path, "t", None)
    assert sp.change_line(tmp_path, "t", mark=True, now=now) == "あなたの体の場所は、いまは分からない(前は あり部屋:机)"
    # 電波からの見立てで決まったときは「かも」と、その意味を添える。同じ場所を人が選び直しても(かも が取れても)言わない
    import json
    (tmp_path / "config" / "spot_guess.json").write_text(json.dumps({"t": {"rules": [{"spot_id": sofa["id"], "min": {"now": -38}}]}}), encoding="utf-8")
    _near(tmp_path, "t", [("2026-11-14T21:59:00", -35, -45), ("2026-11-14T21:59:30", -33, -46)])
    assert sp.change_line(tmp_path, "t", mark=True, now=now) == "あなたの体の場所: あり部屋:ソファかも(「かも」は、体のまわりの電波からの見立て。外れることがある)"
    sp.set_body_spot(tmp_path, "t", sofa["id"], "a", now)
    assert sp.change_line(tmp_path, "t", mark=True, now=now) == ""


def test_guess_ignores_missed_scans(tmp_path):
    """体が目印を聞きのがした回(値なし)があっても、聞こえた回だけで見立てる"""
    import json
    now = datetime(2026, 11, 14, 21, 52)
    (desk,) = sp.save([{"room": "あり部屋", "spot": "机"}], tmp_path)
    (tmp_path / "config" / "spot_guess.json").write_text(json.dumps({"t": {"rules": [{"spot_id": desk["id"], "min": {"bea": -41}, "max": {"now": -50}}]}}), encoding="utf-8")
    d = tmp_path / "characters" / "t" / "state"
    d.mkdir(parents=True)
    rows = [("21:47:16", -55, -30), ("21:48:17", -55, -32), ("21:49:18", -54, None), ("21:50:18", -55, None), ("21:51:19", -54, -31)]
    samples = [{"ts": f"2026-11-14T{t}", "now": n, "marks": {} if b is None else {"bea": b}} for t, n, b in rows]
    (d / "wifi_near.json").write_text(json.dumps({"samples": samples}), encoding="utf-8")
    assert sp.guess(tmp_path, "t", now) == (True, desk["id"])
    # 1 回しか聞こえていなければ、聞こえなかったことにする
    (d / "wifi_near.json").write_text(json.dumps({"samples": [{**x, "marks": {}} for x in samples[:4]] + samples[4:]}), encoding="utf-8")
    assert sp.guess(tmp_path, "t", now) == (True, None)
