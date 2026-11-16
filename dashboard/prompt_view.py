"""🔒 ひみつ の「わたしている文」: その子のプロンプトに入る文を、人が読める形で並べる。

読むだけで、家には何も書かない(「伝えたら覚える」知らせは、ここでは作らない)。並べるもの:

- 毎回わたす文: 自律行動の user prompt(いま組み立てたら、の形)と、会話の system prompt
- 毎回付くファイル: SOUL.md・TODO(TODO_ACTIVE.md → TODO.md → 家の TODO.md の順。autonomous-action.sh と同じ)・diary_summary.md
- 自分で読みに行くファイル: ROUTINES.md・TODO_ARCHIVE.md・REFLECTION_INDEX.md・SOUL_REFLECTIONS.md・ROUTINES_DETAIL.md
- 欲求: いまの値(ぷちは道具 get_desires で見に行く)

ファイルの重さの目安は autonomous-action.sh と同じ(PROMPT_FILE_WARN_KB、既定 40 KB。80 KB を超えると @ 添付が黙って落ちる)。
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

DROP_KB = 80   # これを超えると、Claude Code が @ 添付を黙って落とす(2026-11-13 の実測: 70 KB は付く、85 KB は落ちる)

# (key, ファイル名, 題, いつ読まれるか: always = 毎回付く / self = その子が自分で読みに行く)
FILES: list[tuple[str, str, str, str]] = [
    ("soul", "SOUL.md", "SOUL(魂の定義)", "always"),
    ("todo", "", "TODO(いまの分)", "always"),
    ("diary_summary", "diary_summary.md", "日記のまとめ", "always"),
    ("routines", "ROUTINES.md", "ROUTINES(ルーチン)", "self"),
    ("todo_archive", "TODO_ARCHIVE.md", "TODO_ARCHIVE(終わったこと)", "self"),
    ("reflection_index", "REFLECTION_INDEX.md", "REFLECTION_INDEX(ふりかえりの索引)", "self"),
    ("soul_reflections", "SOUL_REFLECTIONS.md", "SOUL_REFLECTIONS(ふりかえり)", "self"),
    ("routines_detail", "ROUTINES_DETAIL.md", "ROUTINES_DETAIL(ルーチンの記録)", "self"),
]
PROMPTS: list[tuple[str, str]] = [   # (key, 題)
    ("auto_prompt", "自律行動のたびに渡す文"),
    ("chat_prompt", "会話のはじめに渡す文(system prompt)"),
]


def _char_dir(data_dir: Path, character_id: str) -> Path:
    return Path(data_dir) / "characters" / character_id


def todo_path(data_dir: Path, character_id: str) -> Path:
    """自律行動に付く TODO。autonomous-action.sh と同じ順で探す"""
    cdir = _char_dir(data_dir, character_id)
    for name in ("TODO_ACTIVE.md", "TODO.md"):
        if (cdir / name).is_file():
            return cdir / name
    return Path(data_dir) / "TODO.md"


def file_path(data_dir: Path, character_id: str, key: str) -> Path | None:
    """key のファイルの場所(無い key は None)。ROUTINES.md は、その子のものが無ければ家のもの"""
    if key == "todo":
        return todo_path(data_dir, character_id)
    for k, name, _title, _when in FILES:
        if k == key:
            p = _char_dir(data_dir, character_id) / name
            if key == "routines" and not p.is_file():
                return Path(data_dir) / name
            return p
    return None


def file_rows(data_dir: Path, character_id: str, warn_kb: int = 40) -> list[dict]:
    """ファイルの一覧(中身は入れない)。無いファイルは出さない。

    heavy: 毎回付くファイルだけ。"warn" = 目安を超えた / "drop" = 80 KB を超えて、自律行動には付いていないおそれ
    """
    rows = []
    for key, _name, title, when in FILES:
        p = file_path(data_dir, character_id, key)
        if p is None or not p.is_file():
            continue
        st = p.stat()
        kb = st.st_size / 1024
        heavy = ""
        if when == "always":
            heavy = "drop" if kb > DROP_KB else "warn" if kb >= warn_kb else ""
        rows.append({"key": key, "kind": "file", "title": title, "when": when, "name": p.name, "size": st.st_size,
                     "mtime": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="minutes"), "heavy": heavy})
    return rows


def read_file(data_dir: Path, character_id: str, key: str) -> str | None:
    p = file_path(data_dir, character_id, key)
    if p is None or not p.is_file():
        return None
    return p.read_text(encoding="utf-8", errors="replace")


def desire_rows(desires: dict) -> dict:
    """欲求のいまの値を、強い順に(desires.json の形から)"""
    levels = desires.get("desires") if isinstance(desires.get("desires"), dict) else {}
    labels, colors = desires.get("labels") or {}, desires.get("colors") or {}
    rows = [{"key": k, "label": labels.get(k, k), "level": v, "color": colors.get(k, "")}
            for k, v in levels.items() if isinstance(v, (int, float))]
    rows.sort(key=lambda r: -r["level"])
    return {"rows": rows, "dominant": desires.get("dominant", ""), "updated_at": desires.get("updated_at", "")}


def unread_count(data_dir: Path, character_id: str) -> int:
    """その子あての、まだ読んでいない手紙の数(scripts/list_unread_mail.py と同じ数え方)"""
    mailbox = Path(data_dir) / "mailbox"
    if not mailbox.is_dir():
        return 0
    try:
        mails = json.loads((mailbox / ".metadata.json").read_text(encoding="utf-8")).get("mails", {})
    except (OSError, json.JSONDecodeError):
        mails = {}
    n = 0
    for f in mailbox.iterdir():
        if not f.name.endswith(".md"):
            continue
        if f"_to_{character_id}_" not in f.stem and not f.stem.startswith(f"to_{character_id}"):
            continue
        if character_id not in (mails.get(f.name) or {}).get("read_by", []):
            n += 1
    return n


def autonomous_preview(data_dir: Path, project_dir: Path, character_id: str, *, now: datetime, user_name: str,
                       mail_targets: str, permission_rules: str = "", whereabouts: str = "", event_notice: str = "",
                       warn_kb: int = 40) -> str:
    """自律行動の user prompt を、いま組み立てたらどうなるか(prompts/autonomous/user.md)。

    通常回(8 割)の形で作る。その回にあったときだけ足される知らせ(記念日・手紙やノートが読まれた・体の出来事・
    空や部屋やスマホや体の場所が変わった・ぷちSNS のお知らせ)は、伝えると「伝えた」と覚える作りなので、ここでは入れない
    """
    scripts = str(Path(project_dir) / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    import render_prompt

    def render(name: str, /, **variables) -> str:
        return render_prompt.render(f"autonomous/{name}", variables, data_dir=data_dir, project_dir=project_dir)

    data_dir, project_dir = Path(data_dir), Path(project_dir)
    cdir = _char_dir(data_dir, character_id)
    todo = todo_path(data_dir, character_id)
    summary = cdir / "diary_summary.md"
    night = now.hour < 7
    time_rule = render("time_rule_night") if night else render("time_rule_day", user_name=user_name, user_room=f"{user_name}の部屋")
    heavy_lines = []
    for p in (cdir / "SOUL.md", todo, summary):
        if p.is_file() and p.stat().st_size // 1024 >= warn_kb:
            heavy_lines.append(render("heavy_file_line", name=p.name, kb=p.stat().st_size // 1024, warn_kb=warn_kb).rstrip("\n"))
    mailbox_notice = ""
    if (data_dir / "mailbox").is_dir():
        n = unread_count(data_dir, character_id)
        common = {"project_dir": str(project_dir), "character_id": character_id}
        mailbox_notice = render("mail_unread", unread_count=n, **common) if n else render("mail_send", mail_targets=mail_targets, **common)
    return render(
        "user",
        current_date=now.strftime("%Y-%m-%d %H:%M:%S"), character_dir=str(cdir), character_id=character_id,
        reflection_index_line="", todo_path=str(todo), diary_summary_line=f"@{summary}" if summary.is_file() else "",
        routine_mode=render("routine_mode_normal").strip(), time_rule=time_rule.strip(), project_dir=str(project_dir),
        heavy_section=render("heavy_files", heavy_files_note="\n".join(heavy_lines)).strip() if heavy_lines else "",
        mailbox_notice=mailbox_notice.strip(), permission_rules=permission_rules, whereabouts=whereabouts, event_notice=event_notice,
    )
