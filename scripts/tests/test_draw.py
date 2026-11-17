"""draw.py: えがく(数字と線 → 並べた絵 → 絵そのもの)"""
import sys
from pathlib import Path

import pytest

pytest.importorskip("PIL")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import draw  # noqa: E402

MOVING = {"seconds": 2, "fps": 4, "background": "#000000",
          "shapes": [{"type": "circle", "x": 160, "y": 120, "r": 5, "color": "#00afcc", "ring": 2, "to": {"r": 80, "alpha": 0}}]}
STILL = {"shapes": [{"type": "rect", "x": 0, "y": 0, "w": 320, "h": 240, "color": "#cab8d9", "gradient": "#9c7ab8"},
                    {"type": "circle", "x": 160, "y": 120, "r": 40, "color": "#fff262", "blur": 8, "alpha": 0.7}]}


def _house(tmp_path):
    for c in ("ru", "ko"):
        (tmp_path / "characters" / c).mkdir(parents=True)
    return tmp_path


def test_moving_makes_gif_sheet_and_numbers(tmp_path):
    base = _house(tmp_path)
    info = draw.make(base, "ru", "hamon", MOVING)
    d = draw.made_dir(base, "ru")
    assert (d / "hamon.gif").exists() and (d / "hamon_sheet.png").exists() and (d / "hamon.png").exists()
    assert info["numbers"]["frames"] == 8 and max(info["numbers"]["motion"]) > 0
    text = draw.numbers_text(info)
    assert "動き:" in text and "#00afcc → " in text and not info["shown"]


def test_still_and_lacks(tmp_path):
    info = draw.make(_house(tmp_path), "ko", "still", STILL)
    assert info["numbers"]["frames"] == 1
    notes = {x["hex"]: x["note"] for x in info["lacks"]}
    assert "灰色" in notes["#cab8d9"] and notes["#fff262"] == ""
    assert info["banding"] and "段" in info["banding"][0]


def test_565():
    assert draw.to565((0xca, 0xb8, 0xd9)) == (0xce, 0xba, 0xde)


def test_only_own_or_given(tmp_path):
    base = _house(tmp_path)
    draw.make(base, "ru", "hamon", MOVING)
    with pytest.raises(draw.DrawError):
        draw.file_of(base, "ko", "ru", "hamon", "see")
    draw.give(base, "ru", "hamon", "ko", "雨の日")
    assert draw.file_of(base, "ko", "ru", "hamon", "sheet").name == "hamon_sheet.png"
    assert "雨の日" in draw.notice(base, "ko", mark=True)[0]
    assert draw.notice(base, "ko") == []


def test_guess_felt_show_keep_on_redraw(tmp_path):
    base = _house(tmp_path)
    draw.make(base, "ru", "hamon", MOVING)
    draw.add_note(base, "ru", "hamon", "guess", "広がって消える")
    draw.set_flag(base, "ru", "hamon", shown=True)
    info = draw.make(base, "ru", "hamon", MOVING)
    assert info["guess"][0]["text"] == "広がって消える" and info["shown"]


def test_bad_recipe_messages():
    with pytest.raises(draw.DrawError, match="shapes"):
        draw.check({"shapes": []})
    with pytest.raises(draw.DrawError, match="#rrggbb"):
        draw.check({"shapes": [{"type": "dot", "color": "blue"}]})
