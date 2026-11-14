"""いま どこ(scripts/whereabouts.py)のテスト"""

import json
import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import whereabouts as wa  # noqa: E402

NOW = datetime(2026, 11, 14, 12, 55)
LABEL = {"arisan": "ありさん", "kazahaya": "風早さん"}.get


def test_set_lines_and_recent(tmp_path):
    assert wa.people_lines(wa.load(tmp_path)) == []                    # 何も決めていなければ何も出ない
    wa.set_status("arisan", "会社", tmp_path, now=datetime(2026, 11, 14, 9, 2))
    assert wa.people_lines(wa.load(tmp_path), LABEL, NOW) == ["ありさんのいま: 会社(9:02 から)"]
    wa.set_status("arisan", " お外 ", tmp_path, now=datetime(2026, 11, 13, 20, 0))
    assert wa.people_lines(wa.load(tmp_path), LABEL, NOW) == ["ありさんのいま: お外(きのう 20:00 から)"]
    assert wa.choices(wa.load(tmp_path)) == ["自室", "お外", "会社"]   # はじめの候補と重なる言葉は増えない
    wa.set_status("arisan", "図書館", tmp_path, now=datetime(2026, 11, 10, 8, 0))
    assert wa.choices(wa.load(tmp_path)) == ["自室", "お外", "会社", "図書館"]
    assert wa.people_lines(wa.load(tmp_path), LABEL, NOW) == ["ありさんのいま: 図書館(11/10 から)"]


def test_clear_and_two_people(tmp_path):
    wa.set_status("arisan", "自室", tmp_path, now=NOW)
    wa.set_status("kazahaya", "会社", tmp_path, now=NOW)
    assert len(wa.people_lines(wa.load(tmp_path), now=NOW)) == 2
    wa.set_status("arisan", "", tmp_path)
    assert wa.people_lines(wa.load(tmp_path), now=NOW) == ["kazahayaのいま: 会社(12:55 から)"]


def test_too_long(tmp_path):
    with pytest.raises(ValueError):
        wa.set_status("arisan", "あ" * 31, tmp_path)


def test_broken_file(tmp_path):
    p = wa.path(tmp_path)
    p.parent.mkdir(parents=True)
    p.write_text("{broken", encoding="utf-8")
    assert wa.load(tmp_path) == {"users": {}, "recent": []}


def _char(base: Path, cid: str, name: str, state: dict | None) -> None:
    d = base / "characters" / cid
    (d / "config").mkdir(parents=True)
    (d / "config" / "config.json").write_text(json.dumps({"id": cid, "name": name}), encoding="utf-8")
    if state is not None:
        (d / "state").mkdir()
        (d / "state" / "experience_state.json").write_text(json.dumps(state), encoding="utf-8")


def test_body_places_from_wifi_and_host(tmp_path):
    seen = NOW.isoformat()
    _char(tmp_path, "puchiteya", "ぷちてゃ", {"state": "awake", "since": seen, "seen": seen, "net": {"wifi": 2, "ip": "192.168.1.214", "host": "192.168.1.214", "since": "2026-11-14T12:30:00"}})
    _char(tmp_path, "puchiko", "ぷちこ", {"state": "awake", "since": seen, "seen": seen, "net": {"wifi": 3, "host": "100.101.223.118", "since": "2026-11-14T12:40:00"}})
    _char(tmp_path, "puchiru", "ぷちる", {"state": "offline", "since": "2026-11-14T12:50:00", "seen": seen, "net": {}})
    _char(tmp_path, "old", "ふるい", {"state": "awake", "since": seen})             # seen の無い古いデーモン → 分からない
    _char(tmp_path, "stale", "とまってる", {"state": "awake", "since": seen, "seen": "2026-11-14T12:00:00", "net": {"wifi": 1}})
    assert wa.lines(tmp_path, me="puchiko", now=NOW) == [
        "あなたの体のいま: お外(テザリング、12:40 から)",
        "ぷちるの体: いまは見えない(12:50 から)",            # 自分のあとは id 順
        "ぷちてゃの体のいま: 家(家の Wi-Fi、12:30 から)",
    ]
    # wifi の番号が無いファームは、つないだ先のアドレスで
    assert wa.place_of({"host": "192.168.1.12"}, wa.load_places(tmp_path)) == ("家", "")
    assert wa.place_of({"host": "10.0.0.5"}, wa.load_places(tmp_path)) == ("", "")
    # 家の config/places.json で言い方を変えられる
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "places.json").write_text(json.dumps({"wifi": {"3": "おでかけ"}, "how": {"3": "スマホ"}}), encoding="utf-8")
    assert wa.body("puchiko", tmp_path, NOW) == {"place": "おでかけ", "how": "スマホ", "since": "2026-11-14T12:40:00", "offline": False, "spot": ""}


def test_hours_until_and_expiry(tmp_path):
    wa.set_status("arisan", "会社", tmp_path, now=datetime(2026, 11, 14, 9, 2), hours=8)
    assert wa.people_lines(wa.load(tmp_path, NOW), LABEL, NOW) == ["ありさんのいま: 会社(9:02 から、17:02 まで)"]
    late = datetime(2026, 11, 14, 17, 2)
    assert wa.load(tmp_path, late)["users"] == {}                      # 過ぎたら無いもの
    assert wa.load(tmp_path, late)["recent"] == ["会社"]                # 候補には残る
    wa.set_status("arisan", "自室", tmp_path, now=datetime(2026, 11, 14, 22, 0), hours=10)
    assert wa.people_lines(wa.load(tmp_path, datetime(2026, 11, 14, 23, 0)), LABEL, datetime(2026, 11, 14, 23, 0)) == ["ありさんのいま: 自室(22:00 から、あした 8:00 まで)"]
    with pytest.raises(ValueError):
        wa.set_status("arisan", "会社", tmp_path, hours=0)
    with pytest.raises(ValueError):
        wa.set_status("arisan", "会社", tmp_path, hours=24 * 8)


def test_own_presets_replace_the_first_ones(tmp_path):
    """自分で決めた候補: はじめの候補の代わりに並ぶ。外した「はじめの候補」は、前に使っていても出さない"""
    wa.set_status("someone", "会社", tmp_path)
    wa.set_status("someone", "図書館", tmp_path)
    d = wa.load(tmp_path)
    assert wa.choices(d) == ["自室", "お外", "会社", "図書館"]
    assert wa.choices(d, ["寝室", "リビング"]) == ["寝室", "リビング", "図書館"]
    assert wa.choices(d, []) == ["自室", "お外", "会社", "図書館"]   # 空なら、はじめの候補


def test_clean_presets():
    assert wa.clean_presets([" 寝室 ", "寝室", "", "とても長い名前の部屋", "台所", "庭"]) == ["寝室", "とても長い", "台所"]
    assert wa.clean_presets(None) == []
    assert wa.clean_presets("自室") == []
