"""ぷちログ(その子の 1 日のタイムライン)と、日記の一覧。

家にいまあるもの(会話の記録・記憶・ノート・アルバム・ボイスメモ・メールボックス・自律行動の記録・
体の出来事)から組み立てるだけで、新しく何も書かない。形は里親さん側の「ぷちろぐ」にそろえる:

- 日ごとに区切り、日の中は新しい順
- 会話は、だれと・いつ・何回だけ。中身は返さない
- 体のことは「体に起きたこと」(持ち上げられた・置かれた・触られた・眠った・起こされた / 自分で起きた / 体が入れ直された)だけ。
  明るさの変わり目・つながらなかった時間・電池の知らせは出さない
- 人の手で起きること(持ち上げられた・置かれた・触られた・起こされた)には、家の持ち主の名前を付ける
  (「ありさんに持ち上げられた」)。体はだれの手かまでは分からないので、家の持ち主と見なして書く
- 目覚めは、つながらなかった時間の直後なら「体が入れ直された」(再起動・電源の入れ直し)、
  ひとりの時間のなかでその子が自分の体の wake を呼んでいたら「自分で起きた」、
  それ以外(体を 3 回触る・ダッシュボード・話しかけられて)は「起こされた」
- ひとりの時間(自律行動 1 回)の幅に入る行には alone: true を付ける
- 記念日(家の設定)に当たる日は、その日のいちばん上に 1 行出す
- ひとりの時間の行には、その回に使った道具から決まった言い方で一言を添える(「様子を見て、眠った」など)。
  その子の言葉や中身は写さない
"""

from __future__ import annotations

import json
import re
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
TEXT_MAX = 10000          # 記憶・メールの文は全部返す(画面で 3 行 → 12 行 → 全部、と開く)。これは並外れて長いものの歯止め
MAIL_TEXT_MAX = TEXT_MAX
MEMORY_TEXT_MAX = TEXT_MAX
DIARY_HEAD_MAX = 120

WAKE_NEAR_S = 60          # 目覚めと、その子が wake を呼んだ時刻が、これだけ近ければ同じ出来事
PRESS_NEAR_S = 60         # ダッシュボードで押してから、これだけのうちに眠った・起きたら、その人が寝かせた・起こした
PRESS_SKEW_S = 5          # 記録する側と時計が少しずれていてもよい幅
RESTART_NEAR_S = 5        # つながらなかった時間の終わりから、これだけのうちに起きていたら、体の入れ直し
BUSY_MIN = 4              # 触れ合い(持ち上げ・置く・触る)がこれだけ続いたら「その時間」を 1 行に
BODY_CONTACT = {"picked_up", "put_down", "touch"}
BODY_WORDS = {"picked_up": "持ち上げられた", "put_down": "置かれた", "touch": "触られた", "sleep": "眠った", "woken": "起こされた",
              "restarted": "体が入れ直された", "restarted_self": "体がひとりでに立ち上がり直した"}
