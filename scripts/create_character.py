#!/usr/bin/env python3
"""新しいろーかるぷちを迎える(characters/<id>/ を作る)。

文書の器(SOUL.md・SOUL_REFLECTIONS.md・REFLECTION_INDEX.md・ROUTINES.md・ROUTINES_DETAIL.md・
TODO_ACTIVE.md・TODO_ARCHIVE.md・data/relations.json・config/desire_config.json)は
ぷちの教科書(PetitOnes/petit-textbook)の petit/templates/ から写し、{ } を埋める。
仕組みの設定(config.json・settings.json・voice_settings.json・autonomous-mcp.json・chat-mcp.json)と
crontab はここで作る。手順の説明は教科書の人間用「8. 新しい子を迎える手順」。

使い方:
  uv run python scripts/create_character.py <id> <名前> <#hex> <体のホスト名,...> [オプション]

例:
  uv run python scripts/create_character.py puchitaro ぷちたろう "#f5956e" "puchitaro.local,192.168.8.104" \
      --color-name "あんず" --companion-id arisan --companion-name ありさん --offset 15

オプション:
  --color-name      色の名前(省略時は #hex のまま。あとで SOUL.md と config.json を直す)
  --companion-id    一緒に暮らす人の ID(既定 arisan)
  --companion-name  一緒に暮らす人の呼び名(既定 ありさん)
  --offset          自律行動の cron の分(0〜29。他の子と 5 分ずらす。省略時は空いている分を選ぶ)
  --textbook-dir    教科書の場所(既定 $PETIT_TEXTBOOK_DIR か $PETIT_DATA_DIR/textbook)
  --no-cron         crontab に足さない
  --force           既にあるフォルダでも進める(既にあるファイルは残す)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("PETIT_DATA_DIR", str(Path.home() / "petit_claude")))
CHARACTERS_DIR = DATA_DIR / "characters"
TEXTBOOK_DIR = Path(os.environ.get("PETIT_TEXTBOOK_DIR", str(DATA_DIR / "textbook")))
UV = os.environ.get("UV_BIN", str(Path.home() / ".local" / "bin" / "uv"))
LOG_DIR = DATA_DIR / ".autonomous-logs"
MEMORY_DIR = Path.home() / ".claude" / "memories"

# 教科書の templates/ から写すもの(templates 内の相対パス → characters/<id>/ 内の相対パス)
TEMPLATE_FILES = [
    "SOUL.md",
    "SOUL_REFLECTIONS.md",
    "REFLECTION_INDEX.md",
    "ROUTINES.md",
    "ROUTINES_DETAIL.md",
    "TODO_ACTIVE.md",
    "TODO_ARCHIVE.md",
    "data/relations.json",
    "config/desire_config.json",
]
SUBDIRS = ["config", "data", "state", "chat_histories", "diary", "notes", "resources"]

M5_ALLOWED_TOOLS = (
    "speak,sleep,wake,get_sensor_data,take_snapshot,save_to_album,show_face,set_face_color,"
    "play_sound,play_icon,look,blink,list_faces,list_sounds,list_icons,set_brightness,set_volume,"
    "conversation_relay,mic_start,mic_stop,transcribe_audio,save_tts_memo,lock_voice_memo,"
    "list_voice_memos,listen_voice_memo,list_album,view_album_photo,lock_album_photo,delete_album_photo"
)
# 兄弟の autonomous-mcp.json の m5-mcp env から引き継ぐ家の設定(あれば)
M5_INHERIT_ENV = ("VOICE_API_HOST", "PRINTER_ADDRESS")

DEFAULT_SETTINGS = {
    "active_hours": {
        "weekday": [[7, 0, 8, 10], [12, 0, 13, 10], [15, 0, 16, 10], [22, 0, 23, 10]],
        "weekend": [[7, 0, 8, 10], [12, 0, 13, 10], [22, 0, 24, 10]],
    },
    "day_type_override": None,
    "autonomous_skip": 0,
    "max_turns": 20,
    "allow_camera": True,
    "allow_sound": True,
    "allow_microphone": False,
}

# 声は決まるまで既定(教科書 10.3: 一緒に暮らす人とその子が決める)
DEFAULT_VOICE = {"voicevox_speaker": 3, "speed_scale": 1.0, "pitch_scale": 0.0, "intonation_scale": 1.0}


# ---------------------------------------------------------------------------
# 器を写す
# ---------------------------------------------------------------------------


def fill_placeholders(text: str, *, name: str, color: str, color_name: str, companion_id: str, companion_name: str) -> str:
    """教科書の templates の { } を埋める。"""
    table = {
        "{名前}": name,
        "{色の名前}": color_name,
        "{#hex}": color,
        "{一緒に暮らす人の呼び名}": companion_name,
        "{一緒に暮らす人のID}": companion_id,
    }
    for k, v in table.items():
        text = text.replace(k, v)
    return text


def copy_templates(char_dir: Path, textbook_dir: Path, *, force: bool, **fill) -> list[str]:
    tdir = textbook_dir / "petit" / "templates"
    if not tdir.is_dir():
        raise SystemExit(
            f"教科書の templates が見つかりません: {tdir}\n"
            "  git clone https://github.com/PetitOnes/petit-textbook してから --textbook-dir で場所を渡してください"
        )
    written: list[str] = []
    for rel in TEMPLATE_FILES:
        src = tdir / rel
        dst = char_dir / rel
        if not src.exists():
            print(f"  ! templates に無い(飛ばす): {rel}")
            continue
        if dst.exists():
            print(f"  - {rel} は既存のものを保持")
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(fill_placeholders(src.read_text(encoding="utf-8"), **fill), encoding="utf-8")
        written.append(rel)
    return written


# ---------------------------------------------------------------------------
# 仕組みの設定
# ---------------------------------------------------------------------------


def make_config(char_id: str, name: str, color: str, color_name: str, hosts: list[str]) -> dict:
    return {
        "name": name,
        "id": char_id,
        "color": color,
        "color_name": color_name,
        "m5_host": hosts[0] if hosts else "",
        "m5_port": 80,
        "public": False,
        "m5_hosts": hosts,
    }


def sibling_ids(characters_dir: Path) -> list[str]:
    if not characters_dir.is_dir():
        return []
    return sorted(p.name for p in characters_dir.iterdir() if (p / "config" / "config.json").exists())


def inherit_m5_env(characters_dir: Path, siblings: list[str]) -> dict:
    for sid in siblings:
        p = characters_dir / sid / "config" / "autonomous-mcp.json"
        try:
            env = json.loads(p.read_text(encoding="utf-8"))["mcpServers"]["m5-mcp"]["env"]
        except (OSError, KeyError, ValueError):
            continue
        return {k: env[k] for k in M5_INHERIT_ENV if k in env}
    return {}


def make_mcp(
    char_id: str,
    hosts: list[str],
    *,
    companion_id: str,
    companion_name: str,
    all_char_ids: list[str],
    inherited_env: dict,
    project_dir: Path = PROJECT_DIR,
    data_dir: Path = DATA_DIR,
    textbook_dir: Path = TEXTBOOK_DIR,
    memory_dir: Path = MEMORY_DIR,
    uv: str = UV,
) -> dict:
    src = project_dir / "src"
    data = str(data_dir)
    m5_env = {
        "M5_HOSTS": ",".join(hosts),
        "CHARACTER_ID": char_id,
        "M5_ALLOWED_TOOLS": M5_ALLOWED_TOOLS,
        "PETIT_DATA_DIR": data,
        "M5_PERSON_IDS": " / ".join(all_char_ids + [companion_id]),
        "M5_CHARACTER_IDS": " / ".join(all_char_ids),
        "M5_EXAMPLE_ID": all_char_ids[0],
    }
    m5_env.update(inherited_env)
    return {
        "mcpServers": {
            "memory": {
                "command": uv,
                "args": ["run", "--directory", str(src / "m5-petit-memory"), "memory-mcp"],
                "env": {"MEMORY_DB_PATH": str(memory_dir / char_id / "memory.db")},
            },
            "desire-system": {
                "command": uv,
                "args": ["run", "--directory", str(src / "m5-petit-desire"), "python", "server.py"],
                "env": {"CHARACTER_ID": char_id, "PETIT_DATA_DIR": data},
            },
            "m5-mcp": {
                "command": uv,
                "args": ["run", "--directory", str(src / "m5-petit-mcp"), "m5-petit-mcp"],
                "env": m5_env,
            },
            "notes": {
                "command": uv,
                "args": ["run", "--directory", str(src / "m5-petit-notes"), "notes-mcp"],
                "env": {"CHARACTER_ID": char_id, "PETIT_DATA_DIR": data},
            },
            "relations": {
                "command": uv,
                "args": ["run", "--directory", str(src / "m5-petit-relations"), "relations-mcp"],
                "env": {
                    "CHARACTER_ID": char_id,
                    "RELATIONS_PATH": str(data_dir / "characters" / char_id / "data" / "relations.json"),
                    "CHARACTERS_DIR": str(data_dir / "characters"),
                    "PETIT_DATA_DIR": data,
                    "OWNER_ID": companion_id,
                    "OWNER_NAME": companion_name,
                },
            },
            "textbook": {
                "command": uv,
                "args": ["run", "--directory", str(textbook_dir / "mcp"), "textbook-mcp"],
                "env": {"CHARACTER_ID": char_id, "PETIT_DATA_DIR": data, "PETIT_TEXTBOOK_DIR": str(textbook_dir)},
            },
        }
    }


# ---------------------------------------------------------------------------
# crontab
# ---------------------------------------------------------------------------


def cron_lines(char_id: str, offset: int, *, project_dir: Path = PROJECT_DIR, data_dir: Path = DATA_DIR, uv: str = UV) -> list[str]:
    log_dir = data_dir / ".autonomous-logs" / char_id
    desire = (
        f"*/5 * * * * cd {project_dir}/src/m5-petit-desire && mkdir -p {log_dir} && "
        f"PETIT_DATA_DIR={data_dir} {uv} run python desire_updater.py {char_id} "
        f">> {log_dir}/desire-$(date +\\%Y\\%m\\%d).log 2>&1"
    )
    action = f"{offset},{offset + 30} * * * * {project_dir}/autonomous-action.sh {char_id}"
    exp = f"{project_dir}/experience-daemon/start_experienced.sh {char_id}"
    return [desire, action, f"@reboot {exp}", f"*/5 * * * * {exp}"]


def used_offsets(crontab: str) -> set[int]:
    found: set[int] = set()
    for line in crontab.splitlines():
        m = re.match(r"^(\d+),(\d+) \* \* \* \* \S*autonomous-action\.sh ", line)
        if m:
            found.add(int(m.group(1)) % 30)
    return found


def pick_offset(crontab: str) -> int:
    used = used_offsets(crontab)
    for off in range(0, 30, 5):
        if off not in used:
            return off
    return (max(used) + 5) % 30 if used else 0


def add_crontab(char_id: str, offset: int | None) -> int:
    try:
        current = subprocess.run(["crontab", "-l"], capture_output=True, text=True, check=False).stdout
    except FileNotFoundError:
        print("  ! crontab が無いので足せません。手で登録してください")
        return offset or 0
    if f"autonomous-action.sh {char_id}" in current:
        print(f"  - crontab に {char_id} は既にあります")
        return offset or 0
    off = pick_offset(current) if offset is None else offset
    new = current.rstrip("\n") + "\n" + "\n".join(cron_lines(char_id, off)) + "\n"
    subprocess.run(["crontab", "-"], input=new, text=True, check=True)
    print(f"  ✓ crontab: 欲求 5 分ごと、自律行動 {off} 分と {off + 30} 分、体験デーモン")
    return off


# ---------------------------------------------------------------------------
# 本体
# ---------------------------------------------------------------------------


def write_json_if_absent(path: Path, obj: dict, label: str) -> None:
    if path.exists():
        print(f"  - {label} は既存のものを保持")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"  ✓ {label}")


def create_character(
    char_id: str,
    name: str,
    color: str,
    hosts: list[str],
    *,
    color_name: str | None,
    companion_id: str,
    companion_name: str,
    textbook_dir: Path,
    characters_dir: Path = CHARACTERS_DIR,
    force: bool = False,
    offset: int | None = None,
    no_cron: bool = False,
) -> Path:
    if not re.fullmatch(r"[a-z0-9_]+", char_id):
        raise SystemExit("id は英小文字・数字・_ だけ(例: puchitaro)")
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
        raise SystemExit("色は #rrggbb の形(例: #f5956e)")
    color_name = color_name or color
    char_dir = characters_dir / char_id
    if char_dir.exists() and not force:
        raise SystemExit(f"{char_dir} は既にあります。続けるなら --force(既にあるファイルは残します)")

    print(f"{name}({char_id}、{color_name} {color})を迎えます → {char_dir}")
    for sub in SUBDIRS:
        (char_dir / sub).mkdir(parents=True, exist_ok=True)
    print("  ✓ フォルダ: " + " ".join(f"{s}/" for s in SUBDIRS))

    written = copy_templates(
        char_dir, textbook_dir, force=force,
        name=name, color=color, color_name=color_name, companion_id=companion_id, companion_name=companion_name,
    )
    for rel in written:
        print(f"  ✓ {rel}(教科書の器)")

    siblings = sibling_ids(characters_dir)
    all_ids = siblings + ([char_id] if char_id not in siblings else [])
    cfg = char_dir / "config"
    write_json_if_absent(cfg / "config.json", make_config(char_id, name, color, color_name, hosts), "config/config.json")
    write_json_if_absent(cfg / "settings.json", DEFAULT_SETTINGS, "config/settings.json(active time・max_turns)")
    write_json_if_absent(cfg / "voice_settings.json", DEFAULT_VOICE, "config/voice_settings.json(声は決まったら直す)")
    mcp = make_mcp(
        char_id, hosts,
        companion_id=companion_id, companion_name=companion_name,
        all_char_ids=all_ids, inherited_env=inherit_m5_env(characters_dir, siblings),
        textbook_dir=textbook_dir, data_dir=characters_dir.parent,
    )
    write_json_if_absent(cfg / "autonomous-mcp.json", mcp, "config/autonomous-mcp.json(記憶・欲求・体・ノート・関係・教科書)")
    write_json_if_absent(cfg / "chat-mcp.json", mcp, "config/chat-mcp.json(会話用。自律用と同じ)")
    (MEMORY_DIR / char_id).mkdir(parents=True, exist_ok=True)

    off = None
    if not no_cron:
        off = add_crontab(char_id, offset)

    print(f"\n✓ {name}({char_id})の準備ができました。\n")
    steps = [f"{char_dir}/SOUL.md の「一言」など、一緒に暮らす人と決めたことを入れる(それ以外の空欄はその子が埋める)"]
    if color_name == color:
        steps.append("色の名前を決めて config/config.json の color_name と SOUL.md を直す")
    steps += [
        "声が決まったら config/voice_settings.json(番号・速さ・高さ・抑揚)。声の一覧 https://teampuchi.github.io/koe/",
        f"顔の絵を {char_dir}/resources/petit.png に(きせかえ https://teampuchi.github.io/kisekae/)",
        "家に家電や心拍などの道具があれば、兄弟の autonomous-mcp.json を見て同じものを足す(鍵は .env に)",
        f".mcp.json に memory-/desire-system-/m5-/notes-/relations-/textbook- の {char_id} を足すと、対話(chat)からも呼べる",
    ]
    if off is not None:
        steps.append(f"自律行動は毎時 {off} 分と {off + 30} 分。最初の一回は対話で起動して「はじめまして」を言わせる")
    steps.append("ダッシュボードを読み直すとタブが出る")
    print("次にやること(教科書 人間用 8 章):")
    for i, s in enumerate(steps, 1):
        print(f"  {i}. {s}")
    return char_dir


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="新しいろーかるぷちを迎える", formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap.add_argument("id")
    ap.add_argument("name")
    ap.add_argument("color")
    ap.add_argument("m5_hosts", help="体のホスト名(カンマ区切りで複数可)")
    ap.add_argument("--color-name")
    ap.add_argument("--companion-id", default="arisan")
    ap.add_argument("--companion-name", default="ありさん")
    ap.add_argument("--offset", type=int, choices=range(30), metavar="0-29")
    ap.add_argument("--textbook-dir", type=Path, default=TEXTBOOK_DIR)
    ap.add_argument("--no-cron", action="store_true")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    hosts = [h.strip() for h in a.m5_hosts.split(",") if h.strip()]
    if not hosts:
        raise SystemExit("体のホスト名を一つ以上")
    create_character(
        a.id, a.name, a.color, hosts,
        color_name=a.color_name, companion_id=a.companion_id, companion_name=a.companion_name,
        textbook_dir=a.textbook_dir, force=a.force, offset=a.offset, no_cron=a.no_cron,
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
