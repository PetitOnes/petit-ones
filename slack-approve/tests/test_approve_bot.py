"""approve_bot の単体テスト。tmux・Slackは全てモック、実プロセス・実APIは呼ばない。"""

from __future__ import annotations

import json
import subprocess
import time

import pytest

import approve_bot as ab

# ---------------------------------------------------------------------------
# テスト間で共有グローバル状態が漏れないようにリセットする
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_global_state(tmp_path, monkeypatch):
    # LOG_FILE は必ずテスト用の一時パスに差し替える。個別テストがtmp_pathを要求していても
    # 同じインスタンスが渡されるので上書きは無害（本番ログを汚さないための安全弁）。
    monkeypatch.setattr(ab, "LOG_FILE", tmp_path / "slack-approve.log")
    ab._dedupe_cache.clear()
    ab._active_notifications.clear()
    ab._processed_message_ts.clear()
    yield
    ab._dedupe_cache.clear()
    ab._active_notifications.clear()
    ab._processed_message_ts.clear()


# ---------------------------------------------------------------------------
# サンプルのペイン内容（実際のClaude CodeのUIパターンを想定）
# ---------------------------------------------------------------------------

BOX_STYLE_PROMPT = """\
Some earlier tool output here
more output

╭─────────────────────────────────────────────────╮
│ Bash command                                     │
│                                                   │
│   rm -rf ./tmp                                   │
│                                                   │
│ Do you want to proceed?                          │
│                                                   │
│ ❯ 1. Yes                                         │
│   2. Yes, and don't ask again for rm commands    │
│   3. No, and tell Claude what to do differently  │
╰─────────────────────────────────────────────────╯
"""

PLAIN_STYLE_PROMPT = """\
Do you want to make this edit to foo.py?

❯ 1. Yes
  2. Yes, and don't ask again this session
  3. No
"""

TWO_CHOICE_PROMPT = """\
Do you want to make this edit to foo.py?

❯ 1. Yes
  2. No
"""

NOT_A_PROMPT_NUMBERED_LIST = """\
Table of contents
1. Introduction
2. Methods
3. No idea what comes after this, still writing
"""

NOT_A_PROMPT_JUST_YES = """\
The answer is:
1. Yes, absolutely.
That's it, no other options here.
"""


# ---------------------------------------------------------------------------
# find_prompt_block
# ---------------------------------------------------------------------------


def test_detects_box_style_prompt():
    block = ab.find_prompt_block(BOX_STYLE_PROMPT)
    assert block is not None
    assert "1. Yes" in block
    assert "No" in block


def test_detects_plain_style_prompt():
    block = ab.find_prompt_block(PLAIN_STYLE_PROMPT)
    assert block is not None
    assert "❯ 1. Yes" in block


def test_detects_two_choice_prompt():
    block = ab.find_prompt_block(TWO_CHOICE_PROMPT)
    assert block is not None
    assert "❯ 1. Yes" in block
    assert "2. No" in block


def test_ignores_numbered_list_without_question_or_cursor():
    # "3. No idea..." は正規表現上マッチしうるが、Do you want / ❯ が無いので弾かれる
    assert ab.find_prompt_block(NOT_A_PROMPT_NUMBERED_LIST) is None


def test_ignores_yes_without_no_option():
    assert ab.find_prompt_block(NOT_A_PROMPT_JUST_YES) is None


def test_none_or_empty_input():
    assert ab.find_prompt_block(None) is None
    assert ab.find_prompt_block("") is None


def test_trailing_blank_lines_are_stripped():
    block = ab.find_prompt_block(BOX_STYLE_PROMPT + "\n\n\n")
    assert block is not None
    assert block.endswith("╰─────────────────────────────────────────────────╯")


# ---------------------------------------------------------------------------
# parse_options（選択肢の動的パース：2択・3択）
# ---------------------------------------------------------------------------


def test_parse_options_two_choice():
    block = ab.find_prompt_block(TWO_CHOICE_PROMPT)
    assert ab.parse_options(block) == [("1", "Yes"), ("2", "No")]


def test_parse_options_three_choice():
    block = ab.find_prompt_block(PLAIN_STYLE_PROMPT)
    assert ab.parse_options(block) == [
        ("1", "Yes"),
        ("2", "Yes, and don't ask again this session"),
        ("3", "No"),
    ]