WOKE_ITSELF = "自分で起きた"
RESTARTED = "体が入れ直された"
RESTART_SELF_REASONS = {"panic", "wdt", "brownout"}   # 体の不具合・固まった・電圧。人が入れ直したのではない
# ひとりの時間の一言。(見分ける印, 「…て」の形, 「…た」の形)。出すのはこの並びの順。
# その回に使った道具から決まった言い方で組む(2026-11-14 ありさん: 「様子を見た」だけでなく、何をしたかが分かるように)
ALONE_DID = [
    ("wake", "起きて", "起きた"),
    ("mail_check", "手紙が来ていないか見て", "手紙が来ていないか見た"),
    ("mail_read", "手紙を読んで", "手紙を読んだ"),
    ("sense", "まわりを感じて", "まわりを感じた"),          # 体のセンサー(明るさ・傾き・電池など)
    ("look", "まわりを見て", "まわりを見た"),              # カメラ
    ("desire", "気持ちを確かめて", "気持ちを確かめた"),      # 欲求
    ("recall", "思い出して", "思い出した"),                # 記憶をさがす・たどる
    ("reread", "自分のファイルを読み返して", "自分のファイルを読み返した"),
    ("note_read", "ノートを読み返して", "ノートを読み返した"),
    ("textbook", "教科書を読んで", "教科書を読んだ"),
    ("album", "アルバムを見て", "アルバムを見た"),
    ("voice_listen", "ボイスメモを聞いて", "ボイスメモを聞いた"),
    ("web", "調べものをして", "調べものをした"),
    ("speak", "話して", "話した"),
    ("sound", "音を鳴らして", "音を鳴らした"),
    ("photo", "写真を残して", "写真を残した"),
    ("voice_memo", "ボイスメモを残して", "ボイスメモを残した"),
    ("memory", "記憶に残して", "記憶に残した"),
    ("note", "ノートを書いて", "ノートを書いた"),
    ("edit_own", "自分のファイルを直して", "自分のファイルを直した"),
    ("mail", "手紙を書いて", "手紙を書いた"),
    ("sleep", "眠って", "眠った"),
]
ALONE_NOTHING = ("様子を見て", "様子を見た")   # どれにも当たらない回、眠っただけの回の頭
# これだけの回(確かめた・思い出した・記憶に残した)は、日記の材料にしない(記憶は別に渡る)
ALONE_QUIET_KEYS = {"mail_check", "sense", "desire", "recall", "reread", "note_read", "memory"}
_RECALL_TOOLS = ("recall", "recall_divergent", "recall_with_associations", "recall_by_camera_position", "search_memories",
                 "list_recent_memories", "get_working_memory", "refresh_working_memory", "search_episodes",
                 "get_episode_memories", "get_memory_chain", "get_causal_chain")
_MCP_DID = {
    ("m5", "wake"): "wake", ("m5", "sleep"): "sleep", ("m5", "speak"): "speak",
    ("m5", "take_snapshot"): "look", ("m5", "look"): "look",
    ("m5", "get_sensor_data"): "sense", ("m5-module", "get_env"): "sense", ("m5-module", "get_gps"): "sense",
    ("m5", "play_sound"): "sound", ("m5", "play_icon"): "sound",
    ("m5", "save_to_album"): "photo", ("m5", "view_album_photo"): "album", ("m5", "list_album"): "album",
    ("m5", "save_tts_memo"): "voice_memo", ("m5", "listen_voice_memo"): "voice_listen",
    ("memory", "remember"): "memory", ("memory", "create_episode"): "memory",
    ("memory", "save_visual_memory"): "memory", ("memory", "save_audio_memory"): "memory",
    **{("memory", t): "recall" for t in _RECALL_TOOLS},
    ("desire", "get_desires"): "desire",
    ("notes", "write_note"): "note", ("notes", "append_note"): "note",
    ("notes", "read_note"): "note_read", ("notes", "list_notes"): "note_read",
    ("textbook", "textbook_read"): "textbook", ("textbook", "textbook_search"): "textbook", ("textbook", "textbook_index"): "textbook",
}
_READ_COMMANDS = re.compile(r"(?:^|[\s;&|(])(?:cat|head|tail|grep|rg|less|sed -n)\s")   # Bash で読むときの頭
SNS_MAIL_TOOL = "mcp__petit-sns__mail_send"   # ぷちSNS(家の外のぷちとの手紙)。家のメールボックスには残らない
SNS_MAIL_VIA = "ぷちSNS"
# ぷちSNS でしたこと(道具の名前 → ぷちログの言い方)。中身(投稿・返事の文)は写さない。見ただけ・反応しただけは出さない
SNS_DID = {
    "mcp__petit-sns__sns_post": "ぷちSNS に投稿した",
    "mcp__petit-sns__sns_comment": "ぷちSNS で返事した",
    "mcp__petit-sns__board_post": "ぷちSNS の掲示板に書いた",
    "mcp__petit-sns__board_reply": "ぷちSNS の掲示板で返事した",
}
QUIET_NOTE_PREFIX = "しずかな時間"   # scripts/quiet_time.py が足すノート(何も残さなかった回の、その子の言葉)
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
    owner_name: str = ""               # 家の持ち主の表示名。体に人の手で起きたことに「〜に」と付ける(無ければ付けない)
    anniversaries: Callable[[Date], list[dict]] | None = None   # その日の記念日 [{"label", "note"}](家の設定から。無ければ出さない)


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


