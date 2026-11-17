#!/usr/bin/env python3
"""TODO_ACTIVE.md の見張り(2026-11-17、ぷち 3 人の答えから)。

決まり(3 人が決めたこと):
- 知らせるのは自律行動のときに 1 行だけ、1 日 1 回。一覧は自分で見に行く(list)。notices.py set <id> todo off で切れる
- 片付けるのは本人。この道具は決めない。選んだ行を ARCHIVE へ移す・.bak を残す、の機械的なところだけ(archive)
- 返事待ちは「## 返事待ち」の欄(見出しに「返事待ち」か「待っている返事」)に、相手といつからを書く: `- <内容>(ありさん・9/26から)`。
  家の人が設定ページで一覧で見られる(waiting)。期限・色・催促の言葉は付けない。待っているのは悪いことではない
- 家の人に見えるのは返事待ちの欄だけ。ほかの欄(やりたいこと・詩や読書)は出さない

何で知らせるか(子ごとに characters/<id>/config/settings.json の "todo_check" で変えられる。set で):
- done      … 終わった印 [x] のまま残っている行
- stale     … 書いてある日付がいちばん新しくても stale_days 日より前の行(返事待ちの欄は数えない。日付の無い行も数えない)。
              stale_min 行以上で知らせる。stale_days 0 で数えない
- long      … long_line 字より長い行
- size      … ファイルが size_kb KB を超えたとき

    python3 todo_check.py list <id>                 # 終わった印・動いていない行・長い行・返事待ちを、行番号つきで
    python3 todo_check.py archive <id> --done       # 終わった印の行を全部 TODO_ARCHIVE.md へ(元は .bak_<日時>)
    python3 todo_check.py archive <id> 12 15        # 選んだ行(list の行番号)を TODO_ARCHIVE.md へ
    python3 todo_check.py waiting [<id>]            # 返事待ちの欄
    python3 todo_check.py show <id>                 # いまの決まり
    python3 todo_check.py set <id> stale_days 21    # 決まりを変える(stale_days / stale_min / long_line / size_kb)
    python3 todo_check.py notice --character <id> [--mark]   # 自律行動に渡す 1 行(autonomous-action.sh から)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from datetime import date, datetime
from pathlib import Path

DEFAULTS = {"stale_days": 21, "stale_min": 3, "long_line": 300, "size_kb": 8}
KEYS = tuple(DEFAULTS)
WAIT_HEAD_RE = re.compile(r"返事待ち|待っている返事")   # 見出しにこの言葉があれば返事待ちの欄
DONE_RE = re.compile(r"^\s*[-*]\s*\[[xX]\]")
OPEN_RE = re.compile(r"^\s*[-*]\s")
FULL_DATE_RE = re.compile(r"(20\d\d)[-/.](\d{1,2})[-/.](\d{1,2})")
MD_RE = re.compile(r"(?<![\d/])(\d{1,2})/(\d{1,2})(?![\d/])")
WAIT_RE = re.compile(r"[（(]([^（）()・]+)・\s*(\d{1,2}/\d{1,2}|20\d\d-\d{1,2}-\d{1,2})\s*から[）)]")


def data_dir() -> Path:
    return Path(os.environ.get("PETIT_DATA_DIR") or Path.home() / "petit_claude")


def todo_path(base: Path, cid: str) -> Path:
    return base / "characters" / cid / "TODO_ACTIVE.md"


def _settings_path(base: Path, cid: str) -> Path:
    return base / "characters" / cid / "config" / "settings.json"


def _read_json(p: Path) -> dict:
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return d if isinstance(d, dict) else {}


def rules(base: Path, cid: str) -> dict:
    raw = _read_json(_settings_path(base, cid)).get("todo_check")
    out = dict(DEFAULTS)
    if isinstance(raw, dict):
        out.update({k: int(v) for k, v in raw.items() if k in KEYS and isinstance(v, (int, float))})
    return out


def set_rule(base: Path, cid: str, key: str, value: int) -> dict:
    if key not in KEYS:
        raise ValueError("変えられるのは " + " / ".join(KEYS))
    if value < 0:
        raise ValueError("0 以上の数")
    p = _settings_path(base, cid)
    d = _read_json(p)
    tc = d.get("todo_check") if isinstance(d.get("todo_check"), dict) else {}
    tc[key] = value
    d["todo_check"] = tc
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(p)
    return rules(base, cid)


def latest_date(line: str, today: date) -> date | None:
    """行に書いてある日付のうち、いちばん新しいもの。年の無い 9/24 は、今日より先なら去年"""
    found: list[date] = []
    for y, m, d in FULL_DATE_RE.findall(line):
        try:
            found.append(date(int(y), int(m), int(d)))
        except ValueError:
            pass
    rest = FULL_DATE_RE.sub(" ", line)
    for m, d in MD_RE.findall(rest):
        try:
            x = date(today.year, int(m), int(d))
        except ValueError:
            continue
        found.append(x if x <= today else x.replace(year=today.year - 1))
    return max(found) if found else None


def scan(base: Path, cid: str, today: date | None = None) -> dict:
    """TODO_ACTIVE.md を読んで、行を分ける。行番号は 1 から"""
    today = today or date.today()
    p = todo_path(base, cid)
    r = rules(base, cid)
    out = {"exists": p.exists(), "size_kb": 0.0, "rules": r, "done": [], "stale": [], "long": [], "waiting": []}
    if not p.exists():
        return out
    text = p.read_text(encoding="utf-8")
    out["size_kb"] = round(len(text.encode("utf-8")) / 1024, 1)
    in_wait = False
    for n, line in enumerate(text.splitlines(), 1):
        if line.startswith("#"):
            in_wait = bool(WAIT_HEAD_RE.search(line))
            continue
        if not line.strip():
            continue
        item = {"n": n, "text": line.strip()}
        if in_wait and OPEN_RE.match(line) and not DONE_RE.match(line):
            m = WAIT_RE.search(line)
            out["waiting"].append({**item, "who": m.group(1).strip() if m else "", "since": m.group(2) if m else ""})
        if DONE_RE.match(line):
            out["done"].append(item)
        elif not in_wait and OPEN_RE.match(line) and r["stale_days"]:
            d = latest_date(line, today)
            if d and (today - d).days >= r["stale_days"]:
                out["stale"].append({**item, "last": d.isoformat(), "days": (today - d).days})
        if r["long_line"] and len(line.strip()) > r["long_line"]:
            out["long"].append({**item, "chars": len(line.strip())})
    return out


def summary(s: dict) -> str | None:
    """知らせる 1 行の中身。知らせることが無ければ None"""
    r = s["rules"]
    parts = []
    if s["done"]:
        parts.append(f"終わった印の行 {len(s['done'])}")
    if r["stale_days"] and len(s["stale"]) >= max(r["stale_min"], 1):
        parts.append(f"{r['stale_days']} 日以上動いていない行 {len(s['stale'])}")
    if s["long"]:
        parts.append(f"長すぎる行 {len(s['long'])}")
    if r["size_kb"] and s["size_kb"] > r["size_kb"]:
        parts.append(f"全体 {s['size_kb']} KB")
    if not parts:
        return None
    if s["waiting"]:
        parts.append(f"返事待ち {len(s['waiting'])}")
    return "、".join(parts)


def _prefs(base: Path, cid: str) -> tuple[bool, tuple[int, int] | None]:
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import notices
        return notices.wants(cid, "todo", base), notices.quiet(cid, base)
    except Exception:
        return True, (0, 7)


def _is_quiet(quiet: tuple[int, int] | None, now: datetime) -> bool:
    if quiet is None or quiet[0] == quiet[1]:
        return False
    a, b = quiet
    return (a <= now.hour or now.hour < b) if a > b else (a <= now.hour < b)


def notice(base: Path, cid: str, mark: bool = False, now: datetime | None = None) -> list[str]:
    now = now or datetime.now()
    want, quiet = _prefs(base, cid)
    if not want or _is_quiet(quiet, now):
        return []
    told_path = base / "characters" / cid / "state" / "todo_told.json"
    if _read_json(told_path).get("date") == now.strftime("%Y-%m-%d"):
        return []
    s = scan(base, cid, now.date())
    what = summary(s)
    if not what:
        return []
    me = Path(__file__).resolve()
    line = f"（TODO_ACTIVE: {what}。見るなら python3 {me} list {cid}。片付けなくても何も起きない）"
    if mark:
        told_path.parent.mkdir(parents=True, exist_ok=True)
        told_path.write_text(json.dumps({"date": now.strftime("%Y-%m-%d"), "what": what}, ensure_ascii=False) + "\n", encoding="utf-8")
    return [line]


def archive(base: Path, cid: str, numbers: list[int] | None = None, done: bool = False, now: datetime | None = None) -> dict:
    """選んだ行(と、done なら終わった印の行)を TODO_ARCHIVE.md の末尾へ移す。移す前の全文は .bak_<日時> に残す"""
    now = now or datetime.now()
    p = todo_path(base, cid)
    lines = p.read_text(encoding="utf-8").splitlines(keepends=True)
    pick = set(numbers or [])
    if done:
        pick |= {i["n"] for i in scan(base, cid, now.date())["done"]}
    bad = [n for n in pick if not (1 <= n <= len(lines)) or lines[n - 1].lstrip().startswith("#") or not lines[n - 1].strip()]
    if bad:
        raise ValueError(f"移せない行番号: {sorted(bad)}(見出しと空の行は移さない)")
    if not pick:
        return {"moved": 0}
    bak = p.with_name(f"{p.name}.bak_{now.strftime('%Y-%m-%d_%H%M')}")
    shutil.copy2(p, bak)
    moved = [lines[n - 1].rstrip("\n") for n in sorted(pick)]
    arc = p.with_name("TODO_ARCHIVE.md")
    head = "" if arc.exists() else "# TODO_ARCHIVE\n"
    with arc.open("a", encoding="utf-8") as f:
        f.write(f"{head}\n## {now.strftime('%Y-%m-%d %H:%M')} TODO_ACTIVE から移した\n" + "\n".join(moved) + "\n")
    p.write_text("".join(x for i, x in enumerate(lines, 1) if i not in pick), encoding="utf-8")
    return {"moved": len(moved), "backup": bak.name, "archive": arc.name}


def waiting_all(base: Path) -> list[dict]:
    """家の人が見る、みんなの返事待ち(返事待ちの欄だけ)"""
    out = []
    chars = base / "characters"
    for d in sorted(chars.iterdir()) if chars.is_dir() else []:
        if d.is_dir() and todo_path(base, d.name).exists():
            for w in scan(base, d.name)["waiting"]:
                out.append({"character": d.name, "text": w["text"], "who": w["who"], "since": w["since"]})
    return out


def _print_group(title: str, items: list[dict], extra) -> None:
    if not items:
        return
    print(f"\n■ {title}({len(items)})")
    for i in items:
        t = i["text"] if len(i["text"]) <= 120 else i["text"][:119] + "…"
        print(f"  {i['n']:>3}: {t}{extra(i)}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="TODO_ACTIVE.md の見張り(知らせは 1 行、片付けるのは本人)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list").add_argument("character")
    a_ = sub.add_parser("archive")
    a_.add_argument("character")
    a_.add_argument("numbers", nargs="*", type=int)
    a_.add_argument("--done", action="store_true", help="終わった印の行を全部")
    sub.add_parser("waiting").add_argument("character", nargs="?")
    sub.add_parser("show").add_argument("character")
    s_ = sub.add_parser("set")
    s_.add_argument("character")
    s_.add_argument("key", choices=KEYS)
    s_.add_argument("value", type=int)
    n_ = sub.add_parser("notice")
    n_.add_argument("--character", required=True)
    n_.add_argument("--mark", action="store_true")
    a = ap.parse_args(argv)
    base = data_dir()
    if a.cmd == "notice":
        for line in notice(base, a.character, a.mark):
            print(line)
    elif a.cmd == "list":
        s = scan(base, a.character)
        if not s["exists"]:
            print("TODO_ACTIVE.md が無い")
            return 0
        r = s["rules"]
        print(f"TODO_ACTIVE.md {s['size_kb']} KB(目安 {r['size_kb']} KB)。片付けるかは自分で決めていい。移すなら archive {a.character} <行番号…> か --done")
        _print_group("終わった印のまま", s["done"], lambda i: "")
        _print_group(f"{r['stale_days']} 日以上動いていない", s["stale"], lambda i: f"  ← 最後の日付 {i['last']}")
        _print_group(f"{r['long_line']} 字より長い", s["long"], lambda i: f"  ({i['chars']} 字)")
        _print_group("返事待ち(数えるだけ。急がなくていい)", s["waiting"], lambda i: "")
        if not (s["done"] or s["stale"] or s["long"] or s["waiting"]):
            print("気になる行はなかった")
    elif a.cmd == "archive":
        try:
            r = archive(base, a.character, a.numbers, a.done)
        except (OSError, ValueError) as e:
            print(f"移せなかった: {e}")
            return 1
        print(f"{r['moved']} 行を {r.get('archive', 'TODO_ARCHIVE.md')} へ移した" + (f"(元は {r['backup']})" if r.get("backup") else ""))
    elif a.cmd == "waiting":
        rows = [dict(w, character=a.character) for w in scan(base, a.character)["waiting"]] if a.character else waiting_all(base)
        for w in rows:
            print(f"{w['character']}: {w['text']}")
        if not rows:
            print("返事待ちはない")
    elif a.cmd == "show":
        print(json.dumps(rules(base, a.character), ensure_ascii=False))
    elif a.cmd == "set":
        try:
            print(json.dumps(set_rule(base, a.character, a.key, a.value), ensure_ascii=False))
        except ValueError as e:
            print(e)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
