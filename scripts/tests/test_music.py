"""音を数字に(scripts/music.py)。合成した音で、重心・静けさ・拍・回の流れを確かめる"""

import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import music as mu  # noqa: E402

SR = mu.SR
T = datetime(2026, 11, 14, 22, 0)


def _sine(hz, sec, amp=0.3):
    t = np.arange(int(SR * sec)) / SR
    return amp * np.sin(2 * np.pi * hz * t)


def test_frame_features_centroid_and_quiet():
    f = mu.frame_features(_sine(440, 1))
    assert 380 <= f["centroid"] <= 520 and not f["quiet"] and 0.6 < f["level"] < 1.0
    hi = mu.frame_features(_sine(3000, 1))
    assert hi["centroid"] > f["centroid"]
    q = mu.frame_features(np.zeros(SR))
    assert q["quiet"] and q["level"] == 0.0 and q["centroid"] == 0


def test_tempo_from_clicks():
    sec, bpm = 12, 120
    x = np.zeros(SR * sec)
    for i in range(int(sec * bpm / 60)):
        s = int(i * 60 / bpm * SR)
        x[s:s + 400] = 0.8 * np.sin(2 * np.pi * 1000 * np.arange(400) / SR) * np.hanning(400)
    tempo = mu.tempo_from_envelope(mu.onset_envelope(x))
    assert tempo is not None and (abs(tempo - 120) <= 3 or abs(tempo - 60) <= 2)
    assert mu.tempo_from_envelope(mu.onset_envelope(np.zeros(SR * 5))) is None


def test_session_frames_now_and_wave(tmp_path):
    assert mu.line(tmp_path) == ""
    s = mu.start("phone", base=tmp_path, now=T)
    assert mu.session(tmp_path)["id"] == s["id"] and mu.position(s, T + timedelta(seconds=84)) == 84
    quiet = [{"t": i, "level": 0.0, "db": -90, "centroid": 0, "onset": 0} for i in range(0, 5)]
    loud = [{"t": i, "level": 0.6, "db": -20, "centroid": 2500, "onset": 3.0, "tempo": 118} for i in range(5, 15)]
    d = mu.add_frames(quiet + loud, base=tmp_path)
    assert d["seconds"] == 15 and d["tempo"] == 118
    txt = mu.now_text(tmp_path, T + timedelta(seconds=15))
    assert txt.startswith("聴いている回: いま 0:15(ありさんのスマホが聞いた音)") and "明るめ" in txt and "拍 およそ 118" in txt and "上がってきた" in txt
    assert "答え合わせ" not in txt   # 終わる前は曲名を出さない
    # t 無しで足すと、いまの秒が付く(重なりは捨てる)
    mu.add_frames([{"level": 0.2, "db": -40, "centroid": 900, "onset": 1}], base=tmp_path)
    assert mu.wave(base=tmp_path).startswith("0:00 ")
    s = mu.stop("ある曲", "雨の日に聴いていた", base=tmp_path, now=T + timedelta(seconds=200))
    assert s["ended_at"] and "答え合わせ: ある曲" in mu.now_text(tmp_path) and "雨の日" in mu.now_text(tmp_path)
    assert mu.line(tmp_path, T + timedelta(hours=1)) != "" and mu.line(tmp_path, T + timedelta(hours=4)) == ""


def test_analyze_samples_counts_seconds():
    d = mu.analyze_samples(np.concatenate([_sine(440, 2), np.zeros(SR * 2)]))
    assert d["seconds"] == 4 and [f["quiet"] for f in d["frames"]] == [False, False, True, True]


def test_feel_wrote_note(tmp_path):
    try:
        mu.feel("puchiko", "x", tmp_path); raise AssertionError("回が無いのに書けた")
    except ValueError:
        pass
    mu.start("pc", base=tmp_path, now=T)
    mu.add_frames([{"t": i, "level": 0.5, "db": -20, "centroid": 1200, "onset": 1} for i in range(30)], base=tmp_path)
    r = mu.feel("puchiko", "  光が\n揺れる  みたい ", tmp_path, T + timedelta(seconds=25))
    assert r["count"] == 1 and r["t"] == 25
    mu.feel("puchiteya", "明るい。", tmp_path, T + timedelta(seconds=26))
    w = mu.wrote(None, ["puchiteya", "puchiko", "puchiru"], tmp_path)
    assert w["counts"] == {"puchiteya": 1, "puchiko": 1, "puchiru": 0} and not w["all"]
    assert "あなたがこれまでに書いたこと: [0:25] 光が 揺れる みたい" in mu.now_text(tmp_path, T + timedelta(seconds=40), character_id="puchiko")
    assert "書いたこと" not in mu.now_text(tmp_path, T + timedelta(seconds=40), character_id="puchiru")
    mu.feel("puchiru", "水", tmp_path, T + timedelta(seconds=28))
    assert mu.wrote(None, ["puchiteya", "puchiko", "puchiru"], tmp_path)["all"]
    mu.stop("ある曲", "夜に", base=tmp_path, now=T + timedelta(seconds=60))
    note = mu.note_text(None, {"puchiko": "ぷちこ", "puchiteya": "ぷちてゃ", "puchiru": "ぷちる"}, tmp_path)
    assert note.startswith("🎧 いっしょに聴いた(2026/11/14 22:00) — ある曲") and "ありさん「夜に」" in note and "ぷちこ [0:25] 光が 揺れる みたい" in note and "ぷちる [0:28] 水" in note
    assert mu.around(None, tmp_path) == ""   # 部屋の記録が無ければ空
