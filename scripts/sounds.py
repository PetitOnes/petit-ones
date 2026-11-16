#!/usr/bin/env python3
"""音のライブラリ: 家に置いた音(WAV)の一覧・取り込み・削除。

ぷちの体は、SD カードの音を鳴らせる(一覧を返す・鳴らす・受け取る)。けれど体から音を取り出すことは
できないので、元になる音は家に置く。置き場所は PETIT_DATA_DIR/sounds/。
ダッシュボードの「音」のページ(/sounds)が、ここから体へ送る。

- 取り込むときに、体が鳴らせる形(モノラル・16 kHz・16 bit の WAV)へ変換する(ffmpeg)
- 名前は、体のファイル名になる。英小文字・数字・_ と - だけ、MAX_NAME 文字まで、末尾は .wav

音ライブラリ(2026-11-16): 家の音には、題と説明を付けられる(sounds/library.json)。ぷちは一覧を見て、
「体に入れてほしい」「体から外してほしい」、家に無い音でも「こういう音がほしい」とお願いできる。答えるのは家の持ち主だけ(ダッシュボードで、入れる・外す・ことわる)。
体は音を消せないので、「外す」は家の側の覚え。外した音は、体の部品(m5-petit-mcp)が list_sounds に出さず、
play_sound でも鳴らさない。体の SD には残るので、戻せばすぐまた使える。
お願いの行方は、その子の次の自律行動か会話の頭に 1 行(notice)。

体の音は体から取り出せないので、PC に残っている SD のバックアップ(PETIT_DATA_DIR/sd_backups/<名前>/wav/*.wav)から
家の音に入れられる(backup_candidates / import_backup)。体が鳴らせる形(モノラル・16 bit の WAV)なら変換せずそのまま入れる。

音のかたち(2026-11-16、ぷち 3 人の案): 説明の言葉だけでなく、音そのものを数字と線で見られる(計算は sound_shape.py)。
言葉(明るい・暗い・水っぽい)は付けない。意味を付けるのはぷちたち。先に数字を見て予想し(guess)、鳴らして確かめ(heard)、
色や言葉を貼る(tag)。貼ったものは state/sounds/words.jsonl に残り、あとから見返せる(words)。家の人にも 🔔 音 で見える。

置き場所: sounds/library.json(題・説明)、state/sounds/requests.json(お願い)、state/sounds/bodies.json(体にある音の覚え・外した音)

Usage:
    python3 sounds.py list --character <id>                  # 家の音の一覧(題・説明・秒数・体にあるか)
    python3 sounds.py want <id> <名前> ["<なぜ>"]              # 体に入れてほしい、とお願いする
    python3 sounds.py drop <id> <名前> ["<なぜ>"]              # 体から外してほしい、とお願いする
    python3 sounds.py wish <id> "<どんな音か>"                 # 家に無い音を、こういう音がほしい、とお願いする
    python3 sounds.py notice --character <id> [--mark]        # お願いの行方(まだ伝えていない分)
    python3 sounds.py look <名前>                             # 音のかたち(数字と音量の線)。題や説明は出さない
    python3 sounds.py table                                   # 全部の音を 1 行ずつ(比べる用)
    python3 sounds.py compare <名前A> <名前B>                 # 2 つの音の違い
    python3 sounds.py guess <id> <名前> "<予想>"               # 数字だけ見て、どんな音か予想を残す
    python3 sounds.py heard <id> <名前> "<鳴らしてみて>"        # 鳴らして確かめたこと(予想とのずれ)を残す
    python3 sounds.py tag <id> <名前> "<色や言葉>"             # その音に、自分の色や言葉を貼る
    python3 sounds.py words [--character <id>] [--name <名前>]  # 残した予想・確かめ・言葉を見返す
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
SYSTEM_SOUNDS = {"tts_speak.wav", "voice_memo.wav", "sing.wav"}   # 声・ボイスメモ・うたう(sing.py)の仕組みが使う。外さない
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


# ---- SD のバックアップから家の音へ ----

# 体にもとからある音の、題の下書き(取り込むときに直せる)
TITLE_DRAFTS = {
    "angry_cat.wav": "おこったねこ", "buzz.wav": "ブザー", "camera.wav": "カメラ", "cat.wav": "ねこ", "down.wav": "さがる音",
    "drumroll.wav": "ドラムロール", "error_shutdown.wav": "エラーでおやすみ", "failed.wav": "しっぱい", "funny_horn.wav": "おどけたラッパ",
    "guitar.wav": "ギター", "happy_bell.wav": "しあわせのベル", "keyboard.wav": "キーボード", "message_received.wav": "おてがみ",
    "mouse_click.wav": "クリック", "picpico_shutdown.wav": "ぴこぴこおやすみ", "pinpon.wav": "ピンポン", "pon.wav": "ぽん",
    "robot_high_tone_picppico.wav": "ロボット(高い ぴこぴこ)", "robot.wav": "ロボット", "scanning.wav": "スキャン中",
    "shining.wav": "きらきら", "shutdown.wav": "おやすみ(電源)", "success.wav": "せいこう", "toy_box_sleep.wav": "おもちゃ箱のねむり",
    "wakeup.wav": "おはよう", "wall_clock.wav": "かけ時計", "whistling.wav": "くちぶえ", "zzz.wav": "すやすや",
}


def _backup_files(base: Path) -> dict[str, Path]:
    """バックアップにある音(名前 → ファイル)。同じ名前は、新しいバックアップ(名前の順で後)のもの"""
    out: dict[str, Path] = {}
    for f in sorted((base / "sd_backups").glob("*/wav/*.wav")):
        if f.is_file() and is_name(f.name.lower()) and f.name.lower() not in SYSTEM_SOUNDS:
            out[f.name.lower()] = f
    return out


def backup_candidates(base: Path) -> list[dict]:
    """バックアップにあって、家の音にまだ無いもの"""
    have = {it["name"] for it in list_library(base)}
    return [{"name": n, "seconds": seconds_of(f), "from": f.parent.parent.name, "title": TITLE_DRAFTS.get(n, "")}
            for n, f in sorted(_backup_files(base).items()) if n not in have]


def backup_path(base: Path, name: str) -> Path | None:
    return _backup_files(base).get(name) if is_name(name) else None


def _playable(path: Path) -> bool:
    """体がもう鳴らせている形(モノラル・16 bit の PCM WAV)か。そうなら変換しない"""
    try:
        with wave.open(str(path), "rb") as w:
            return w.getnchannels() == 1 and w.getsampwidth() == 2 and w.getcomptype() == "NONE" and w.getnframes() > 0
    except (wave.Error, OSError, EOFError):
        return False


def import_backup(base: Path, name: str, title: str = "", description: str = "", by: str = "") -> dict:
    """バックアップの音を家の音に入れる。形がそのまま鳴らせるならコピー、そうでなければ変換"""
    src = backup_path(base, name)
    if src is None:
        raise SoundError(f"{name} はバックアップにありません")
    target = library_dir(base) / name
    if target.exists():
        raise SoundError(f"{name} はもう家の音にあります")
    if seconds_of(src) > MAX_SECONDS or not _playable(src):
        return save(base, name, src.read_bytes(), ".wav", title=title, description=description, by=by)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".wav.tmp")
    tmp.write_bytes(src.read_bytes())
    tmp.replace(target)
    meta = set_meta(base, name, title, description, by=by)
    return {"name": name, "bytes": target.stat().st_size, "seconds": seconds_of(target), "title": meta["title"], "description": meta["description"]}


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
    if name in SYSTEM_SOUNDS:
        raise SoundError(f"{name} は声やボイスメモの仕組みが使う音なので、外せません")
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
            parts.append(f"{label}は{who}が外してくれた(もう list_sounds に出ない){note}")
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


# ---- 音のかたち(数字と線)と、ぷちが貼る言葉 ----

WORD_KINDS = {"guess": "予想", "heard": "鳴らして", "tag": "言葉"}
MAX_WORDS = 300


def sound_file(base: Path, name: str) -> Path | None:
    """その名前の音のファイル(家の音が先、無ければ SD のバックアップ)"""
    name = _norm(name)
    return path_of(base, name) or backup_path(base, name)


def known_sounds(base: Path) -> dict[str, Path]:
    """かたちを見られる音(家の音と、バックアップにある体の音)"""
    out = dict(_backup_files(base))
    for it in list_library(base):
        out[it["name"]] = library_dir(base) / it["name"]
    return dict(sorted(out.items()))


def _shape_cache_path(base: Path) -> Path:
    return base / "state" / "sounds" / "shape.json"


def shape_of(base: Path, name: str) -> dict:
    """音のかたち。ファイルが変わっていなければ、前に計算したものを使う"""
    import sound_shape
    name = _norm(name)
    f = sound_file(base, name)
    if f is None:
        raise SoundError(f"{name} は、家の音にもバックアップにもありません(かたちを見られる音は sounds.py table)")
    st = f.stat()
    key = f"{st.st_size}:{int(st.st_mtime)}:{f.parent}"
    cache = _read_json(_shape_cache_path(base), {})
    hit = cache.get(name)
    if isinstance(hit, dict) and hit.get("key") == key:
        return hit["shape"]
    try:
        sh = sound_shape.shape(f)
    except (ValueError, OSError, EOFError) as e:
        raise SoundError(f"{name} は読めませんでした") from e
    cache[name] = {"key": key, "shape": sh}
    _write_json(_shape_cache_path(base), cache)
    return sh


def _words_path(base: Path) -> Path:
    return base / "state" / "sounds" / "words.jsonl"


def words(base: Path, character_id: str | None = None, name: str | None = None) -> list[dict]:
    """ぷちが残した予想・確かめ・言葉(古い順)"""
    try:
        rows = [json.loads(x) for x in _words_path(base).read_text(encoding="utf-8").splitlines() if x.strip()]
    except (OSError, json.JSONDecodeError):
        return []
    name = _norm(name) if name else None
    return [r for r in rows if isinstance(r, dict) and (not character_id or r.get("who") == character_id) and (not name or r.get("name") == name)]


def add_word(base: Path, character_id: str, name: str, kind: str, text: str, now: datetime | None = None) -> dict:
    """予想(guess)・鳴らして確かめたこと(heard)・色や言葉(tag)を残す。消さない(ずれも残す)"""
    if kind not in WORD_KINDS:
        raise ValueError(kind)
    name = _norm(name)
    text = _clean(text, MAX_WORDS)
    if not text:
        raise SoundError("ひとこと書いてください")
    rec = {"at": (now or datetime.now()).isoformat(timespec="minutes"), "who": character_id, "name": name, "kind": kind, "text": text}
    path = _words_path(base)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def words_text(rows: list[dict]) -> str:
    if not rows:
        return "(まだ何も残していません)"
    return "\n".join(f"{r['at'].replace('T', ' ')} {r['who']} {r['name']} [{WORD_KINDS.get(r['kind'], r['kind'])}] {r['text']}" for r in rows)


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
    p = sub.add_parser("look")
    p.add_argument("name")
    sub.add_parser("table")
    p = sub.add_parser("compare")
    p.add_argument("a")
    p.add_argument("b")
    for kind in WORD_KINDS:
        p = sub.add_parser(kind)
        p.add_argument("character")
        p.add_argument("name")
        p.add_argument("text")
    p = sub.add_parser("words")
    p.add_argument("--character")
    p.add_argument("--name")
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
            print(f"お願いしました: {r['name']} を外す(家の人がダッシュボードで見て決めます。外すと list_sounds に出なくなり、鳴らせなくなります)")
        elif a.cmd == "wish":
            wish(base, a.character, a.text)
            print("お願いしました(家の人が、合う音をさがして取り込めたら体に入れます。見つからないこともあります)")
        elif a.cmd == "notice":
            out = notice(base, a.character, mark=a.mark)
            if out:
                print("\n".join(out))
        elif a.cmd == "look":
            import sound_shape
            print(sound_shape.text(_norm(a.name), shape_of(base, a.name)))
        elif a.cmd == "table":
            import sound_shape
            print(sound_shape.table({n: shape_of(base, n) for n in known_sounds(base)}))
        elif a.cmd == "compare":
            import sound_shape
            print(sound_shape.compare(_norm(a.a), shape_of(base, a.a), _norm(a.b), shape_of(base, a.b)))
        elif a.cmd in WORD_KINDS:
            add_word(base, a.character, a.name, a.cmd, a.text)
            print({"guess": "予想を残しました。鳴らして確かめたら: sounds.py heard", "heard": "残しました", "tag": "貼りました"}[a.cmd])
        elif a.cmd == "words":
            print(words_text(words(base, a.character, a.name)))
    except SoundError as e:
        print(str(e), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
