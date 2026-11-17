"""合奏(scripts/ensemble.py)"""

from __future__ import annotations

import sys
import wave
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import ensemble  # noqa: E402
import sing  # noqa: E402


def _wav(p: Path, seconds: float, hz: float = 440, sr: int = sing.SR) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    t = np.arange(int(sr * seconds)) / sr
    with wave.open(str(p), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((np.sin(2 * np.pi * hz * t) * 0.5 * 32767).astype("<i2").tobytes())


@pytest.fixture
def house(tmp_path: Path) -> Path:
    for c in ("puchiru", "puchiteya"):
        (tmp_path / "characters" / c).mkdir(parents=True)
    _wav(tmp_path / "sounds" / "made" / "puchiru" / "ichiteki.wav", 1.0)
    _wav(tmp_path / "sounds" / "made" / "puchiteya" / "hikari.wav", 2.0, 660, 16000)   # 違う速さも合わせる
    return tmp_path


TRACKS = [{"by": "puchiru", "name": "ichiteki", "start": 0}, {"by": "puchiteya", "name": "hikari", "start": 0.5, "vol": 0.8}]


def test_mix_length_and_peak(house: Path) -> None:
    x = ensemble.mix(house, TRACKS)
    assert abs(len(x) / sing.SR - 2.5) < 0.01
    assert np.abs(x).max() <= sing.PEAK + 1e-6


def test_save_and_notice_once(house: Path) -> None:
    info = ensemble.save(house, "arisan", "first", TRACKS, why="はじめての合奏")
    assert info["ensemble"][1]["vol"] == 0.8 and (house / "sounds" / "made" / "arisan" / "first.wav").is_file()
    lines = sing.notice(house, "puchiru", mark=True)
    assert len(lines) == 1 and "ichiteki" in lines[0] and "0.5 秒 puchiteya の hikari" in lines[0]
    assert sing.notice(house, "puchiru", mark=True) == []
    assert "合奏:" in sing.look_text(house, "arisan", "first")
    sing.comment(house, "arisan", "first", "puchiru", "きれい")   # 合奏にも感想が書ける


def test_bad_tracks(house: Path) -> None:
    with pytest.raises(ensemble.EnsembleError):
        ensemble.mix(house, [])
    with pytest.raises(ensemble.EnsembleError):
        ensemble.mix(house, [{"by": "puchiru", "name": "nai"}])
    with pytest.raises(ensemble.EnsembleError):
        ensemble.mix(house, [{"by": "puchiru", "name": "ichiteki", "start": 99}])
    with pytest.raises(ensemble.EnsembleError):
        ensemble.mix(house, [{"by": "arisan", "kind": "memo", "name": "../x.webm"}])
    with pytest.raises(ensemble.EnsembleError):
        ensemble.mix(house, [TRACKS[0]] * 9)


def test_voice_memo(house: Path) -> None:
    import shutil
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg が無い")
    memo = house / "voice_memo" / "arisan" / "20261117_100000_arisan_はなうた.wav"
    _wav(memo, 1.5, 330, 22050)
    x = ensemble.mix(house, TRACKS + [{"by": "arisan", "kind": "memo", "name": memo.name, "start": 2}])
    assert abs(len(x) / sing.SR - 3.5) < 0.01
    info = ensemble.save(house, "arisan", "with-memo", TRACKS + [{"by": "arisan", "kind": "memo", "name": memo.name, "start": 2}])
    assert "arisan のボイスメモ" in ensemble.describe(info)
