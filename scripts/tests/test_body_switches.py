"""からだの使い方・からだ おやすみ(scripts/body_switches.py)のテスト"""

import json
import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import body_switches as bs  # noqa: E402

NOON = datetime(2026, 11, 14, 12, 0)


def test_legacy_and_defaults():
    assert bs.base_switches({}) == {"see": True, "speak": True, "sound": True, "hear": False}
    assert bs.base_switches({"allow_camera": False, "allow_microphone": True}) == {"see": False, "speak": True, "sound": True, "hear": True}
    assert bs.base_switches({"allow_camera": False, "body": {"see": True, "speak": False}})["see"] is True   # body が勝つ
    assert bs.base_switches({"body": {"speak": False}})["speak"] is False


def test_rest_until_and_hours():
    s = {"rest": {"until": "2026-11-14T12:30"}}
    r = bs.rest_state(s, NOON)
    assert r and r["why"] == "いまから" and r["until"] == datetime(2026, 11, 14, 12, 30)
    assert bs.rest_state(s, datetime(2026, 11, 14, 12, 30)) is None                 # 過ぎたら終わり
    s = {"rest": {"hours": [[23, 0, 7, 0]]}}
    assert bs.rest_state(s, NOON) is None
    assert bs.rest_state(s, datetime(2026, 11, 14, 23, 30))["until"] == datetime(2026, 11, 15, 7, 0)   # 日をまたぐ前半
    assert bs.rest_state(s, datetime(2026, 11, 15, 6, 59))["until"] == datetime(2026, 11, 15, 7, 0)    # 後半
    assert bs.rest_state({"rest": {"hours": [[13, 0, 15, 0]]}}, datetime(2026, 11, 14, 14, 0))["until"] == datetime(2026, 11, 14, 15, 0)


def test_effective_disallowed_and_rules():
    eff = bs.effective({"body": {"hear": True}, "rest": {"until": "2026-11-14T15:30"}}, NOON)
    assert eff["switches"] == {"see": False, "speak": False, "sound": False, "hear": True}   # おやすみ中は 聞く だけ残る
    assert bs.disallowed_tools(eff["switches"]) == ["mcp__m5-mcp__take_snapshot", "mcp__m5-mcp__speak", "mcp__m5-mcp__play_sound", "mcp__m5-mcp__play_icon"]
    v = bs.template_vars(eff)
    assert v["rest_note"].startswith("いまは からだ おやすみ(15:30 まで。いまから): カメラ・声・効果音は使わない。")
    eff2 = bs.effective({}, NOON)
    assert bs.disallowed_tools(eff2["switches"]) == ["mcp__m5-mcp__mic_start", "mcp__m5-mcp__mic_stop"]   # 既定はマイクだけ止まる
    assert bs.template_vars(eff2)["rest_note"] == ""


def test_set_rest_keeps_other_settings(tmp_path):
    p = bs.settings_path("puchiko", tmp_path)
    p.parent.mkdir(parents=True)
    p.write_text(json.dumps({"allow_camera": False, "rest": {"hours": [[23, 0, 7, 0]]}}), encoding="utf-8")
    bs.set_rest("puchiko", 30, tmp_path, now=NOON)
    s = bs.load_settings("puchiko", tmp_path)
    assert s["allow_camera"] is False and s["rest"]["hours"] == [[23, 0, 7, 0]] and s["rest"]["until"] == "2026-11-14T12:30"
    assert bs.view(s, NOON)["rest"] == {"on": True, "why": "いまから", "until": "12:30", "until_iso": "2026-11-14T12:30", "hours": [[23, 0, 7, 0]]}
    bs.set_rest("puchiko", None, tmp_path)
    assert "until" not in bs.load_settings("puchiko", tmp_path)["rest"]
    with pytest.raises(ValueError):
        bs.set_rest("puchiko", 24 * 60 + 1, tmp_path)
