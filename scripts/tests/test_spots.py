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