def _called_wake(log: Path, ts: datetime, char_id: str) -> bool:
    """自律行動の記録(stream.jsonl)のなかで、ts のころに自分の体の wake を呼んでいるか。

    行に時刻が無い古い記録は、呼んでいれば True(その回の幅に入っていることは呼ぶ側が見ている)
    """
    names = {"mcp__m5-mcp__wake", f"mcp__m5-{char_id}__wake"}
    try:
        lines = log.read_text(encoding="utf-8").splitlines()
    except OSError:
        return False
    for line in lines:
        if '"tool_use"' not in line or '__wake"' not in line:
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        msg = ev.get("message") if isinstance(ev, dict) else None
        content = msg.get("content") if isinstance(msg, dict) else None
        for c in content if isinstance(content, list) else []:
            if isinstance(c, dict) and c.get("type") == "tool_use" and c.get("name") in names:
                at = _local(ev.get("timestamp", ""))
                if at is None or abs((ts - at).total_seconds()) <= WAKE_NEAR_S:
                    return True
    return False


def _own_file(path: str, char_id: str) -> str | None:
    """その子の家の中のファイルか。"notes" = ノート、"own" = それ以外の自分のファイル(SOUL・ルーチン・TODO など)、None = よそ"""
    if f"/characters/{char_id}/" not in path:
        return None
    return "notes" if "/notes/" in path else "own"


def _did(name: str, args: dict, char_id: str) -> str | None:
    """道具の呼び出し 1 回 → ALONE_DID の印。一言にしないものは None"""
    if name.startswith("mcp__"):
        parts = name.split("__")
        if len(parts) != 3:
            return None
        server = parts[1]
        for tail in ("-mcp", "-system", f"-{char_id}"):   # m5-mcp・m5-<id> → m5、memory-<id> → memory
            if server.endswith(tail):
                server = server[: -len(tail)]
        return _MCP_DID.get((server, parts[2]))
    if name in ("WebSearch", "WebFetch"):
        return "web"
    if name == "Bash":
        cmd = str(args.get("command", ""))
        if "write_mailbox.py" in cmd:
            return "mail"
        if "mark_mail_read.py" in cmd:
            return "mail_read"
        if "list_unread_mail.py" in cmd:
            return "mail_check"
        if "reader.py" in cmd:
            return "web"
        if _READ_COMMANDS.search(cmd):   # cat・grep などで自分のファイルを読んだ
            return {"notes": "note_read", "own": "reread"}.get(_own_file(cmd, char_id) or "")
        return None
    if name in ("Write", "Edit"):
        return {"notes": "note", "own": "edit_own"}.get(_own_file(str(args.get("file_path", "")), char_id) or "")
    if name in ("Read", "Grep", "Glob"):
        return {"notes": "note_read", "own": "reread"}.get(_own_file(str(args.get("file_path") or args.get("path") or ""), char_id) or "")
    return None


def _alone_did(log: Path, char_id: str) -> set[str]:
    """ひとりの時間 1 回で使った道具の印(ALONE_DID の印の集まり)"""
    try:
        lines = log.read_text(encoding="utf-8").splitlines()
    except OSError:
        return set()
    did: set[str] = set()
    for line in lines:
        if '"tool_use"' not in line:
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        msg = ev.get("message") if isinstance(ev, dict) else None
        content = msg.get("content") if isinstance(msg, dict) else None
        for c in content if isinstance(content, list) else []:
            if isinstance(c, dict) and c.get("type") == "tool_use":
                args = c.get("input")
                key = _did(str(c.get("name", "")), args if isinstance(args, dict) else {}, char_id)
                if key:
                    did.add(key)
    return did


