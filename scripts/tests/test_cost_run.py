"""1 回ぶんの代(scripts/cost_run.py)と、読むときにそれを使うこと(cost_correct.py)のテスト"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cost_correct  # noqa: E402
import cost_run  # noqa: E402


def test_run_cost_is_difference_per_session(tmp_path):
    assert cost_run.run_cost("s1", 0.20, tmp_path) == 0.20          # はじめての回
    assert cost_run.run_cost("s1", 0.35, tmp_path) == 0.15          # 続きの回は差
    assert cost_run.run_cost("s2", 0.10, tmp_path) == 0.10          # ほかのセッションは別
    assert cost_run.run_cost("s1", 0.05, tmp_path) == 0.05          # 累計が減ったら別物として、そのまま
    assert cost_run.run_cost("", 0.30, tmp_path) == 0.30            # id が無ければ、そのまま


def test_load_corrected_uses_cost_run(tmp_path):
    log = tmp_path / "token_log.jsonl"
    rows = [
        {"timestamp": "2026-11-19T12:00:00+09:00", "source": "autonomous", "character": "puchiko", "session_type": "resume",
         "input": 10, "output": 100, "cache_creation": 0, "cache_read": 100000, "cost_usd": 5.0, "cost_run": 0.04},
    ]
    log.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    out = cost_correct.load_corrected(log)
    assert out[0]["cost"] == 0.04 and out[0]["cost_raw"] == 5.0 and out[0]["fixed"] is False


def test_unknown_previous_falls_back_to_estimate(tmp_path):
    """前の累計を知らない続きの回(cost_run == cost_usd)は、今までの推定にまかせる"""
    log = tmp_path / "token_log.jsonl"
    base = {"source": "chat", "character": "puchiko", "input": 10, "output": 100, "cache_creation": 0, "cache_read": 100000}
    rows = [{**base, "timestamp": "2026-11-19T12:00:00+09:00", "cost_usd": 0.03, "cost_run": 0.03},
            {**base, "timestamp": "2026-11-19T12:05:00+09:00", "cost_usd": 0.06, "cost_run": 0.06}]
    log.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    out = cost_correct.load_corrected(log)
    assert out[1]["fixed"] is True and abs(out[1]["cost"] - 0.03) < 1e-9
