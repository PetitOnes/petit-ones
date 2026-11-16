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
    python3 toolbox.py gates                                     # 道具の門(家の config/toolbox.json)
    python3 toolbox.py gate <alone|chat> <key> on|off            # 門を開け閉め(alone の on は、許しの一覧に無い道具を足す)
    python3 toolbox.py disallowed --mode <alone|chat> --config <mcp.json> --project <dir>   # 止める道具(--disallowedTools 用、カンマ区切り)
    python3 toolbox.py extra-allowed --config <mcp.json> --project <dir>                    # 自律で足す道具(--allowedTools に足す、カンマ区切り)
    python3 toolbox.py describe --config <mcp.json> [--timeout 25]   # 部品につないで道具の説明を集め、state/toolbox/descriptions.json に

道具の門(2026-11-16 ありさん: 会話と自律で渡す道具をダッシュボードから決めたい): config/toolbox.json
    {"alone": {"on": [鍵…], "off": [鍵…]}, "chat": {"off": [鍵…]}}
- 自律(alone): autonomous-action.sh の許しの一覧が元。on で足し、off で止める
- 会話(chat): 権限を全部通す起動なので、つないである部品の道具は全部使える。off で止めるだけ
- 止めるのは --disallowedTools(両方で本当に効く)。鍵は部品の名前に戻す(mcp__<server>__<tool>、台本は Bash(python3 <project>/scripts/<名前>.py *))
- 体の部品(m5-mcp)は M5_ALLOWED_TOOLS で登録する道具を絞っている。そこに無い道具は、どちらの場にも「つないでいない」
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import select
import subprocess
import sys
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path