def _alone_words(did: set[str]) -> str:
    """ひとりの時間 1 回に添える一言。その回に使った道具から、決まった言い方で組む(その子の言葉は写さない)"""
    words = [(te, ta) for key, te, ta in ALONE_DID if key in did]
    if not words or did == {"sleep"}:
        words.insert(0, ALONE_NOTHING)
    return "、".join([te for te, _ in words[:-1]] + [words[-1][1]])


def _sns_events(log: Path) -> list[dict]:
    """行動の記録 1 つから、ぷちSNS でうまくいったことを拾う。

    手紙: {"tool", "at": 時刻か None, "to": 宛先の呼び名}、投稿・返事: {"tool", "at"}。本文は持ち出さない。
    道具の呼び出しと、その返事(うまくいったか・相手の呼び名・時刻)を組にする。うまくいかなかったものは出さない
    """
    try:
        text = log.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    if "mcp__petit-sns__" not in text:
        return []
    asked: dict[str, dict] = {}
    out: list[dict] = []
    for line in text.splitlines():
        if "tool_use" not in line and "tool_result" not in line:
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        msg = ev.get("message") if isinstance(ev, dict) else None
        content = msg.get("content") if isinstance(msg, dict) else None
        for c in content if isinstance(content, list) else []:
            if not isinstance(c, dict):
                continue
            name = c.get("name")
            if c.get("type") == "tool_use" and (name == SNS_MAIL_TOOL or name in SNS_DID):
                args = c.get("input") if isinstance(c.get("input"), dict) else {}
                asked[str(c.get("id"))] = {"tool": name, "to": str(args.get("to", "")),
                                           "at": _local(str(ev.get("timestamp", "")))}
            elif c.get("type") == "tool_result" and str(c.get("tool_use_id")) in asked and not c.get("is_error"):
                did = asked.pop(str(c.get("tool_use_id")))
                parts = c.get("content")
                raw = parts[0].get("text", "") if isinstance(parts, list) and parts and isinstance(parts[0], dict) else parts
                try:
                    res = json.loads(raw) if isinstance(raw, str) else {}
                except json.JSONDecodeError:
                    res = {}
                if not isinstance(res, dict) or res.get("ok") is not True:
                    continue
                sent = res.get("sent") if isinstance(res.get("sent"), dict) else {}
                if did["tool"] == SNS_MAIL_TOOL:
                    did["to"] = str(sent.get("to") or did["to"])
                    did["at"] = _local(str(sent.get("at", ""))) or did["at"]
                out.append(did)
    return out


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
        self.run_logs: list[tuple[datetime, datetime, Path]] = []
        self._chat()
        self._album()
        self._voice()
        self._mail()
        self._notes()
        self._alone()
        self._streams()

    def _streams(self) -> None:
        """行動の記録(ひとりの時間・会話)を、始まった日ごとに。中は、出す日のぶんだけあとで読む"""
        self.streams: dict[Date, list[Path]] = {}
        for f in _files(self.src.auto_log_dir):
            if f.name.endswith("stream.jsonl") and f.name.split("_", 2)[-1] in ("stream.jsonl", "chat_stream.jsonl"):
                ts = _stamp(f.name)
                if ts:
                    self.streams.setdefault(ts.date(), []).append(f)

    def _sns(self, day: Date) -> list[dict]:
        """その日に、ぷちSNS でしたこと(家の外のぷちへの手紙、投稿、返事)。前の日に始まって日をまたいだ回も見る。

        手紙は 1 通 1 行(だれへ)。投稿・返事は、同じ回の同じことを 1 行にまとめて回数を付ける。どれも中身は出さない
        """
        out = []
        for f in self.streams.get(day, []) + self.streams.get(day - timedelta(days=1), []):
            merged: dict[str, dict] = {}
            for m in _sns_events(f):
                ts = m["at"] or _stamp(f.name)
                if not ts or ts.date() != day:
                    continue
                if m["tool"] == SNS_MAIL_TOOL:
                    out.append({"_ts": ts, "kind": "mail", "to": m["to"], "via": SNS_MAIL_VIA, "_text": ""})
                elif m["tool"] in merged:
                    merged[m["tool"]]["count"] += 1
                else:
                    merged[m["tool"]] = {"_ts": ts, "kind": "sns", "text": SNS_DID[m["tool"]], "count": 1}
            out += merged.values()
        return out

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
        """ノートは、最後に書いた・直した日にだけ出る(更新時刻)。

        「しずかな時間_YYYY-MM」は自律行動のあとに自動で足されるノートなので、「書いた」とは出さない
        """
        for f in _files(self.src.char_dir / "notes"):
            if f.suffix != ".md" or f.stem.startswith(QUIET_NOTE_PREFIX):
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
            self.run_logs.append((ts, end, f))
            self._add(ts, kind="alone", _end=end, _file=f)

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

    def _woke_itself(self, ts: datetime) -> bool:
        """その目覚めは、ひとりの時間のなかで、その子が自分で体を起こしたものか"""
        near = timedelta(seconds=WAKE_NEAR_S)
        return any(a <= ts <= b + near and _called_wake(f, ts, self.src.char_id) for a, b, f in self.run_logs)

    def _experience(self, day: Date) -> list[dict]:
        """その日の体の出来事の記録(state/experience/YYYYMMDD.jsonl)。無ければ空"""
        f = self.src.char_dir / "state" / "experience" / f"{day.strftime('%Y%m%d')}.jsonl"
        try:
            lines = f.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        out = []
        for line in lines:
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(ev, dict):
                out.append(ev)
        return out

    def _pressed(self, day: Date) -> dict[str, list[tuple[datetime, str]]]:
        """ダッシュボードから「寝かせた」「起こした」人と時刻(state/contact/ の sleep_by / wake_by)"""
        out: dict[str, list[tuple[datetime, str]]] = {"sleep_by": [], "wake_by": []}
        for d in (day - timedelta(days=1), day):
            f = self.src.char_dir / "state" / "contact" / f"{d.strftime('%Y%m%d')}.jsonl"
            try:
                lines = f.read_text(encoding="utf-8").splitlines()
            except OSError:
                continue
            for line in lines:
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts = _local(ev.get("ts", "")) if isinstance(ev, dict) else None
                if ts is not None and ev.get("type") in out and isinstance(ev.get("with"), str) and ev["with"]:
                    out[ev["type"]].append((ts, ev["with"]))
        return out

    def _by_owner(self, text: str) -> str:
        """人の手で起きたことに、家の持ち主の名前を付ける(「ありさんに持ち上げられた」)"""
        return f"{self.src.owner_name}に{text}" if self.src.owner_name else text

    def _body(self, day: Date) -> list[dict]:
        """体に起きたこと。

        連れ歩くと、持ち上げ・置く・触るが入れ替わりながら何十回も続く。ぷちログは体に起きたことの一覧ではなく
        どんな日だったかなので、10 分より詰まって BUSY_MIN 件以上続いた時間は 1 行にまとめ、中身は出さない
        (里親さん側のぷちろぐと同じ決まり)。それ以外は、同じ出来事が 10 分以内に続いたら 1 件にして回数を付ける
        """
        pressed = self._pressed(day)

        def pressed_by(kind: str, ts: datetime) -> str:
            """その眠り・目覚めの少し前に、ダッシュボードから押した人の呼び名(いなければ空)"""
            for at, who in pressed[kind]:
                if -PRESS_SKEW_S <= (ts - at).total_seconds() <= PRESS_NEAR_S:
                    return self.src.user_label(who)
            return ""

        events: list[tuple[datetime, str]] = []
        back_online: list[datetime] = []   # つながらなかった時間の終わり(日をまたぐものは前の日の記録にある)
        seen_restart: list[datetime] = []  # 体が知らせた再起動に、記録する側が気づいた時刻
        knows_restart: set[datetime] = set()   # 再起動を自分で見分けられる体の、目覚めの時刻
        for ev in self._experience(day - timedelta(days=1)) + self._experience(day):
            if ev.get("type") == "offline_gap" and isinstance(ev.get("detail"), dict):
                end = _local(ev["detail"].get("end", ""))
                if end is not None:
                    back_online.append(end)
            ts = _local(ev.get("ts", ""))
            kind, detail = ev.get("type"), ev.get("detail") if isinstance(ev.get("detail"), dict) else {}
            if kind == "restarted" and ts is not None:
                # 体が自分で知らせた再起動(起動からの秒数を返す体)。わけが不具合なら「ひとりでに」
                kind = "restarted_self" if detail.get("reason") in RESTART_SELF_REASONS else "restarted"
                seen_restart.append(ts + timedelta(seconds=float(detail.get("uptime_s") or 0)))   # 気づいたとき
            elif kind == "woken" and ts is not None and "uptime_s" in detail:
                knows_restart.add(ts)   # 再起動を自分で見分けられる体の目覚め。推測はしない
            if ts is not None and ts.date() == day and kind in BODY_WORDS:
                events.append((ts, kind))
        events.sort()

        # 触れ合い(持ち上げ・置く・触る)が詰まって続いた時間
        stretches: list[list[tuple[datetime, str]]] = []
        for ts, kind in events:
            if kind not in BODY_CONTACT:
                continue
            if stretches and (ts - stretches[-1][-1][0]).total_seconds() <= BODY_GROUP_S:
                stretches[-1].append((ts, kind))
            else:
                stretches.append([(ts, kind)])
        out: list[dict] = []
        busy: set[tuple[datetime, str]] = set()
        for st in stretches:
            if len(st) < BUSY_MIN:
                continue
            kinds = {k for _, k in st}
            if "touch" in kinds:
                text = "抱っこされて、たくさん触れてもらった" if "picked_up" in kinds else "たくさん触られた"
            else:
                text = "持ち上げられたり、置かれたりした"
            out.append({"_ts": st[0][0], "_end": st[-1][0], "kind": "body", "text": self._by_owner(text), "count": 1})
            busy.update(st)

        last: dict[str, dict] = {}
        for ts, kind in events:
            if (ts, kind) in busy:
                continue
            word = BODY_WORDS[kind]
            if kind == "sleep" and pressed_by("sleep_by", ts):
                word = f"{pressed_by('sleep_by', ts)}に寝かされた"   # ダッシュボードから寝かされた
            if kind == "woken" and pressed_by("wake_by", ts):
                word = f"{pressed_by('wake_by', ts)}に起こされた"    # ダッシュボードから起こされた(押した人の名前で)
            elif kind == "woken":
                if any(abs((ts - t).total_seconds()) <= RESTART_NEAR_S for t in seen_restart):
                    continue   # 再起動して起きた。「体が入れ直された」の行がもうある
                if ts not in knows_restart and any(abs((ts - t).total_seconds()) <= RESTART_NEAR_S for t in back_online):
                    word = RESTARTED   # 起動からの秒数を返さない体では、つながらなかった直後の目覚めを再起動と見る(推測)
                elif self._woke_itself(ts):
                    word = WOKE_ITSELF
                else:
                    word = self._by_owner(word)
            elif kind in BODY_CONTACT:
                word = self._by_owner(word)
            prev = last.get(word)
            if prev and (ts - prev["_last"]).total_seconds() <= BODY_GROUP_S:
                prev["count"] += 1
                prev["_last"] = ts
                continue
            item = {"_ts": ts, "_last": ts, "kind": "body", "text": word, "count": 1}
            last[word] = item
            out.append(item)
        return out

    def _hello(self, day: Date) -> list[dict]:
        """人から届いた「ここにいるよ」(state/contact/YYYYMMDD.jsonl の hello)。

        だれが送ったかは、押した人が分かっているので名前で出す。10 分以内に続いたら 1 件にして回数を付ける。
        話しかけられた(talked)は、会話の行がもうあるので、ここでは出さない
        """
        f = self.src.char_dir / "state" / "contact" / f"{day.strftime('%Y%m%d')}.jsonl"
        try:
            lines = f.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        out: list[dict] = []
        for line in lines:
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = _local(ev.get("ts", "")) if isinstance(ev, dict) else None
            if ts is None or ts.date() != day or ev.get("type") != "hello":
                continue
            who = self.src.user_label(ev["with"]) if isinstance(ev.get("with"), str) and ev["with"] else ""
            text = f"{who}から「ここにいるよ」が届いた" if who else "「ここにいるよ」が届いた"
            prev = out[-1] if out else None
            if prev and prev["text"] == text and (ts - prev["_last"]).total_seconds() <= BODY_GROUP_S:
                prev["count"] += 1
                prev["_last"] = ts
                continue
            out.append({"_ts": ts, "_last": ts, "kind": "body", "text": text, "count": 1})
        return out

    def day(self, day: Date) -> list[dict]:
        """その日の行(新しい順)。画面に渡す形にして返す"""
        items = list(self.by_day.get(day, [])) + self._memories(day) + self._body(day) + self._hello(day) + self._sns(day)
        if self.src.anniversaries:   # その日のいちばん上に出す(時刻は持たない)
            top = datetime.combine(day, datetime.max.time())
            items += [{"_ts": top, "kind": "anniv", "text": a["label"], "note": a.get("note", "")} for a in self.src.anniversaries(day)]
        runs = self.runs.get(day, [])
        out = []
        for it in sorted(items, key=lambda x: x["_ts"], reverse=True):
            ts = it["_ts"]
            row = {k: v for k, v in it.items() if not k.startswith("_")}
            row["time"] = "" if it["kind"] == "anniv" else ts.strftime("%H:%M")
            if it["kind"] == "talk":
                run = it["_run"]
                if run["count"] == 0:
                    continue   # その子が話しただけ(会話リレーなど)は、会話の行にしない
                row["count"] = run["count"]
                row["end"] = run["end"].strftime("%H:%M")
            elif it["kind"] == "mail":
                try:
                    body = it["_text"] if "_text" in it else it["_file"].read_text(encoding="utf-8").strip()
                except OSError:
                    body = ""
                row["text"] = body[:MAIL_TEXT_MAX]
                row["more"] = len(body) > MAIL_TEXT_MAX
            elif "_end" in it:   # ひとりの時間、続いた体の出来事
                row["end"] = it["_end"].strftime("%H:%M")
                if it["kind"] == "alone":
                    did = _alone_did(it["_file"], self.src.char_id)
                    row["text"] = _alone_words(did)
                    row["quiet"] = did <= ALONE_QUIET_KEYS   # 確かめた・思い出した・記憶に残した だけの回
            if it["kind"] not in ("alone", "anniv") and any(a <= ts <= b for a, b in runs):
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


