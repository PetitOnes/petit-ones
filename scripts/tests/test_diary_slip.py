"""合作日記の紙(scripts/diary_slip.py)"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
pytest.importorskip("PIL")
import diary_slip as ds  # noqa: E402

NOW = datetime(2026, 11, 17, 21, 0)


@pytest.fixture
def house(tmp_path: Path) -> Path:
    c = tmp_path / "characters" / "puchiko"
    (c / "config").mkdir(parents=True)
    (c / "config" / "config.json").write_text(json.dumps({"name": "ぷちこ", "color": "#cab8d9"}), encoding="utf-8")
    (c / "state" / "body").mkdir(parents=True)
    rows = [{"ts": f"2026-11-17T{h:02d}:{m:02d}", "amb": h * 10 + m, "tilt": 3} for h in range(0, 21) for m in (0, 5)]
    (c / "state" / "body" / "20261117.jsonl").write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    return tmp_path


def test_line_only_in_the_evening_and_until_made(house: Path) -> None:
    assert ds.line("puchiko", house, datetime(2026, 11, 17, 18, 59)) == ""
    assert "きょうの紙" in ds.line("puchiko", house, NOW)
    ok, _ = ds.make("puchiko", [("text", "ひとこと")], base=house, now=NOW)
    assert ok
    assert ds.line("puchiko", house, NOW) == ""


def test_parts_in_order_and_remake_replaces(house: Path) -> None:
    ok, msg = ds.make("puchiko", [("line", "amb"), ("text", "詩の\\n二行め")], "紫は灰色に", base=house, now=NOW)
    assert ok, msg
    slip = ds.load(house)[0]
    assert [b["kind"] for b in slip["blocks"]] == ["line", "text"]
    assert slip["blocks"][0]["points"][0] == [0, 0.0]
    assert slip["blocks"][1]["text"] == "詩の\n二行め"
    ok, _ = ds.make("puchiko", [("text", "作り直し")], base=house, now=NOW)
    assert ok and len(ds.load(house)) == 1 and ds.load(house)[0]["blocks"][0]["text"] == "作り直し"


def test_limits(house: Path) -> None:
    assert not ds.make("puchiko", [], base=house, now=NOW)[0]
    assert not ds.make("puchiko", [("text", "あ")] * 7, base=house, now=NOW)[0]
    assert not ds.make("puchiko", [("text", "あ" * 301)], base=house, now=NOW)[0]
    assert not ds.make("puchiko", [("line", "nope")], base=house, now=NOW)[0]
    assert not ds.make("puchiko", [("text", "あ")], "端" * 31, base=house, now=NOW)[0]
    assert not ds.make("puchiko", [("photo", "/etc/hostname")], base=house, now=NOW)[0]   # 家の外のファイルは載せない
    assert ds.load(house) == []


def test_drawing_and_photo_are_copied(house: Path) -> None:
    from PIL import Image
    svg = house / "characters" / "puchiko" / "e.svg"
    svg.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 50"><circle cx="25" cy="25" r="20" fill="#cab8d9"/>'
                   '<path d="M50 40 Q75 0 100 40" stroke="black" fill="none"/></svg>', encoding="utf-8")
    photo = house / "p.png"
    Image.new("RGB", (100, 60), (200, 100, 50)).save(photo)
    ok, msg = ds.make("puchiko", [("draw", str(svg)), ("photo", str(photo))], base=house, now=NOW)
    assert ok, msg
    svg.unlink()
    photo.unlink()
    img = ds.render(ds.load(house)[0], house)
    assert img.width == ds.WIDTH and img.mode == "1"
    assert "読めなかった" not in json.dumps(ds.load(house))
    assert not ds.make("puchiko", [("draw", str(house / "nothing.svg"))], base=house, now=NOW)[0]


def test_heard_sound_graph(house: Path) -> None:
    (house / "state" / "heard").mkdir(parents=True)
    (house / "state" / "heard" / "1_2.json").write_text(json.dumps({"ts": "2026-11-17T10:00:00", "shape": [{"db": -50}, {"db": -64}]}), encoding="utf-8")
    ok, msg = ds.make("puchiko", [("sound", "heard:1_2")], base=house, now=NOW)
    assert ok, msg
    assert ds.load(house)[0]["blocks"][0]["values"] == [-50.0, -64.0]
    assert not ds.make("puchiko", [("sound", "heard:../x")], base=house, now=NOW)[0]


def test_printed_slip_cannot_be_remade_and_put_away(house: Path) -> None:
    ds.make("puchiko", [("text", "あ")], base=house, now=NOW)
    sid = ds.load(house)[0]["id"]
    assert ds.mark(sid, "printed_at", house)
    assert not ds.make("puchiko", [("text", "い")], base=house, now=NOW)[0]
    assert ds.summary(ds.load(house)[0]) == {"text": "あ", "kinds": "文"}


def test_packet_shape(house: Path) -> None:
    ds.make("puchiko", [("text", "あ")], base=house, now=NOW)
    img = ds.render(ds.load(house)[0], house)
    pk = ds.packet(img)
    assert pk.startswith(b"\x1b\x40\x1d\x76\x30\x00\x30\x00")
    assert len(pk) == 2 + 8 + 48 * img.height + 6


def test_print_without_address(house: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PRINTER_ADDRESS", raising=False)
    r = ds.print_slips(["x"], house)
    assert r["done"] == [] and "PRINTER_ADDRESS" in r["error"]


def test_drawing_from_egaku(house: Path) -> None:
    from PIL import Image
    d = house / "drawings" / "made" / "puchiko"
    d.mkdir(parents=True)
    Image.new("RGB", (320, 240), (16, 16, 24)).save(d / "しずか.png")
    ok, msg = ds.make("puchiko", [("drawing", "しずか")], base=house, now=NOW)
    assert ok, msg
    assert ds.load(house)[0]["blocks"][0]["kind"] == "photo"
    assert not ds.make("puchiko", [("drawing", "../../x")], base=house, now=NOW)[0]
    assert not ds.make("puchiko", [("drawing", "ない")], base=house, now=NOW)[0]
