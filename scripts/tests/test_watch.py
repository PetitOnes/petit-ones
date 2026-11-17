"""ぷち時計への通知(scripts/watch.py)"""

import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import watch  # noqa: E402

NOON = datetime(2026, 11, 17, 12, 0)


def _held(base, now=NOON, **kw):
    watch.make_key(base, owner_name="ありさん")
    watch.sync({"still_s": 30, **kw}, base, now)


def test_no_watch_no_line(tmp_path):
    assert watch.line("puchiko", tmp_path, NOON) == ""
    ok, msg = watch.send("puchiko", "やあ", tmp_path, NOON)
    assert not ok and "つながっていない" in msg


def test_line_only_when_held(tmp_path):
    _held(tmp_path)
    s = watch.line("puchiko", tmp_path, NOON)
    assert "ありさんの時計" in s and "あと 3 回" in s and "watch.py send --character puchiko" in s
    # 15 分動いていない → 手元にない
    watch.sync({"still_s": 16 * 60}, tmp_path, NOON)
    assert watch.line("puchiko", tmp_path, NOON) == ""
    # 時計から 10 分以上連絡がない → 手元にない
    watch.sync({"still_s": 0}, tmp_path, NOON)
    assert watch.line("puchiko", tmp_path, NOON + timedelta(minutes=11)) == ""


def test_charging_or_face_down_is_not_held(tmp_path):
    _held(tmp_path, charging=True)
    assert not watch.held(tmp_path, NOON)
    watch.sync({"still_s": 0, "face_down": True}, tmp_path, NOON)
    assert not watch.held(tmp_path, NOON)


def test_night_and_off(tmp_path):
    _held(tmp_path, now=datetime(2026, 11, 17, 3, 0))
    assert watch.line("puchiko", tmp_path, datetime(2026, 11, 17, 3, 0)) == ""
    ok, msg = watch.send("puchiko", "よる", tmp_path, datetime(2026, 11, 17, 3, 0))
    assert not ok and "夜" in msg
    _held(tmp_path)
    watch.sync({"still_s": 0, "notify_set": False}, tmp_path, NOON)   # 時計で切った
    ok, msg = watch.send("puchiko", "やあ", tmp_path, NOON)
    assert not ok and "切ってある" in msg
    assert watch.sync({"still_s": 0}, tmp_path, NOON)["notify"] is False


def test_send_limits_and_delivery(tmp_path):
    _held(tmp_path)
    assert not watch.send("puchiko", "あ" * 41, tmp_path, NOON)[0]
    assert not watch.send("puchiko", "1\n2\n3\n4", tmp_path, NOON)[0]
    for i in range(3):
        assert watch.send("puchiko", f"ひとこと{i}", tmp_path, NOON)[0]
    ok, msg = watch.send("puchiko", "4 回目", tmp_path, NOON)
    assert not ok and "3 回" in msg
    assert watch.send("puchiru", "ぷちるは別に数える", tmp_path, NOON)[0]
    got = watch.sync({"still_s": 0, "after": 0}, tmp_path, NOON)["notices"]
    assert [n["id"] for n in got] == [1, 2, 3, 4]
    r = watch.sync({"still_s": 0, "after": 4}, tmp_path, NOON)
    assert r["notices"] == [] and r["last_id"] == 4
    # 次の日はまた 3 回
    _held(tmp_path, now=NOON + timedelta(days=1))
    assert "あと 3 回" in watch.line("puchiko", tmp_path, NOON + timedelta(days=1))


def test_mita_told_once_only_to_sender(tmp_path):
    _held(tmp_path)
    watch.send("puchiko", "空が明るい", tmp_path, NOON)
    watch.send("puchiru", "水の音", tmp_path, NOON)
    assert watch.notice("puchiko", tmp_path) == ""
    watch.sync({"still_s": 0, "mita": [1]}, tmp_path, NOON)
    s = watch.notice("puchiko", tmp_path, mark=True)
    assert "空が明るい" in s and "見たよ" in s
    assert watch.notice("puchiko", tmp_path) == ""
    assert watch.notice("puchiru", tmp_path) == ""


def test_key(tmp_path):
    k = watch.make_key(tmp_path)
    assert watch.key_ok(k, tmp_path) and not watch.key_ok("x", tmp_path) and not watch.key_ok(None, tmp_path)
    assert (watch.config_path(tmp_path).stat().st_mode & 0o777) == 0o600