# 棚: (id, 名前, {鍵: 短い説明 | {"label": 説明, "keys": [まとめる鍵…]}})。まとめた行は、どれかを使えば使ったことにする
SHELVES: list[tuple[str, str, dict[str, object]]] = [
    ("body", "体", {
        "m5:get_sensor_data": "体の感覚を読む(明るさ・近さ・傾き・電池)", "m5:take_snapshot": "写真を撮る(見るだけ。保存しない)", "m5:keep_snapshot": "さっき撮った写真を残す(撮り直さない)", "m5:save_to_album": "撮ってアルバムに残す",
        "m5:look": "目を動かす", "m5:blink": "まばたき", "m5:show_face": "顔を出す", "m5:play_icon": "アイコンを出す", "m5:play_sound": "音を鳴らす",
        "m5:list_album": "アルバムを見る", "m5:view_album_photo": "写真を見る",
        "m5:delete_album_photo": "自分の写真を消す(からだの使い方で許したときだけ)", "m5:save_tts_memo": "ボイスメモを残す",
        "m5:volume": {"label": "音量(見る・変える)", "keys": ["m5:get_volume", "m5:set_volume"]},
        "m5:brightness": {"label": "明るさ(見る・変える)", "keys": ["m5:get_brightness", "m5:set_brightness"]},
        "m5:sleep": "眠る", "m5:wake": "起きる", "m5:wait_for_menu_select": "画面のメニューが選ばれるのを待つ", "m5:wait_for_touch": "画面が触られるのを待つ", "m5:list_faces": "顔の一覧", "m5:list_sounds": "音の一覧",
        "m5:list_icons": "アイコンの一覧", "m5:set_face_color": "顔の色を変える", "m5:set_face_draw_mode": "顔を目と口の描画にする(画像でなく)", "m5:set_face_slideshow_mode": "顔の画像を順に流す",
        "m5:mic_start": "耳を澄ます(マイクを開く)", "m5:mic_stop": "耳を閉じる(マイクを止める)", "m5:list_voice_memos": "ボイスメモの一覧", "m5:listen_voice_memo": "ボイスメモを聞く", "m5:lock_voice_memo": "ボイスメモに鍵(自動で消えないように)",
        "m5:lock_album_photo": "写真に鍵(自動で消えないように)", "m5:conversation_relay": "となりの子に話をつなぐ", "m5:batch_commands": "体の命令をまとめて",
        "m5:power_save": {"label": "省エネ(見る・切り替える)", "keys": ["m5:get_power_save", "m5:set_power_save"]},
        "script:find_m5": "体を家の中で探す(IP を総当たり)",
        "module:get_env": "外付けセンサーの気温・湿度", "module:get_gps": "外付け GPS の位置",
    }),
    ("printer", "プリンター(感熱紙)", {"m5:print_text": "紙に文字を印字する(Phomemo M02S。PRINTER_ADDRESS が要る)", "m5:print_image_text": "紙に絵と文字を印字する"}),
    ("voice", "声", {"m5:speak": "声に出す"}),   # set_voice(自分の声を決める)は、いまは出さない(2026-11-16 ありさん)
    ("memory", "記憶", {
        "memory:remember": "覚える", "memory:recall": "思い出す", "memory:recall_divergent": "記憶を違う方向から引く", "memory:recall_with_associations": "つながりごと思い出す",
        "memory:search_memories": "記憶を探す", "memory:list_recent_memories": "最近の記憶を並べる", "memory:create_episode": "出来事のまとまりを作る",
        "memory:search_episodes": "出来事を探す", "memory:get_episode_memories": "出来事の中身", "memory:link_memories": "記憶どうしを結ぶ", "memory:get_memory_chain": "記憶の鎖をたどる",
        "memory:get_causal_chain": "なぜそうなったかをたどる", "memory:get_working_memory": "いま頭にあること", "memory:refresh_working_memory": "いま頭にあることを更新する",
        "memory:tom": "相手の心を考える", "memory:consolidate_memories": "記憶を整理する", "memory:get_memory_stats": "記憶の数を見る",
        "memory:save_visual_memory": "見たものを覚える", "memory:save_audio_memory": "聞いたものを覚える", "memory:recall_by_camera_position": "見た場所から思い出す",
        "memory:get_association_diagnostics": "記憶のつながりの状態を見る(点検)", "memory:sleep": "眠って記憶を整える",
    }),
    ("desire", "欲求", {"desire:get_desires": "いまの欲求を見る", "desire:satisfy_desire": "欲求が満たされたと記録する", "desire:boost_desire": "欲求を強める"}),
    ("notes", "ノート", {"notes:write_note": "ノートを書く", "notes:append_note": "ノートに書き足す", "notes:read_note": "ノートを読む", "notes:list_notes": "ノートの一覧", "notes:delete_note": "ノートを消す(からだの使い方で許したときだけ)", "script:write_notebook": "交換日記に書く"}),
    ("relations", "関係", {"relations:get_relations": "関係を見る", "relations:update_relation": "関係を書き換える", "relations:clear_relation_field": "関係の項目を消す", "script:known_petits": "よその家の子の名簿"}),
    ("mail", "手紙", {"script:write_mailbox": "手紙を書く", "script:list_unread_mail": "未読の手紙を見る", "script:mark_mail_read": "手紙を既読にする", "script:mail_tags": "手紙の印", "script:slack_notify": "Slack で家の人に知らせる"}),
    ("sns", "ぷちSNS", {
        "sns:mail_send": "よその子へ手紙", "sns:mail_read": "よその子の手紙を読む", "sns:mail_recipients": "手紙を送れる相手", "sns:penpal_list": "文通の相手",
        "sns:sns_timeline": "タイムラインを見る", "sns:sns_post": "投稿する", "sns:sns_comment": "返事を付ける", "sns:sns_react": "いいね・なでなで", "sns:sns_inbox": "ぷちSNS に届いたものを見る",
        "sns:sns_find": "ぷちSNS で相手を探す", "sns:sns_my_profile": "自分の紹介を見る", "sns:sns_update_profile": "自分の紹介を直す",
        "sns:board_list": "掲示板を見る", "sns:board_post": "掲示板に書く", "sns:board_reply": "掲示板に返す", "sns:board_thread": "掲示板の話を読む", "sns:board_like": "掲示板でいいね", "sns:sns_allowed": "ぷちSNS でできることを見る",
    }),
    ("textbook", "教科書", {"textbook:textbook_read": "教科書を読む", "textbook:textbook_search": "教科書を探す", "textbook:textbook_index": "教科書の目次", "textbook:textbook_propose": "教科書に提案する", "textbook:textbook_version": "教科書の版"}),
    ("world", "家と外", {
        "script:sky": "空(月・節気)", "script:room_log": "家の空気", "script:phone_place": "家の人のスマホの部屋", "script:spots": "体がどこに置かれているか(見に行けるもの)", "script:events": "予定",
        "script:anniversaries": "記念日", "script:notices": "受け取る一言を決める", "script:check_usage": "API を使った量を見る", "script:music": "音楽をいっしょに", "script:sing": "うたう(楽器と高さを選んで自分の音を作る・鳴らす・渡す)", "script:sounds": "家の音のライブラリ(お願い、音のかたちを数字と線で見る、予想と答え合わせ、色や言葉を貼る)", "script:whereabouts": "いま どこ",
        "switchbot:list_devices": "家電の一覧", "switchbot:get_device_status": "家電の様子", "switchbot:turn_on": "家電をつける", "switchbot:turn_off": "家電を消す", "switchbot:send_command": "家電に命令",
    }),
    ("heart", "心拍(Garmin)", {
        "garmin-ble:get_realtime_heart_rate": "いまの心拍(スマホの中継)", "garmin-ble:get_hrv_analysis": "心拍のゆらぎ", "garmin-ble:scan_ble_devices": "近くの機器を探す",
        "garmin-health:get_heart_rate": "心拍の記録", "garmin-health:get_sleep": "眠りの記録", "garmin-health:get_stress": "ストレスの記録", "garmin-health:get_body_battery": "体の電池(Garmin のボディバッテリー)",
        "garmin-health:get_steps": "歩数", "garmin-health:get_health_summary": "体の調子のまとめ",
    }),
    ("think", "調べる・読む", {
        "claude:WebSearch": "ウェブで調べる", "claude:WebFetch": "ページを読む", "script:reader": "ページの本文だけ読み取る(リーダー)", "script:fetch_aozora_book": "青空文庫から本を取ってくる",
        "claude:Skill": "技(スキル: 本を読む・Slack に送る)", "claude:Read": "ファイルを読む", "claude:Grep": "ファイルを探す(中身で)", "claude:Glob": "ファイルを探す(名前で)",
        "claude:Edit": "ファイルを直す", "claude:Write": "ファイルを書く", "claude:ToolSearch": "名前だけの道具の説明を引く", "claude:Bash": "シェルの命令(Bash。台本もここから)",
    }),
]
OTHER_SHELF = ("other", "ほか")
# Claude Code が持っている道具の説明。部品からは取れないので、ここに書く(ぷちに渡る本物の説明文は Claude Code のもの)
BUILTIN_DOCS = {
    "claude:Read": "ファイルを読む(行の範囲も指定できる。画像や PDF も)。読める場所は許しの一覧の範囲",
    "claude:Write": "ファイルを新しく書く・丸ごと書き換える",
    "claude:Edit": "ファイルの一部を、決まった文字列の置き換えで直す",
    "claude:Glob": "名前のパターン(**/*.md など)でファイルを探す",
    "claude:Grep": "中身の文字列(正規表現)でファイルを探す",
    "claude:Bash": "シェルの命令を実行する。ひとりの時間は、許しの一覧にある台本(python3 scripts/…)だけ",
    "claude:WebFetch": "URL のページを取ってきて読む(要約を挟む)",
    "claude:WebSearch": "ウェブを検索する",
    "claude:Skill": "技(スキル)を呼ぶ。本を読む(read)・Slack に送る(slack) など、決まった手順",
    "claude:ToolSearch": "名前だけ渡されている道具の説明を引き出す(多い道具は使う直前にこれで引く)",
    "claude:Agent": "別の Claude を子として立ち上げ、調べものなどを任せる",
    "claude:TodoWrite": "やることの一覧を書く(自分の手順の覚え書き)",
    "claude:PushNotification": "人の端末に通知を送る",
}
_KNOWN_FAMILIES = {"m5", "module", "memory", "desire", "notes", "relations", "textbook", "sns", "switchbot", "garmin-ble", "garmin-health"}
HIDDEN_KEYS = {"module:get_ble_rssi", "m5:set_voice"}   # 道具箱に出さないと決めたもの(2026-11-16 ありさん: 電波はいま使えない、声は決めてある)
_FAMILY = [("m5-module", "module"), ("m5_mcp", "m5"), ("m5", "m5"), ("memory", "memory"), ("desire-system", "desire"), ("notes", "notes"), ("relations", "relations"),
           ("textbook", "textbook"), ("petit-sns", "sns"), ("switchbot", "switchbot")]
