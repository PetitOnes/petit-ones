"""日記づくりの結果の見分け(scripts/diary_result.py)"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import diary_result as dr  # noqa: E402


def test_good_result_is_the_diary():
    raw = json.dumps({"type": "result", "is_error": False, "result": " きょうは静かだった。\n"})
    assert dr.claude_text(raw) == "きょうは静かだった。"


def test_auth_failure_is_not_a_diary():
    result = {"type": "result", "subtype": "success", "is_error": True,
              "result": "Failed to authenticate: OAuth session expired and could not be refreshed"}
    with pytest.raises(dr.DiaryFailed) as e:
        dr.claude_text(json.dumps(result))
    assert "Failed to authenticate" in str(e.value)
    assert e.value.result == result


def test_empty_or_broken_output_is_not_a_diary():
    with pytest.raises(dr.DiaryFailed):
        dr.claude_text(json.dumps({"is_error": False, "result": ""}), "何かの警告")
    with pytest.raises(dr.DiaryFailed) as e:
        dr.claude_text("", "command  not\nfound")
    assert str(e.value) == "command not found"
    with pytest.raises(dr.DiaryFailed):
        dr.claude_text("[]")


def test_failed_text_is_recognized():
    assert dr.is_failed(dr.failed_text("x"))
    assert not dr.is_failed("きょうは静かだった。")
    assert not dr.is_failed("")
    assert not dr.is_failed(None)
