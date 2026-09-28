#!/usr/bin/env python3
"""体験デーモン本体。

M5デバイスの /sensors と /status を約0.5秒間隔でポーリングし、
detectors.ExperienceDetector でイベントを検出して JSONL に追記する。

- API（Anthropic/Claude）は一切呼ばない
- デバイスがオフラインでも絶対にクラッシュせず、リトライし続ける
- ランタイム依存は標準ライブラリのみ（urllib.request を使用）

Usage:
    python3 experienced.py --character puchiko
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

from detectors import Event, ExperienceDetector

DATA_DIR = Path(os.getenv("PETIT_DATA_DIR", str(Path.home() / "petit_claude")))

# 実機確認: /sensors, /status とも小さいJSON。0.5秒間隔なら余裕。
POLL_INTERVAL_SEC = 0.5
HTTP_TIMEOUT_SEC = 3.0


def _character_dir(character: str) -> Path:
    return DATA_DIR / "characters" / character


def _load_hosts(character: str) -> list[str]:
    """config.json の m5_hosts（配列、優先）/ m5_host（単体、フォールバック）を読む。"""
    config_path = _character_dir(character) / "config" / "config.json"
    hosts: list[str] = []
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        logging.warning("config.json 読み込み失敗 (%s): %s", config_path, e)
        return hosts
    for h in config.get("m5_hosts", []) or []:
        if h and h not in hosts:
            hosts.append(h)
    single = config.get("m5_host")
    if single and single not in hosts:
        hosts.append(single)
    return hosts


class M5Client:
    """m5-mcp と同じ流儀: 接続に成功したホストを覚えて次回はそちらを優先する。"""

    def __init__(self, hosts: list[str]) -> None:
        self._hosts = hosts
        self._active_host: str | None = None

    def get_json(self, path: str) -> dict | None:
        if not self._hosts:
            return None
        candidates = []
        if self._active_host:
            candidates.append(self._active_host)
        candidates.extend(h for h in self._hosts if h != self._active_host)

        for host in candidates:
            url = f"http://{host}{path}"
            try:
                with urllib.request.urlopen(url, timeout=HTTP_TIMEOUT_SEC) as resp:  # noqa: S310
                    data = json.loads(resp.read().decode("utf-8"))
                self._active_host = host
                return data
            except (urllib.error.URLError, TimeoutError, ValueError, OSError):
                continue
        # 全ホスト失敗。次回のためにアクティブホストは変更しない（そのまま維持）。
        return None


def _experience_dir(character: str) -> Path:
    return _character_dir(character) / "state" / "experience"


def _state_path(character: str) -> Path:
    return _character_dir(character) / "state" / "experience_state.json"


def _append_events(character: str, events: list[Event], now: datetime) -> None:
    if not events:
        return
    exp_dir = _experience_dir(character)
    exp_dir.mkdir(parents=True, exist_ok=True)
    path = exp_dir / f"{now.strftime('%Y%m%d')}.jsonl"
    with path.open("a", encoding="utf-8") as f:
        for event in events:
            f.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")


def _write_state(character: str, state: str, since: datetime) -> None:
    path = _state_path(character)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"state": state, "since": since.isoformat(timespec="seconds")}
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    except OSError as e:
        logging.warning("state ファイル書き込み失敗: %s", e)


def run(character: str) -> None:
    hosts = _load_hosts(character)
    if not hosts:
        logging.warning(
            "m5_host(s) が config.json に見つからない。ホスト無しのまま待機ループに入る。"
        )
    client = M5Client(hosts)
    detector = ExperienceDetector()

    current_state = "awake"
    state_since = datetime.now()
    _write_state(character, current_state, state_since)

    logging.info("experienced 起動: character=%s hosts=%s", character, hosts)

    while True:
        loop_start = time.monotonic()
        now = datetime.now()
        events: list[Event] = []
        new_state = current_state

        sensors = client.get_json("/sensors")
        status = client.get_json("/status")

        try:
            if sensors is None and status is None:
                events += detector.record_poll_failure(now)
                new_state = "offline"
            else:
                events += detector.record_poll_success(now)
                if sensors is not None:
                    events += detector.process_sensors(now, sensors)
                if status is not None:
                    events += detector.process_status(now, status)
                if detector.is_sleeping:
                    new_state = "asleep"
                else:
                    new_state = "awake"
        except Exception:
            # 検出ロジックのバグでデーモンを落とさない。ログだけ残して次サイクルへ。
            logging.exception("検出処理中に予期しないエラー。このサイクルはスキップして継続する。")
            events = []
            new_state = current_state

        if new_state != current_state:
            current_state = new_state
            state_since = now
            _write_state(character, current_state, state_since)

        try:
            _append_events(character, events, now)
        except OSError:
            logging.exception("JSONL 書き込み失敗。次サイクルへ継続する。")

        elapsed = time.monotonic() - loop_start
        time.sleep(max(0.0, POLL_INTERVAL_SEC - elapsed))


def main() -> int:
    parser = argparse.ArgumentParser(description="体験デーモン（ローカル常駐・API呼び出しゼロ）")
    parser.add_argument("--character", required=True, help="キャラクターID（例: puchiko）")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    try:
        run(args.character)
    except KeyboardInterrupt:
        logging.info("停止シグナル受信、終了する")
    return 0


if __name__ == "__main__":
    sys.exit(main())