def test_parse_options_strips_box_borders_and_whitespace():
    block = ab.find_prompt_block(BOX_STYLE_PROMPT)
    options = dict(ab.parse_options(block))
    assert options["1"] == "Yes"
    assert options["2"] == "Yes, and don't ask again for rm commands"
    assert options["3"] == "No, and tell Claude what to do differently"
    assert "│" not in options["3"]
    assert not options["3"].endswith(" ")


def test_parse_options_ignores_duplicate_numbers():
    block = "1. Yes\n1. Yes again\n2. No\n"
    assert ab.parse_options(block) == [("1", "Yes"), ("2", "No")]


def test_parse_options_empty_for_no_numbered_lines():
    assert ab.parse_options("nothing numbered here") == []


# ---------------------------------------------------------------------------
# truncate_block
# ---------------------------------------------------------------------------


def test_truncate_block_keeps_tail_lines():
    lines = [f"line{i}" for i in range(100)]
    block = "\n".join(lines)
    truncated = ab.truncate_block(block, max_lines=40)
    assert truncated.split("\n") == lines[-40:]


def test_truncate_block_short_input_unchanged():
    block = "a\nb\nc"
    assert ab.truncate_block(block, max_lines=40) == block


def test_truncate_block_char_limit():
    block = "x" * 5000
    truncated = ab.truncate_block(block)
    assert len(truncated) <= ab.MAX_DISPLAY_CHARS


# ---------------------------------------------------------------------------
# prompt_hash / should_notify (dedupe)
# ---------------------------------------------------------------------------


def test_prompt_hash_stable_and_distinct():
    h1 = ab.prompt_hash("claude", "some block")
    h2 = ab.prompt_hash("claude", "some block")
    h3 = ab.prompt_hash("claude3", "some block")
    h4 = ab.prompt_hash("claude", "different block")
    assert h1 == h2
    assert h1 != h3
    assert h1 != h4


def test_should_notify_dedupes_within_window():
    key = "test-key-1"
    assert ab.should_notify(key, now=1000.0, window_sec=600.0) is True
    # 直後の再チェックは抑制される
    assert ab.should_notify(key, now=1001.0, window_sec=600.0) is False
    # ウィンドウが経過したら再度通知してよい
    assert ab.should_notify(key, now=1601.0, window_sec=600.0) is True


def test_should_notify_different_keys_independent():
    assert ab.should_notify("key-a", now=0.0) is True
    assert ab.should_notify("key-b", now=0.0) is True


# ---------------------------------------------------------------------------
# compute_current_hash（送信前の存在照合の基礎）
# ---------------------------------------------------------------------------


def test_compute_current_hash_none_when_session_missing(monkeypatch):
    monkeypatch.setattr(ab, "tmux_session_exists", lambda s: False)
    assert ab.compute_current_hash("claude") is None


def test_compute_current_hash_none_when_no_prompt_visible(monkeypatch):
    monkeypatch.setattr(ab, "tmux_session_exists", lambda s: True)
    monkeypatch.setattr(ab, "capture_pane", lambda s: "nothing interesting here")
    assert ab.compute_current_hash("claude") is None


def test_compute_current_hash_matches_manual_computation(monkeypatch):
    monkeypatch.setattr(ab, "tmux_session_exists", lambda s: True)
    monkeypatch.setattr(ab, "capture_pane", lambda s: PLAIN_STYLE_PROMPT)
    block = ab.find_prompt_block(PLAIN_STYLE_PROMPT)
    expected = ab.prompt_hash("claude", ab.truncate_block(block))
    assert ab.compute_current_hash("claude") == expected


# ---------------------------------------------------------------------------
# mark_message_processed（同一message_tsの二重処理防止）
# ---------------------------------------------------------------------------


def test_mark_message_processed_first_time_true():
    assert ab.mark_message_processed("111.222") is True


def test_mark_message_processed_second_time_false():
    assert ab.mark_message_processed("111.222") is True
    assert ab.mark_message_processed("111.222") is False


def test_mark_message_processed_none_ts_always_true():
    assert ab.mark_message_processed(None) is True
    assert ab.mark_message_processed(None) is True


# ---------------------------------------------------------------------------
# load_allowed_sessions
# ---------------------------------------------------------------------------


def test_load_allowed_sessions_default(monkeypatch):
    monkeypatch.delenv("SLACK_APPROVE_SESSIONS", raising=False)
    assert ab.load_allowed_sessions() == ["claude", "claude3", "main"]


