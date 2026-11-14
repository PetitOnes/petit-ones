#!/usr/bin/env python3
"""ターミナルチャット(ttyd/tmux の claude)の system prompt を組み立てて標準出力に出す。

使い方:
    python3 scripts/build_chat_prompt.py puchiko                # 1 人
    python3 scripts/build_chat_prompt.py puchiteya puchiko puchiru   # 複数人(先頭に名前を付けて話す決まりが付く)

文面は prompts/chat/system.md(家の PETIT_DATA_DIR/prompts/chat/system.md があればそちら)。
名前は characters/<id>/config/config.json の name。欲求は data/desires.json の起動時点の値。
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
import render_prompt  # noqa: E402

PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("PETIT_DATA_DIR") or (Path.home() / "petit_claude"))


def load_env_value(key: str, default: str = "") -> str:
    try:
        for line in (DATA_DIR / ".env").read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith(f"{key}="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError:
        pass
    return default


def char_name(char_id: str) -> str:
    try:
        return json.loads((DATA_DIR / "characters" / char_id / "config" / "config.json").read_text(encoding="utf-8")).get("name") or char_id
    except (OSError, ValueError):
        return char_id


def desires_text(char_id: str) -> str:
    """欲求の起動時点スナップショット(前の bash 版と同じ見た目)。"""
    try:
        d = json.loads((DATA_DIR / "characters" / char_id / "data" / "desires.json").read_text(encoding="utf-8"))
        labels = d.get("labels", {})
        desires = d.get("desires", {})
        dominant = d.get("dominant", "")
        lines = [f"最も強い欲求: {labels.get(dominant, dominant)}"]
        for k, v in sorted(desires.items(), key=lambda x: -x[1]):
            bar = "█" * int(v * 10) + "░" * (10 - int(v * 10))
            lines.append(f"  {labels.get(k, k)}: [{bar}] {v:.2f}")
        return "\n".join(lines)
    except Exception as e:  # noqa: BLE001 - 読めなくてもチャットは始める
        return f"(desires読み込み失敗: {e})"


def all_character_ids() -> list[str]:
    ids = []
    for p in sorted((DATA_DIR / "characters").glob("*/config/config.json")):
        ids.append(p.parent.parent.name)
    return ids


def build_vars(char_ids: list[str]) -> dict:
    chars = []
    for cid in char_ids:
        soul_path = DATA_DIR / "characters" / cid / "SOUL.md"
        chars.append({
            "id": cid,
            "name": char_name(cid),
            "soul": soul_path.read_text(encoding="utf-8") if soul_path.exists() else "",
            "desires": desires_text(cid),
        })
    owner_id = load_env_value("COMPANION_ID", "arisan")
    owner_name = load_env_value("COMPANION_NAME", "ありさん")
    targets = [c for c in all_character_ids()] + [owner_id]
    return {
        "chars": chars,
        "multi": len(chars) > 1,
        "char_count": str(len(chars)),
        "first_id": chars[0]["id"] if chars else "",
        "name_prefix_examples": " / ".join(f"**{c['name']}**:" for c in chars),
        "owner_name": owner_name,
        "now": datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%Y-%m-%d %H:%M (JST)"),
        "data_dir": str(DATA_DIR),
        "scripts_dir": str(PROJECT_DIR / "scripts"),
        "mailbox_dir": str(DATA_DIR / "mailbox"),
        "mail_targets": ", ".join(targets),
    }


def _whereabouts_lines() -> str:
    """いま どこ(家の人の「いま」と、ぷちの体の居場所。scripts/whereabouts.py)。読めなければ空"""
    try:
        import whereabouts
        return "\n".join(whereabouts.lines(DATA_DIR))
    except Exception:
        return ""


def main(argv: list[str]) -> int:
    ids = argv or all_character_ids()
    variables = build_vars(ids)
    variables["whereabouts"] = _whereabouts_lines()
    try:
        import events
        variables["events"] = "\n".join(events.lines(DATA_DIR, None))
    except Exception:
        variables["events"] = ""
    try:
        import sky
        variables["sky_change"] = sky.change_line(datetime.now(sky.JST).date(), sky.load_place(DATA_DIR))
    except Exception:
        variables["sky_change"] = ""
    sys.stdout.write(render_prompt.render("chat/system", variables, data_dir=DATA_DIR, project_dir=PROJECT_DIR))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
