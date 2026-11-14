"""家の知らせ(scripts/house_alert.py)のテスト"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import house_alert as ha

AUTH = {"type": "result", "subtype": "success", "is_error": True,
        "result": "Failed to authenticate: OAuth session expired and could not be refreshed"}
NET = {"type": "result", "subtype": "success", "is_error": True,
       "result": "API Error: Can't reach the API server — check your internet or DNS (EAI_AGAIN)"}
GOOD = {"type": "result", "subtype": "success", "is_error": False, "result": "部屋は静かだった。"}
T0 = datetime(2026, 11, 14, 6, 0)


class Box:
    """送った文をためるだけの、にせの送り先。"""

    def __init__(self, works: bool = True):
        self.sent: list[str] = []
        self.works = works

    def __call__(self, text: str) -> bool:
        if self.works:
            self.sent.append(text)
        return self.works


def test_classify():
    assert ha.classify(AUTH)[0] == "claude_auth"
    assert ha.classify(NET)[0] == "claude_network"
    assert ha.classify(GOOD) == (None, "")
    assert ha.classify(None)[0] == "claude_no_result"
    assert ha.classify({"is_error": True, "subtype": "error_during_execution", "result": ""})[0] == "claude_error"
    # 回数の上限で終わった回は、失敗ではない(is_error が立たない)
    assert ha.classify({"is_error": False, "subtype": "error_max_turns"}) == (None, "")


def test_first_failure_is_told_at_once(tmp_path):
    box = Box()
    text = ha.check_result(tmp_path, AUTH, "自律行動", "puchi", T0, box)
    assert text and "ログインが切れています" in text
    assert "11/14 06:00 puchi の 自律行動" in text
    assert "理由: Failed to authenticate" in text
    assert len(box.sent) == 1


def test_repeat_only_after_hours(tmp_path):
    box = Box()
    ha.check_result(tmp_path, AUTH, "自律行動", "a", T0, box)
    assert ha.check_result(tmp_path, AUTH, "自律行動", "b", T0 + timedelta(minutes=30), box) is None
    assert ha.check_result(tmp_path, AUTH, "自律行動", "a", T0 + timedelta(hours=2, minutes=59), box) is None
    text = ha.check_result(tmp_path, AUTH, "自律行動", "a", T0 + timedelta(hours=3), box)
    assert text and "11/14 06:00 から 4 回" in text and "a の 自律行動、b の 自律行動" in text
    assert len(box.sent) == 2


def test_recovery_is_told_once(tmp_path):
    box = Box()
    ha.check_result(tmp_path, AUTH, "自律行動", "a", T0, box)
    ha.check_result(tmp_path, AUTH, "自律行動", "a", T0 + timedelta(minutes=30), box)
    text = ha.check_result(tmp_path, GOOD, "ダッシュボード(chat)", "a", T0 + timedelta(hours=1), box)
    assert text and text.startswith("[house-alert] 直りました")
    assert "11/14 06:00 から 2 回" in text
    assert ha.check_result(tmp_path, GOOD, "自律行動", "a", T0 + timedelta(hours=2), box) is None
    assert json.loads(ha.state_path(tmp_path).read_text(encoding="utf-8")) == {}


def test_success_without_failure_writes_nothing(tmp_path):
    box = Box()
    assert ha.check_result(tmp_path, GOOD, "自律行動", "a", T0, box) is None
    assert not ha.state_path(tmp_path).exists()
    assert box.sent == []


def test_send_failure_is_retried_next_time(tmp_path):
    down = Box(works=False)
    assert ha.check_result(tmp_path, AUTH, "自律行動", "a", T0, down) is None
    box = Box()
    text = ha.check_result(tmp_path, AUTH, "自律行動", "a", T0 + timedelta(minutes=30), box)
    assert text and "11/14 06:00 から 2 回" in text


def test_one_off_failure_is_not_told(tmp_path):
    """ログイン切れ以外は、つづけて 2 回起きてから知らせる。1 回きりで直ったら何も出さない。"""
    box = Box()
    assert ha.check_result(tmp_path, NET, "自律行動", "a", T0, box) is None
    assert ha.check_result(tmp_path, GOOD, "自律行動", "a", T0 + timedelta(minutes=30), box) is None
    assert box.sent == []
    assert ha.check_result(tmp_path, NET, "自律行動", "a", T0 + timedelta(hours=1), box) is None
    text = ha.check_result(tmp_path, NET, "自律行動", "b", T0 + timedelta(hours=1, minutes=5), box)
    assert text and "ネットワーク" in text and "2 回" in text


def test_send_exception_does_not_raise(tmp_path):
    def boom(text: str) -> bool:
        raise OSError("no network")

    assert ha.check_result(tmp_path, AUTH, "自律行動", "a", T0, boom) is None


def test_disabled_by_env(tmp_path, monkeypatch):
    monkeypatch.setenv("HOUSE_ALERT", "0")
    box = Box()
    assert ha.check_result(tmp_path, AUTH, "自律行動", "a", T0, box) is None
    assert box.sent == []


def test_detail_hides_secrets_and_ips():
    text = ha.clean_detail("key sk-ant-abcdefghijklmnop at 192.168.1.20\nnext " + "x" * 300)
    assert "sk-ant" not in text and "192.168" not in text and "\n" not in text
    assert len(text) <= ha.DETAIL_MAX


def test_read_result(tmp_path):
    p = tmp_path / "s.jsonl"
    p.write_text('{"type":"system"}\nnot json\n' + json.dumps(AUTH, separators=(",", ":")) + "\n", encoding="utf-8")
    assert ha.read_result(p)["is_error"] is True
    assert ha.read_result(tmp_path / "none.jsonl") is None


def test_other_kind_report_and_ok(tmp_path):
    box = Box()
    assert ha.report(tmp_path, "backup", "バックアップ", detail="push に失敗", now=T0, send=box) is None
    text = ha.report(tmp_path, "backup", "バックアップ", detail="push に失敗", now=T0 + timedelta(days=1), send=box)
    assert text and "家で失敗がありました(backup)" in text
    assert ha.ok(tmp_path, ["backup"], "バックアップ", now=T0 + timedelta(hours=1), send=box).startswith("[house-alert] 直りました")