def test_load_allowed_sessions_custom(monkeypatch):
    monkeypatch.setenv("SLACK_APPROVE_SESSIONS", "claude, claude3 ,  approve-test")
    assert ab.load_allowed_sessions() == ["claude", "claude3", "approve-test"]


def test_load_allowed_sessions_ignores_blank_entries(monkeypatch):
    monkeypatch.setenv("SLACK_APPROVE_SESSIONS", "claude,,  ,claude3")
    assert ab.load_allowed_sessions() == ["claude", "claude3"]


def test_load_allowed_sessions_empty_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("SLACK_APPROVE_SESSIONS", "   ,  ,")
    assert ab.load_allowed_sessions() == ["claude", "claude3", "main"]


# ---------------------------------------------------------------------------
# tmux 操作 (tmux呼び出しはすべてsubprocess.runをモック)
# ---------------------------------------------------------------------------


def _fake_completed(returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def test_tmux_session_exists_true(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _fake_completed(returncode=0))
    assert ab.tmux_session_exists("claude") is True


def test_tmux_session_exists_false(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _fake_completed(returncode=1))
    assert ab.tmux_session_exists("claude") is False


def test_tmux_session_exists_handles_missing_tmux(monkeypatch):
    def _raise(*a, **k):
        raise OSError("tmux not found")

    monkeypatch.setattr(subprocess, "run", _raise)
    assert ab.tmux_session_exists("claude") is False


def test_capture_pane_returns_stdout(monkeypatch):
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **k: _fake_completed(returncode=0, stdout="pane text")
    )
    assert ab.capture_pane("claude") == "pane text"


def test_capture_pane_returns_none_on_error(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _fake_completed(returncode=1))
    assert ab.capture_pane("claude") is None


def test_send_choice_rejects_disallowed_session(monkeypatch):
    monkeypatch.setattr(ab, "ALLOWED_SESSIONS", ["claude", "claude3", "main"])
    called = {}

    def _run(*a, **k):
        called["ran"] = True
        return _fake_completed(returncode=0)

    monkeypatch.setattr(subprocess, "run", _run)
    ok, err = ab.send_choice("some-other-session", "1")
    assert ok is False
    assert "許可されていない" in err
    assert "ran" not in called  # tmuxを呼んでいない


def test_send_choice_rejects_invalid_choice(monkeypatch):
    monkeypatch.setattr(ab, "ALLOWED_SESSIONS", ["claude", "claude3", "main"])
    ok, err = ab.send_choice("claude", "9")
    assert ok is False
    assert "不正な選択肢" in err


def test_send_choice_sends_digit_only_no_enter(monkeypatch):
    monkeypatch.setattr(ab, "ALLOWED_SESSIONS", ["claude", "claude3", "main"])
    captured_args = {}

    def _run(args, **kwargs):
        captured_args["args"] = args
        return _fake_completed(returncode=0)

    monkeypatch.setattr(subprocess, "run", _run)
    ok, err = ab.send_choice("claude", "2")
    assert ok is True
    assert err == ""
    assert captured_args["args"] == ["tmux", "send-keys", "-t", "claude", "2"]
    assert "Enter" not in captured_args["args"]


def test_send_choice_honors_env_configured_sessions(monkeypatch):
    # main ではなく approve-test のような任意名でも、環境変数経由の許可リストに入っていれば送れる
    monkeypatch.setattr(ab, "ALLOWED_SESSIONS", ["approve-test"])
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _fake_completed(returncode=0))
    ok, _err = ab.send_choice("approve-test", "1")
    assert ok is True


def test_send_choice_allows_main_session_by_default(monkeypatch):
    # 仕様: デフォルトの許可リストに ありさん本人の対話セッション用 "main" を含む
    monkeypatch.delenv("SLACK_APPROVE_SESSIONS", raising=False)
    monkeypatch.setattr(ab, "ALLOWED_SESSIONS", ab.load_allowed_sessions())
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _fake_completed(returncode=0))
    ok, _err = ab.send_choice("main", "1")
    assert ok is True


def test_send_choice_reports_tmux_failure(monkeypatch):
    monkeypatch.setattr(ab, "ALLOWED_SESSIONS", ["claude"])
    monkeypatch.setattr(
        subprocess, "run",
        lambda *a, **k: _fake_completed(returncode=1, stderr="can't find session"),
    )
    ok, err = ab.send_choice("claude", "1")
    assert ok is False
    assert "can't find session" in err