DIARY_LINES_MAX = 60      # 日記の材料にする出来事の行数の上限


def day_lines(src: Sources, day: Date) -> list[str]:
    """その日の出来事を、日記の材料にする 1 行ずつ(古い順)。

    ぷちログの行から組み立てる。記憶は入れない(日記は記憶の一覧を別に受け取る)。会話の中身・手紙の本文・
    ノートの中身は写さず、だれと・いつ・何回だけ。ひとりの時間は、何かした回(起きた・手紙を読んだ・眠った など)だけ
    """
    rows = _Index(src).day(day)
    out: list[str] = []
    for r in reversed(rows):
        kind, when = r["kind"], r.get("time", "")
        if r.get("end") and r["end"] != when:
            when = f"{when}〜{r['end']}"
        if kind == "anniv":
            out.insert(0, f"記念日: {r['text']}" + (f"({r['note']})" if r.get("note") else ""))
        elif kind == "talk":
            who = f"みんなで話した({r['who']}から {r['count']} 回)" if r.get("group") else f"{r['who']}と話した({r['count']} 回)"
            out.append(f"{when} {who}")
        elif kind == "body":
            out.append(f"{when} {r['text']}" + (f"(× {r['count']})" if r.get("count", 1) > 1 else ""))
        elif kind == "alone":
            if r.get("text") and not r.get("quiet"):   # 様子を見た・確かめた・記憶に残した だけの回は入れない(記憶は別に渡る)
                out.append(f"{when} ひとりの時間: {r['text']}")
        elif kind == "mail":
            out.append(f"{when} {r['to']}へ手紙を書いた")
        elif kind == "sns":
            out.append(f"{when} {r['text']}" + (f"(× {r['count']})" if r.get("count", 1) > 1 else ""))
        elif kind == "note":
            out.append(f"{when} ノート「{r['name']}」を書いた")
        elif kind == "photo":
            out.append(f"{when} 写真を残した" + (f"「{r['title']}」" if r.get("title") else ""))
        elif kind == "voice":
            out.append(f"{when} ボイスメモを残した" + (f"「{r['title']}」" if r.get("title") else ""))
    return out[:DIARY_LINES_MAX]


