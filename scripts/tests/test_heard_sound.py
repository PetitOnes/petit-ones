import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import heard_sound as hs  # noqa: E402

RESULT = {"duration_sec": 3.0,
          "shape": [{"t": 0.0, "db": -55.0, "centroid": 900, "onset": 0.5}, {"t": 1.0, "db": -30.0, "centroid": 2800, "onset": 6.1},
                    {"t": 2.0, "db": -42.0, "centroid": 2400, "onset": 4.0}],
          "events": [{"label": "Computer keyboard", "score": 0.74}, {"label": "Typing", "score": 0.7}],
          "timeline": [{"t": 1.0, "labels": [{"label": "Typing", "score": 0.7}]}]}


def test_shape_has_no_names(tmp_path):
    rec = hs.save(tmp_path, "arisan", "x_sound.webm", RESULT, now=datetime(2026, 11, 17, 10, 30), suffix="ab12")
    assert rec["id"] == "20261117_103000_ab12"
    text = hs.shape_text(rec)
    assert "大きさの線(1 秒ごと): " in text and "-55 -30 -42" in text and "2800" in text
    assert "keyboard" not in text.lower() and "Typing" not in text   # 名前は先に渡さない


def test_answer_and_tag(tmp_path, monkeypatch, capsys):
    hs.save(tmp_path, "arisan", "x_sound.webm", RESULT, now=datetime(2026, 11, 17, 10, 30))
    monkeypatch.setenv("PETIT_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(sys, "argv", ["heard_sound.py", "answer", "20261117_103000", "--character", "puchiko"])
    hs.main()
    assert "Computer keyboard(0.74)" in capsys.readouterr().out
    monkeypatch.setattr(sys, "argv", ["heard_sound.py", "tag", "puchiko", "20261117_103000", "雨の手前の音"])
    hs.main()
    rec = json.loads((tmp_path / "state" / "heard" / "20261117_103000.json").read_text(encoding="utf-8"))
    assert "puchiko" in rec["asked"] and rec["words"]["puchiko"][0]["text"] == "雨の手前の音"


def test_bad_id_and_empty(tmp_path):
    assert hs.load(tmp_path, "../../etc/passwd") is None
    rec = hs.save(tmp_path, "arisan", "x", {}, now=datetime(2026, 11, 17, 11, 0))
    assert hs.shape_text(rec) == "(音のかたちが取れなかった)"
    assert "名前の無い音" in hs.answer_text(rec)


def _clicks(times, secs=3, sr=16000):
    import numpy as np
    x = np.random.default_rng(0).normal(0, 0.0005, sr * secs)
    for t in times:
        i = int(t * sr)
        x[i:i + 160] += 0.3 * np.exp(-np.arange(160) / 30)   # 10 ms で消える「かちゃ」
    return x


def test_grains_count_clicks_inside_one_second():
    r = hs.analyze_samples(_clicks([0.1, 0.35, 0.6, 0.85, 2.5]))
    assert r["grains"] == [4, 0, 1]
    assert len(r["fine"]) == 30


def test_quiet_has_no_grains_and_fine_text(tmp_path):
    import numpy as np
    r = hs.analyze_samples(np.random.default_rng(1).normal(0, 0.001, 16000 * 2))
    assert r["grains"] == [0, 0]
    rec = hs.save(tmp_path, "arisan", "x", RESULT, now=datetime(2026, 11, 17, 12, 0))
    rec.update(hs.analyze_samples(_clicks([0.1, 0.35, 0.6, 0.85])))
    text = hs.fine_text(rec)
    assert "細かい線(0.1 秒ごと" in text and "粒(1 秒ごと): 4 0 0" in text
    assert "粒(その 1 秒に" in hs.shape_text(rec)