# ---------------------------------------------------------------------------
# build_prompt_blocks（動的なボタン数・ラベル・JSON value）
# ---------------------------------------------------------------------------


def test_build_prompt_blocks_two_choice_has_two_buttons():
    options = [("1", "Yes"), ("2", "No")]
    blocks, fallback = ab.build_prompt_blocks("claude", "some block", options, "HASH123")
    assert "claude" in fallback
    action_block = next(b for b in blocks if b["type"] == "actions")
    assert len(action_block["elements"]) == 2
    values = [json.loads(el["value"]) for el in action_block["elements"]]
    assert [v["choice"] for v in values] == ["1", "2"]
    assert all(v["session"] == "claude" for v in values)
    assert all(v["hash"] == "HASH123" for v in values)


def test_build_prompt_blocks_three_choice_has_three_buttons_with_distinct_action_ids():
    options = [("1", "Yes"), ("2", "Yes（セッション中ずっと）"), ("3", "No")]
    blocks, _fallback = ab.build_prompt_blocks("claude", "block", options, "HASH")
    action_block = next(b for b in blocks if b["type"] == "actions")
    assert len(action_block["elements"]) == 3
    action_ids = [el["action_id"] for el in action_block["elements"]]
    # Slackは同一メッセージ内でaction_idの重複を許さないため、3つとも別名にする
    assert len(set(action_ids)) == 3


def test_build_prompt_blocks_does_not_render_a_third_button_for_two_choice_prompt():
    # 回帰テスト: 2択のプロンプトなのに固定3ボタンを出すと、
    # 存在しない「3」を押しても実際は違う選択肢が送られてしまうバグがあった
    options = ab.parse_options(ab.find_prompt_block(TWO_CHOICE_PROMPT))
    blocks, _fallback = ab.build_prompt_blocks("claude", "block", options, "HASH")
    action_block = next(b for b in blocks if b["type"] == "actions")
    values = [json.loads(el["value"])["choice"] for el in action_block["elements"]]
    assert values == ["1", "2"]
    assert "3" not in values


def test_build_prompt_blocks_truncates_long_label_for_slack_limit():
    long_label = "No, and do something with a very long explanation " * 3
    options = [("1", "Yes"), ("2", long_label)]
    blocks, _fallback = ab.build_prompt_blocks("claude", "block", options, "HASH")
    action_block = next(b for b in blocks if b["type"] == "actions")
    button_text = action_block["elements"][1]["text"]["text"]
    assert len(button_text) <= ab.SLACK_BUTTON_LABEL_MAX
    value = json.loads(action_block["elements"][1]["value"])
    assert value["label"] == button_text


def test_build_prompt_blocks_includes_prompt_text():
    blocks, _fallback = ab.build_prompt_blocks(
        "claude3", "some prompt text", [("1", "Yes"), ("2", "No")], "HASH"
    )
    section_texts = [
        b["text"]["text"] for b in blocks if b["type"] == "section"
    ]
    assert any("some prompt text" in t for t in section_texts)
    assert any("claude3" in t for t in section_texts)


def test_build_prompt_blocks_stale_marks_header_and_fallback():
    blocks, fallback = ab.build_prompt_blocks(
        "claude", "block", [("1", "Yes"), ("2", "No")], "HASH", stale=True
    )
    assert "待っています" in fallback
    header_text = blocks[0]["text"]["text"]
    assert "待っています" in header_text


# ---------------------------------------------------------------------------
# _handle_approve_choice
# ---------------------------------------------------------------------------


class FakeSlackClient:
    def __init__(self):
        self.posted_ephemeral = []
        self.updated = []
        self.posted_messages = []
        self.deleted = []
        self._next_ts = 1000

    def chat_postEphemeral(self, **kwargs):  # noqa: N802 (Slack SDKのメソッド名に合わせる)
        self.posted_ephemeral.append(kwargs)

    def chat_update(self, **kwargs):
        self.updated.append(kwargs)

    def chat_postMessage(self, **kwargs):  # noqa: N802 (Slack SDKのメソッド名に合わせる)
        self._next_ts += 1
        ts = f"{self._next_ts}.000000"
        self.posted_messages.append({**kwargs, "ts": ts})
        return {"ts": ts}

    def chat_delete(self, **kwargs):
        self.deleted.append(kwargs)
        return {"ok": True}