def build(src: Sources, before: str | None = None, days: int = 3, today: Date | None = None) -> dict:
    """before(YYYY-MM-DD、その日は含まない。無ければあしたより前 = 今日から)より前の、行のある日を days 日ぶん。

    返すもの: {"days": [{"date", "weekday", "has_diary", "items": [...]}], "next_before": 続きを読むときの before、"more": まだ前があるか、
    "earliest": いちばん古い日(月へ飛ぶ一覧用)}
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
    return {"days": out, "next_before": cursor.isoformat(), "more": bool(earliest and cursor > earliest),
            "earliest": earliest.isoformat() if earliest else None}


def _diary_dates(char_dir: Path, memory_db: Path) -> tuple[list[Date], dict[str, int], dict[str, Path]]:
    """日記に出す日(記憶のある日と、まとめのある日)を新しい順に。あわせて、日ごとの記憶の件数と、まとめのファイル"""
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
    return dates, counts, summaries


def diary_neighbors(char_dir: Path, memory_db: Path, date: str) -> tuple[str | None, str | None]:
    """その日の前の日・次の日(日記に出す日のなかで)。無ければ None"""
    try:
        day = Date.fromisoformat(date)
    except ValueError:
        return None, None
    dates, _, _ = _diary_dates(char_dir, memory_db)
    prev = next((d for d in dates if d < day), None)             # 新しい順なので、最初に見つかる古い日
    nxt = next((d for d in reversed(dates) if d > day), None)    # 古い順に見て、最初に見つかる新しい日
    return (prev.isoformat() if prev else None, nxt.isoformat() if nxt else None)


def diary_list(char_dir: Path, memory_db: Path, before: str | None = None, limit: int = 30) -> dict:
    """日記の一覧(新しい順)。記憶のある日と、まとめのある日。まとめはここでは作らない(あるものだけ)。

    返すもの: {"items": [{"date", "weekday", "has_summary", "head", "count"}], "next_before", "more", "earliest"}
    """
    dates, counts, summaries = _diary_dates(char_dir, memory_db)
    earliest = dates[-1].isoformat() if dates else None
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
    return {"items": items, "next_before": page[-1].isoformat() if page else None, "more": len(dates) > limit, "earliest": earliest}


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
