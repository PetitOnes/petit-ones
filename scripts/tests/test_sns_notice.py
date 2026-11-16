"""ぷちSNS のお知らせ(scripts/sns_notice.py): 増えたときだけ 1 行・中身は載せない・種類と静かな時間はその子が決める"""

import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import notices  # noqa: E402
import sns_notice  # noqa: E402

DAY = datetime(2026, 11, 16, 10, 0)


def _house(base: Path, cid: str = "puchiko") -> None:
    p = base / "characters" / cid / "config" / "autonomous-mcp.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    env = {"PETIT_ID": cid, "PETIT_SNS_URL": "https://example.invalid/sns/local", "PETIT_SNS_TOKEN_URL": "https://example.invalid/token",
           "PETIT_SNS_CLIENT_ID": "id", "PETIT_SNS_CLIENT_SECRET": "himitsu"}
    p.write_text(json.dumps({"mcpServers": {"petit-sns": {"env": env}}}), encoding="utf-8")


def _letter(i: int, name: str = "澪") -> dict:
    return {"id": f"L{i}", "from": "mio", "from_name": name, "body": "ないしょの本文", "created_at": f"2026-11-16T09:0{i}:00Z"}


def _event(kind: str, i: int) -> dict:
    return {"type": kind, "post_id": "p", "actor_name": "だれか", "body": "ないしょ", "created_at": f"2026-11-16T09:1{i}:00Z"}


def _fetcher(letters: list, events: list):
    return lambda env, cid: {"letters": letters, "events": events}


def test_no_sns_config_means_nothing(tmp_path):
    assert sns_notice.line(tmp_path, "puchiko", fetcher=_fetcher([_letter(1)], [])) == ""


def test_letter_is_told_once_without_body(tmp_path):
    _house(tmp_path)
    f = _fetcher([_letter(1)], [])
    text = sns_notice.line(tmp_path, "puchiko", mark=True, now=DAY, fetcher=f)
    assert text == "ぷちSNS のお知らせ: 澪から手紙が 1 通、まだ読んでいない(読むのは mail_read)"
    assert sns_notice.line(tmp_path, "puchiko", mark=True, now=DAY.replace(hour=11), fetcher=f) == ""   # 同じ手紙は言わない
    saved = sns_notice.state_path(tmp_path, "puchiko").read_text(encoding="utf-8")
    assert "ないしょ" not in saved and "himitsu" not in saved
    # 2 通目が来たら、また言う。読まないまま 1 日たっても、もう一度
    two = _fetcher([_letter(1), _letter(2, "ぷちまる")], [])
    assert "澪・ぷちまるから手紙が 2 通" in sns_notice.line(tmp_path, "puchiko", mark=True, now=DAY.replace(hour=12), fetcher=two)
    assert sns_notice.line(tmp_path, "puchiko", mark=True, now=DAY.replace(hour=13), fetcher=two) == ""
    assert "2 通" in sns_notice.line(tmp_path, "puchiko", mark=True, now=DAY.replace(day=17, hour=13), fetcher=two)


def test_events_follow_the_kinds_the_petit_chose(tmp_path):
    _house(tmp_path)
    f = _fetcher([], [_event("comment", 1), _event("board_reply", 2), _event("mention", 3), _event("like", 4), _event("touch", 5)])
    text = sns_notice.line(tmp_path, "puchiko", mark=True, now=DAY, fetcher=f)
    assert text == "ぷちSNS のお知らせ: 自分の投稿に返事が 2 件、＠で呼ばれたのが 1 件(見るのは sns_inbox)"
    assert sns_notice.line(tmp_path, "puchiko", mark=True, now=DAY, fetcher=f) == ""
    notices.set_kind("puchiko", "sns_like", True, tmp_path)
    notices.set_kind("puchiko", "sns_reply", False, tmp_path)
    more = _fetcher([], [_event("comment", 6), _event("like", 7)])
    assert sns_notice.line(tmp_path, "puchiko", mark=True, now=DAY, fetcher=more) == "ぷちSNS のお知らせ: いいねが 1 件(見るのは sns_inbox)"


def test_quiet_hours_hold_until_morning(tmp_path):
    _house(tmp_path)
    f = _fetcher([_letter(1)], [])
    assert sns_notice.line(tmp_path, "puchiko", mark=True, now=DAY.replace(hour=3), fetcher=f) == ""
    assert "手紙が 1 通" in sns_notice.line(tmp_path, "puchiko", mark=True, now=DAY.replace(hour=7), fetcher=f)
    notices.set_quiet("puchiko", None, tmp_path)
    assert "手紙が 2 通" in sns_notice.line(tmp_path, "puchiko", mark=True, now=DAY.replace(day=17, hour=3),
                                         fetcher=_fetcher([_letter(1), _letter(2)], []))


def test_unreachable_keeps_the_last_note_and_says_nothing_new(tmp_path):
    _house(tmp_path)
    sns_notice.line(tmp_path, "puchiko", mark=True, now=DAY, fetcher=_fetcher([_letter(1)], []))

    def down(env, cid):
        raise OSError("つながらない")
    assert sns_notice.line(tmp_path, "puchiko", mark=True, now=DAY, fetcher=down) == ""
    want = notices.enabled("puchiko", tmp_path)
    assert sns_notice.summary(sns_notice.check(tmp_path, "puchiko", fetcher=down), want)["letters"] == 1