_SCRIPT = re.compile(r"scripts/([A-Za-z0-9_]+)\.py")
_STAMP = re.compile(r"^(\d{8})_(\d{6})")


def data_dir() -> Path:
    return Path(os.getenv("PETIT_DATA_DIR", str(Path.home() / "petit_claude")))


def _json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


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


def _is_real(key: str, project_dir: Path | None) -> bool:
    """記録にだけある鍵が、本物の道具か。昔の記録には、言い間違いの名前(claude:desires.json など)も残っている"""
    fam, _, name = key.partition(":")
    if key in HIDDEN_KEYS:
        return False
    if fam == "claude":
        return key in BUILTIN_DOCS
    if fam == "script":
        return project_dir is None or (project_dir / "scripts" / f"{name}.py").is_file()
    return fam in _KNOWN_FAMILIES and re.fullmatch(r"[a-z][a-z0-9_]*", name) is not None


def shelves_with(usages: dict[str, dict[str, dict]], allowed: dict[str, set[str]] | None = None, project_dir: Path | None = None) -> list[dict]:
    """棚ごとに道具を並べ、子ごとの使われ方と、どの場で許されているか(allowed = {"alone": 鍵の集合, "chat": 鍵の集合})を添える。
    記録にだけある本物の鍵は「ほか」へ(project_dir を渡すと、無い台本と言い間違いの名前は出さない)"""
    lab = labels()
    known = set(lab)
    extra = sorted(k for k in {k for u in usages.values() for k in u} - known if project_dir is None or _is_real(k, project_dir))
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
    return keys | ALWAYS


