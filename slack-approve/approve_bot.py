#!/usr/bin/env python3
"""slack-approve — tmux上のClaude Codeの許可プロンプトをSlackから承認するボット。

1プロセスで2つの役割を持つ:

- 見張りスレッド: 数秒おきに対象tmuxセッションの画面末尾を `tmux capture-pane` で取得し、
  「Do you want to ...?」型の許可プロンプトを検出したらSlackチャンネルに通知
  （Block Kit、実際にプロンプトに存在する選択肢の数・ラベルに合わせた動的なボタン付き）を投稿する。
  同一プロンプトは一定時間（デフォルト10分）は再通知しない。
  さらに、投稿済みの通知は継続的に追跡し:
    - 画面から消えたことが2周連続（約10秒）で確認できたら、通知を自動削除する
      （Slackから承認済みのものは削除しない）。
    - 5分以上画面に残り続けて未応答なら、古い通知を削除して「⏰ まだ待っています」付きで
      再通知する。
- Socket Modeハンドラ: Slackのボタンが押されたら、許可された本人の操作か確認したうえで、
  送信前にそのセッションのpaneを再captureして同じプロンプトがまだ画面にあるかを照合し、
  一致した場合のみ `tmux send-keys` で選択肢の番号だけを送信し（Enterは送らない）、
  元メッセージを更新する。同一メッセージの二重処理（連打・Slackの再送）はin-memoryで防ぐ。

API（Anthropic/Claude）は一切呼ばない。tmux と Slack だけとやり取りする。

Usage:
    uv run python approve_bot.py
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

# ---------------------------------------------------------------------------
# 環境変数の読み込み（カレントディレクトリの .env を先に、無ければ petit_claude/.env で補完）
# ---------------------------------------------------------------------------

DATA_DIR = Path(os.getenv("PETIT_DATA_DIR", str(Path.home() / "petit_claude")))

load_dotenv()  # カレントディレクトリの .env（あれば）
load_dotenv(DATA_DIR / ".env")  # 本番の認証情報はここ

LOG_FILE = DATA_DIR / ".autonomous-logs" / "slack-approve.log"

# ---------------------------------------------------------------------------
# 設定
# ---------------------------------------------------------------------------

POLL_INTERVAL_SEC = 5.0
DEDUPE_WINDOW_SEC = 600.0  # 同一プロンプトは10分再通知しない（新規出現時のみ。下記の設計メモ参照）
MAX_DISPLAY_LINES = 40  # Slackに貼るプロンプト本文の末尾行数
MAX_DISPLAY_CHARS = 2900  # Slackのcode block用に念のため文字数でも切る
SOCKET_RETRY_SEC = 5.0
SLACK_BUTTON_LABEL_MAX = 75  # Slackのplain_textボタンのラベル文字数上限

# 「画面から消えた」と判定するまでの連続未検出回数（POLL_INTERVAL_SEC=5秒前提で約10秒）
MISSING_STREAK_THRESHOLD = 2
# 同じプロンプトが画面に残り続けたまま未応答の場合、再通知するまでの秒数
STALE_RENOTIFY_SEC = 300.0

# parse_optionsが万一何も拾えなかった場合の保険（実際にはfind_prompt_blockが
# 「1. Yes」＋「No」を含む選択肢の存在を保証しているので、通常はここに来ない）
DEFAULT_OPTIONS: list[tuple[str, str]] = [
    ("1", "Yes"),
    ("2", "Yes（セッション中ずっと）"),
    ("3", "No"),
]

# ---------------------------------------------------------------------------
# dedupe と アクティブ通知トラッキングの役割分担（設計メモ）
# ---------------------------------------------------------------------------
# - `_dedupe_cache`（should_notify）: **新規に**Slackへ投稿するときだけ参照する時間窓ガード。
#   「一度消えたプロンプトが再出現した」場合の連投防止に使う（10分）。
# - `_active_notifications`: **投稿済みで未解決**のプロンプトを画面がある限り追跡する。
#   同じプロンプトが画面に残っている間はこちらだけを見て「既に通知済みなので再投稿しない」を
#   判断する（時間窓は使わない＝解決 or 消滅するまで無期限）。5分居座ったら再通知、
#   2周連続で消えたら自動削除、を担当する。
# - 通知が自動削除されたとき（画面から消えたことを確認できた）は `_dedupe_cache` の該当エントリも
#   消す。これにより「一度消えたものが再出現」した場合は待たずに新規通知として扱える。
#   一方、Slackボタンで承認済み（acted）の場合は `_dedupe_cache` を消さない。tmuxの画面更新が
#   1テンポ遅れて古い内容がまだ見えている間に誤って即再通知してしまうのを防ぐため。


def load_allowed_sessions() -> list[str]:
    """見張り対象 兼 send-keys許可対象のtmuxセッション名一覧を環境変数から読む。

    SLACK_APPROVE_SESSIONS（カンマ区切り）。未設定時は "claude,claude3,main"。
    """
    raw = os.getenv("SLACK_APPROVE_SESSIONS", "claude,claude3,main")
    sessions = [s.strip() for s in raw.split(",") if s.strip()]
    return sessions or ["claude", "claude3", "main"]


ALLOWED_SESSIONS = load_allowed_sessions()

# ---------------------------------------------------------------------------
# 許可プロンプト検出
# ---------------------------------------------------------------------------

# 行頭の枠線(│)やカーソル(❯)・空白などの飾りを許容しつつ「N. Yes」「N. No」を拾う。
# Claude Codeの実際のUIは箱の中に
#   ❯ 1. Yes
#     2. Yes, and don't ask again this session
#     3. No, and tell Claude what to do differently
# のように表示されるが、枠線の有無や選択肢の順序変化に強くするため
# 行頭の非単語文字（空白・│・❯ 等）はまとめて読み飛ばす。
# 実際の選択肢は2択（1. Yes / 2. No）のこともあるため、検出条件自体は
# 「1. Yes」と「Noを含む選択肢」が両方あるかだけを見る（ボタンの数はparse_optionsが動的に決める）。
OPTION_RE = re.compile(r"^[^\w\n]*(\d)\.\s*(Yes|No)\b", re.MULTILINE)
QUESTION_RE = re.compile(r"Do you want")
CURSOR_RE = re.compile(r"❯")

# parse_options用: 番号付き選択肢の行（番号＋ラベル）を拾う。OPTION_REと違い番号は複数桁も許容。
OPTION_LINE_RE = re.compile(r"^[^\w\n]*(\d+)\.\s*(.+)$")
# ラベル末尾の枠線・罫線・余白を落とす（箱スタイルUIの右側の│などを除去するため）
_TRAILING_DECORATION_RE = re.compile(r"[\s│┃║╎╏╭╮╯╰─━┄┈]+$")


def find_prompt_block(pane_text: str | None) -> str | None:
    """pane_textの中に許可プロンプトが見えるなら、末尾の空行を落としたブロックを返す。

    検出条件（すべて満たす場合のみ）:
    - 「1. Yes」の行がある
    - 「2. No」または「3. No」の行がある（選択肢の一部としてのNo）
    - 加えて「Do you want」という文言、または選択カーソル「❯」のどちらかが存在する
    """
    if not pane_text:
        return None

    matches = OPTION_RE.findall(pane_text)
    has_yes_option1 = any(num == "1" and label == "Yes" for num, label in matches)
    has_no_option = any(label == "No" for _num, label in matches)
    if not (has_yes_option1 and has_no_option):
        return None
    if not (QUESTION_RE.search(pane_text) or CURSOR_RE.search(pane_text)):
        return None

    lines = pane_text.split("\n")
    while lines and lines[-1].strip() == "":
        lines.pop()
    if not lines:
        return None
    return "\n".join(lines)


def parse_options(block: str) -> list[tuple[str, str]]:
    """許可プロンプトのブロックから「番号. ラベル」形式の選択肢を実際の内容で抽出する。

    実際のプロンプトが2択（1. Yes / 2. No）でも3択でも、画面にある選択肢だけを返す。
    重複した番号は最初の1件のみ採用し、ラベルは枠線・末尾の余白を取り除く。
    """
    options: list[tuple[str, str]] = []
    seen: set[str] = set()
    for line in block.split("\n"):
        m = OPTION_LINE_RE.match(line)
        if not m:
            continue
        num, raw_label = m.group(1), m.group(2)
        if num in seen:
            continue
        label = _TRAILING_DECORATION_RE.sub("", raw_label).strip()
        if not label:
            continue
        options.append((num, label))
        seen.add(num)
    return options


def truncate_block(block: str, max_lines: int = MAX_DISPLAY_LINES) -> str:
    """表示・ハッシュ化用に末尾max_lines行・MAX_DISPLAY_CHARS文字に切り詰める。"""
    lines = block.split("\n")
    if len(lines) > max_lines:
        lines = lines[-max_lines:]
    text = "\n".join(lines)
    if len(text) > MAX_DISPLAY_CHARS:
        text = text[-MAX_DISPLAY_CHARS:]
    return text


def prompt_hash(session: str, display_block: str) -> str:
    """dedupe用のハッシュ。セッション名＋表示ブロックの内容から決める。"""
    payload = f"{session}\n{display_block}".encode()
    return hashlib.sha256(payload).hexdigest()


def compute_current_hash(session: str) -> str | None:
    """このセッションの画面に今も許可プロンプトが見えているなら、そのハッシュを返す。

    poll_once と全く同じ手順（capture→検出→truncate→hash）で計算するため、
    ボタンのvalueに埋め込まれたハッシュと直接比較できる（送信前の存在照合に使う）。
    見えていなければNone。
    """
    if not tmux_session_exists(session):
        return None
    pane = capture_pane(session)
    block = find_prompt_block(pane)
    if block is None:
        return None
    return prompt_hash(session, truncate_block(block))


# ---------------------------------------------------------------------------
# dedupe（同一プロンプトの再通知抑制。新規投稿時のみ使用。上の設計メモ参照）
# ---------------------------------------------------------------------------

_dedupe_lock = threading.Lock()
_dedupe_cache: dict[str, float] = {}


def should_notify(prompt_key: str, now: float, window_sec: float = DEDUPE_WINDOW_SEC) -> bool:
    """同じprompt_keyがwindow_sec以内に通知済みならFalse。通知したらキャッシュを更新する。"""
    with _dedupe_lock:
        last = _dedupe_cache.get(prompt_key)
        if last is not None and (now - last) < window_sec:
            return False
        _dedupe_cache[prompt_key] = now
        return True


# ---------------------------------------------------------------------------
# アクティブ通知トラッキング（死んだ通知の自動削除・しつこいプロンプトの再通知用）
# ---------------------------------------------------------------------------
# キー: prompt_hash / 値: {session, channel, message_ts, posted_at, missing_streak, acted}

_active_lock = threading.Lock()
_active_notifications: dict[str, dict] = {}

# 同一message_tsの二重処理防止（連打・Slackの再送対策）
_processed_lock = threading.Lock()
_processed_message_ts: set[str] = set()


def mark_message_processed(message_ts: str | None) -> bool:
    """同一message_tsのボタン操作を一度しか処理しないようにする。

    初めて見るmessage_tsならTrue（処理してよい）を返して記録する。
    既に処理済みならFalse。message_tsが無い場合は判定できないのでTrue（処理してよい）を返す。
    """
    if not message_ts:
        return True
    with _processed_lock:
        if message_ts in _processed_message_ts:
            return False
        _processed_message_ts.add(message_ts)
        return True


def _mark_active_acted(key: str) -> None:
    """Slackボタンで応答済み（承認 or 送信スキップ確定）になったことを記録する。

    以後、見張りループの自動削除・再通知の対象から外れる
    （メッセージは既にハンドラ側で最終状態に更新済みのため）。
    """
    with _active_lock:
        record = _active_notifications.get(key)
        if record is not None:
            record["acted"] = True


# ---------------------------------------------------------------------------
# tmux 操作
# ---------------------------------------------------------------------------


def tmux_session_exists(session: str) -> bool:
    try:
        result = subprocess.run(
            ["tmux", "has-session", "-t", session],
            capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def capture_pane(session: str) -> str | None:
    """tmux capture-pane -pt <session> の出力（画面に見えている末尾部分）を返す。"""
    try:
        result = subprocess.run(
            ["tmux", "capture-pane", "-pt", session],
            capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def send_choice(session: str, choice: str) -> tuple[bool, str]:
    """許可された選択肢の番号だけをtmuxセッションに送る（Enterは送らない）。

    session が ALLOWED_SESSIONS に無い、または choice が 1/2/3 以外なら拒否する。
    """
    if session not in ALLOWED_SESSIONS:
        return False, f"許可されていないセッション: {session}"
    if choice not in {"1", "2", "3"}:
        return False, f"不正な選択肢: {choice}"
    try:
        result = subprocess.run(
            ["tmux", "send-keys", "-t", session, choice],
            capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, str(e)
    if result.returncode != 0:
        return False, (result.stderr.strip() or "tmux send-keys がエラーを返した")
    return True, ""


# ---------------------------------------------------------------------------
# 操作ログ
# ---------------------------------------------------------------------------


def log_action(line: str) -> None:
    """操作ログを ~/petit_claude/.autonomous-logs/slack-approve.log に追記する。"""
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(f"{ts} {line}\n")
    except OSError:
        logging.exception("操作ログの書き込みに失敗した")


# ---------------------------------------------------------------------------
# Slack Block Kit
# ---------------------------------------------------------------------------


def _build_button(num: str, label: str, phash: str, session: str, idx: int) -> dict:
    display_label = label
    if len(display_label) > SLACK_BUTTON_LABEL_MAX:
        display_label = display_label[: SLACK_BUTTON_LABEL_MAX - 3] + "..."
    button: dict = {
        "type": "button",
        "text": {"type": "plain_text", "text": display_label},
        "action_id": f"approve_choice_{num}",
        "value": json.dumps(
            {"session": session, "choice": num, "hash": phash, "label": display_label}
        ),
    }
    # 先頭の選択肢（通常「Yes」）は目立たせ、「No」で始まる選択肢は危険色にする。
    if idx == 0:
        button["style"] = "primary"
    elif label.strip().lower().startswith("no"):
        button["style"] = "danger"
    return button


def build_prompt_blocks(
    session: str,
    display_block: str,
    options: list[tuple[str, str]],
    phash: str,
    *,
    stale: bool = False,
) -> tuple[list[dict], str]:
    """実際にプロンプトに存在する選択肢の数・ラベルに合わせてボタンを組み立てる。"""
    if stale:
        fallback_text = f"⏰ [{session}] まだ待っています"
        header_text = f"⏰ *まだ待っています* — セッション `{session}`"
    else:
        fallback_text = f"[{session}] Claude Codeが許可待ちです"
        header_text = f"*許可プロンプト検出* — セッション `{session}`"

    blocks = [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": header_text},
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"```{display_block}```"},
        },
        {
            "type": "actions",
            "block_id": f"approve_actions_{session}",
            "elements": [
                _build_button(num, label, phash, session, idx)
                for idx, (num, label) in enumerate(options)
            ],
        },
    ]
    return blocks, fallback_text


# ---------------------------------------------------------------------------
# 見張りループ
# ---------------------------------------------------------------------------


def post_prompt_notification(
    client,
    session: str,
    block: str,
    display_block: str,
    key: str,
    options: list[tuple[str, str]],
    *,
    stale: bool = False,
) -> dict | None:
    """Slackに許可プロンプト通知を投稿する。成功したら {channel, message_ts} を返す。"""
    channel = os.getenv("SLACK_APPROVE_CHANNEL")
    if not channel:
        logging.error("SLACK_APPROVE_CHANNEL が設定されていない。通知をスキップする。")
        return None
    blocks, fallback = build_prompt_blocks(session, display_block, options, key, stale=stale)
    resp = client.chat_postMessage(channel=channel, text=fallback, blocks=blocks)
    message_ts = resp["ts"]
    logging.info(
        "許可プロンプトを検出、Slackに通知した: session=%s stale=%s", session, stale
    )
    return {"channel": channel, "message_ts": message_ts}


def _delete_dead_notification(client, key: str, record: dict) -> None:
    """画面から消えたことを確認できた通知をSlackから削除する。"""
    try:
        client.chat_delete(channel=record["channel"], ts=record["message_ts"])
        log_action(
            f"[AUTO-DELETE] session={record['session']} hash={key[:12]} reason=vanished"
        )
    except Exception:
        logging.exception(
            "死んだ通知の削除に失敗した: session=%s", record.get("session")
        )
    finally:
        # 消滅を確認済みなので、再出現した場合は待たずに新規通知として扱ってよい。
        with _dedupe_lock:
            _dedupe_cache.pop(key, None)


def _sweep_vanished_notifications(client, seen_hashes: set[str]) -> None:
    """今回のポーリングで画面に見えなかったアクティブ通知を処理する。

    2周連続（約MISSING_STREAK_THRESHOLD*POLL_INTERVAL_SEC秒）で見えなかったら
    「死んだ通知」とみなしてSlackから削除する。Slackから既に承認済み（acted=True）の
    ものは、既にメッセージが✅などに更新済みなので削除しない（トラッキングだけ終了する）。

    注意: 対象tmuxセッション内でウィンドウを切り替えると capture-pane が別ウィンドウの
    内容を返すようになり、実際には消えていない許可プロンプトが「見えなくなった」と
    誤検知されることがある。誤って自動削除してもtmux側の状態（画面の実際のプロンプト）
    には影響しないため実害は限定的だが、ウィンドウ切り替えを伴う運用が増えるなら
    MISSING_STREAK_THRESHOLD を上げるなどの対応を検討すること。
    """
    with _active_lock:
        keys = list(_active_notifications.keys())

    for key in keys:
        record_to_delete: dict | None = None
        with _active_lock:
            record = _active_notifications.get(key)
            if record is None or key in seen_hashes:
                continue
            if record.get("acted"):
                del _active_notifications[key]
                continue
            record["missing_streak"] = record.get("missing_streak", 0) + 1
            if record["missing_streak"] >= MISSING_STREAK_THRESHOLD:
                record_to_delete = record
                del _active_notifications[key]
        if record_to_delete is not None:
            _delete_dead_notification(client, key, record_to_delete)


def _maybe_renotify_if_stale(
    client, key: str, session: str, block: str, display_block: str, now: float
) -> None:
    """同じプロンプトがSTALE_RENOTIFY_SEC以上画面に残り続けて未応答なら再通知する。

    古い通知は削除してから新規投稿し直す（「⏰ まだ待っています」付き）。
    内容は変わっていない前提なのでprompt_hash自体は同じキーのまま使い回す。
    """
    with _active_lock:
        record = _active_notifications.get(key)
        if record is None or record.get("acted"):
            return
        elapsed = now - record["posted_at"]
        if elapsed < STALE_RENOTIFY_SEC:
            return
        old_channel = record["channel"]
        old_ts = record["message_ts"]

    try:
        client.chat_delete(channel=old_channel, ts=old_ts)
    except Exception:
        logging.exception("再通知前の旧メッセージ削除に失敗した: session=%s", session)

    try:
        options = parse_options(display_block) or DEFAULT_OPTIONS
        posted = post_prompt_notification(
            client, session, block, display_block, key, options, stale=True
        )
    except Exception:
        logging.exception("再通知の投稿に失敗した: session=%s", session)
        return
    if posted is None:
        return

    with _active_lock:
        current = _active_notifications.get(key)
        if current is None:
            return
        current["channel"] = posted["channel"]
        current["message_ts"] = posted["message_ts"]
        current["posted_at"] = now
        current["missing_streak"] = 0

    log_action(f"[STALE-RENOTIFY] session={session} hash={key[:12]} elapsed={elapsed:.0f}s")


def poll_once(client) -> None:
    now = time.time()
    seen_hashes: set[str] = set()

    for session in ALLOWED_SESSIONS:
        if not tmux_session_exists(session):
            continue
        pane = capture_pane(session)
        block = find_prompt_block(pane)
        if block is None:
            continue

        display_block = truncate_block(block)
        key = prompt_hash(session, display_block)
        seen_hashes.add(key)

        with _active_lock:
            record = _active_notifications.get(key)

        if record is not None:
            with _active_lock:
                record["missing_streak"] = 0
            _maybe_renotify_if_stale(client, key, session, block, display_block, now)
            continue

        if not should_notify(key, now):
            continue

        try:
            options = parse_options(display_block) or DEFAULT_OPTIONS
            posted = post_prompt_notification(
                client, session, block, display_block, key, options
            )
        except Exception:
            logging.exception("Slackへの通知投稿に失敗した: session=%s", session)
            continue
        if posted is None:
            continue
        with _active_lock:
            _active_notifications[key] = {
                "session": session,
                "channel": posted["channel"],
                "message_ts": posted["message_ts"],
                "posted_at": now,
                "missing_streak": 0,
                "acted": False,
            }

    _sweep_vanished_notifications(client, seen_hashes)


def poll_loop(client) -> None:
    logging.info("見張りループ開始。対象セッション=%s", ALLOWED_SESSIONS)
    while True:
        try:
            poll_once(client)
        except Exception:
            logging.exception("見張りループで予期しないエラーが発生した。継続する。")
        time.sleep(POLL_INTERVAL_SEC)


# ---------------------------------------------------------------------------
# Slack アクションハンドラ
# ---------------------------------------------------------------------------


def _parse_action_value(value: str) -> dict | None:
    """ボタンのvalue（JSON文字列）をパースする。パースできなければNone。"""
    try:
        data = json.loads(value)
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    return data


def _handle_approve_choice(body: dict, client) -> None:
    actions = body.get("actions") or []
    if not actions:
        return
    raw_value = actions[0].get("value", "")
    payload = _parse_action_value(raw_value)
    channel_id = (body.get("channel") or {}).get("id")
    message_ts = (body.get("message") or {}).get("ts")
    user_id = (body.get("user") or {}).get("id", "")

    if payload is None:
        logging.error("approve_choiceのvalueをパースできない: %r", raw_value)
        return

    if not mark_message_processed(message_ts):
        log_action(f"[DUPLICATE-CLICK] message_ts={message_ts} user={user_id}")
        return

    session = str(payload.get("session", ""))
    choice = str(payload.get("choice", ""))
    expected_hash = str(payload.get("hash", ""))
    label = str(payload.get("label", choice))

    allowed_user = os.getenv("SLACK_APPROVE_ALLOWED_USER", "")
    if allowed_user and user_id != allowed_user:
        log_action(f"[DENY-USER] user={user_id} session={session} choice={choice}")
        if channel_id:
            try:
                client.chat_postEphemeral(
                    channel=channel_id, user=user_id, text="ありさんだけが押せます"
                )
            except Exception:
                logging.exception("chat_postEphemeral に失敗した")
        return

    # 送信前の存在照合: 押された時点でもそのプロンプトがまだ画面にあるか確認してから送る。
    # tmux上でプロンプトが既に消えている（ユーザーが手元で答えた・別の入力が進んだ等）のに
    # 数字だけ送ってしまうと、入力欄に意図しない数字が残ってしまうバグがあったための対策。
    current_hash = compute_current_hash(session)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if current_hash != expected_hash:
        text = f"⌛ このプロンプトはもう画面にありません（送信しませんでした） ({now_str})"
        log_action(
            f"[STALE-SKIP] user={user_id} session={session} choice={choice} "
            f"hash={expected_hash[:12]}"
        )
        _mark_active_acted(expected_hash)
        if channel_id and message_ts:
            try:
                client.chat_update(
                    channel=channel_id,
                    ts=message_ts,
                    text=text,
                    blocks=[{"type": "section", "text": {"type": "mrkdwn", "text": text}}],
                )
            except Exception:
                logging.exception("chat_update に失敗した")
        return

    ok, err = send_choice(session, choice)

    if ok:
        text = f"✅ {label} で承認 ({now_str})"
        log_action(f"[OK] user={user_id} session={session} choice={choice} label={label}")
    else:
        text = f"⚠️ 送信失敗: {err} ({now_str})"
        log_action(f"[ERROR] user={user_id} session={session} choice={choice} error={err}")

    _mark_active_acted(expected_hash)

    if channel_id and message_ts:
        try:
            client.chat_update(
                channel=channel_id,
                ts=message_ts,
                text=text,
                blocks=[{"type": "section", "text": {"type": "mrkdwn", "text": text}}],
            )
        except Exception:
            logging.exception("chat_update に失敗した")


def build_app() -> App:
    bot_token = os.getenv("SLACK_APPROVE_BOT_TOKEN")
    if not bot_token:
        raise RuntimeError("SLACK_APPROVE_BOT_TOKEN が設定されていない")
    app = App(token=bot_token)

    @app.action(re.compile(r"^approve_choice_\d+$"))
    def _on_approve_choice(ack, body, client):
        ack()
        try:
            _handle_approve_choice(body, client)
        except Exception:
            logging.exception("approve_choice ハンドラで予期しないエラーが発生した")

    return app


def run_socket_mode(app: App, app_token: str) -> None:
    """Socket Modeで待ち受ける。切断・例外時は自動的に張り直す。"""
    while True:
        try:
            handler = SocketModeHandler(app, app_token)
            logging.info("Socket Mode 接続を開始する")
            handler.start()  # ブロックする。内部で切断時の再接続も行う。
            logging.warning("Socket Mode handler.start() が返った。再接続する。")
        except KeyboardInterrupt:
            raise
        except Exception:
            logging.exception("Socket Mode 接続でエラーが発生した。%s秒後に再試行する。",
                               SOCKET_RETRY_SEC)
        time.sleep(SOCKET_RETRY_SEC)


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    app_token = os.getenv("SLACK_APPROVE_APP_TOKEN")
    if not app_token:
        logging.error("SLACK_APPROVE_APP_TOKEN が設定されていない")
        return 1
    if not os.getenv("SLACK_APPROVE_CHANNEL"):
        logging.warning("SLACK_APPROVE_CHANNEL が設定されていない。通知は投稿されない。")

    try:
        app = build_app()
    except RuntimeError:
        logging.exception("起動に失敗した")
        return 1

    thread = threading.Thread(target=poll_loop, args=(app.client,), daemon=True)
    thread.start()

    try:
        run_socket_mode(app, app_token)
    except KeyboardInterrupt:
        logging.info("停止シグナル受信、終了する")
    return 0


if __name__ == "__main__":
    sys.exit(main())