def _action_body(
    user_id: str, session: str, choice: str, phash: str = "HASH", label: str = "Yes"
) -> dict:
    value = json.dumps({"session": session, "choice": choice, "hash": phash, "label": label})
    return {
        "user": {"id": user_id},
        "actions": [{"value": value}],
        "channel": {"id": "C123"},
        "message": {"ts": "111.222"},
    }


def test_handle_approve_choice_rejects_wrong_user(monkeypatch, tmp_path):
    monkeypatch.setattr(ab, "LOG_FILE", tmp_path / "slack-approve.log")
    monkeypatch.setenv("SLACK_APPROVE_ALLOWED_USER", "UALLOWED")
    monkeypatch.setattr(ab, "ALLOWED_SESSIONS", ["claude"])

    called = {}
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: called.setdefault("ran", True))

    client = FakeSlackClient()
    body = _action_body("USOMEONEELSE", "claude", "1")
    ab._handle_approve_choice(body, client)

    assert "ran" not in called
    assert len(client.posted_ephemeral) == 1
    assert "ありさん" in client.posted_ephemeral[0]["text"]
    assert client.updated == []


def test_handle_approve_choice_accepts_allowed_user(monkeypatch, tmp_path):
    monkeypatch.setattr(ab, "LOG_FILE", tmp_path / "slack-approve.log")
    monkeypatch.setenv("SLACK_APPROVE_ALLOWED_USER", "UALLOWED")
    monkeypatch.setattr(ab, "ALLOWED_SESSIONS", ["claude"])
    monkeypatch.setattr(ab, "compute_current_hash", lambda session: "HASH")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _fake_completed(returncode=0))

    client = FakeSlackClient()
    body = _action_body("UALLOWED", "claude", "1", phash="HASH", label="Yes")
    ab._handle_approve_choice(body, client)

    assert client.posted_ephemeral == []
    assert len(client.updated) == 1
    assert "Yes" in client.updated[0]["text"]
    assert (tmp_path / "slack-approve.log").exists()
    log_content = (tmp_path / "slack-approve.log").read_text()
    assert "[OK]" in log_content


def test_handle_approve_choice_rejects_disallowed_session(monkeypatch, tmp_path):
    monkeypatch.setattr(ab, "LOG_FILE", tmp_path / "slack-approve.log")
    monkeypatch.setenv("SLACK_APPROVE_ALLOWED_USER", "UALLOWED")
    monkeypatch.setattr(ab, "ALLOWED_SESSIONS", ["claude", "claude3", "main"])
    monkeypatch.setattr(ab, "compute_current_hash", lambda session: "HASH")

    called = {}
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: called.setdefault("ran", True))

    client = FakeSlackClient()
    body = _action_body("UALLOWED", "some-random-session", "1", phash="HASH")
    ab._handle_approve_choice(body, client)

    assert "ran" not in called
    assert len(client.updated) == 1
    assert "送信失敗" in client.updated[0]["text"]
    log_content = (tmp_path / "slack-approve.log").read_text()
    assert "[ERROR]" in log_content


def test_handle_approve_choice_no_allowed_user_configured_allows_anyone(monkeypatch, tmp_path):
    # SLACK_APPROVE_ALLOWED_USER が空文字/未設定なら誰でも押せてしまうのは危険なので、
    # 空の場合は許可制限をスキップする現行仕様を明示するテスト（本番では必ず設定される）。
    monkeypatch.setattr(ab, "LOG_FILE", tmp_path / "slack-approve.log")
    monkeypatch.delenv("SLACK_APPROVE_ALLOWED_USER", raising=False)
    monkeypatch.setattr(ab, "ALLOWED_SESSIONS", ["claude"])
    monkeypatch.setattr(ab, "compute_current_hash", lambda session: "HASH")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _fake_completed(returncode=0))

    client = FakeSlackClient()
    body = _action_body("UANYONE", "claude", "3", phash="HASH")
    ab._handle_approve_choice(body, client)

    assert client.posted_ephemeral == []
    assert len(client.updated) == 1


