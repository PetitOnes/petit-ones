"""体の数字の線と差分(scripts/body_log.py)と、5 分ごとのまとめ(experience-daemon/body_sampler.py)のテスト"""

import json
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "experience-daemon"))

import body_log as bl
import body_sampler as bs

NOW = datetime(2026, 11, 16, 15, 2)


def house(tmp_path: Path, rows: list[dict], day: str = "20261116") -> Path:
    d = tmp_path / "characters" / "puchi" / "state" / "body"
    d.mkdir(parents=True, exist_ok=True)
    with (d / f"{day}.jsonl").open("a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    return tmp_path


def R(hhmm: str, amb: int, tilt: int = 8, day: str = "2026-11-16", **kw) -> dict:
    return {"ts": f"{day}T{hhmm}", "amb": amb, "amb_min": amb, "amb_max": amb, "tilt": tilt, "tilt_max": tilt, **kw}


def test_sampler_flushes_on_five_minute_boundary(tmp_path):
    s = bs.BodySampler()
    assert s.add(datetime(2026, 11, 16, 15, 0, 1), {"ambient": 100, "ax": 0, "ay": 0, "az": 1, "proximity": 0, "battery": 90}) is None
    assert s.add(datetime(2026, 11, 16, 15, 4, 59), {"ambient": 300, "ax": 0, "ay": 0, "az": 1}) is None
    assert s.add(datetime(2026, 11, 16, 15, 5, 0), None) == {"ts": "2026-11-16T15:00", "n": 2, "amb": 200, "amb_min": 100, "amb_max": 300, "tilt": 0, "tilt_max": 0, "prox": 0, "bat": 90}
    assert s.add(datetime(2026, 11, 16, 15, 10, 0), {"ambient": 1}) is None       # つながらなかった 5 分は行を作らない
    assert round(bs.tilt_deg(0, 0.42, 0.91)) == 25 and bs.tilt_deg(0, 0, 0) is None
    cdir = tmp_path / "characters" / "puchi"
    (cdir / "state").mkdir(parents=True)
    (cdir / "state" / "spot.json").write_text(json.dumps({"spot_id": "window"}), encoding="utf-8")
    bs.append_sample(cdir, {"ts": "2026-11-16T15:00", "n": 1, "amb": 5})
    assert json.loads((cdir / "state" / "body" / "20261116.jsonl").read_text(encoding="utf-8"))["spot"] == "window"


def test_spark_and_buckets():
    assert bl.spark([0, 50, 100, None]) == "▁▅█·" and bl.spark([None, None]) == "··" and bl.spark([7, 7]) == "▁▁"
    rows = [{"_t": datetime(2026, 11, 16, 0, 5), "amb": 3}, {"_t": datetime(2026, 11, 16, 0, 25), "amb": 9}, {"_t": datetime(2026, 11, 16, 1, 0), "amb": 1}]
    assert bl.buckets(rows, "amb", datetime(2026, 11, 16, 1, 40)) == [9, None, 1, None]


def test_line_numbers_only(tmp_path):
    base = house(tmp_path, [R("13:55", 120), R("14:00", 120), R("14:05", 352), R("14:55", 300, tilt=8), R("15:00", 93, tilt=25, spot="ari-desk")])
    house(tmp_path, [R("15:00", 88, day="2026-11-15")], day="20261115")
    got = bl.line(base, "puchi", NOW)
    assert got[0].startswith("明るさ きょう 0 時→いま(30 分ごと") and len(got[1]) == 31 and got[1].endswith("█▇▁")
    assert got[2] == "いま 93 / 1 時間前 120(-27) / きのうの同じ時刻 88(+5) / きょうの最大 352(14:05)・最小 93(15:00)"
    assert got[3] == "傾き いま 25° / 1 時間前 8° / きょうの最大 25°(15:00)"
    assert got[4] == "変わり目: 14:05 明るさ 120→352 / 15:00 明るさ 300→93 / 15:00 傾き 8°→25°"
    assert got[5] == "場所: ari-desk(15:00〜)"
    assert bl.line(tmp_path, "nobody", NOW)[0].startswith("体の数字の記録が、きょうはまだ無い")


def test_changes_skip_gaps_and_series(tmp_path):
    base = house(tmp_path, [R("10:00", 10), R("12:00", 400), R("12:05", 410), R("12:10", 380)])
    assert bl.changes(bl.load(base, "puchi", NOW)) == []           # 2 時間空いた前後はくらべない。小さな揺れは拾わない
    assert bl.series(base, "puchi", "amb", 4, NOW) == ["12:00 400", "12:05 410", "12:10 380"]


def test_notice_only_big_and_once(tmp_path):
    base = house(tmp_path, [R("14:00", 120), R("14:05", 352), R("14:10", 300), R("14:15", 200), R("14:55", 300, tilt=8), R("15:00", 290, tilt=25)])
    assert bl.notice(base, "puchi", mark=True, now=datetime(2026, 11, 16, 13, 50)) == []     # はじめは基準を作るだけ
    got = bl.notice(base, "puchi", mark=True, now=NOW)
    assert len(got) == 1 and got[0].startswith("（体の数字が大きく動いた: 14:05 明るさ 120→352 / 15:00 傾き 8°→25°。線は ")
    assert bl.notice(base, "puchi", mark=True, now=NOW) == []
    (base / "characters" / "puchi" / "config").mkdir()
    (base / "characters" / "puchi" / "config" / "settings.json").write_text(json.dumps({"notices": {"body_change": False}}), encoding="utf-8")
    (base / "characters" / "puchi" / "state" / "body_told.json").unlink()
    assert bl.notice(base, "puchi", mark=True, now=NOW) == []      # 受け取らない子
