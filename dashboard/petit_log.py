"""ぷちログ(その子の 1 日のタイムライン)と、日記の一覧。

家にいまあるもの(会話の記録・記憶・ノート・アルバム・ボイスメモ・メールボックス・自律行動の記録・
体の出来事)から組み立てるだけで、新しく何も書かない。形は里親さん側の「ぷちろぐ」にそろえる:

- 日ごとに区切り、日の中は新しい順
- 会話は、だれと・いつ・何回だけ。中身は返さない
- 体のことは「体に起きたこと」(持ち上げられた・置かれた・触られた・眠った・起きた)だけ。
  明るさの変わり目・つながらなかった時間・電池の知らせは出さない
- ひとりの時間(自律行動 1 回)の幅に入る行には alone: true を付ける
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import date as Date
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

TALK_GAP_S = 30 * 60      # 同じ相手との会話で、これだけ空いたら別のひとまとまり
BODY_GROUP_S = 10 * 60    # 同じ体の出来事が続くときに、1 件にまとめる間隔
ALONE_MAX_S = 30 * 60     # ひとりの時間 1 回の長さの上限(記録の終わりが分からないとき用)
DAYS_MAX = 7              # 1 回に返す日数の上限
LOOKBACK_DAYS = 31        # 1 回の読みで、さかのぼって探す日数の上限(空の日が続くとき)
MAIL_TEXT_MAX = 120
MEMORY_TEXT_MAX = 400
DIARY_HEAD_MAX = 120

BODY_WORDS = {"picked_up": "持ち上げられた", "put_down": "置かれた", "touch": "触られた", "sleep": "眠った", "woken": "起きた"}
_AUDIO_EXTS = {".wav", ".mp3", ".webm", ".ogg", ".m4a", ".mp4"}
_WEEKDAYS = "月火水木金土日"


@dataclass
class Sources:
    """1 人ぶんの置き場所。名前の引き方は呼ぶ側(main.py)が渡す"""
    char_id: str
    char_dir: Path            # characters/<id>/
    album_dir: Path           # photo_album/<id>/
    voice_dir: Path           # voice_memo/<id>/
    mailbox_dir: Path         # mailbox/
    auto_log_dir: Path        # .autonomous-logs/<id>/
    memory_db: Path
    user_label: Callable[[str], str]   # 人の id → 表示名
    name_of: Callable[[str], str]      # ぷち・人の id → 表示名(メールの宛先)


def _local(ts: str) -> datetime | None:
    """ISO の時刻 → この PC の時刻(タイムゾーンなし)。読めなければ None"""
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None
    return dt.astimezone().replace(tzinfo=None) if dt.tzinfo else dt


def _stamp(name: str) -> datetime | None:
    """ファイル名の先頭 YYYYMMDD_HHMMSS(か YYYYMMDD_HHMM)→ 時刻"""
    parts = name.split("_")
    if len(parts) < 2 or len(parts[0]) != 8 or not parts[0].isdigit():
        return None
    t = "".join(ch for ch in parts[1] if ch.isdigit())[:6]
    if len(t) < 4:
        return None
    try:
        return datetime.strptime(parts[0] + t.ljust(6, "0"), "%Y%m%d%H%M%S")
    except ValueError:
        return None


def _title_from(name: str, char_id: str) -> str:
    """YYYYMMDD_HHMMSS_<id>_<題>.<ext> の題"""
    stem = Path(name).stem
    parts = stem.split("_")
    rest = parts[2:]
    if rest and rest[0] == char_id:
        rest = rest[1:]
    return "_".join(rest)


def _files(d: Path) -> list[Path]:
    try:
        return [f for f in d.iterdir() if f.is_file()]
    except OSError:
        return []


class _Index:
    """1 回の読みのあいだだけ持つ、日付ごとの束。ファイル名の一覧と会話の記録は 1 回だけ読む"""

    def __init__(self, src: Sources):
        self.src = src
        self.by_day: dict[Date, list[dict]] = {}
        self.runs: dict[Date, list[tuple[datetime, datetime]]] = {}
        self._chat()
        self._album()
        self._voice()
        self._mail()
        self._notes()
        self._alone()

    def _add(self, ts: datetime, **item) -> None:
        item["_ts"] = ts
        self.by_day.setdefault(ts.date(), []).append(item)

    def _chat(self) -> None:
        """会話: 相手ごとに、30 分空くまでをひとまとまりにして、何回話しかけられたかを数える"""
        src = self.src
        for f in _files(src.char_dir / "chat_histories"):
            if not (f.name.startswith("chat_history") and f.suffix == ".json"):
                continue
            who_id = f.stem[len("chat_history_"):] if f.stem.startswith("chat_history_") else "arisan"
            try:
                log = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            cur: dict | None = None
            for m in log if isinstance(log, list) else []:
                ts = _local(m.get("timestamp", "")) if isinstance(m, dict) else None
                if ts is None:
                    continue
                group = bool(m.get("via"))
                if cur and cur["group"] == group and (ts - cur["end"]).total_seconds() <= TALK_GAP_S and ts.date() == cur["start"].date():
                    cur["end"] = ts
                else:
                    cur = {"start": ts, "end": ts, "group": group, "count": 0}
                    who = src.user_label(who_id)
                    self._add(ts, kind="talk", who=who, group=group, _run=cur)
                if m.get("role") == "user":
                    cur["count"] += 1

    def _album(self) -> None:
        src = self.src
        for f in _files(src.album_dir):
            ts = _stamp(f.name)
            if ts and f.suffix.lower() == ".jpg":
                self._add(ts, kind="photo", title=_title_from(f.name, src.char_id), url=f"/api/album/{src.char_id}/{f.name}")

    def _voice(self) -> None:
        src = self.src
        for f in _files(src.voice_dir):
            ts = _stamp(f.name)
            if ts and f.suffix.lower() in _AUDIO_EXTS:
                self._add(ts, kind="voice", title=_title_from(f.name, src.char_id), url=f"/api/voice_memo/{src.char_id}/{f.name}")

    def _mail(self) -> None:
        """その子が書いたメール(from_<id>_to_<宛先>_YYYYMMDD_HHMM….md)。本文は、出す日のぶんだけあとで読む"""
        src = self.src
        prefix = f"from_{src.char_id}_to_"
        for f in _files(src.mailbox_dir):
            if not (f.name.startswith(prefix) and f.suffix == ".md"):
                continue
            rest = f.stem[len(prefix):].split("_")
            i = next((k for k, p in enumerate(rest) if len(p) == 8 and p.isdigit()), -1)
            if i < 1:
                continue
            ts = _stamp("_".join(rest[i:]))
            if ts:
                self._add(ts, kind="mail", to=src.name_of("_".join(rest[:i])), _file=f)

    def _notes(self) -> None:
        """ノートは、最後に書いた・直した日にだけ出る(更新時刻)"""
        for f in _files(self.src.char_dir / "notes"):
            if f.suffix != ".md":
                continue
            try:
                ts = datetime.fromtimestamp(f.stat().st_mtime)
            except OSError:
                continue
            self._add(ts, kind="note", name=f.stem)

    def _alone(self) -> None:
        """ひとりの時間 = 自律行動 1 回(YYYYMMDD_HHMMSS_stream.jsonl)。終わりは記録の更新時刻"""
        for f in _files(self.src.auto_log_dir):
            parts = f.name.split("_")
            if len(parts) != 3 or parts[2] != "stream.jsonl":   # chat_stream・mic_stream などは別もの
                continue
            ts = _stamp(f.name)
            if ts is None:
                continue
            try:
                if f.stat().st_size == 0:
                    continue
                end = datetime.fromtimestamp(f.stat().st_mtime)
            except OSError:
                continue
            end = min(max(end, ts), ts + timedelta(seconds=ALONE_MAX_S))
            self.runs.setdefault(ts.date(), []).append((ts, end))
            self._add(ts, kind="alone", _end=end)

    def _memories(self, day: Date) -> list[dict]:
        if not self.src.memory_db.exists():
            return []
        try:
            conn = sqlite3.connect(f"file:{self.src.memory_db}?mode=ro", uri=True)
            rows = conn.execute(
                "SELECT content, timestamp, category, emotion FROM memories WHERE timestamp LIKE ? ORDER BY timestamp DESC",
                (f"{day.isoformat()}%",),
            ).fetchall()
            conn.close()
        except sqlite3.Error:
            return []
        out = []
        for content, ts_raw, category, emotion in rows:
            ts = _local(ts_raw or "")
            if ts is None:
                continue
            text = content or ""
            out.append({"_ts": ts, "kind": "memory", "text": text[:MEMORY_TEXT_MAX], "more": len(text) > MEMORY_TEXT_MAX,
                        "category": category or "", "emotion": emotion or ""})
        return out

    def _body(self, day: Date) -> list[dict]:
        """体に起きたこと。同じ出来事が 10 分以内に続いたら 1 件にまとめて回数を付ける"""
        f = self.src.char_dir / "state" / "experience" / f"{day.strftime('%Y%m%d')}.jsonl"
        try:
            lines = f.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        out: list[dict] = []
        last: dict[str, dict] = {}
        for line in lines:
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            word = BODY_WORDS.get(ev.get("type"))
            ts = _local(ev.get("ts", ""))
            if not word or ts is None or ts.date() != day:
                continue
            prev = last.get(word)
            if prev and (ts - prev["_last"]).total_seconds() <= BODY_GROUP_S:
                prev["count"] += 1
                prev["_last"] = ts
                continue
            item = {"_ts": ts, "_last": ts, "kind": "body", "text": word, "count": 1}
            last[word] = item
            out.append(item)
        return out

    def day(self, day: Date) -> list[dict]:
        """その日の行(新しい順)。画面に渡す形にして返す"""
        items = list(self.by_day.get(day, [])) + self._memories(day) + self._body(day)
        runs = self.runs.get(day, [])
        out = []
        for it in sorted(items, key=lambda x: x["_ts"], reverse=True):
            ts = it["_ts"]
            row = {k: v for k, v in it.items() if not k.startswith("_")}
            row["time"] = ts.strftime("%H:%M")
            if it["kind"] == "talk":
                run = it["_run"]
                if run["count"] == 0:
                    continue   # その子が話しただけ(会話リレーなど)は、会話の行にしない
                row["count"] = run["count"]
                row["end"] = run["end"].strftime("%H:%M")
            elif it["kind"] == "mail":
                try:
                    body = it["_file"].read_text(encoding="utf-8").strip()
                except OSError:
                    body = ""
                row["text"] = body[:MAIL_TEXT_MAX]
                row["more"] = len(body) > MAIL_TEXT_MAX
            elif it["kind"] == "alone":
                row["end"] = it["_end"].strftime("%H:%M")
            if it["kind"] != "alone" and any(a <= ts <= b for a, b in runs):
                row["alone"] = True
            out.append(row)
        return out

    def has_diary(self, day: Date) -> bool:
        return (self.src.char_dir / "diary" / f"{day.isoformat()}.txt").exists()

    def earliest(self) -> Date | None:
        days = list(self.by_day)
        try:
            conn = sqlite3.connect(f"file:{self.src.memory_db}?mode=ro", uri=True)
            first = conn.execute("SELECT min(substr(timestamp, 1, 10)) FROM memories").fetchone()[0]
            conn.close()
            if first:
                days.append(Date.fromisoformat(first))
        except (sqlite3.Error, ValueError):
            pass
        return min(days) if days else None


def build(src: Sources, before: str | None = None, days: int = 3, today: Date | None = None) -> dict:
    """before(YYYY-MM-DD、その日は含まない。無ければあしたより前 = 今日から)より前の、行のある日を days 日ぶん。

    返すもの: {"days": [{"date", "weekday", "has_diary", "items": [...]}], "next_before": 続きを読むときの before、"more": まだ前があるか}
    """
    today = today or Date.today()
    days = max(1, min(days, DAYS_MAX))
    try:
        cursor = Date.fromisoformat(before) if before else today + timedelta(days=1)
    except ValueError:
        cursor = today + timedelta(days=1)
    index = _Index(src)
    earliest = index.earliest()
    out = []
    for _ in range(LOOKBACK_DAYS):
        if len(out) >= days or (earliest and cursor <= earliest):
            break
        cursor -= timedelta(days=1)
        items = index.day(cursor)
        if items:
            out.append({"date": cursor.isoformat(), "weekday": _WEEKDAYS[cursor.weekday()], "has_diary": index.has_diary(cursor), "items": items})
    return {"days": out, "next_before": cursor.isoformat(), "more": bool(earliest and cursor > earliest)}


def diary_list(char_dir: Path, memory_db: Path, before: str | None = None, limit: int = 30) -> dict:
    """日記の一覧(新しい順)。記憶のある日と、まとめのある日。まとめはここでは作らない(あるものだけ)。

    返すもの: {"items": [{"date", "weekday", "has_summary", "head", "count"}], "next_before", "more"}
    """
    counts: dict[str, int] = {}
    try:
        conn = sqlite3.connect(f"file:{memory_db}?mode=ro", uri=True)
        for d, n in conn.execute("SELECT substr(timestamp, 1, 10) AS d, count(*) FROM memories GROUP BY d"):
            if d:
                counts[d] = n
        conn.close()
    except sqlite3.Error:
        pass
    summaries = {f.stem: f for f in _files(char_dir / "diary") if f.suffix == ".txt"}
    dates = []
    for d in set(counts) | set(summaries):
        try:
            dates.append(Date.fromisoformat(d))
        except ValueError:
            continue
    dates.sort(reverse=True)
    if before:
        try:
            cut = Date.fromisoformat(before)
            dates = [d for d in dates if d < cut]
        except ValueError:
            pass
    limit = max(1, min(limit, 100))
    page = dates[:limit]
    items = []
    for d in page:
        key = d.isoformat()
        head = ""
        f = summaries.get(key)
        if f:
            try:
                head = " ".join(f.read_text(encoding="utf-8").split())[:DIARY_HEAD_MAX]
            except OSError:
                head = ""
        items.append({"date": key, "weekday": _WEEKDAYS[d.weekday()], "has_summary": bool(f and head), "head": head, "count": counts.get(key, 0)})
    return {"items": items, "next_before": page[-1].isoformat() if page else None, "more": len(dates) > limit}


def diary_summary(char_dir: Path, date: str) -> str | None:
    """その日のまとめ(あれば)。無ければ None。ここでは作らない"""
    try:
        Date.fromisoformat(date)
    except ValueError:
        return None
    f = char_dir / "diary" / f"{date}.txt"
    try:
        text = f.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return text or None