def test_handle_approve_choice_skips_send_when_prompt_no_longer_present(monkeypatch, tmp_path):
    # 送信前の存在照合: ボタン押下時にはもうプロンプトが画面から消えていた場合、送らない
    monkeypatch.setattr(ab, "LOG_FILE", tmp_path / "slack-approve.log")
    monkeypatch.setenv("SLACK_APPROVE_ALLOWED_USER", "UALLOWED")
    monkeypatch.setattr(ab, "ALLOWED_SESSIONS", ["claude"])
    monkeypatch.setattr(ab, "compute_current_hash", lambda session: "SOME-OTHER-HASH")

    called = {}
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: called.setdefault("ran", True))

    client = FakeSlackClient()
    body = _action_body("UALLOWED", "claude", "1", phash="HASH-EXPECTED")
    ab._handle_approve_choice(body, client)

    assert "ran" not in called  # tmux send-keysを呼んでいない
    assert len(client.updated) == 1
    assert "もう画面にありません" in client.updated[0]["text"]
    log_content = (tmp_path / "slack-approve.log").read_text()
    assert "[STALE-SKIP]" in log_content


def test_handle_approve_choice_sends_when_prompt_still_present(monkeypatch, tmp_path):
    monkeypatch.setattr(ab, "LOG_FILE", tmp_path / "slack-approve.log")
    monkeypatch.setenv("SLACK_APPROVE_ALLOWED_USER", "UALLOWED")
    monkeypatch.setattr(ab, "ALLOWED_SESSIONS", ["claude"])
    monkeypatch.setattr(ab, "compute_current_hash", lambda session: "HASH-EXPECTED")

    captured_args = {}

    def _run(args, **kwargs):
        captured_args["args"] = args
        return _fake_completed(returncode=0)

    monkeypatch.setattr(subprocess, "run", _run)

    client = FakeSlackClient()
    body = _action_body("UALLOWED", "claude", "1", phash="HASH-EXPECTED", label="Yes")
    ab._handle_approve_choice(body, client)

    assert captured_args["args"] == ["tmux", "send-keys", "-t", "claude", "1"]
    assert len(client.updated) == 1
    assert "✅ Yes" in client.updated[0]["text"]


def test_handle_approve_choice_ignores_duplicate_message_ts(monkeypatch, tmp_path):
    # 同一message_tsの二重処理防止（連打・Slackの再送対策）
    monkeypatch.setattr(ab, "LOG_FILE", tmp_path / "slack-approve.log")
    monkeypatch.setenv("SLACK_APPROVE_ALLOWED_USER", "UALLOWED")
    monkeypatch.setattr(ab, "ALLOWED_SESSIONS", ["claude"])
    monkeypatch.setattr(ab, "compute_current_hash", lambda session: "HASH")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _fake_completed(returncode=0))

    client = FakeSlackClient()
    body = _action_body("UALLOWED", "claude", "1", phash="HASH")
    ab._handle_approve_choice(body, client)
    ab._handle_approve_choice(body, client)
    ab._handle_approve_choice(body, client)

    assert len(client.updated) == 1  # 2回目以降は無視される
    log_content = (tmp_path / "slack-approve.log").read_text()
    assert log_content.count("[DUPLICATE-CLICK]") == 2


# ---------------------------------------------------------------------------
# poll_once: 見張りループの通知トラッキング（新規投稿・重複抑制）
# ---------------------------------------------------------------------------


def _set_single_session_pane(monkeypatch, session, pane_text_or_none):
    monkeypatch.setattr(ab, "ALLOWED_SESSIONS", [session])
    monkeypatch.setattr(ab, "tmux_session_exists", lambda s: True)
    monkeypatch.setattr(ab, "capture_pane", lambda s: pane_text_or_none)


def test_poll_once_posts_and_tracks_new_prompt(monkeypatch):
    monkeypatch.setenv("SLACK_APPROVE_CHANNEL", "C999")
    _set_single_session_pane(monkeypatch, "claude", PLAIN_STYLE_PROMPT)
    client = FakeSlackClient()

    ab.poll_once(client)

    assert len(client.posted_messages) == 1
    assert len(ab._active_notifications) == 1


def test_poll_once_does_not_repost_while_still_visible(monkeypatch):
    monkeypatch.setenv("SLACK_APPROVE_CHANNEL", "C999")
    _set_single_session_pane(monkeypatch, "claude", PLAIN_STYLE_PROMPT)
    client = FakeSlackClient()

    ab.poll_once(client)
    ab.poll_once(client)

    assert len(client.posted_messages) == 1  # 同じプロンプトが残っている間は再投稿しない


