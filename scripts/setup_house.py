#!/usr/bin/env python3
"""家(PETIT_DATA_DIR)を用意する。create_character.py の対(家で一つのものを作る)。

何度実行してもよい。既にあるものは「あります」と出して触らない。

作るもの:
  - フォルダ: characters/ mailbox/ chat_history/ config/ state/ .autonomous-logs/ token_logs/
  - 交換ノート・グループチャットの空ファイル(chat_history/*.json)
  - .env(無ければ .env.example から写す。鍵は自分で入れる)
  - ぷちの教科書の clone(PETIT_DATA_DIR/textbook)
  - 夜の cron 3 本: 記憶の整理 04:05、教科書の pull 04:30、日記の生成 23:50
確かめるもの(足りなければ言うだけ):
  - uv / claude / jq / python3 / git
  - 部品リポが src/ に並んでいるか(無ければ vcs import src < petit.repos)、依存(uv sync 済みか)
  - 家ごとの上書き config/house.sh(任意。無くてよい)

使い方:
  uv run python scripts/setup_house.py            # 作る
  uv run python scripts/setup_house.py --check    # 見るだけ(何も作らない)
  uv run python scripts/setup_house.py --no-cron  # cron に足さない
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("PETIT_DATA_DIR", str(Path.home() / "petit_claude")))
TEXTBOOK_DIR = Path(os.environ.get("PETIT_TEXTBOOK_DIR", str(DATA_DIR / "textbook")))
TEXTBOOK_REPO = "https://github.com/PetitOnes/petit-textbook.git"
UV = os.environ.get("UV_BIN", str(Path.home() / ".local" / "bin" / "uv"))

HOUSE_DIRS = ["characters", "mailbox", "chat_history", "config", "state", ".autonomous-logs", "token_logs"]
CHAT_FILES = ["exchange_notebook.json", "group_chat.json", "trio_chat.json"]
COMPONENTS = ["src/m5-petit-memory", "src/m5-petit-desire", "src/m5-petit-mcp", "src/m5-petit-notes", "src/m5-petit-relations", "dashboard"]
REPOS_FILE = "petit.repos"  # 部品リポの一覧(vcs import src < petit.repos)
COMMANDS = ["uv", "claude", "jq", "python3", "git"]


class Report:
    def __init__(self, check_only: bool):
        self.check_only = check_only
        self.missing: list[str] = []

    def ok(self, what: str) -> None:
        print(f"  = {what}(あります)")

    def made(self, what: str) -> None:
        print(f"  ✓ {what}")

    def need(self, what: str, how: str) -> None:
        print(f"  ! {what} → {how}")
        self.missing.append(what)


def ensure_dirs(data_dir: Path, r: Report) -> None:
    for d in HOUSE_DIRS:
        p = data_dir / d
        if p.is_dir():
            r.ok(f"{d}/")
        elif r.check_only:
            r.need(f"{d}/", "setup_house.py が作る")
        else:
            p.mkdir(parents=True)
            r.made(f"{d}/")


def ensure_chat_files(data_dir: Path, r: Report) -> None:
    for f in CHAT_FILES:
        p = data_dir / "chat_history" / f
        if p.exists():
            r.ok(f"chat_history/{f}")
        elif r.check_only:
            r.need(f"chat_history/{f}", "setup_house.py が空([])で作る")
        else:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("[]\n", encoding="utf-8")
            r.made(f"chat_history/{f}(空)")


def ensure_env(data_dir: Path, project_dir: Path, r: Report) -> None:
    p = data_dir / ".env"
    if p.exists():
        r.ok(".env")
        return
    example = project_dir / ".env.example"
    if r.check_only or not example.exists():
        r.need(".env", f"{example} を {p} に写して鍵を入れる")
        return
    shutil.copy(example, p)
    r.made(f".env(.env.example から。鍵は自分で入れる: {p})")


def ensure_textbook(textbook_dir: Path, r: Report) -> None:
    if (textbook_dir / "petit" / "TEXTBOOK_INDEX.md").exists():
        r.ok(f"教科書 {textbook_dir}")
        return
    if r.check_only:
        r.need("教科書", f"git clone {TEXTBOOK_REPO} {textbook_dir}")
        return
    try:
        subprocess.run(["git", "clone", "-q", TEXTBOOK_REPO, str(textbook_dir)], check=True)
        r.made(f"教科書を clone: {textbook_dir}")
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        r.need("教科書", f"clone に失敗({e})。手で git clone {TEXTBOOK_REPO} {textbook_dir}")


def check_commands(r: Report) -> None:
    for c in COMMANDS:
        path = shutil.which(c) or (UV if c == "uv" and Path(UV).exists() else None)
        if path:
            r.ok(f"コマンド {c}")
        else:
            hint = {
                "uv": "curl -LsSf https://astral.sh/uv/install.sh | sh",
                "claude": "https://docs.claude.com/ の Claude Code を入れる",
                "jq": "sudo apt install jq",
                            }.get(c, "入れる")
            r.need(f"コマンド {c}", hint)


def ensure_src(project_dir: Path, r: Report) -> None:
    """部品リポを src/ に並べる(vcs import)。無いものだけ取る"""
    missing = [c for c in COMPONENTS if c.startswith("src/") and not (project_dir / c).is_dir()]
    if not missing:
        r.ok("部品リポ src/(petit.repos)")
        return
    cmd = f"pip install vcstool && vcs import src < {REPOS_FILE}"
    if r.check_only or not shutil.which("vcs"):
        r.need("部品リポ src/ " + " ".join(missing), f"(cd {project_dir} && {cmd})")
        return
    (project_dir / "src").mkdir(exist_ok=True)
    with open(project_dir / REPOS_FILE, encoding="utf-8") as f:
        res = subprocess.run(["vcs", "import", "src"], stdin=f, cwd=project_dir, capture_output=True, text=True, check=False)
    if res.returncode == 0:
        r.made("部品リポを src/ に並べた(vcs import)")
    else:
        r.need("部品リポ src/", f"vcs import に失敗: {res.stderr.strip()[-200:]}")


def check_components(project_dir: Path, r: Report) -> None:
    for comp in COMPONENTS:
        d = project_dir / comp
        if not d.is_dir():
            r.need(comp, f"vcs import src < {REPOS_FILE}" if comp.startswith("src/") else "リポジトリが欠けている(git pull)")
        elif (d / ".venv").is_dir():
            r.ok(f"依存 {comp}")
        else:
            r.need(f"依存 {comp}", f"(cd {d} && uv sync)")


def check_house_overrides(data_dir: Path, r: Report) -> None:
    """autonomous-action.sh は家に依らない(git 管理)。家ごとの上書きは任意の config/house.sh"""
    p = data_dir / "config" / "house.sh"
    if p.exists():
        r.ok("config/house.sh(家ごとの上書き)")
    else:
        print("  - config/house.sh は無し(無くてよい。USER_ROOM や時間帯のルールを変えたいときに作る)")


def cron_lines(project_dir: Path, data_dir: Path, textbook_dir: Path, uv: str = UV) -> dict[str, str]:
    logs = data_dir / ".autonomous-logs"
    return {
        "memory_sleep_all.sh": f"5 4 * * * PETIT_DATA_DIR={data_dir} {project_dir}/scripts/memory_sleep_all.sh >> {logs}/memory-sleep.log 2>&1",
        "petit-textbook": f"30 4 * * * cd {textbook_dir} && git pull -q --ff-only >/dev/null 2>&1  # ぷちの教科書(petit-textbook)を毎朝取り直す",
        "generate_diary.py": f"50 23 * * * cd {project_dir}/dashboard && PETIT_DATA_DIR={data_dir} {uv} run python generate_diary.py >> {logs}/diary.log 2>&1",
    }


def ensure_cron(project_dir: Path, data_dir: Path, textbook_dir: Path, r: Report) -> None:
    try:
        current = subprocess.run(["crontab", "-l"], capture_output=True, text=True, check=False).stdout
    except FileNotFoundError:
        r.need("cron", "crontab が無い。夜の 3 本は手で登録する")
        return
    add = []
    for key, line in cron_lines(project_dir, data_dir, textbook_dir).items():
        if key in current:
            r.ok(f"cron {key}")
        elif r.check_only:
            r.need(f"cron {key}", line)
        else:
            add.append(line)
    if add:
        new = current.rstrip("\n") + ("\n" if current.strip() else "") + "\n".join(add) + "\n"
        subprocess.run(["crontab", "-"], input=new, text=True, check=True)
        for line in add:
            r.made(f"cron: {line.split('  #')[0]}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="家(PETIT_DATA_DIR)を用意する")
    ap.add_argument("--check", action="store_true", help="見るだけ")
    ap.add_argument("--no-cron", action="store_true")
    ap.add_argument("--data-dir", type=Path, default=DATA_DIR)
    ap.add_argument("--textbook-dir", type=Path, default=None)
    a = ap.parse_args(argv)
    data_dir: Path = a.data_dir
    textbook_dir: Path = a.textbook_dir or (TEXTBOOK_DIR if a.data_dir == DATA_DIR else data_dir / "textbook")
    r = Report(a.check)

    print(f"家: {data_dir}  コード: {PROJECT_DIR}" + ("  (見るだけ)" if a.check else ""))
    print("[前提]")
    check_commands(r)
    ensure_src(PROJECT_DIR, r)
    check_components(PROJECT_DIR, r)
    print("[家のフォルダ]")
    if not data_dir.exists() and not a.check:
        data_dir.mkdir(parents=True)
        r.made(f"{data_dir}/")
    ensure_dirs(data_dir, r)
    ensure_chat_files(data_dir, r)
    ensure_env(data_dir, PROJECT_DIR, r)
    check_house_overrides(data_dir, r)
    print("[教科書]")
    ensure_textbook(textbook_dir, r)
    if not a.no_cron:
        print("[夜の cron]")
        ensure_cron(PROJECT_DIR, data_dir, textbook_dir, r)

    print()
    if r.missing:
        print("足りないもの: " + " / ".join(r.missing))
    else:
        print("家の用意はできています。次は scripts/create_character.py で子を迎える(教科書 人間用 8 章)")
    return 1 if r.missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
