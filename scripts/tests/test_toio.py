"""toio.py: 番人に頼む前の確かめと、走ったあとの数字と線"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import toio

MAT = toio.DEFAULT_MAT


def test_points_and_speeds():
    assert toio.check_point({}, 200, 250) == (200, 250)
    assert toio.check_point({}, MAT["x0"] - 30, 250)   # 端を確かめるために、少しは外へ出られる
    with pytest.raises(toio.ToioError):
        toio.check_point({}, 900, 250)
    with pytest.raises(toio.ToioError):
        toio.check_path({}, [[200, 200]] * (toio.MAX_POINTS + 1))
    with pytest.raises(toio.ToioError):
        toio.check_path({}, "200,200")
    assert toio.clamp_speed(500) == 115 and toio.clamp_speed(1) == 10
    assert toio.clamp_wheel(-300) == -115 and toio.clamp_wheel(5) == 0
    assert toio.mat_of({"mat": {"x1": 500}})["x1"] == 500


def test_led_makes_pale_colors_visible():
    r, g, b = toio.led("#cab8d9")   # ラベンダーは、そのままだと白に見える
    assert max(r, g, b) - min(r, g, b) > 150
    assert toio.led("#ffffff") == (255, 255, 255)
    with pytest.raises(toio.ToioError):
        toio.rgb("purple")


def test_thin_keeps_ends():
    tr = [[i * 0.1, 200 + (i // 5), 250, 0] for i in range(100)]
    out = toio.thin(tr)
    assert out[0] == tr[0] and out[-1] == tr[-1] and len(out) < len(tr)


def test_summary_and_map(tmp_path):
    run = {"at": "2026-11-18T13:26:02", "who": "a", "by": "a", "result": "マットの外で場所を失った", "seconds": 1.9,
           "trail": [[0, 183, 211, 118], [1.0, 190, 180, 90], [1.6, 193, 151, 87]],
           "events": [{"t": 1.69, "kind": "lost", "x": 193, "y": 151}]}
    text = toio.summarize(run, MAT)
    assert "自分で" in text and "場所を失った (193, 151)" in text and "×" in text and "S" in text
    toio.save_run(tmp_path, run)
    toio.save_run(tmp_path, {**run, "by": "b"})
    assert len(toio.runs(tmp_path, "a", n=5)) == 2 and toio.runs(tmp_path, "a", by="b")[0]["by"] == "b"


def test_marks():
    assert toio.marks_of(["puchiteya", "puchiko", "puchiru"]) == {"puchiteya": "t", "puchiko": "k", "puchiru": "r"}
    assert len(set(toio.marks_of(["aa1", "aa1x"]).values())) == 2
