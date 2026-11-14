#!/usr/bin/env python3
"""からだの使い方(見る・話す・鳴らす・聞く)と「からだ おやすみ」。会話・体のイベント・自律行動で同じ決まり。

置き場所は その子の characters/<id>/config/settings.json:

    {"body": {"see": true, "speak": true, "sound": true, "hear": false},
     "rest": {"until": "2026-11-14T15:30:00", "hours": [[23, 0, 7, 0]]}}

- body: ふだんのスイッチ。see = 見る(カメラ take_snapshot)、speak = 話す(声 speak)、sound = 鳴らす(効果音 play_sound・play_icon)、
  hear = 聞く(マイク mic_start・mic_stop)。無ければ古い allow_camera / allow_sound / allow_microphone を読む(speak は true)
- rest: からだ おやすみ = 見る・話す・鳴らす を止める(聞く はそのまま)。考える・書く・調べる・手紙はいつも通り。
  until = いまから何時間(📍 の「からだ おやすみ 30 分」や設定ページのボタン)。hours = 毎日この時間(日をまたいでよい)
- 決め方: おやすみ中なら 見る・話す・鳴らす は false。それ以外はふだんのスイッチ

使うところ:
- ダッシュボード(会話・体のイベント): effective() → 道具一覧と --disallowedTools、文は prompts/autonomous/permission_rules.md
- 自律行動(autonomous-action.sh): `body_switches.py rules --character <id>`(文)と `disallowed --character <id>`(止める道具)

Usage:
    python3 body_switches.py show --character <id>
    python3 body_switches.py rules --character <id>                 # ## 現在の制限 の各行(無ければ何も出さない)
    python3 body_switches.py disallowed --character <id>            # 止める道具(カンマ区切り。無ければ何も出さない)
    python3 body_switches.py rest --character <id> --minutes 30     # いまから 30 分 からだ おやすみ(--off でやめる)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

SWITCHES = ("see", "speak", "sound", "hear")
DEFAULTS = {"see": True, "speak": True, "sound": True, "hear": False}
LEGACY = {"see": "allow_camera", "sound": "allow_sound", "hear": "allow_microphone"}
REST_OFF = ("see", "speak", "sound")   # おやすみ中に止めるもの
TOOLS = {"see": ["take_snapshot"], "speak": ["speak"], "sound": ["play_sound", "play_icon"], "hear": ["mic_start", "mic_stop"]}
WORDS = {"see": "見る(カメラ)", "speak": "話す(声)", "sound": "鳴らす(効果音)", "hear": "聞く(マイク)"}
TOOL_PREFIX = "mcp__m5-mcp__"
REST_MAX_MIN = 24 * 60
REST_WORDS = {"until": "いまから", "hours": "毎日の時間"}


def data_dir() -> Path:
    return Path(os.environ.get("PETIT_DATA_DIR") or Path.home() / "petit_claude")


def settings_path(character_id: str, base: Path | None = None) -> Path:
    return (base or data_dir()) / "characters" / character_id / "config" / "settings.json"


def load_settings(character_id: str, base: Path | None = None) -> dict:
    try:
        d = json.loads(settings_path(character_id, base).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def base_switches(settings: dict) -> dict[str, bool]:
    """ふだんのスイッチ。body に無いものは古い allow_* から(それも無ければ既定)"""
    body = settings.get("body") if isinstance(settings.get("body"), dict) else {}
    out = {}
    for k in SWITCHES:
        if k in body:
            out[k] = bool(body[k])
        elif k in LEGACY and LEGACY[k] in settings:
            out[k] = bool(settings[LEGACY[k]])
        else:
            out[k] = DEFAULTS[k]
    return out


def _hm(t: datetime) -> str:
    return f"{t.hour}:{t.minute:02d}"


def rest_state(settings: dict, now: datetime) -> dict | None:
    """おやすみ中なら {"why": "いまから"|"毎日の時間", "until": datetime}。違えば None"""
    rest = settings.get("rest") if isinstance(settings.get("rest"), dict) else {}
    try:
        until = datetime.fromisoformat(rest.get("until") or "")
    except (TypeError, ValueError):
        until = None
    if until and until > now:
        return {"why": REST_WORDS["until"], "until": until}
    for r in rest.get("hours") or []:
        if not (isinstance(r, list) and len(r) == 4):
            continue
        sh, sm, eh, em = (int(x) for x in r)
        start_m, end_m, now_m = sh * 60 + sm, eh * 60 + em, now.hour * 60 + now.minute
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        if start_m == end_m:
            continue
        if start_m < end_m:   # 同じ日の中(13:00〜15:00)
            if start_m <= now_m < end_m:
                return {"why": REST_WORDS["hours"], "until": today + timedelta(minutes=end_m)}
        elif now_m >= start_m:   # 日をまたぐ(23:00〜7:00)の、前半
            return {"why": REST_WORDS["hours"], "until": today + timedelta(days=1, minutes=end_m)}
        elif now_m < end_m:      # 後半
            return {"why": REST_WORDS["hours"], "until": today + timedelta(minutes=end_m)}
    return None


def effective(settings: dict, now: datetime | None = None) -> dict:
    """いま使ってよいもの。{"switches": {see, speak, sound, hear}, "rest": None | {"why", "until"}}"""
    now = now or datetime.now()
    sw = base_switches(settings)
    rest = rest_state(settings, now)
    if rest:
        for k in REST_OFF:
            sw[k] = False
    return {"switches": sw, "rest": rest}


def disallowed_tools(switches: dict[str, bool]) -> list[str]:
    """止める道具(Claude Code の --disallowedTools に渡す。skip-permissions でも効く)"""
    return [TOOL_PREFIX + t for k in SWITCHES if not switches.get(k, True) for t in TOOLS[k]]


def rest_note(rest: dict | None) -> str:
    """「いまは からだ おやすみ(15:30 まで。いまから): カメラ・声・効果音は使わない。…」"""
    if not rest:
        return ""
    return (f"いまは からだ おやすみ({_hm(rest['until'])} まで。{rest['why']}): カメラ・声・効果音は使わない。"
            "考える・書く・調べる・手紙・記憶はいつも通り")


def template_vars(eff: dict) -> dict:
    """prompts/autonomous/permission_rules.md に渡す値"""
    sw = eff["switches"]
    return {"allow_camera": sw["see"], "allow_speak": sw["speak"], "allow_sound": sw["sound"], "allow_mic": sw["hear"],
            "rest_note": rest_note(eff["rest"])}


def view(settings: dict, now: datetime | None = None) -> dict:
    """設定ページ・📍 に出す形(JSON にできる)"""
    now = now or datetime.now()
    eff = effective(settings, now)
    rest = eff["rest"]
    rest_cfg = settings.get("rest") if isinstance(settings.get("rest"), dict) else {}
    return {
        "base": base_switches(settings),
        "effective": eff["switches"],
        "rest": {"on": bool(rest), "why": rest["why"] if rest else "", "until": _hm(rest["until"]) if rest else "",
                 "until_iso": rest["until"].isoformat(timespec="minutes") if rest else "",
                 "hours": [r for r in (rest_cfg.get("hours") or []) if isinstance(r, list) and len(r) == 4]},
        "words": WORDS,
    }


def set_rest(character_id: str, minutes: int | None, base: Path | None = None, now: datetime | None = None) -> dict:
    """いまから minutes 分 おやすみ(None・0 でやめる)。settings.json の rest.until だけ書き換える"""
    now = (now or datetime.now()).replace(second=0, microsecond=0)
    if minutes is not None and not (0 <= minutes <= REST_MAX_MIN):
        raise ValueError(f"分は 0〜{REST_MAX_MIN}")
    p = settings_path(character_id, base)
    s = load_settings(character_id, base)
    rest = dict(s.get("rest") or {}) if isinstance(s.get("rest"), dict) else {}
    if minutes:
        rest["until"] = (now + timedelta(minutes=minutes)).isoformat(timespec="minutes")
    else:
        rest.pop("until", None)
    s["rest"] = rest
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(s, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(p)
    return s


def _rules_text(eff: dict, base: Path) -> str:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import render_prompt
    return render_prompt.render("autonomous/permission_rules", template_vars(eff), data_dir=base,
                                project_dir=Path(__file__).resolve().parent.parent).strip()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("show", "rules", "disallowed", "rest"):
        sp = sub.add_parser(name)
        sp.add_argument("--character", required=True)
        if name == "rest":
            sp.add_argument("--minutes", type=int, default=None)
            sp.add_argument("--off", action="store_true")
    a = ap.parse_args()
    base = data_dir()
    settings = load_settings(a.character, base)
    if a.cmd == "show":
        print(json.dumps(view(settings), ensure_ascii=False, indent=2))
    elif a.cmd == "rules":
        text = _rules_text(effective(settings), base)
        if text:
            print(text)
    elif a.cmd == "disallowed":
        tools = disallowed_tools(effective(settings)["switches"])
        if tools:
            print(",".join(tools))
    elif a.cmd == "rest":
        try:
            set_rest(a.character, None if a.off else a.minutes, base)
        except ValueError as e:
            print(e, file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
