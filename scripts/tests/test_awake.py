import json
import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import awake  # noqa: E402
import body_switches as bs  # noqa: E402

NOON = datetime(2026, 11, 14, 12, 0)


def test_set_awake_keeps_other_settings(tmp_path):
    p = bs.settings_path("puchiteya", tmp_path)
    p.parent.mkdir(parents=True)
    p.write_text(json.dumps({"active_hours": {"weekday": [[7, 0, 8, 10]]}, "rest": {"until": "2026-11-14T12:30"}}), encoding="utf-8")
    awake.set_awake("puchiteya", 3, tmp_path, now=NOON)
    s = bs.load_settings("puchiteya", tmp_path)
    assert s["active_hours"] == {"weekday": [[7, 0, 8, 10]]} and s["rest"] == {"until": "2026-11-14T12:30"}
    assert s["awake"]["until"] == "2026-11-14T15:00"
    assert awake.view(s, NOON) == {"on": True, "until": "15:00", "until_iso": "2026-11-14T15:00"}


def test_expires_and_off(tmp_path):
    awake.set_awake("puchiko", 1, tmp_path, now=NOON)
    s = bs.load_settings("puchiko", tmp_path)
    assert awake.view(s, datetime(2026, 11, 14, 13, 0))["on"] is False   # ちょうどで終わり
    awake.set_awake("puchiko", None, tmp_path)
    assert "until" not in bs.load_settings("puchiko", tmp_path)["awake"]


def test_bad_values(tmp_path):
    with pytest.raises(ValueError):
        awake.set_awake("puchiko", 25, tmp_path)
    assert awake.view({}, NOON)["on"] is False
    assert awake.view({"awake": {"until": "xx"}}, NOON)["on"] is False