# ---------------------------------------------------------------------------
# poll_once: 死んだ通知の自動削除
# ---------------------------------------------------------------------------


def test_poll_once_auto_deletes_after_two_missing_polls(monkeypatch):
    monkeypatch.setenv("SLACK_APPROVE_CHANNEL", "C999")
    _set_single_session_pane(monkeypatch, "claude", PLAIN_STYLE_PROMPT)
    client = FakeSlackClient()
    ab.poll_once(client)
    assert len(ab._active_notifications) == 1

    monkeypatch.setattr(ab, "capture_pane", lambda s: "nothing here now")

    ab.poll_once(client)  # missing_streak=1、まだ削除しない
    assert client.deleted == []
    assert len(ab._active_notifications) == 1

    ab.poll_once(client)  # missing_streak=2（約10秒相当）、削除する
    assert len(client.deleted) == 1
    assert ab._active_notifications == {}


def test_poll_once_does_not_delete_already_acted_notification(monkeypatch):
    monkeypatch.setenv("SLACK_APPROVE_CHANNEL", "C999")
    _set_single_session_pane(monkeypatch, "claude", PLAIN_STYLE_PROMPT)
    client = FakeSlackClient()
    ab.poll_once(client)
    key = next(iter(ab._active_notifications))
    ab._mark_active_acted(key)

    monkeypatch.setattr(ab, "capture_pane", lambda s: "nothing here now")
    ab.poll_once(client)
    ab.poll_once(client)

    assert client.deleted == []  # Slackで承認済み(✅更新済み)のものは削除しない
    assert ab._active_notifications == {}  # トラッキングだけは終了する


def test_auto_delete_clears_dedupe_cache_for_immediate_renotify(monkeypatch):
    monkeypatch.setenv("SLACK_APPROVE_CHANNEL", "C999")
    _set_single_session_pane(monkeypatch, "claude", PLAIN_STYLE_PROMPT)
    client = FakeSlackClient()
    ab.poll_once(client)
    key = next(iter(ab._active_notifications))

    monkeypatch.setattr(ab, "capture_pane", lambda s: "nothing here now")
    ab.poll_once(client)
    ab.poll_once(client)  # 削除される

    assert key not in ab._dedupe_cache  # 再出現時は新規として即時通知してよい


# ---------------------------------------------------------------------------
# poll_once: しつこいプロンプトの再通知
# ---------------------------------------------------------------------------


def test_stale_prompt_is_renotified_after_threshold(monkeypatch):
    monkeypatch.setenv("SLACK_APPROVE_CHANNEL", "C999")
    _set_single_session_pane(monkeypatch, "claude", PLAIN_STYLE_PROMPT)
    client = FakeSlackClient()
    ab.poll_once(client)
    key = next(iter(ab._active_notifications))
    ab._active_notifications[key]["posted_at"] = time.time() - ab.STALE_RENOTIFY_SEC - 1

    ab.poll_once(client)

    assert len(client.deleted) == 1  # 古い通知を削除
    assert len(client.posted_messages) == 2  # 新規投稿
    assert "待っています" in client.posted_messages[-1]["text"]
    assert key in ab._active_notifications
    assert ab._active_notifications[key]["missing_streak"] == 0


def test_stale_prompt_not_renotified_before_threshold(monkeypatch):
    monkeypatch.setenv("SLACK_APPROVE_CHANNEL", "C999")
    _set_single_session_pane(monkeypatch, "claude", PLAIN_STYLE_PROMPT)
    client = FakeSlackClient()
    ab.poll_once(client)

    ab.poll_once(client)  # まだ閾値未満

    assert client.deleted == []
    assert len(client.posted_messages) == 1


def test_renotified_message_marked_acted_is_not_renotified_again(monkeypatch):
    monkeypatch.setenv("SLACK_APPROVE_CHANNEL", "C999")
    _set_single_session_pane(monkeypatch, "claude", PLAIN_STYLE_PROMPT)
    client = FakeSlackClient()
    ab.poll_once(client)
    key = next(iter(ab._active_notifications))
    ab._active_notifications[key]["posted_at"] = time.time() - ab.STALE_RENOTIFY_SEC - 1
    ab._mark_active_acted(key)

    ab.poll_once(client)

    assert client.deleted == []
    assert len(client.posted_messages) == 1
