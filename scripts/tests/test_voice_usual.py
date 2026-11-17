import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import voice_usual as vu  # noqa: E402


def test_quiet_until_enough_then_numbers_only(tmp_path):
    for _ in range(vu.MIN_SAMPLES):
        assert vu.note(tmp_path, "arisan", {"f0_mean_hz": 230.0, "speech_rate": 2.0, "pause_ratio": 0.2}) == ""
    assert vu.note(tmp_path, "arisan", {"f0_mean_hz": 236.0, "speech_rate": 2.1, "pause_ratio": 0.22}) == ""   # いつも通り
    line = vu.note(tmp_path, "arisan", {"f0_mean_hz": 275.0, "speech_rate": 2.0, "pause_ratio": 0.45})
    assert line == "（声の数字: 高さ 275 Hz(いつもは 230 Hz)、間 0.45(いつもは 0.20)）"
    assert "疲" not in line and "元気" not in line


def test_unknown_and_bad_names_are_not_kept(tmp_path):
    assert vu.note(tmp_path, "unknown", {"f0_mean_hz": 200.0}) == ""
    assert vu.note(tmp_path, "../x", {"f0_mean_hz": 200.0}) == ""
    assert not (tmp_path / "state").exists()


def test_keeps_last_only(tmp_path):
    for i in range(vu.KEEP + 10):
        vu.note(tmp_path, "kazahaya", {"f0_mean_hz": 120.0 + i % 3})
    assert len(vu.history(tmp_path, "kazahaya")) == vu.KEEP
