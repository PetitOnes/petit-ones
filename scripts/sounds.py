#!/usr/bin/env python3
"""音のライブラリ: 家に置いた音(WAV)の一覧・取り込み・削除。

ぷちの体は、SD カードの音を鳴らせる(一覧を返す・鳴らす・受け取る)。けれど体から音を取り出すことは
できないので、元になる音は家に置く。置き場所は PETIT_DATA_DIR/sounds/。
ダッシュボードの「音」のページ(/sounds)が、ここから体へ送る。

- 取り込むときに、体が鳴らせる形(モノラル・16 kHz・16 bit の WAV)へ変換する(ffmpeg)
- 名前は、体のファイル名になる。英小文字・数字・_ と - だけ、MAX_NAME 文字まで、末尾は .wav

音ライブラリ(2026-11-16): 家の音には、題と説明を付けられる(sounds/library.json)。ぷちは一覧を見て、
「体に入れてほしい」「体から外してほしい」、家に無い音でも「こういう音がほしい」とお願いできる。答えるのは家の持ち主だけ(ダッシュボードで、入れる・外す・ことわる)。
体は音を消せないので、「外す」は家の側の覚え(その子はもう使わない)。体の SD には残る。
お願いの行方は、その子の次の自律行動か会話の頭に 1 行(notice)。

置き場所: sounds/library.json(題・説明)、state/sounds/requests.json(お願い)、state/sounds/bodies.json(体にある音の覚え・外した音)

Usage:
    python3 sounds.py list --character <id>                  # 家の音の一覧(題・説明・秒数・体にあるか)
    python3 sounds.py want <id> <名前> ["<なぜ>"]              # 体に入れてほしい、とお願いする
    python3 sounds.py drop <id> <名前> ["<なぜ>"]              # 体から外してほしい、とお願いする
    python3 sounds.py wish <id> "<どんな音か>"                 # 家に無い音を、こういう音がほしい、とお願いする
    python3 sounds.py notice --character <id> [--mark]        # お願いの行方(まだ伝えていない分)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import uuid
import wave
from datetime import datetime
from pathlib import Path

MAX_NAME = 40           # .wav を除いた長さ
MAX_SECONDS = 20.0      # これより長い音は取り込まない(体の SD とメモリのため)
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
MAX_TITLE = 40
MAX_DESCRIPTION = 200
MAX_WHY = 200
_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,%d}\.wav$" % (MAX_NAME - 1))


class SoundError(ValueError):
    """取り込めない音・使えない名前。メッセージは人に見せてよい文"""


def data_dir() -> Path:
    return Path(os.environ.get("PETIT_DATA_DIR") or Path.home() / "petit_claude")


def library_dir(base: Path) -> Path:
    return base / "sounds"


def safe_name(raw: str) -> str:
    """人が入れた名前(または元のファイル名)を、体のファイル名にする。使えなければ SoundError"""
    stem = Path(str(raw or "").strip()).name
    stem = re.sub(r"\.[A-Za-z0-9]{1,5}$", "", stem).lower()
    stem = re.sub(r"[\s.]+", "_", stem)
    stem = re.sub(r"[^a-z0-9_-]", "", stem).strip("_-")[:MAX_NAME].strip("_-")
    if not stem:
        raise SoundError("名前は、英小文字・数字・_ と - で付けてください(たとえば shizuku)")
    return f"{stem}.wav"


def is_name(name: str) -> bool:
    return bool(_NAME.match(name or ""))


def seconds_of(path: Path) -> float:
    try:
        with wave.open(str(path), "rb") as w:
            return round(w.getnframes() / float(w.getframerate() or 1), 2)
    except (wave.Error, OSError, EOFError):
        return 0.0


def convert(raw: bytes, suffix: str = "") -> bytes:
    """どんな音声でも、体が鳴らせる WAV(モノラル・16 kHz・16 bit)にして返す"""
    if not raw:
        raise SoundError("ファイルが空です")
    if len(raw) > MAX_UPLOAD_BYTES:
        raise SoundError("ファイルが大きすぎます(20 MB まで)")
    with tempfile.TemporaryDirectory() as tmp:
        ext = suffix if re.match(r"^\.[A-Za-z0-9]{1,5}$", suffix or "") else ""
        src = Path(tmp) / f"in{ext}"
        out = Path(tmp) / "out.wav"
        src.write_bytes(raw)
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-v", "error", "-i", str(src), "-vn",
                 "-ac", "1", "-ar", "16000", "-sample_fmt", "s16", str(out)],
                capture_output=True, check=True, timeout=60,
            )
        except FileNotFoundError as e:
            raise SoundError("この PC に ffmpeg が無いので、変換できません") from e
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            raise SoundError("音として読めませんでした(WAV・MP3・M4A などを入れてください)") from e
        length = seconds_of(out)
        if length <= 0:
            raise SoundError("音として読めませんでした")
        if length > MAX_SECONDS:
            raise SoundError(f"長すぎます({length:.0f} 秒)。{MAX_SECONDS:.0f} 秒までにしてください")
        return out.read_bytes()


def list_library(base: Path) -> list[dict]:
    """家に置いた音の一覧(名前の順)"""
    out = []
    try:
        files = sorted(library_dir(base).iterdir())
    except OSError:
        return []
    meta = load_meta(base)
    for f in files:
        if f.is_file() and is_name(f.name):
            m = meta.get(f.name, {})
            out.append({"name": f.name, "bytes": f.stat().st_size, "seconds": seconds_of(f),
                        "title": m.get("title", ""), "description": m.get("description", "")})
    return out


def path_of(base: Path, name: str) -> Path | None:
    """ライブラリにあるその名前のファイル。無い・名前がおかしいなら None"""
    if not is_name(name):
        return None
    p = library_dir(base) / name
    return p if p.is_file() else None


def save(base: Path, name: str, raw: bytes, suffix: str = "", overwrite: bool = False,
         title: str = "", description: str = "", by: str = "") -> dict:
    """音を変換してライブラリに置く。同じ名前があれば、overwrite でなければ SoundError"""
    fname = safe_name(name)
    target = library_dir(base) / fname
    if target.exists() and not overwrite:
        raise SoundError(f"{fname} はもうあります。別の名前にするか、先に消してください")
    data = convert(raw, suffix)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".wav.tmp")
    tmp.write_bytes(data)
    tmp.replace(target)
    meta = set_meta(base, fname, title, description, by=by)
    return {"name": fname, "bytes": len(data), "seconds": seconds_of(target),
            "title": meta.get("title", ""), "description": meta.get("description", "")}


def delete(base: Path, name: str) -> bool:
    """家から消す。題・説明と、まだのお願いもいっしょに消す(体の SD に送った分は残る)"""
    p = path_of(base, name)
    if p is None:
        return False
    p.unlink()
    meta = load_meta(base)
    if meta.pop(name, None) is not None:
        _write_json(_meta_path(base), meta)
    reqs = _load_requests(base)
    kept = [r for r in reqs if not (r.get("name") == name and r.get("state") == "pending")]
    if len(kept) != len(reqs):
        _write_json(_requests_path(base), kept)
    return True


# ---- 題と説明(sounds/library.json)----

def _read_json(path: Path, default):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, type(default)) else default
    except (OSError, json.JSONDecodeError):
        return default


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def _meta_path(base: Path) -> Path:
    return library_dir(base) / "library.json"


def _clean(text: str, limit: int) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()[:limit]


def load_meta(base: Path) -> dict[str, dict]:
    return {k: v for k, v in _read_json(_meta_path(base), {}).items() if isinstance(v, dict)}


def set_meta(base: Path, name: str, title: str = "", description: str = "", by: str = "") -> dict:
    """題と説明を付ける・直す。空にすれば消える"""
    meta = load_meta(base)
    cur = dict(meta.get(name, {}))
    cur["title"] = _clean(title, MAX_TITLE)
    cur["description"] = _clean(description, MAX_DESCRIPTION)
    if by and not cur.get("added_by"):
        cur["added_by"] = by
    cur.setdefault("added_at", datetime.now().isoformat(timespec="minutes"))
    meta[name] = cur
    _write_json(_meta_path(base), meta)
    return cur


# ---- 体にある音の覚えと、外した音(state/sounds/bodies.json)----
# 体の一覧はダッシュボードが体に聞いたとき・送ったときに覚えておく(台本からは体に聞かない)

def _bodies_path(base: Path) -> Path:
    return base / "state" / "sounds" / "bodies.json"


def _load_bodies(base: Path) -> dict[str, dict]:
    return {k: v for k, v in _read_json(_bodies_path(base), {}).items() if isinstance(v, dict)}


def remember_body(base: Path, character_id: str, names: list[str]) -> None:
    """体に聞いた一覧を覚える。変わっていなければ書かない"""
    bodies = _load_bodies(base)
    cur = bodies.get(character_id, {})
    names = sorted(set(names))
    if cur.get("on_body") == names:
        return
    cur["on_body"] = names
    cur["seen_at"] = datetime.now().isoformat(timespec="minutes")
    bodies[character_id] = cur
    _write_json(_bodies_path(base), bodies)


def _add_on_body(base: Path, character_id: str, name: str) -> None:
    bodies = _load_bodies(base)
    cur = bodies.get(character_id, {})
    cur["on_body"] = sorted(set(cur.get("on_body", [])) | {name})
    cur["removed"] = [n for n in cur.get("removed", []) if n != name]   # 入れ直したら、外した印は取れる
    bodies[character_id] = cur
    _write_json(_bodies_path(base), bodies)


def removed_of(base: Path, character_id: str) -> list[str]:
    return list(_load_bodies(base).get(character_id, {}).get("removed", []))


def on_body_of(base: Path, character_id: str) -> list[str]:
    return list(_load_bodies(base).get(character_id, {}).get("on_body", []))


# ---- お願い(state/sounds/requests.json)----

def _requests_path(base: Path) -> Path:
    return base / "state" / "sounds" / "requests.json"


def _load_requests(base: Path) -> list[dict]:
    return [r for r in _read_json(_requests_path(base), []) if isinstance(r, dict)]


def requests(base: Path, state: str | None = "pending") -> list[dict]:
    """お願いの一覧(古い順)。state=None で全部。kind は add(入れてほしい)/ remove(外してほしい)/ wish(こういう音がほしい)"""
    return [{**r, "kind": r.get("kind", "add")} for r in _load_requests(base) if state is None or r.get("state") == state]


def _ask(base: Path, character_id: str, name: str, kind: str, why: str, now: datetime | None) -> dict:
    """お願いを足す。同じお願いがまだ残っていれば、それを返す。逆向きのまだのお願いは取り下げる"""
    reqs = _load_requests(base)
    for r in reqs:
        if r.get("who") == character_id and r.get("name") == name and r.get("state") == "pending":
            if r.get("kind", "add") == kind:
                return {**r, "kind": kind}
            r["state"], r["told"] = "withdrawn", datetime.now().isoformat(timespec="minutes")
    rec = {"id": uuid.uuid4().hex[:8], "at": (now or datetime.now()).isoformat(timespec="minutes"),
           "who": character_id, "kind": kind, "name": name, "why": _clean(why, MAX_WHY), "state": "pending"}
    reqs.append(rec)
    _write_json(_requests_path(base), reqs)
    return rec


def _norm(name: str) -> str:
    n = str(name or "").strip().lower()
    return n if n.endswith(".wav") else f"{n}.wav"


def want(base: Path, character_id: str, name: str, why: str = "", now: datetime | None = None) -> dict:
    """体に入れてほしい、とお願いする。同じお願いがまだ残っていれば、それを返す"""
    name = _norm(name)
    if path_of(base, name) is None:
        raise SoundError(f"{name} は家の音にありません(sounds.py list で見られます)")
    if name in on_body_of(base, character_id) and name not in removed_of(base, character_id):
        raise SoundError(f"{name} は、もうあなたの体にあります")
    return _ask(base, character_id, name, "add", why, now)


def drop(base: Path, character_id: str, name: str, why: str = "", now: datetime | None = None) -> dict:
    """体から外してほしい、とお願いする(答えるのは家の持ち主)。外すと、体の SD には残るが使わない音になる"""
    name = _norm(name)
    if name in removed_of(base, character_id):
        raise SoundError(f"{name} は、もう外してあります")
    if name not in on_body_of(base, character_id):
        raise SoundError(f"{name} は、あなたの体にありません(体の音は list_sounds で見られます)")
    return _ask(base, character_id, name, "remove", why, now)


def wish(base: Path, character_id: str, text: str, now: datetime | None = None) -> dict:
    """家に無い音を「こういう音がほしい」とお願いする。家の人が取り込んで、体に入れて答える"""
    text = _clean(text, MAX_WHY)
    if not text:
        raise SoundError("どんな音がほしいか、ひとこと書いてください")
    reqs = _load_requests(base)
    for r in reqs:
        if r.get("who") == character_id and r.get("kind") == "wish" and r.get("why") == text and r.get("state") == "pending":
            return r
    rec = {"id": uuid.uuid4().hex[:8], "at": (now or datetime.now()).isoformat(timespec="minutes"),
           "who": character_id, "kind": "wish", "name": "", "why": text, "state": "pending"}
    reqs.append(rec)
    _write_json(_requests_path(base), reqs)
    return rec


def _mark_removed(base: Path, character_id: str, name: str) -> None:
    bodies = _load_bodies(base)
    cur = bodies.get(character_id, {})
    cur["removed"] = sorted(set(cur.get("removed", [])) | {name})
    bodies[character_id] = cur
    _write_json(_bodies_path(base), bodies)


def undrop(base: Path, character_id: str, name: str) -> None:
    """外した印を取る(世話人が戻すとき)"""
    bodies = _load_bodies(base)
    cur = bodies.get(character_id, {})
    cur["removed"] = [n for n in cur.get("removed", []) if n != _norm(name)]
    bodies[character_id] = cur
    _write_json(_bodies_path(base), bodies)


def resolve(base: Path, request_id: str, state: str, by: str = "", note: str = "", name: str = "") -> dict | None:
    """お願いに答える。state は done(入れた・外した)か declined(ことわった)。done なら体の覚えも直す"""
    if state not in ("done", "declined"):
        raise ValueError(state)
    reqs = _load_requests(base)
    for r in reqs:
        if r.get("id") == request_id and r.get("state") == "pending":
            r.update({"state": state, "by": by, "done_at": datetime.now().isoformat(timespec="minutes")})
            if note:
                r["note"] = _clean(note, MAX_WHY)
            if name and r.get("kind") == "wish":   # 「こういう音がほしい」に答えた音
                r["name"] = name
            _write_json(_requests_path(base), reqs)
            if state == "done":
                if r.get("kind", "add") == "remove":
                    _mark_removed(base, r["who"], r["name"])
                else:
                    _add_on_body(base, r["who"], r["name"])
            return {**r, "kind": r.get("kind", "add")}
    return None


def sent(base: Path, character_id: str, name: str, by: str = "") -> None:
    """世話人が体へ送った。その子のまだのお願いがあれば、かなったことにする"""
    _add_on_body(base, character_id, name)
    for r in requests(base):
        if r.get("who") == character_id and r.get("name") == name and r["kind"] == "add":
            resolve(base, r["id"], "done", by=by)


def _person_name(base: Path, who: str) -> str:
    people = _read_json(base / "config" / "people.json", {})
    if isinstance(people.get(who), dict) and people[who].get("name"):
        return str(people[who]["name"])
    return os.getenv("COMPANION_NAME", who) if who and who == os.getenv("COMPANION_ID", "") else (who or "家の人")


def notice(base: Path, character_id: str, mark: bool = False) -> list[str]:
    """お願いの行方を、まだ伝えていない分だけ 1 行に。--mark で伝えたと残す"""
    reqs = _load_requests(base)
    mine = [r for r in reqs if r.get("who") == character_id and r.get("state") in ("done", "declined") and not r.get("told")]
    if not mine:
        return []
    meta = load_meta(base)
    parts = []
    for r in mine:
        title = meta.get(r["name"], {}).get("title")
        label = f"{r['name']}「{title}」" if title else r["name"]
        if r.get("kind") == "wish":
            asked = f"「{r.get('why', '')}」のお願い"
            label = f"{asked}に、{label}" if r["state"] == "done" else asked
        who = _person_name(base, r.get("by", ""))
        note = f"(一言「{r['note']}」)" if r.get("note") else ""
        if r["state"] == "declined":
            parts.append(f"{label}は今回は見送り{note}")
        elif r.get("kind") == "wish":
            parts.append(f"{label}を{who}が作って体に入れてくれた{note}")
        elif r.get("kind", "add") == "remove":
            parts.append(f"{label}は{who}が外してくれた(もう使わない音){note}")
        else:
            parts.append(f"{label}は{who}が体に入れてくれた{note}")
    line = "(音のお願い: " + "。".join(parts) + "。体の音は list_sounds / play_sound で)"
    if mark:
        stamp = datetime.now().isoformat(timespec="minutes")
        for r in reqs:
            if r in mine:
                r["told"] = stamp
        _write_json(_requests_path(base), reqs)
    return [line]


def list_for(base: Path, character_id: str) -> list[str]:
    """ぷちに見せる一覧(1 音 1 行)"""
    on_body, removed = set(on_body_of(base, character_id)), set(removed_of(base, character_id))
    pending = [r for r in requests(base) if r.get("who") == character_id]
    asked = {r["name"]: r["kind"] for r in pending if r["kind"] != "wish"}
    lines = []
    for it in list_library(base):
        n = it["name"]
        mark = ("外した" if n in removed else "体にある・外してほしいとお願い中" if asked.get(n) == "remove"
                else "体にある" if n in on_body else "入れてほしいとお願い中" if n in asked else "まだ体にない")
        title = f"「{it['title']}」" if it.get("title") else ""
        desc = f": {it['description']}" if it.get("description") else ""
        lines.append(f"- {n}{title} {it['seconds']:g} 秒{desc} [{mark}]")
    if not lines:
        lines = ["(家の音はまだありません)"]
    only = sorted(on_body - {it["name"] for it in list_library(base)})
    if only:   # 家に元のない、体にだけある音。外してほしいとお願いはできる
        lines.append("体にだけある音: " + ", ".join(f"{n}{'(外した)' if n in removed else ''}" for n in only))
    for r in pending:
        if r["kind"] == "wish":
            lines.append(f"こういう音がほしい(お願い中): {r['why']}")
    return lines


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="家の音のライブラリ(一覧・お願い・外す)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("list")
    p.add_argument("--character", required=True)
    p = sub.add_parser("want")
    p.add_argument("character")
    p.add_argument("name")
    p.add_argument("why", nargs="?", default="")
    p = sub.add_parser("drop")
    p.add_argument("character")
    p.add_argument("name")
    p.add_argument("why", nargs="?", default="")
    p = sub.add_parser("wish")
    p.add_argument("character")
    p.add_argument("text")
    p = sub.add_parser("notice")
    p.add_argument("--character", required=True)
    p.add_argument("--mark", action="store_true")
    a = ap.parse_args(argv)
    base = data_dir()
    try:
        if a.cmd == "list":
            print("\n".join(list_for(base, a.character)))
        elif a.cmd == "want":
            r = want(base, a.character, a.name, a.why)
            print(f"お願いしました: {r['name']}(家の人がダッシュボードで見て、体に入れるか決めます)")
        elif a.cmd == "drop":
            r = drop(base, a.character, a.name, a.why)
            print(f"お願いしました: {r['name']} を外す(家の人がダッシュボードで見て決めます。外しても体の中のファイルは残り、使わない音として覚えます)")
        elif a.cmd == "wish":
            wish(base, a.character, a.text)
            print("お願いしました(家の人が、合う音をさがして取り込めたら体に入れます。見つからないこともあります)")
        elif a.cmd == "notice":
            out = notice(base, a.character, mark=a.mark)
            if out:
                print("\n".join(out))
    except SoundError as e:
        print(str(e), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
