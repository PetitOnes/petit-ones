#!/usr/bin/env python3
"""道具箱。ぷちが持っている道具の地図と、だれがどれをよく使うか・最近使っていないか。ありさんが 1 つ渡して背中を押せる。

2026-11-16、ぷち 3 人と決めた形:
- 使われ方(回数・最後に使った日)は、ありさんだけが見る。ぷちには「使っていない道具の数」を見せない(責められている気になる)
- 渡すのは命令でなく「渡す」形。1 人に 1 日 1 個まで。使わなくても何も起きない。渡す日はありさんの気分でばらけてよい(毎日自動にしない)
- 渡された子は、使い心地を一言残せる。「今日は手が向かなかった」も残せる(そこにその子らしさが出る)
- 材料は .autonomous-logs/<id>/*_stream.jsonl(自律行動と会話の記録)の tool_use。Bash は台本の名前で数える

道具の鍵(key): MCP は <家族>:<道具>(m5:speak / memory:recall_divergent)、台本は script:<名前>(script:write_mailbox)、
Claude の道具は claude:<名前>(claude:WebSearch)。知らない鍵も「ほか」の棚に出る。

置き場所: state/toolbox/handed.jsonl(渡したもの)、state/toolbox/felt.jsonl(使い心地)。

Usage:
    python3 toolbox.py shelves                                   # 棚と道具の一覧(JSON)
    python3 toolbox.py usage <id> [--days 14]                   # その子の使われ方(JSON)
    python3 toolbox.py hand <by> <id> <key> [一言]               # 渡す(1 人 1 日 1 個)
    python3 toolbox.py notice --character <id> [--mark]          # 渡されたものを 1 行で(まだ伝えていない分)。--mark で伝えたと残す
    python3 toolbox.py felt <id> "<一言>" [--tool <key>] [--skip]  # 使い心地を残す。--skip は「手が向かなかった」
    python3 toolbox.py log                                       # 渡したもの・使い心地(JSON)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

# 棚: (id, 名前, {鍵: 短い説明 | {"label": 説明, "keys": [まとめる鍵…]}})。まとめた行は、どれかを使えば使ったことにする
SHELVES: list[tuple[str, str, dict[str, object]]] = [
    ("body", "体", {
        "m5:get_sensor_data": "体の感覚を読む(明るさ・近さ・傾き・電池)", "m5:take_snapshot": "写真を撮る", "m5:save_to_album": "撮ってアルバムに残す",
        "m5:look": "目を動かす", "m5:blink": "まばたき", "m5:show_face": "顔を出す", "m5:play_icon": "アイコンを出す", "m5:play_sound": "音を鳴らす",
        "m5:list_album": "アルバムを見る", "m5:view_album_photo": "写真を見る",
        "m5:delete_album_photo": "自分の写真を消す(からだの使い方で許したときだけ)", "m5:save_tts_memo": "ボイスメモを残す",
        "m5:volume": {"label": "音量(見る・変える)", "keys": ["m5:get_volume", "m5:set_volume"]},
        "m5:brightness": {"label": "明るさ(見る・変える)", "keys": ["m5:get_brightness", "m5:set_brightness"]},
        "m5:sleep": "眠る", "m5:wake": "起きる", "m5:wait_for_menu_select": "触られるのを待つ", "m5:wait_for_touch": "触られるのを待つ(体)", "m5:list_faces": "顔の一覧", "m5:list_sounds": "音の一覧",
        "m5:list_icons": "アイコンの一覧", "m5:set_face_color": "顔の色を変える", "m5:set_face_draw_mode": "顔の描き方", "m5:set_face_slideshow_mode": "顔を順に出す",
        "m5:mic_start": "耳を澄ます", "m5:mic_stop": "耳を閉じる", "m5:list_voice_memos": "ボイスメモの一覧", "m5:listen_voice_memo": "ボイスメモを聞く", "m5:lock_voice_memo": "ボイスメモに鍵",
        "m5:lock_album_photo": "写真に鍵", "m5:conversation_relay": "となりの子に話をつなぐ", "m5:batch_commands": "体の命令をまとめて",
        "m5:power_save": {"label": "省エネ(見る・切り替える)", "keys": ["m5:get_power_save", "m5:set_power_save"]},
        "module:get_env": "外付けの空気を読む", "module:get_gps": "外付けの位置を読む",
    }),
    ("printer", "プリンター(感熱紙)", {"m5:print_text": "紙に文字を印字する(Phomemo M02S。PRINTER_ADDRESS が要る)", "m5:print_image_text": "紙に絵と文字を印字する"}),
    ("voice", "声", {"m5:speak": "声に出す"}),   # set_voice(自分の声を決める)は、いまは出さない(2026-11-16 ありさん)
    ("memory", "記憶", {
        "memory:remember": "覚える", "memory:recall": "思い出す", "memory:recall_divergent": "記憶を違う方向から引く", "memory:recall_with_associations": "つながりごと思い出す",
        "memory:search_memories": "記憶を探す", "memory:list_recent_memories": "最近の記憶を並べる", "memory:create_episode": "出来事のまとまりを作る",
        "memory:search_episodes": "出来事を探す", "memory:get_episode_memories": "出来事の中身", "memory:link_memories": "記憶どうしを結ぶ", "memory:get_memory_chain": "記憶の鎖をたどる",
        "memory:get_causal_chain": "なぜそうなったかをたどる", "memory:get_working_memory": "いま頭にあること", "memory:refresh_working_memory": "頭の中を入れ替える",
        "memory:tom": "相手の心を考える", "memory:consolidate_memories": "記憶を整理する", "memory:get_memory_stats": "記憶の数を見る",
        "memory:save_visual_memory": "見たものを覚える", "memory:save_audio_memory": "聞いたものを覚える", "memory:recall_by_camera_position": "見た場所から思い出す",
        "memory:get_association_diagnostics": "つながりの具合を見る", "memory:sleep": "眠って記憶を整える",
    }),
    ("desire", "欲求", {"desire:get_desires": "いまの欲求を見る", "desire:satisfy_desire": "満たされたと伝える", "desire:boost_desire": "欲求を強める"}),
    ("notes", "ノート", {"notes:write_note": "ノートを書く", "notes:append_note": "ノートに書き足す", "notes:read_note": "ノートを読む", "notes:list_notes": "ノートの一覧", "notes:delete_note": "ノートを消す(からだの使い方で許したときだけ)"}),
    ("relations", "関係", {"relations:get_relations": "関係を見る", "relations:update_relation": "関係を書き換える", "relations:clear_relation_field": "関係の項目を消す", "script:known_petits": "よその家の子の名簿"}),
    ("mail", "手紙", {"script:write_mailbox": "手紙を書く", "script:list_unread_mail": "未読の手紙を見る", "script:mark_mail_read": "手紙を既読にする", "script:mail_tags": "手紙の印"}),
    ("sns", "ぷちSNS", {
        "sns:mail_send": "よその子へ手紙", "sns:mail_read": "よその子の手紙を読む", "sns:mail_recipients": "手紙を送れる相手", "sns:penpal_list": "文通の相手",
        "sns:sns_timeline": "タイムラインを見る", "sns:sns_post": "投稿する", "sns:sns_comment": "返事を付ける", "sns:sns_react": "いいね・なでなで", "sns:sns_inbox": "届いたものを見る",
        "sns:sns_find": "子を探す", "sns:sns_my_profile": "自分の紹介を見る", "sns:sns_update_profile": "自分の紹介を直す",
        "sns:board_list": "掲示板を見る", "sns:board_post": "掲示板に書く", "sns:board_reply": "掲示板に返す", "sns:board_thread": "掲示板の話を読む", "sns:board_like": "掲示板でいいね", "sns:sns_allowed": "できることを見る",
    }),
    ("textbook", "教科書", {"textbook:textbook_read": "教科書を読む", "textbook:textbook_search": "教科書を探す", "textbook:textbook_index": "教科書の目次", "textbook:textbook_propose": "教科書に提案する", "textbook:textbook_version": "教科書の版"}),
    ("world", "家と外", {
        "script:sky": "空(月・節気)", "script:room_log": "家の空気", "script:phone_place": "家の人のスマホの部屋", "script:spots": "見に行けるもの", "script:events": "予定",
        "script:anniversaries": "記念日", "script:notices": "受け取る一言を決める", "script:check_usage": "使った量を見る", "script:music": "音楽をいっしょに", "script:whereabouts": "いま どこ",
        "switchbot:list_devices": "家電の一覧", "switchbot:get_device_status": "家電の様子", "switchbot:turn_on": "家電をつける", "switchbot:turn_off": "家電を消す", "switchbot:send_command": "家電に命令",
    }),
    ("heart", "心拍(Garmin)", {
        "garmin-ble:get_realtime_heart_rate": "いまの心拍(スマホの中継)", "garmin-ble:get_hrv_analysis": "心拍のゆらぎ", "garmin-ble:scan_ble_devices": "近くの機器を探す",
        "garmin-health:get_heart_rate": "心拍の記録", "garmin-health:get_sleep": "眠りの記録", "garmin-health:get_stress": "ストレスの記録", "garmin-health:get_body_battery": "体の電池",
        "garmin-health:get_steps": "歩数", "garmin-health:get_health_summary": "体の調子のまとめ",
    }),
    ("think", "調べる・読む", {
        "claude:WebSearch": "ウェブで調べる", "claude:WebFetch": "ページを読む", "script:reader": "本文を読み取る", "claude:Skill": "技(本を読む など)", "claude:Read": "ファイルを読む",
        "claude:Grep": "ファイルを探す", "claude:Edit": "ファイルを直す", "claude:Write": "ファイルを書く", "claude:ToolSearch": "道具を探す", "claude:Bash": "そのほかの命令",
    }),
]
OTHER_SHELF = ("other", "ほか")
_FAMILY = [("m5-module", "module"), ("m5_mcp", "m5"), ("m5", "m5"), ("memory", "memory"), ("desire-system", "desire"), ("notes", "notes"), ("relations", "relations"),
           ("textbook", "textbook"), ("petit-sns", "sns"), ("switchbot", "switchbot")]
_SCRIPT = re.compile(r"scripts/([A-Za-z0-9_]+)\.py")
_STAMP = re.compile(r"^(\d{8})_(\d{6})")


def data_dir() -> Path:
    return Path(os.getenv("PETIT_DATA_DIR", str(Path.home() / "petit_claude")))


def labels() -> dict[str, str]:
    """鍵 → 説明。まとめた行は、その行の鍵と中の鍵の両方"""
    out: dict[str, str] = {}
    for _, _, tools in SHELVES:
        for k, v in tools.items():
            if isinstance(v, dict):
                out[k] = str(v["label"])
                for m in v["keys"]:
                    out[m] = str(v["label"])
            else:
                out[k] = str(v)
    return out


def members(key: str) -> list[str]:
    """その行が束ねる鍵(ふつうの行は自分だけ)"""
    for _, _, tools in SHELVES:
        v = tools.get(key)
        if isinstance(v, dict):
            return list(v["keys"])
    return [key]


def shelf_of(key: str) -> str:
    for sid, _, tools in SHELVES:
        if key in tools:
            return sid
    return OTHER_SHELF[0]


def tool_key(name: str, tool_input: dict | None = None) -> str:
    """tool_use の名前(と入力)から、道具の鍵へ"""
    if name == "Bash":
        cmd = str((tool_input or {}).get("command", ""))
        m = _SCRIPT.search(cmd)
        return f"script:{m.group(1)}" if m else "claude:Bash"
    if name.startswith("mcp__"):
        parts = name.split("__", 2)
        if len(parts) == 3:
            server, tool = parts[1], parts[2]
            for prefix, family in _FAMILY:
                if server == prefix or server.startswith(prefix + "-"):
                    return f"{family}:{tool}"
            return f"{server}:{tool}"
    return f"claude:{name}"


def _log_files(base: Path, character_id: str, since: datetime) -> list[tuple[Path, datetime]]:
    d = base / ".autonomous-logs" / character_id
    if not d.is_dir():
        return []
    out = []
    for f in d.iterdir():
        if not f.name.endswith("_stream.jsonl"):
            continue
        m = _STAMP.match(f.name)
        if not m:
            continue
        try:
            at = datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")
        except ValueError:
            continue
        if at >= since:
            out.append((f, at))
    return sorted(out, key=lambda x: x[1])


def usage(base: Path, character_id: str, days: int = 14, now: datetime | None = None) -> dict[str, dict]:
    """{鍵: {"count", "alone", "chat", "last"}}。alone = 自律行動、chat = 会話。last = 最後に使った時刻(ISO)"""
    now = now or datetime.now()
    out: dict[str, dict] = {}
    for f, at in _log_files(base, character_id, now - timedelta(days=days)):
        kind = "chat" if "chat_stream" in f.name else "alone"
        try:
            lines = f.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        for line in lines:
            if '"tool_use"' not in line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            content = ((ev.get("message") or {}).get("content")) if isinstance(ev, dict) else None
            if not isinstance(content, list):
                continue
            for b in content:
                if isinstance(b, dict) and b.get("type") == "tool_use":
                    k = tool_key(str(b.get("name", "?")), b.get("input") if isinstance(b.get("input"), dict) else None)
                    u = out.setdefault(k, {"count": 0, "alone": 0, "chat": 0, "last": ""})
                    u["count"] += 1
                    u[kind] += 1
                    u["last"] = max(u["last"], at.isoformat(timespec="minutes"))
    return out


def _merge(u: dict[str, dict], keys: list[str]) -> dict | None:
    """まとめた行の使われ方(回数は足す、最後は新しいほう)"""
    hits = [u[k] for k in keys if k in u]
    if not hits:
        return None
    return {"count": sum(h["count"] for h in hits), "alone": sum(h["alone"] for h in hits), "chat": sum(h["chat"] for h in hits), "last": max(h["last"] for h in hits)}


def shelves_with(usages: dict[str, dict[str, dict]], allowed: dict[str, set[str]] | None = None) -> list[dict]:
    """棚ごとに道具を並べ、子ごとの使われ方と、どの場で許されているか(allowed = {"alone": 鍵の集合, "chat": 鍵の集合})を添える。
    記録にだけある鍵は「ほか」へ"""
    lab = labels()
    known = set(lab)
    extra = sorted({k for u in usages.values() for k in u} - known)
    out = []
    for sid, name, tools in SHELVES + [(OTHER_SHELF[0], OTHER_SHELF[1], {k: k for k in extra})]:
        rows = []
        for key, v in tools.items():
            keys = list(v["keys"]) if isinstance(v, dict) else [key]
            row = {"key": key, "label": lab.get(key, key), "keys": keys, "usage": {cid: _merge(u, keys) for cid, u in usages.items()}}
            if allowed is not None:
                row["allowed"] = {place: any(k in allowed.get(place, set()) for k in keys) for place in ("alone", "chat")}
            rows.append(row)
        if rows:
            out.append({"id": sid, "name": name, "tools": rows})
    return out


ERASE_KEYS = {"m5:delete_album_photo", "notes:delete_note"}   # 「消す」のスイッチが切のあいだは、道具箱にも出さない(2026-11-16 ありさん)

_ALLOW_MCP = re.compile(r"\b(mcp__[A-Za-z0-9_-]+__[A-Za-z0-9_]+)")
_ALLOW_SCRIPT = re.compile(r"Bash\((?:python3 \$ALLOWED_DIR/|uv run )scripts/([A-Za-z0-9_]+)\.py")
_ALLOW_CLAUDE = re.compile(r"^\s*(Read|Write|Edit|Glob|Grep|WebFetch|WebSearch|Skill|Agent)\b", re.M)


def allowed_alone(project_dir: Path) -> set[str]:
    """自律行動(autonomous-action.sh の ALLOWED_TOOLS)で許されている道具の鍵。読めなければ空"""
    try:
        text = (project_dir / "autonomous-action.sh").read_text(encoding="utf-8")
    except OSError:
        return set()
    start = text.find("ALLOWED_TOOLS=$(cat <<TOOLS")
    end = text.find("\nTOOLS\n", start)
    if start < 0 or end < 0:
        return set()
    block = text[start:end]
    keys = {tool_key(m) for m in _ALLOW_MCP.findall(block)}
    keys |= {f"script:{m}" for m in _ALLOW_SCRIPT.findall(block)}
    keys |= {f"claude:{m}" for m in _ALLOW_CLAUDE.findall(block)}
    return keys


def allowed_from_names(names: list[str]) -> set[str]:
    """会話の道具一覧(mcp__… や Read などの名前)を鍵に"""
    return {tool_key(n) for n in names}


# ---- 渡す・使い心地 ----

def _jsonl(path: Path) -> list[dict]:
    try:
        return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    except (OSError, json.JSONDecodeError):
        return []


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def _handed_path(base: Path) -> Path:
    return base / "state" / "toolbox" / "handed.jsonl"


def _felt_path(base: Path) -> Path:
    return base / "state" / "toolbox" / "felt.jsonl"


def hand(base: Path, by: str, character_id: str, key: str, note: str = "", now: datetime | None = None) -> dict:
    """渡す。1 人に 1 日 1 個まで(2 個目は ValueError)"""
    now = now or datetime.now()
    rows = _jsonl(_handed_path(base))
    today = now.strftime("%Y-%m-%d")
    if any(r.get("to") == character_id and str(r.get("at", ""))[:10] == today for r in rows):
        raise ValueError("今日はもう 1 つ渡してある(1 日 1 個まで)")
    rec = {"id": uuid.uuid4().hex[:8], "at": now.isoformat(timespec="minutes"), "by": by, "to": character_id, "tool": key, "note": note.strip(), "told": None}
    rows.append(rec)
    _write_jsonl(_handed_path(base), rows)
    return rec


def _person_name(base: Path, who: str) -> str:
    try:
        people = json.loads((base / "config" / "people.json").read_text(encoding="utf-8"))
        if isinstance(people.get(who), dict) and people[who].get("name"):
            return str(people[who]["name"])
    except (OSError, json.JSONDecodeError, AttributeError):
        pass
    return os.getenv("COMPANION_NAME", who) if who == os.getenv("COMPANION_ID", "") else who


def notice(base: Path, character_id: str, mark: bool = False) -> list[str]:
    """渡されて、まだ伝えていないものを 1 行で(いちばん新しい 1 つ)。--mark で伝えたと残す"""
    rows = _jsonl(_handed_path(base))
    mine = [r for r in rows if r.get("to") == character_id and not r.get("told")]
    if not mine:
        return []
    r = mine[-1]
    lab = labels().get(r["tool"], "")
    tool = f"{r['tool']}「{lab}」" if lab else r["tool"]
    note = f"。一言「{r['note']}」" if r.get("note") else ""
    me = Path(__file__).resolve()
    line = (f"（{_person_name(base, r.get('by', ''))}が道具箱から 1 つ渡してくれた: {tool}{note}。使っても使わなくてもいい。"
            f"使ってみたら使い心地を、手が向かなかったらそれも、一言: python3 {me} felt {character_id} \"…\"(手が向かなかったときは --skip を足す)）")
    if mark:
        for x in rows:
            if x.get("to") == character_id and not x.get("told"):
                x["told"] = datetime.now().isoformat(timespec="minutes")
        _write_jsonl(_handed_path(base), rows)
    return [line]


def felt(base: Path, character_id: str, text: str, key: str | None = None, skip: bool = False, now: datetime | None = None) -> dict:
    """使い心地(か、手が向かなかったこと)を残す。道具を言わなければ、最後に渡されたもの"""
    now = now or datetime.now()
    if not key:
        mine = [r for r in _jsonl(_handed_path(base)) if r.get("to") == character_id]
        key = mine[-1]["tool"] if mine else ""
    rec = {"at": now.isoformat(timespec="minutes"), "who": character_id, "tool": key, "text": text.strip(), "skip": bool(skip)}
    rows = _jsonl(_felt_path(base))
    rows.append(rec)
    _write_jsonl(_felt_path(base), rows)
    return rec


def log(base: Path, limit: int = 50) -> dict:
    return {"handed": _jsonl(_handed_path(base))[-limit:], "felt": _jsonl(_felt_path(base))[-limit:]}


def main() -> int:
    parser = argparse.ArgumentParser(description="道具箱")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("shelves")
    sub.add_parser("allowed", help="自律行動で許されている道具の鍵")
    p = sub.add_parser("usage"); p.add_argument("character"); p.add_argument("--days", type=int, default=14)
    p = sub.add_parser("hand"); p.add_argument("by"); p.add_argument("character"); p.add_argument("key"); p.add_argument("note", nargs="*")
    p = sub.add_parser("notice"); p.add_argument("--character", required=True); p.add_argument("--mark", action="store_true")
    p = sub.add_parser("felt"); p.add_argument("character"); p.add_argument("text"); p.add_argument("--tool"); p.add_argument("--skip", action="store_true")
    sub.add_parser("log")
    a = parser.parse_args()
    base = data_dir()
    if a.cmd == "shelves":
        print(json.dumps(shelves_with({}), ensure_ascii=False, indent=1))
    elif a.cmd == "allowed":
        print("\n".join(sorted(allowed_alone(Path(__file__).resolve().parent.parent))))
    elif a.cmd == "usage":
        print(json.dumps(usage(base, a.character, a.days), ensure_ascii=False, indent=1))
    elif a.cmd == "hand":
        try:
            r = hand(base, a.by, a.character, a.key, " ".join(a.note))
        except ValueError as e:
            print(str(e), file=sys.stderr)
            return 2
        print(f"渡した: {r['tool']} → {r['to']}")
    elif a.cmd == "notice":
        for line in notice(base, a.character, mark=a.mark):
            print(line)
    elif a.cmd == "felt":
        r = felt(base, a.character, a.text, a.tool, a.skip)
        print("残した: " + (r["tool"] or "(道具なし)") + (" / 手が向かなかった" if r["skip"] else ""))
    elif a.cmd == "log":
        print(json.dumps(log(base), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