ALWAYS = {"claude:ToolSearch"}   # Claude Code がいつも持っている道具(許しの一覧に関わらず)
MODES = ("alone", "chat")


# ---- 道具の門(家の config/toolbox.json) ----

def gates_path(base: Path) -> Path:
    return base / "config" / "toolbox.json"


def gates(base: Path) -> dict[str, dict[str, list[str]]]:
    d = _json(gates_path(base), {})
    out = {"alone": {"on": [], "off": []}, "chat": {"on": [], "off": []}}
    for mode in MODES:
        m = d.get(mode) if isinstance(d, dict) and isinstance(d.get(mode), dict) else {}
        for k in ("on", "off"):
            out[mode][k] = [str(x) for x in (m.get(k) or []) if isinstance(x, str)]
    return out


def set_gate(base: Path, mode: str, key: str, on: bool, base_allowed: set[str] | None = None) -> dict:
    """門を開け閉め。on は off から外し、alone で許しの一覧(base_allowed)に無い道具なら on に足す。off は on から外し off に足す"""
    if mode not in MODES:
        raise ValueError("mode は alone か chat")
    g = gates(base)
    m = g[mode]
    m["on"] = [k for k in m["on"] if k != key]
    m["off"] = [k for k in m["off"] if k != key]
    if on and mode == "alone" and not (base_allowed and any(k in base_allowed for k in members(key))):
        m["on"].append(key)
    if not on:
        m["off"].append(key)
    p = gates_path(base)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(g, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(p)
    return g


def _servers(config_path: Path) -> dict[str, dict]:
    d = _json(config_path, {})
    servers = d.get("mcpServers") if isinstance(d, dict) else None
    return {k: v for k, v in servers.items() if isinstance(v, dict)} if isinstance(servers, dict) else {}


def _family(server: str) -> str:
    return tool_key(f"mcp__{server}__x").split(":", 1)[0]


def registered(config_paths: list[Path], extra_keys: set[str] | None = None) -> set[str]:
    """その MCP 設定で、部品が実際に持っている道具の鍵。体の部品は M5_ALLOWED_TOOLS で絞られていれば、その分だけ"""
    keys = set(labels()) | (extra_keys or set())
    out: set[str] = set()
    for cp in config_paths:
        for name, cfg in _servers(cp).items():
            fam = _family(name)
            only = (cfg.get("env") or {}).get("M5_ALLOWED_TOOLS") if fam == "m5" else None
            allow = {x.strip() for x in str(only).split(",") if x.strip()} if only else None
            for k in keys:
                f, _, t = k.partition(":")
                if f == fam and (allow is None or t in allow):
                    out.add(k)
    return out


def concrete_names(key: str, config_path: Path, project_dir: Path) -> list[str]:
    """鍵を、Claude Code に渡す名前に戻す(その設定にあるサーバーの名前で)。台本は Bash(python3 <project>/scripts/<名前>.py *)"""
    names: list[str] = []
    servers = _servers(config_path)
    for k in members(key):
        fam, _, tool = k.partition(":")
        if fam == "script":
            names.append(f"Bash(python3 {project_dir}/scripts/{tool}.py *)")
        elif fam == "claude":
            names.append(tool)
        else:
            names.extend(f"mcp__{name}__{tool}" for name in servers if _family(name) == fam)
    return names


def disallowed(base: Path, mode: str, config_path: Path, project_dir: Path) -> list[str]:
    """その場で止める道具(--disallowedTools 用)"""
    out: list[str] = []
    for key in gates(base).get(mode, {}).get("off", []):
        out.extend(n for n in concrete_names(key, config_path, project_dir) if n not in out)
    return out


def extra_allowed(base: Path, config_path: Path, project_dir: Path) -> list[str]:
    """自律で、許しの一覧に足す道具(--allowedTools に足す)"""
    out: list[str] = []
    g = gates(base)["alone"]
    for key in g["on"]:
        if key in g["off"]:
            continue
        out.extend(n for n in concrete_names(key, config_path, project_dir) if n not in out)
    return out


def effective(key: str, base_alone: set[str], reg: set[str], g: dict) -> dict:
    """その道具が、いまそれぞれの場で渡っているか。{"alone": {"on", "can"}, "chat": {"on", "can"}}。
    can = 画面から開け閉めできるか(Claude の道具と、部品が持っていない道具はできない)"""
    fam = key.partition(":")[0]
    ks = members(key)
    present = fam in ("script", "claude") or any(k in reg for k in ks)
    can = fam != "claude" and present
    in_alone = any(k in base_alone for k in ks) or key in g["alone"]["on"]
    return {"alone": {"on": present and in_alone and key not in g["alone"]["off"], "can": can},
            "chat": {"on": present and key not in g["chat"]["off"], "can": can}}


# ---- 道具の説明を部品から集める(2026-11-16 ありさん: 一言だけでなく、渡している説明を全部見たい) ----

def descriptions_path(base: Path) -> Path:
    return base / "state" / "toolbox" / "descriptions.json"


def _mcp_list_tools(cmd: list[str], env: dict[str, str], timeout: float) -> list[dict]:
    """部品を立ち上げて tools/list を聞く。小さな stdio の JSON-RPC(ライブラリ無し)。返事が無ければ空"""
    # ダッシュボードのサービスは PATH が短い(uvx が見つからない)ので、~/.local/bin を足す。立ち上がらない部品は空(つながらなかった)
    run_env = {**os.environ, **env}
    run_env["PATH"] = f"{Path.home() / '.local' / 'bin'}:{run_env.get('PATH', '/usr/bin:/bin')}"
    try:
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                env=run_env, text=True, bufsize=1)
    except OSError:
        return []
    try:
        def send(obj: dict) -> None:
            assert proc.stdin is not None
            proc.stdin.write(json.dumps(obj) + "\n")
            proc.stdin.flush()
        send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "petit-toolbox", "version": "1"}}})
        deadline = time.monotonic() + timeout
        got_init = False
        while time.monotonic() < deadline:
            r, _, _ = select.select([proc.stdout], [], [], 0.5)
            if not r:
                if proc.poll() is not None:
                    break
                continue
            line = proc.stdout.readline() if proc.stdout else ""
            if not line:
                break
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            if msg.get("id") == 1 and not got_init:
                got_init = True
                send({"jsonrpc": "2.0", "method": "notifications/initialized"})
                send({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
            elif msg.get("id") == 2:
                tools = (msg.get("result") or {}).get("tools") or []
                return [t for t in tools if isinstance(t, dict)]
        return []
    finally:
        try:
            proc.kill()
        except OSError:
            pass


def _script_doc(project_dir: Path, name: str) -> str:
    try:
        tree = ast.parse((project_dir / "scripts" / f"{name}.py").read_text(encoding="utf-8"))
        return (ast.get_docstring(tree) or "").strip()
    except (OSError, SyntaxError):
        return ""


def describe(base: Path, config_path: Path, project_dir: Path | None = None, timeout: float = 25.0) -> dict:
    """部品ごとに道具の説明を集めて state/toolbox/descriptions.json に残す。つながらなかった部品は前の分を残す"""
    cache = _json(descriptions_path(base), {})
    tools: dict[str, dict] = dict(cache.get("tools") or {}) if isinstance(cache, dict) else {}
    done: list[str] = []
    failed: list[str] = []
    for name, cfg in _servers(config_path).items():
        cmd = [str(cfg.get("command", ""))] + [str(a) for a in (cfg.get("args") or [])]
        env = {str(k): str(v) for k, v in (cfg.get("env") or {}).items() if k != "M5_ALLOWED_TOOLS"}   # 説明は絞らずに全部集める(渡すかは別)
        found = _mcp_list_tools(cmd, env, timeout) if cmd[0] else []
        if not found:
            failed.append(name)
            continue
        done.append(name)
        for t in found:
            key = tool_key(f"mcp__{name}__{t.get('name', '')}")
            props = ((t.get("inputSchema") or {}).get("properties") or {})
            params = [{"name": pn, "desc": str((pv or {}).get("description", ""))} for pn, pv in props.items() if isinstance(pv, dict) or pv is None]
            tools[key] = {"name": t.get("name", ""), "server": name, "description": str(t.get("description") or ""), "params": params}
    if project_dir:
        for f in sorted((project_dir / "scripts").glob("*.py")):   # 台本は全部(棚に無いものも、記録に出たときのために)
            doc = _script_doc(project_dir, f.stem)
            if doc:
                tools[f"script:{f.stem}"] = {"name": f.name, "server": "scripts", "description": doc, "params": []}
    for key, doc in BUILTIN_DOCS.items():
        tools[key] = {"name": key.split(":", 1)[1], "server": "Claude Code", "description": doc, "params": []}
    out = {"at": datetime.now().isoformat(timespec="minutes"), "tools": tools, "done": done, "failed": failed}
    p = descriptions_path(base)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def descriptions(base: Path) -> dict:
    d = _json(descriptions_path(base), {})
    return d if isinstance(d, dict) else {}


def families_in(config_paths: list[Path]) -> set[str]:
    """MCP 設定(mcpServers)につないである部品の家族(m5 / memory / sns …)"""
    out: set[str] = set()
    for p in config_paths:
        try:
            servers = json.loads(p.read_text(encoding="utf-8")).get("mcpServers", {})
        except (OSError, json.JSONDecodeError, AttributeError):
            continue
        for name in servers if isinstance(servers, dict) else []:
            out.add(tool_key(f"mcp__{name}__x").split(":", 1)[0])
    return out


def allowed_chat(config_paths: list[Path], extra_keys: set[str] | None = None) -> set[str]:
    """会話で使える道具の鍵。会話のセッションは権限を全部通す起動なので、許しの一覧でなく「つないである部品」で決まる。
    台本(script:*)と Claude の道具(claude:*)はいつも。からだの使い方で止める分(見る・聞く・消す など)はここでは見ない"""
    fams = families_in(config_paths)
    keys = set(labels()) | (extra_keys or set())
    return {k for k in keys if k.split(":", 1)[0] in fams or k.startswith(("script:", "claude:"))} | ALWAYS


def allowed_from_names(names: list[str]) -> set[str]:
    """会話の道具一覧(mcp__… や Read などの名前)を鍵に。Bash が丸ごと許されていれば、台本(script:*)もぜんぶ"""
    keys = {tool_key(n) for n in names} | ALWAYS
    if "Bash" in names:
        keys |= {k for k in labels() if k.startswith("script:")}
    return keys


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
    sub.add_parser("gates")
    p = sub.add_parser("gate"); p.add_argument("mode"); p.add_argument("key"); p.add_argument("on")
    p = sub.add_parser("disallowed"); p.add_argument("--mode", required=True); p.add_argument("--config", required=True); p.add_argument("--project", required=True)
    p = sub.add_parser("extra-allowed"); p.add_argument("--config", required=True); p.add_argument("--project", required=True)
    p = sub.add_parser("describe"); p.add_argument("--config", required=True); p.add_argument("--timeout", type=float, default=25.0); p.add_argument("--project")
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
    elif a.cmd == "gates":
        print(json.dumps(gates(base), ensure_ascii=False, indent=1))
    elif a.cmd == "gate":
        try:
            g = set_gate(base, a.mode, a.key, a.on.lower() == "on")
        except ValueError as e:
            print(str(e), file=sys.stderr)
            return 2
        print(json.dumps(g[a.mode], ensure_ascii=False))
    elif a.cmd == "disallowed":
        print(",".join(disallowed(base, a.mode, Path(a.config), Path(a.project))))
    elif a.cmd == "extra-allowed":
        print(",".join(extra_allowed(base, Path(a.config), Path(a.project))))
    elif a.cmd == "describe":
        r = describe(base, Path(a.config), Path(a.project) if a.project else None, a.timeout)
        print(f"集めた: {len(r['tools'])} 道具 / つながった部品 {len(r['done'])} / つながらなかった {len(r['failed'])}")
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
