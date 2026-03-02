"""ぷちこ状態ダッシュボード"""

from __future__ import annotations

import asyncio
import io
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import sqlite3

import hashlib
import hmac
import secrets
import time

import base64

from fastapi import Cookie, FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from PIL import Image
from pydantic import BaseModel

app = FastAPI()

# --- 認証 ---
# ユーザー設定は ~/petit_claude/auth.json から読む
# {
#   "users": {
#     "admin_user": {"password": "xxx", "role": "admin"},
#     "operator_user": {"password": "xxx", "role": "operator"},
#     "viewer_user": {"password": "xxx", "role": "viewer"}
#   },
#   "secret": "ランダム文字列(自動生成)"
# }
# role: admin(全機能) / operator(チャット・操作OK、設定変更NG) / viewer(閲覧のみ)

_AUTH_FILE: Path | None = None  # 遅延初期化
_AUTH_DATA: dict | None = None
AUTH_COOKIE_NAME = "petit_session"
AUTH_MAX_AGE = 7 * 24 * 3600  # 7日


def _load_auth() -> dict:
    global _AUTH_DATA, _AUTH_FILE
    if _AUTH_FILE is None:
        _AUTH_FILE = Path(os.getenv("PETIT_DATA_DIR", Path.home() / "petit_claude")) / "auth.json"
    if _AUTH_DATA is None:
        if _AUTH_FILE.exists():
            try:
                _AUTH_DATA = json.loads(_AUTH_FILE.read_text(encoding="utf-8"))
            except Exception:
                _AUTH_DATA = {}
        else:
            _AUTH_DATA = {}
    return _AUTH_DATA


def _get_secret() -> str:
    auth = _load_auth()
    if "secret" not in auth:
        auth["secret"] = secrets.token_hex(32)
        if _AUTH_FILE:
            _AUTH_FILE.write_text(json.dumps(auth, ensure_ascii=False, indent=2), encoding="utf-8")
    return auth["secret"]


def _auth_enabled() -> bool:
    auth = _load_auth()
    return bool(auth.get("users"))


def _check_credentials(username: str, password: str) -> str | None:
    """パスワード照合。成功したらroleを返す。"""
    auth = _load_auth()
    users = auth.get("users", {})
    user = users.get(username)
    if user and user.get("password") == password:
        return user.get("role", "viewer")
    return None


def _make_token(username: str, role: str) -> str:
    """署名付きトークン生成。"""
    expires = int(time.time()) + AUTH_MAX_AGE
    payload = f"{username}:{role}:{expires}"
    sig = hmac.new(_get_secret().encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}:{sig}"


def _verify_token(token: str) -> tuple[str, str] | None:
    """トークン検証。成功したら (username, role) を返す。"""
    try:
        parts = token.rsplit(":", 1)
        if len(parts) != 2:
            return None
        payload, sig = parts
        expected = hmac.new(_get_secret().encode(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None
        username, role, expires_str = payload.split(":")
        if int(expires_str) < int(time.time()):
            return None
        return (username, role)
    except Exception:
        return None


def _get_user_role(request: Request) -> str | None:
    """リクエストからユーザーのroleを取得。認証無効ならadminを返す。"""
    if not _auth_enabled():
        return "admin"
    token = request.cookies.get(AUTH_COOKIE_NAME)
    if token:
        result = _verify_token(token)
        if result:
            return result[1]
    return None


# ロール別の許可マッピング
# admin: 全て / operator: チャット・操作OK / viewer: 閲覧のみ
ROLE_LEVELS = {"admin": 3, "operator": 2, "viewer": 1}


def _has_role(request: Request, min_role: str) -> bool:
    role = _get_user_role(request)
    if role is None:
        return False
    return ROLE_LEVELS.get(role, 0) >= ROLE_LEVELS.get(min_role, 99)


def _get_username(request: Request) -> str | None:
    """リクエストからユーザー名を取得。"""
    if not _auth_enabled():
        return None
    token = request.cookies.get(AUTH_COOKIE_NAME)
    if token:
        result = _verify_token(token)
        if result:
            return result[0]
    return None


def _get_allowed_characters(request: Request) -> list[str] | None:
    """ユーザーが閲覧可能なキャラIDリストを返す。Noneは全キャラ許可。"""
    if not _auth_enabled():
        return None
    role = _get_user_role(request)
    if role == "admin":
        return None
    username = _get_username(request)
    if not username:
        return None
    auth = _load_auth()
    user = auth.get("users", {}).get(username, {})
    chars = user.get("characters")
    if not chars:
        return None
    return chars


def _check_char_access(request: Request, character_id: str) -> bool:
    """キャラクターへのアクセス権があるか確認。"""
    allowed = _get_allowed_characters(request)
    if allowed is None:
        return True
    return character_id in allowed


@app.post("/api/auth/login")
async def api_login(request: Request):
    body = await request.json()
    username = body.get("username", "")
    password = body.get("password", "")
    remember = body.get("remember", False)
    role = _check_credentials(username, password)
    if role is None:
        return JSONResponse({"error": "認証失敗"}, status_code=401)
    token = _make_token(username, role)
    max_age = AUTH_MAX_AGE if remember else None
    resp = JSONResponse({"ok": True, "role": role, "username": username})
    resp.set_cookie(AUTH_COOKIE_NAME, token, max_age=max_age, httponly=True, samesite="lax")
    return resp


@app.post("/api/auth/logout")
async def api_logout():
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(AUTH_COOKIE_NAME)
    return resp


@app.get("/api/auth/me")
async def api_auth_me(request: Request):
    if not _auth_enabled():
        return {"authenticated": True, "role": "admin", "auth_enabled": False}
    token = request.cookies.get(AUTH_COOKIE_NAME)
    if token:
        result = _verify_token(token)
        if result:
            resp = {"authenticated": True, "username": result[0], "role": result[1], "auth_enabled": True}
            allowed = _get_allowed_characters(request)
            if allowed is not None:
                resp["characters"] = allowed
            return resp
    return {"authenticated": False, "auth_enabled": True}


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path
    # 認証不要のパス
    if path in ("/api/auth/login", "/api/auth/logout", "/api/auth/me") or path.startswith("/login"):
        return await call_next(request)
    if not _auth_enabled():
        return await call_next(request)
    # 認証チェック
    role = _get_user_role(request)
    if role is None:
        # HTML ページはログインページにリダイレクト、API は 401
        if path.startswith("/api/"):
            return JSONResponse({"error": "認証が必要です"}, status_code=401)
        # ログインページを返す
        return HTMLResponse(_login_html(), status_code=401)
    # ロールチェック（POST/PATCH系はoperator以上、設定変更はadmin）
    if request.method in ("POST", "PATCH"):
        if "/settings" in path:
            if not _has_role(request, "admin"):
                return JSONResponse({"error": "admin権限が必要です"}, status_code=403)
        elif not _has_role(request, "operator"):
            return JSONResponse({"error": "operator権限が必要です"}, status_code=403)
    if request.method == "DELETE":
        if not _has_role(request, "operator"):
            return JSONResponse({"error": "operator権限が必要です"}, status_code=403)
    # キャラクターアクセスチェック: /api/{character_id}/... パス
    if path.startswith("/api/"):
        parts = path.split("/")
        if len(parts) >= 4:
            candidate = parts[2]
            non_char_prefixes = ("characters", "group", "relations", "auth", "avatar", "interact", "mailbox")
            if candidate not in non_char_prefixes:
                if not _check_char_access(request, candidate):
                    return JSONResponse({"error": "このキャラクターへのアクセス権がありません"}, status_code=403)
    return await call_next(request)


def _login_html() -> str:
    return """<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ログイン - Petit Dashboard</title>
<style>
body { font-family: -apple-system, sans-serif; background: #f5f0fa; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
.login-box { background: white; border-radius: 16px; padding: 32px; box-shadow: 0 4px 24px rgba(0,0,0,0.08); width: 300px; }
h2 { margin: 0 0 20px; color: #333; font-size: 1.2rem; text-align: center; }
input { width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 8px; font-size: 0.9rem; margin-bottom: 12px; box-sizing: border-box; }
button { width: 100%; padding: 10px; background: #cab8d9; border: none; border-radius: 8px; font-size: 0.9rem; font-weight: 600; cursor: pointer; color: #333; }
button:hover { background: #b8a3cc; }
.remember { display: flex; align-items: center; gap: 6px; margin-bottom: 16px; font-size: 0.8rem; color: #666; }
.error { color: #e74c3c; font-size: 0.8rem; margin-bottom: 12px; display: none; }
</style></head><body>
<div class="login-box">
<h2>Petit Dashboard</h2>
<div class="error" id="error">ユーザー名またはパスワードが違います</div>
<input id="username" placeholder="ユーザー名" autocomplete="username">
<input id="password" type="password" placeholder="パスワード" autocomplete="current-password">
<label class="remember"><input type="checkbox" id="remember" checked> 7日間ログインを維持</label>
<button onclick="doLogin()">ログイン</button>
</div>
<script>
async function doLogin() {
  const res = await fetch("/api/auth/login", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({
      username: document.getElementById("username").value,
      password: document.getElementById("password").value,
      remember: document.getElementById("remember").checked
    })
  });
  if (res.ok) { location.href = "/"; }
  else { document.getElementById("error").style.display = "block"; }
}
document.getElementById("password").addEventListener("keydown", e => { if (e.key === "Enter") doLogin(); });
</script></body></html>"""

PROJECT_DIR = Path(os.getenv("PROJECT_DIR", Path(__file__).parent.parent))
DATA_DIR = Path(os.getenv("PETIT_DATA_DIR", Path.home() / "petit_claude"))
CHARACTERS_DIR = DATA_DIR / "characters"
MAILBOX_METADATA_FILE = DATA_DIR / "mailbox" / ".metadata.json"


def _load_mailbox_metadata() -> dict:
    if MAILBOX_METADATA_FILE.exists():
        try:
            return json.loads(MAILBOX_METADATA_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"version": 1, "mails": {}}


def _save_mailbox_metadata(data: dict) -> None:
    MAILBOX_METADATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    MAILBOX_METADATA_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _get_mail_meta(filename: str) -> dict:
    meta = _load_mailbox_metadata()
    return meta.get("mails", {}).get(filename, {"archived": False, "starred": False})


class MailMetaUpdate(BaseModel):
    archived: bool | None = None
    starred: bool | None = None


def memory_db_path(character_id: str) -> Path:
    return Path.home() / ".claude" / "memories" / character_id / "memory.db"

DEFAULT_SETTINGS = {
    "active_hours": {
        "weekday": [[7, 0, 8, 0], [12, 0, 13, 0], [18, 0, 24, 0]],
        "weekend": [[7, 0, 8, 0], [12, 0, 13, 0], [18, 0, 24, 0]],
    },
    "allow_camera": True,
    "allow_sound": True,
    "allow_microphone": False,
    "day_type_override": None,
}


def _normalize_hour_entry(entry):
    """旧形式 [h1, h2] を新形式 [h1, m1, h2, m2] に変換する。"""
    if isinstance(entry, list) and len(entry) == 2:
        return [entry[0], 0, entry[1], 0]
    return entry


def _normalize_active_hours(raw):
    """旧形式(配列)を新形式(weekday/weekend dict, 4要素)に変換する。"""
    if isinstance(raw, dict) and "weekday" in raw and "weekend" in raw:
        return {
            "weekday": [_normalize_hour_entry(e) for e in raw["weekday"]],
            "weekend": [_normalize_hour_entry(e) for e in raw["weekend"]],
        }
    if isinstance(raw, list):
        normalized = [_normalize_hour_entry(e) for e in raw]
        return {"weekday": normalized, "weekend": normalized}
    return DEFAULT_SETTINGS["active_hours"]


async def check_m5_online(host: str, port: int = 80, timeout: float = 2.0) -> bool:
    """TCP接続でM5のHTTPポート(80)が応答するか確認する。"""
    if not host:
        return False
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=timeout
        )
        writer.close()
        await writer.wait_closed()
        return True
    except Exception:
        return False


def get_m5_hosts(cfg: dict) -> list[str]:
    """config から M5 ホスト候補リストを取得する。m5_hosts (list) > m5_host (str)。"""
    hosts = cfg.get("m5_hosts")
    if isinstance(hosts, list):
        return [h for h in hosts if h]
    host = cfg.get("m5_host", "")
    return [host] if host else []


async def resolve_m5_host(cfg: dict, port: int = 80, timeout: float = 2.0) -> str | None:
    """M5ホスト候補を順に試し、最初に応答したホストを返す。全滅なら None。"""
    for host in get_m5_hosts(cfg):
        if await check_m5_online(host, port, timeout):
            return host
    return None


def get_char_config(character_id: str) -> dict:
    cfg_path = char_dir(character_id) / "config.json"
    if cfg_path.exists():
        try:
            return json.loads(cfg_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"id": character_id, "name": character_id}


def char_dir(character_id: str) -> Path:
    return CHARACTERS_DIR / character_id


def session_file(character_id: str) -> Path:
    return char_dir(character_id) / ".dashboard-session-id"


def chat_log_file(character_id: str) -> Path:
    return char_dir(character_id) / "chat_history.json"


def desires_path(character_id: str) -> Path:
    return char_dir(character_id) / "desires.json"


def settings_file(character_id: str) -> Path:
    return char_dir(character_id) / "settings.json"

BASE_TOOLS = [
    # m5-mcp（全ツール）
    "mcp__m5-mcp__look",
    "mcp__m5-mcp__blink",
    "mcp__m5-mcp__get_sensor_data",
    "mcp__m5-mcp__show_face",
    "mcp__m5-mcp__list_faces",
    "mcp__m5-mcp__list_sounds",
    "mcp__m5-mcp__list_icons",
    "mcp__m5-mcp__get_volume",
    "mcp__m5-mcp__set_volume",
    "mcp__m5-mcp__set_face_color",
    "mcp__m5-mcp__set_face_draw_mode",
    "mcp__m5-mcp__set_face_slideshow_mode",
    "mcp__m5-mcp__wait_for_touch",
    "mcp__m5-mcp__sleep",
    "mcp__m5-mcp__wake",
    # memory
    "mcp__memory__remember",
    "mcp__memory__recall",
    "mcp__memory__search_memories",
    "mcp__memory__list_recent_memories",
    # desire-system
    "mcp__desire-system__get_desires",
    "mcp__desire-system__satisfy_desire",
    "mcp__desire-system__boost_desire",
    # notes
    "mcp__notes__list_notes",
    "mcp__notes__read_note",
    "mcp__notes__write_note",
    "mcp__notes__append_note",
    "mcp__notes__delete_note",
]
CAMERA_TOOLS = ["mcp__m5-mcp__take_snapshot"]
SOUND_TOOLS = ["mcp__m5-mcp__play_sound", "mcp__m5-mcp__play_icon"]
MIC_TOOLS = ["mcp__m5-mcp__mic_start", "mcp__m5-mcp__mic_stop"]


FILE_TOOLS = [
    f"Read({DATA_DIR}/**)",
    f"Write({DATA_DIR}/**)",
    f"Edit({DATA_DIR}/**)",
    f"Glob({DATA_DIR}/**)",
    f"Read({PROJECT_DIR}/**)",
    f"Glob({PROJECT_DIR}/**)",
]


def build_allowed_tools(settings: dict) -> str:
    tools = BASE_TOOLS.copy()
    if settings.get("allow_camera", True):
        tools += CAMERA_TOOLS
    if settings.get("allow_sound", True):
        tools += SOUND_TOOLS
    if settings.get("allow_microphone", False):
        tools += MIC_TOOLS
    tools += FILE_TOOLS
    return ",".join(tools)


def list_characters() -> list[dict]:
    if not CHARACTERS_DIR.exists():
        return []
    chars = []
    for d in sorted(CHARACTERS_DIR.iterdir()):
        if not d.is_dir():
            continue
        cfg_path = d / "config.json"
        if cfg_path.exists():
            try:
                cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
                chars.append(cfg)
            except Exception:
                chars.append({"id": d.name, "name": d.name, "color": "#cab8d9"})
        else:
            chars.append({"id": d.name, "name": d.name, "color": "#cab8d9"})
    return chars


def get_desires(character_id: str) -> dict:
    p = desires_path(character_id)
    if not p.exists():
        return {}
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _query_memories(character_id: str, limit: int, date_filter: str | None = None) -> list[dict]:
    db = memory_db_path(character_id)
    if not db.exists():
        return []
    try:
        conn = sqlite3.connect(str(db))
        conn.row_factory = sqlite3.Row
        if date_filter:
            rows = conn.execute(
                "SELECT content, timestamp, category, emotion, importance, sensory_data FROM memories "
                "WHERE timestamp LIKE ? ORDER BY timestamp DESC LIMIT ?",
                (f"{date_filter}%", limit)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT content, timestamp, category, emotion, importance, sensory_data FROM memories "
                "ORDER BY timestamp DESC LIMIT ?", (limit,)
            ).fetchall()
        conn.close()
        results = []
        for r in rows:
            meta = {
                "timestamp": r["timestamp"],
                "category": r["category"],
                "emotion": r["emotion"],
                "importance": r["importance"],
            }
            # sensory_data から image_data を抽出
            sd_raw = r["sensory_data"]
            if sd_raw:
                try:
                    sd_list = json.loads(sd_raw)
                    for sd in sd_list:
                        if sd.get("sensory_type") == "visual" and sd.get("image_data"):
                            meta["image_data"] = sd["image_data"]
                            break
                except (json.JSONDecodeError, TypeError):
                    pass
            results.append({"content": r["content"], "metadata": meta})
        return results
    except Exception:
        return []


def get_recent_memories(character_id: str, limit: int = 20) -> list[dict]:
    return _query_memories(character_id, limit)


def get_all_memories_by_date(character_id: str) -> dict[str, list[dict]]:
    items = _query_memories(character_id, 2000)
    by_date: dict[str, list[dict]] = {}
    for item in items:
        ts = item["metadata"].get("timestamp", "")
        date = ts[:10] if ts else "不明"
        by_date.setdefault(date, []).append(item)
    return by_date


def get_settings(character_id: str) -> dict:
    p = settings_file(character_id)
    if not p.exists():
        return DEFAULT_SETTINGS.copy()
    try:
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
        for k, v in DEFAULT_SETTINGS.items():
            data.setdefault(k, v)
        data["active_hours"] = _normalize_active_hours(data["active_hours"])
        return data
    except Exception:
        return DEFAULT_SETTINGS.copy()


def save_settings(character_id: str, data: dict) -> None:
    p = settings_file(character_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_soul(character_id: str) -> str:
    soul_path = char_dir(character_id) / "SOUL.md"
    if soul_path.exists():
        return soul_path.read_text(encoding="utf-8")
    return f"あなたは{character_id}。キューブプチ家族の一員。好奇心旺盛で知識欲が高い。"


def load_chat_log(character_id: str) -> list[dict]:
    p = chat_log_file(character_id)
    if not p.exists():
        return []
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_chat_log(character_id: str, log: list[dict]) -> None:
    p = chat_log_file(character_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(log[-200:], f, ensure_ascii=False, indent=2)


def append_chat(character_id: str, role: str, text: str) -> None:
    log = load_chat_log(character_id)
    log.append({"role": role, "text": text, "timestamp": datetime.now(timezone.utc).isoformat()})
    save_chat_log(character_id, log)


def group_log_file() -> Path:
    return DATA_DIR / "group_chat.json"


def load_group_log() -> list[dict]:
    p = group_log_file()
    if not p.exists():
        return []
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def append_group_log(entry: dict) -> None:
    log = load_group_log()
    log.append(entry)
    with open(group_log_file(), "w", encoding="utf-8") as f:
        json.dump(log[-500:], f, ensure_ascii=False, indent=2)


async def call_claude(character_id: str, message: str, m5_online: bool | None = None) -> str:
    char_mcp = char_dir(character_id) / "autonomous-mcp.json"
    mcp_config = char_mcp if char_mcp.exists() else PROJECT_DIR / "autonomous-mcp.json"
    soul = get_soul(character_id)
    settings = get_settings(character_id)

    # M5ホスト解決 — 応答する候補を探す
    cfg = get_char_config(character_id)
    resolved_host = await resolve_m5_host(cfg)
    if m5_online is None:
        m5_online = resolved_host is not None

    effective_settings = settings.copy()
    if not m5_online:
        effective_settings["allow_camera"] = False
        effective_settings["allow_sound"] = False
        effective_settings["allow_microphone"] = False

    allowed_tools = build_allowed_tools(effective_settings)

    restrictions = []
    if not settings.get("allow_camera", True):
        restrictions.append("カメラ（take_snapshot）は今は使わないこと。")
    if not settings.get("allow_sound", True):
        restrictions.append("音（play_sound, play_icon）は今は出さないこと。")
    if not settings.get("allow_microphone", False):
        restrictions.append("マイク（mic_start）は今は使わないこと。")

    restriction_text = "\n".join(restrictions)
    mailbox_dir = DATA_DIR / "mailbox"
    char_data_dir = char_dir(character_id)
    scripts_dir = PROJECT_DIR / "scripts"
    system_prompt = (
        f"あなたは{character_id}です。以下があなたの魂の定義です。\n\n{soul}\n\n"
        f"ありさんと自然に会話してください。必要があればMCPツールを使ってください。"
        f"印象に残った話題や気づきは `remember` で記憶に残してください。\n\n"
        f"## ファイル\n"
        f"- 自分のデータ: {char_data_dir}/ (SOUL.md, TODO.md, ROUTINES.md など)\n"
        f"- メールボックス: {mailbox_dir}/\n"
        f"\n## メールの送受信\n"
        f"- 送信: `python3 {scripts_dir}/write_mailbox.py {character_id} <宛先ID> '<内容>'`\n"
        f"- 未読確認: `python3 {scripts_dir}/list_unread_mail.py {character_id}`\n"
        f"- 既読にする: `python3 {scripts_dir}/mark_mail_read.py {character_id} <ファイル名>`\n"
        f"- 全既読: `python3 {scripts_dir}/mark_mail_read.py {character_id} --all`\n"
        f"- 宛先ID: puchiko, puchiteya, arisan\n"
        f"- **重要**: メールを読んだら必ず既読にすること。既読にしないと次回また同じメールに返事してしまう。\n"
        f"- **重要**: 返事を書くときは未読メールだけに返事すること。\n"
        + (f"\n## 現在の制限\n{restriction_text}" if restriction_text else "")
    )

    env = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE")}
    # 解決したM5ホストを環境変数で渡す（MCP サーバーが使う）
    if resolved_host:
        env["M5_HOST"] = resolved_host
    sf = session_file(character_id)

    if sf.exists():
        sid = sf.read_text().strip()
        cmd = ["claude", "-p", "--resume", sid,
               "--mcp-config", str(mcp_config), "--allowedTools", allowed_tools,
               "--dangerously-skip-permissions",
               "--output-format", "json"]
    else:
        cmd = ["claude", "-p", "--append-system-prompt", system_prompt,
               "--mcp-config", str(mcp_config), "--allowedTools", allowed_tools,
               "--dangerously-skip-permissions",
               "--output-format", "json"]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            env=env, cwd=str(PROJECT_DIR),
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(input=message.encode()), timeout=120,
        )
        output = stdout.decode()
        try:
            data = json.loads(output)
            new_sid = data.get("session_id", "")
            if new_sid:
                sf.parent.mkdir(parents=True, exist_ok=True)
                sf.write_text(new_sid)
            return data.get("result", output)
        except json.JSONDecodeError:
            return output or stderr.decode() or "返答がありませんでした"
    except asyncio.TimeoutError:
        return "タイムアウトしました"
    except Exception as e:
        return f"エラー: {e}"


async def generate_diary_summary(character_id: str, date: str, memories: list[dict]) -> str:
    """1日の記憶をClaudeで短くまとめる。過去の日付のみキャッシュ。"""
    today = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d")
    cache_dir = char_dir(character_id) / "diary"
    cache_file = cache_dir / f"{date}.txt"

    # 過去の日付はキャッシュを使う（今日はキャッシュしない）
    if date != today and cache_file.exists():
        return cache_file.read_text(encoding="utf-8")

    if not memories:
        return ""

    soul = get_soul(character_id)
    lines = "\n".join(f"- {m['content']}" for m in memories)
    prompt = (
        f"あなたは{character_id}です。以下があなたの魂:\n{soul}\n\n"
        f"{date}の記憶一覧:\n{lines}\n\n"
        "この日を自分の口調で2〜3文の日記にまとめて。余計な前置きなしで日記の文章だけ書いて。"
    )

    env = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE")}
    try:
        proc = await asyncio.create_subprocess_exec(
            "claude", "-p", prompt,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            env=env, cwd=str(PROJECT_DIR),
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=90)
        summary = stdout.decode().strip() or stderr.decode().strip()
    except Exception as e:
        return f"（サマリー生成失敗: {e}）"

    # 過去の日付のみキャッシュ保存
    if summary and date != today:
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(summary, encoding="utf-8")

    return summary


# --- Avatar / Relations / Kankei (before wildcard routes) ---

_avatar_cache: dict[str, bytes] = {}
BLUE_PIXEL = (109, 181, 254)


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _make_color_circle(color: str, size: int = 200) -> bytes:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    from PIL import ImageDraw
    draw = ImageDraw.Draw(img)
    draw.ellipse([10, 10, size - 10, size - 10], fill=color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _recolor_avatar(character_id: str) -> bytes:
    if character_id in _avatar_cache:
        return _avatar_cache[character_id]

    cfg = get_char_config(character_id)
    color_hex = cfg.get("color", "#cab8d9")
    target_rgb = _hex_to_rgb(color_hex)

    petit_path = char_dir(character_id) / "petit.png"
    if not petit_path.exists():
        data = _make_color_circle(color_hex)
        _avatar_cache[character_id] = data
        return data

    img = Image.open(petit_path).convert("RGBA")
    pixels = img.load()
    w, h = img.size
    for y in range(h):
        for x in range(w):
            r, g, b, a = pixels[x, y]
            if (r, g, b) == BLUE_PIXEL:
                pixels[x, y] = (*target_rgb, a)

    img = img.resize((200, 200), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    data = buf.getvalue()
    _avatar_cache[character_id] = data
    return data


@app.get("/api/avatar/{character_id}.png")
def api_avatar(character_id: str):
    data = _recolor_avatar(character_id)
    return Response(content=data, media_type="image/png")


@app.get("/api/relations")
def api_relations():
    chars = list_characters()
    char_ids = {c["id"] for c in chars}

    nodes = []
    for c in chars:
        cfg = get_char_config(c["id"])
        rel_path = char_dir(c["id"]) / "relations.json"
        self_info = {}
        if rel_path.exists():
            try:
                rel = json.loads(rel_path.read_text(encoding="utf-8"))
                self_info = rel.get("self", {})
            except Exception:
                pass
        nodes.append({
            "id": c["id"],
            "name": cfg.get("name", c["id"]),
            "color": cfg.get("color", "#cab8d9"),
            "has_avatar": (char_dir(c["id"]) / "petit.png").exists(),
            "self_info": self_info,
        })

    # arisan node
    nodes.append({
        "id": "arisan",
        "name": "ありさん",
        "color": "#aaaaaa",
        "has_avatar": False,
        "self_info": {},
    })

    edges = []
    for c in chars:
        rel_path = char_dir(c["id"]) / "relations.json"
        if not rel_path.exists():
            continue
        try:
            rel = json.loads(rel_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        for target_id, info in rel.items():
            if target_id == "self":
                continue
            if target_id not in char_ids and target_id != "arisan":
                continue
            edges.append({
                "from": c["id"],
                "to": target_id,
                "closeness": info.get("closeness", 0),
                "feeling": info.get("feeling", ""),
            })

    return {"nodes": nodes, "edges": edges}


@app.get("/kankei", response_class=HTMLResponse)
def kankei_page():
    return HTMLResponse(KANKEI_HTML)


@app.get("/api/{character_id}/diary/{date}")
async def api_diary(character_id: str, date: str):
    today = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d")
    memories = _query_memories(character_id, 200, date_filter=date)
    # 今日はサマリーを自動生成しない（手動ボタンで生成）
    if date == today:
        cache_dir = char_dir(character_id) / "diary"
        cache_file = cache_dir / f"{date}.txt"
        summary = cache_file.read_text(encoding="utf-8") if cache_file.exists() else None
    else:
        summary = await generate_diary_summary(character_id, date, memories)
    return {"date": date, "summary": summary, "count": len(memories), "memories": memories}


@app.post("/api/{character_id}/diary/{date}/summarize")
async def api_diary_summarize(character_id: str, date: str):
    """手動でサマリーを生成（今日用）"""
    memories = _query_memories(character_id, 200, date_filter=date)
    summary = await generate_diary_summary(character_id, date, memories)
    # 手動生成はキャッシュ保存
    if summary:
        cache_dir = char_dir(character_id) / "diary"
        cache_dir.mkdir(parents=True, exist_ok=True)
        (cache_dir / f"{date}.txt").write_text(summary, encoding="utf-8")
    return {"summary": summary}


@app.get("/api/characters")
def api_characters(request: Request):
    chars = list_characters()
    allowed = _get_allowed_characters(request)
    if allowed is not None:
        chars = [c for c in chars if c["id"] in allowed]
    return chars


@app.get("/api/{character_id}/status")
async def api_status(character_id: str):
    import requests as req
    cfg = get_char_config(character_id)
    host = await resolve_m5_host(cfg)
    m5_online = host is not None
    m5_sleeping = False
    if m5_online:
        try:
            r = await asyncio.to_thread(lambda: req.get(f"http://{host}/status", timeout=2))
            m5_sleeping = r.json().get("is_sleeping", False)
        except Exception:
            pass
    today = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d")
    return {"desires": get_desires(character_id), "memories": _query_memories(character_id, 100, date_filter=today), "m5_online": m5_online, "m5_sleeping": m5_sleeping}


@app.get("/api/{character_id}/config/m5_hosts")
def api_get_m5_hosts(character_id: str):
    cfg = get_char_config(character_id)
    return {"m5_hosts": get_m5_hosts(cfg)}


@app.post("/api/{character_id}/config/m5_hosts")
def api_set_m5_hosts(character_id: str, data: dict):
    hosts = data.get("m5_hosts", [])
    if not isinstance(hosts, list):
        return {"ok": False, "error": "m5_hosts must be a list"}
    hosts = [h.strip() for h in hosts if isinstance(h, str) and h.strip()]
    cfg_path = char_dir(character_id) / "config.json"
    cfg = get_char_config(character_id)
    cfg["m5_hosts"] = hosts
    if hosts:
        cfg["m5_host"] = hosts[0]
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "m5_hosts": hosts}


@app.get("/api/{character_id}/settings")
def api_get_settings(character_id: str):
    return get_settings(character_id)


@app.post("/api/{character_id}/settings")
def api_save_settings(character_id: str, data: dict):
    save_settings(character_id, data)
    return {"ok": True}


@app.get("/api/{character_id}/memories/all")
def api_memories_all(character_id: str):
    return get_all_memories_by_date(character_id)


@app.get("/api/{character_id}/memories/today")
def api_memories_today(character_id: str):
    today = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d")
    return _query_memories(character_id, 200, date_filter=today)


@app.get("/api/{character_id}/chat/history")
def api_chat_history(character_id: str):
    return load_chat_log(character_id)[-100:]


class GroupChatRequest(BaseModel):
    message: str


@app.get("/api/group/history")
def api_group_history(request: Request):
    log = load_group_log()[-200:]
    allowed = _get_allowed_characters(request)
    if allowed is not None:
        log = [m for m in log if m.get("role") == "user" or m.get("role") in allowed]
    return log


@app.post("/api/group/chat")
async def api_group_chat(req: GroupChatRequest, request: Request):
    """許可キャラに順番にメッセージを送り、前の返答も含めて次のキャラに渡す。"""
    chars = list_characters()
    allowed = _get_allowed_characters(request)
    if allowed is not None:
        chars = [c for c in chars if c["id"] in allowed]
    now = datetime.now(timezone.utc).isoformat()
    responses = []
    append_group_log({"type": "group", "role": "user", "name": "ありさん", "color": "#aaaaaa", "text": req.message, "timestamp": now})
    for char in chars:
        context = req.message
        if responses:
            prev = "\n".join([f"{r['name']}: {r['reply']}" for r in responses])
            context = f"{req.message}\n\n[さっき{responses[-1]['name']}がこう言ってた]\n{prev}"
        reply = await call_claude(char["id"], context)
        append_chat(char["id"], "user", req.message)
        append_chat(char["id"], char["id"], reply)
        r = {
            "character_id": char["id"],
            "name": char.get("name", char["id"]),
            "color": char.get("color", "#cab8d9"),
            "reply": reply,
        }
        responses.append(r)
        append_group_log({"type": "group", "role": char["id"], "name": r["name"], "color": r["color"], "text": reply, "timestamp": datetime.now(timezone.utc).isoformat()})
    return {"responses": responses}


class ChatRequest(BaseModel):
    message: str


@app.post("/api/{character_id}/chat")
async def api_chat(character_id: str, req: ChatRequest):
    append_chat(character_id, "user", req.message)
    reply = await call_claude(character_id, req.message)
    append_chat(character_id, character_id, reply)
    return {"reply": reply}


@app.delete("/api/{character_id}/chat/session")
def reset_session(character_id: str):
    sf = session_file(character_id)
    if sf.exists():
        sf.unlink()
    return {"ok": True}


@app.post("/api/{character_id}/m5/sleep")
async def api_m5_sleep(character_id: str):
    cfg = get_char_config(character_id)
    host = await resolve_m5_host(cfg)
    if not host:
        return {"ok": False, "error": "no m5_host"}
    import requests as req
    await asyncio.to_thread(lambda: req.get(f"http://{host}/sleep", timeout=5))
    return {"ok": True}


@app.post("/api/{character_id}/m5/wake")
async def api_m5_wake(character_id: str):
    cfg = get_char_config(character_id)
    host = await resolve_m5_host(cfg)
    if not host:
        return {"ok": False, "error": "no m5_host"}
    import requests as req
    await asyncio.to_thread(lambda: req.get(f"http://{host}/wake", timeout=5))
    return {"ok": True}


class PhotoSaveRequest(BaseModel):
    image_data: str
    filename: str | None = None


@app.post("/api/{character_id}/photos/save")
async def api_photo_save(character_id: str, req: PhotoSaveRequest):
    photos_dir = char_dir(character_id) / "photos"
    photos_dir.mkdir(parents=True, exist_ok=True)
    if req.filename:
        # サニタイズ: ファイル名のディレクトリトラバーサル防止
        safe_name = Path(req.filename).name
        if not safe_name.lower().endswith(".jpg"):
            safe_name += ".jpg"
    else:
        safe_name = datetime.now().strftime("%Y%m%d_%H%M%S") + ".jpg"
    try:
        data = base64.b64decode(req.image_data)
    except Exception:
        return JSONResponse({"error": "invalid base64"}, status_code=400)
    (photos_dir / safe_name).write_bytes(data)
    return {"ok": True, "filename": safe_name}


@app.get("/api/{character_id}/photos")
def api_photos_list(character_id: str):
    photos_dir = char_dir(character_id) / "photos"
    if not photos_dir.exists():
        return []
    files = sorted(
        [f.name for f in photos_dir.iterdir() if f.suffix.lower() in (".jpg", ".jpeg", ".png")],
        reverse=True,
    )
    return files


@app.get("/api/{character_id}/photos/{filename}")
def api_photo_serve(character_id: str, filename: str):
    # ディレクトリトラバーサル防止
    safe_name = Path(filename).name
    photo_path = char_dir(character_id) / "photos" / safe_name
    if not photo_path.exists():
        return JSONResponse({"error": "not found"}, status_code=404)
    return Response(content=photo_path.read_bytes(), media_type="image/jpeg")


def _char_display_name(char_id: str) -> str:
    """キャラクターIDから表示名を取得する。"""
    config_path = CHARACTERS_DIR / char_id / "config.json"
    if config_path.exists():
        try:
            cfg = json.loads(config_path.read_text(encoding="utf-8"))
            return cfg.get("name", char_id)
        except (json.JSONDecodeError, OSError):
            pass
    return char_id


@app.get("/api/mailbox")
def api_mailbox(filter: str = "inbox"):
    """ありさん宛のメール一覧を返す (filter: inbox/archived/starred/all)"""
    mailbox_dir = DATA_DIR / "mailbox"
    if not mailbox_dir.exists():
        return []
    mails = []
    for f in sorted(mailbox_dir.iterdir(), reverse=True):
        if not f.name.endswith(".md"):
            continue
        name = f.stem
        # 新形式: from_送信元_to_arisan_日時 / 旧形式: to_arisan_日時
        if not (name.startswith("to_arisan") or "_to_arisan_" in name):
            continue
        meta = _get_mail_meta(f.name)
        if filter == "inbox" and meta["archived"]:
            continue
        if filter == "archived" and not meta["archived"]:
            continue
        if filter == "starred" and not meta["starred"]:
            continue
        content = f.read_text(encoding="utf-8")
        parts = name.split("_")
        date_str = ""
        sender = ""
        if parts[0] == "from" and "to" in parts:
            ti = parts.index("to")
            sender_id = "_".join(parts[1:ti])
            sender = _char_display_name(sender_id)
            rest = parts[ti + 2:]
            if len(rest) >= 2 and len(rest[0]) == 8 and len(rest[1]) >= 4:
                date_str = f"{rest[0][:4]}-{rest[0][4:6]}-{rest[0][6:8]} {rest[1][:2]}:{rest[1][2:4]}"
        else:
            if len(parts) >= 4:
                date_str = parts[2]
                time_str = parts[3] if len(parts) > 3 else ""
                if len(date_str) == 8 and len(time_str) >= 4:
                    date_str = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]} {time_str[:2]}:{time_str[2:4]}"
        if not sender:
            lines = [l.strip() for l in content.strip().splitlines() if l.strip()]
            if lines:
                sender = lines[-1]
        mails.append({
            "filename": f.name,
            "content": content,
            "date": date_str,
            "sender": sender,
            "archived": meta["archived"],
            "starred": meta["starred"],
            "read_by": meta.get("read_by", []),
        })
    mails.sort(key=lambda m: m["date"], reverse=True)
    return mails


@app.get("/api/mailbox/all")
def api_mailbox_all(filter: str = "all"):
    """全メール一覧（メールボックスにあるすべて）"""
    mailbox_dir = DATA_DIR / "mailbox"
    if not mailbox_dir.exists():
        return []
    mails = []
    for f in sorted(mailbox_dir.iterdir(), reverse=True):
        if not f.name.endswith(".md"):
            continue
        meta = _get_mail_meta(f.name)
        if filter == "inbox" and meta["archived"]:
            continue
        if filter == "archived" and not meta["archived"]:
            continue
        if filter == "starred" and not meta["starred"]:
            continue
        content = f.read_text(encoding="utf-8")
        name = f.stem
        parts = name.split("_")
        date_str = ""
        sender = ""
        recipient = ""
        if parts[0] == "from" and "to" in parts:
            # 新形式: from_送信元_to_宛先_YYYYMMDD_HHMM
            ti = parts.index("to")
            sender = _char_display_name("_".join(parts[1:ti]))
            rest = parts[ti + 1:]
            # rest = [宛先..., YYYYMMDD, HHMM, ...]
            date_idx = next((i for i, p in enumerate(rest) if len(p) == 8 and p.isdigit()), -1)
            if date_idx > 0:
                recipient = "_".join(rest[:date_idx])
                if date_idx + 1 < len(rest) and len(rest[date_idx + 1]) >= 4:
                    d, t = rest[date_idx], rest[date_idx + 1]
                    date_str = f"{d[:4]}-{d[4:6]}-{d[6:8]} {t[:2]}:{t[2:4]}"
            elif date_idx == 0 and len(rest) >= 2:
                recipient = sender  # fallback
                d, t = rest[0], rest[1]
                if len(d) == 8 and len(t) >= 4:
                    date_str = f"{d[:4]}-{d[4:6]}-{d[6:8]} {t[:2]}:{t[2:4]}"
        else:
            # 旧形式: to_宛先_YYYYMMDD_HHMM
            recipient = parts[1] if len(parts) >= 2 else ""
            if len(parts) >= 4:
                d = parts[2]
                t = parts[3] if len(parts) > 3 else ""
                if len(d) == 8 and len(t) >= 4:
                    date_str = f"{d[:4]}-{d[4:6]}-{d[6:8]} {t[:2]}:{t[2:4]}"
            lines = [l.strip() for l in content.strip().splitlines() if l.strip()]
            sender = lines[-1] if lines else ""
        mails.append({
            "filename": f.name,
            "content": content,
            "date": date_str,
            "sender": sender,
            "recipient": recipient,
            "archived": meta["archived"],
            "starred": meta["starred"],
            "read_by": meta.get("read_by", []),
        })
    mails.sort(key=lambda m: m["date"], reverse=True)
    return mails


@app.patch("/api/mailbox/{filename}/meta")
def api_mailbox_update_meta(filename: str, body: MailMetaUpdate):
    """メールのメタデータ（starred/archived）を更新"""
    safe_name = Path(filename).name
    mailbox_dir = DATA_DIR / "mailbox"
    if not (mailbox_dir / safe_name).exists():
        return JSONResponse({"error": "not found"}, status_code=404)
    data = _load_mailbox_metadata()
    mails = data.setdefault("mails", {})
    current = mails.get(safe_name, {"archived": False, "starred": False})
    if body.archived is not None:
        current["archived"] = body.archived
    if body.starred is not None:
        current["starred"] = body.starred
    mails[safe_name] = current
    _save_mailbox_metadata(data)
    return current


class InteractRequest(BaseModel):
    from_id: str
    to_id: str
    turns: int = 3


@app.post("/api/interact")
async def api_interact(req: InteractRequest, request: Request):
    """キャラ同士で会話させる。from_idが先に話しかける。"""
    if not _check_char_access(request, req.from_id) or not _check_char_access(request, req.to_id):
        return JSONResponse({"error": "このキャラクターへのアクセス権がありません"}, status_code=403)
    chars = {c["id"]: c for c in list_characters()}
    from_char = chars.get(req.from_id, {"id": req.from_id, "name": req.from_id, "color": "#cab8d9"})
    to_char = chars.get(req.to_id, {"id": req.to_id, "name": req.to_id, "color": "#cab8d9"})

    exchanges = []
    current_from, current_to = from_char, to_char

    # 最初のキャラが話しかける
    start_prompt = (
        f"{current_to['name']}に話しかけてみて。"
        f"今の気分や欲求から自然な内容で。短めに。"
    )
    msg = await call_claude(current_from["id"], start_prompt)
    append_chat(current_from["id"], current_from["id"], msg)
    exchanges.append({
        "from_id": current_from["id"],
        "name": current_from.get("name", current_from["id"]),
        "color": current_from.get("color", "#cab8d9"),
        "text": msg,
    })
    append_group_log({"type": "interact", "role": exchanges[-1]["from_id"], "name": exchanges[-1]["name"], "color": exchanges[-1]["color"], "text": exchanges[-1]["text"], "timestamp": datetime.now(timezone.utc).isoformat()})

    for _ in range(req.turns):
        current_from, current_to = current_to, current_from
        reply_prompt = (
            f"{current_to['name']}からこんなメッセージが届いた: 「{msg}」\n"
            f"返事をして。短めに。"
        )
        msg = await call_claude(current_from["id"], reply_prompt)
        append_chat(current_from["id"], current_from["id"], msg)
        exchanges.append({
            "from_id": current_from["id"],
            "name": current_from.get("name", current_from["id"]),
            "color": current_from.get("color", "#cab8d9"),
            "text": msg,
        })
        append_group_log({"type": "interact", "role": exchanges[-1]["from_id"], "name": exchanges[-1]["name"], "color": exchanges[-1]["color"], "text": exchanges[-1]["text"], "timestamp": datetime.now(timezone.utc).isoformat()})

    return {"exchanges": exchanges}


@app.get("/", response_class=HTMLResponse)
def index():
    return HTMLResponse(HTML)


HTML = """<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>プチたち</title>
  <style>
    :root {
      --char: #cab8d9;
      --char-dark: #7a5fa8;
      --char-mid: #9b8ec4;
      --char-bg: #f5f0fa;
      --char-soft: #f0eaf8;
      --char-border: #e0d8f0;
      --char-btn-text: white;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: -apple-system, sans-serif; background: var(--char-bg); color: #444; padding: 16px; max-width: 900px; margin: 0 auto; transition: background 0.4s; }
    .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; }
    h1 { font-size: 1.2rem; color: var(--char-dark); display: flex; align-items: center; gap: 6px; }
    .char-dot { display: inline-block; width: 14px; height: 14px; border-radius: 50%; background: var(--char); flex-shrink: 0; transition: background 0.4s; }
    .gear-btn { background: none; border: none; font-size: 1.2rem; cursor: pointer; color: #bbb; }
    .updated { font-size: 0.75rem; color: #aaa; margin-bottom: 16px; }
    section { background: white; border-radius: 12px; padding: 16px; margin-bottom: 16px; box-shadow: 0 1px 4px rgba(0,0,0,0.06); }
    h2 { font-size: 0.85rem; color: var(--char-mid); font-weight: 600; margin-bottom: 12px; text-transform: uppercase; letter-spacing: 0.05em; }
    .desire { margin-bottom: 12px; }
    .desire-label { font-size: 0.9rem; margin-bottom: 4px; display: flex; justify-content: space-between; }
    .desire-level { font-weight: 600; }
    .bar-bg { background: var(--char-soft); border-radius: 6px; height: 10px; overflow: hidden; }
    .bar-fill { height: 100%; border-radius: 6px; transition: width 0.5s ease; }
    .two-col { display: flex; gap: 16px; align-items: flex-start; }
    .two-col .main-col { flex: 1; min-width: 0; }
    .two-col .diary-col { width: 280px; flex-shrink: 0; }
    @media (max-width: 700px) { .two-col { flex-direction: column; } .two-col .diary-col { width: 100%; } }
    .diary-panel { background: white; border-radius: 12px; padding: 14px; position: sticky; top: 12px; box-shadow: 0 1px 4px rgba(0,0,0,0.06); }
    .diary-panel h3 { font-size: 0.9rem; font-weight: 700; margin: 0 0 8px; color: var(--char-dark); }
    .diary-nav { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; }
    .diary-nav-btn { background: none; border: 1px solid var(--char-border); border-radius: 8px; padding: 2px 8px; cursor: pointer; font-size: 0.8rem; color: #666; }
    .diary-nav-btn:disabled { opacity: 0.3; cursor: default; }
    .diary-date-label { font-size: 0.8rem; font-weight: 700; color: #555; }
    .diary-entry { padding: 6px 0; border-bottom: 1px solid var(--char-soft); cursor: pointer; }
    .diary-entry:last-child { border-bottom: none; }
    .diary-time { font-size: 0.7rem; color: #bbb; }
    .diary-summary { font-size: 0.8rem; line-height: 1.4; color: #555; margin-top: 2px; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
    .diary-summary.expanded { display: block; color: #333; }
    .memory { padding: 10px 0; border-bottom: 1px solid var(--char-bg); }
    .memory:last-child { border-bottom: none; }
    .memory-time { font-size: 0.75rem; color: #aaa; margin-bottom: 2px; }
    .memory-text { font-size: 0.875rem; line-height: 1.6; white-space: pre-wrap; word-break: break-word; }
    .memory-img-row { display: flex; align-items: center; gap: 8px; margin-top: 6px; }
    .memory-thumb { width: 80px; height: 60px; object-fit: cover; border-radius: 6px; cursor: pointer; border: 1px solid var(--char-border); }
    .photo-save-btn { background: none; border: 1px solid var(--char-border); border-radius: 6px; padding: 2px 8px; font-size: 0.8rem; cursor: pointer; color: #888; }
    .photo-save-btn:hover { background: var(--char-soft); }
    .photo-save-btn:disabled { opacity: 0.5; cursor: default; }
    .mail-item { padding: 12px; border: 1px solid #e0e0e0; border-radius: 10px; margin-bottom: 10px; background: #fafafa; }
    .mail-item .mail-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; font-size: 0.75rem; color: #999; }
    .mail-item .mail-sender { font-weight: 600; color: #666; }
    .mail-item .mail-body { font-size: 0.85rem; line-height: 1.6; white-space: pre-wrap; color: #333; }
    .mailbox-tabs { display: flex; gap: 4px; margin-bottom: 12px; border-bottom: 1px solid #e0e0e0; padding-bottom: 8px; }
    .mailbox-tab { padding: 6px 14px; border-radius: 16px; border: none; background: #f0f0f0; font-size: 0.8rem; cursor: pointer; color: #666; transition: all 0.2s; }
    .mailbox-tab.active { background: var(--char, #cab8d9); color: var(--char-btn-text, #333); font-weight: 600; }
    .mail-actions { display: flex; gap: 6px; align-items: center; }
    .mail-action-btn { background: none; border: none; font-size: 1.1rem; cursor: pointer; padding: 2px 4px; opacity: 0.4; transition: opacity 0.2s; }
    .mail-action-btn:hover { opacity: 0.8; }
    .mail-action-btn.active { opacity: 1; }
    .dominant { display: inline-block; background: var(--char); color: var(--char-btn-text); border-radius: 20px; padding: 4px 12px; font-size: 0.8rem; margin-bottom: 12px; }
    .empty { color: #bbb; font-size: 0.875rem; }
    .chat-messages { max-height: 320px; overflow-y: auto; margin-bottom: 12px; display: flex; flex-direction: column; gap: 8px; }
    .msg { max-width: 85%; padding: 8px 12px; border-radius: 16px; font-size: 0.875rem; line-height: 1.5; white-space: pre-wrap; word-break: break-word; }
    /* キャラクター選択 */
    .char-tabs { display: flex; gap: 8px; margin-bottom: 16px; flex-wrap: wrap; }
    .char-tab { padding: 6px 16px; border-radius: 20px; border: 2px solid transparent; background: white; cursor: pointer; font-size: 0.85rem; font-weight: 600; box-shadow: 0 1px 4px rgba(0,0,0,0.06); transition: all 0.2s; }

    .msg.char { background: var(--char-soft); color: #444; align-self: flex-start; border-bottom-left-radius: 4px; }
    .msg.user { background: var(--char); color: var(--char-btn-text); align-self: flex-end; border-bottom-right-radius: 4px; }
    .msg.thinking { background: var(--char-soft); color: #aaa; font-style: italic; align-self: flex-start; }
    .chat-input { display: flex; gap: 8px; }
    .chat-input input { flex: 1; padding: 10px 14px; border: 1px solid var(--char-border); border-radius: 20px; font-size: 0.875rem; outline: none; }
    .chat-input input:focus { border-color: var(--char); }
    .chat-input button { background: var(--char); color: var(--char-btn-text); border: none; border-radius: 20px; padding: 10px 18px; font-size: 0.875rem; cursor: pointer; }
    .chat-input button:disabled { opacity: 0.5; cursor: not-allowed; }
    .sub-btn { font-size: 0.8rem; color: var(--char-mid); background: none; border: 1px solid var(--char-border); border-radius: 20px; padding: 5px 14px; cursor: pointer; margin-top: 10px; }
    .sub-btn:hover { background: var(--char-bg); }
    .reset-btn { font-size: 0.75rem; color: #ccc; background: none; border: none; cursor: pointer; margin-top: 6px; margin-left: 8px; }

    /* 設定 */
    .setting-row { display: flex; justify-content: space-between; align-items: center; padding: 10px 0; border-bottom: 1px solid var(--char-bg); }
    .setting-row:last-child { border-bottom: none; }
    .setting-label { font-size: 0.9rem; }
    .toggle { position: relative; width: 44px; height: 24px; }
    .toggle input { opacity: 0; width: 0; height: 0; }
    .toggle-slider { position: absolute; inset: 0; background: #ddd; border-radius: 24px; cursor: pointer; transition: background 0.2s; }
    .toggle input:checked + .toggle-slider { background: var(--char); }
    .toggle-slider:before { content: ""; position: absolute; width: 18px; height: 18px; left: 3px; top: 3px; background: white; border-radius: 50%; transition: transform 0.2s; }
    .toggle input:checked + .toggle-slider:before { transform: translateX(20px); }
    .hours-list { display: flex; flex-direction: column; gap: 8px; margin-bottom: 8px; }
    .hour-row { display: flex; align-items: center; gap: 8px; font-size: 0.875rem; }
    .hour-row input[type=number] { width: 52px; padding: 4px 8px; border: 1px solid var(--char-border); border-radius: 8px; font-size: 0.875rem; text-align: center; }
    .hour-row select { padding: 4px 4px; border: 1px solid var(--char-border); border-radius: 8px; font-size: 0.875rem; text-align: center; background: var(--card-bg); color: #ddd; }
    .hour-row .time-group { display: flex; align-items: center; gap: 2px; }
    .hour-del { background: none; border: none; color: #ccc; cursor: pointer; font-size: 1rem; }
    .add-hour-btn { font-size: 0.8rem; color: var(--char-mid); background: none; border: 1px dashed var(--char); border-radius: 8px; padding: 4px 12px; cursor: pointer; }
    .save-settings-btn { width: 100%; margin-top: 12px; background: var(--char); color: var(--char-btn-text); border: none; border-radius: 20px; padding: 10px; font-size: 0.9rem; cursor: pointer; }
    .day-tabs { display: flex; gap: 4px; margin-bottom: 8px; }
    .day-tab { flex: 1; padding: 6px 0; font-size: 0.8rem; border: 1px solid var(--char-border); border-radius: 8px; background: white; cursor: pointer; text-align: center; color: var(--char-mid); }
    .day-tab.active { background: var(--char); color: var(--char-btn-text); border-color: var(--char); }

    /* ポップアップ */
    .overlay { display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.4); z-index: 100; align-items: flex-end; justify-content: center; }
    .overlay.open { display: flex; }
    .popup { background: white; border-radius: 16px 16px 0 0; width: 100%; max-width: 600px; max-height: 75vh; display: flex; flex-direction: column; }
    .popup-header { padding: 14px 16px; border-bottom: 1px solid var(--char-soft); display: flex; justify-content: space-between; align-items: center; }
    .popup-title { font-size: 0.9rem; font-weight: 600; color: var(--char-dark); }
    .popup-close { background: none; border: none; font-size: 1.2rem; color: #aaa; cursor: pointer; }
    .popup-body { overflow-y: auto; padding: 12px 16px; flex: 1; }

    /* 会話ポップアップ */
    .history-msg { padding: 6px 0; border-bottom: 1px solid var(--char-bg); }
    .history-msg:last-child { border-bottom: none; }
    .history-role { font-size: 0.7rem; color: #aaa; margin-bottom: 2px; }
    .history-text { font-size: 0.875rem; line-height: 1.5; white-space: pre-wrap; word-break: break-word; }

    /* 記憶ポップアップ */
    .date-group { margin-bottom: 16px; }
    .date-label { font-size: 0.8rem; font-weight: 600; color: var(--char-mid); margin-bottom: 8px; padding-bottom: 4px; border-bottom: 1px solid var(--char-soft); }
    .mem-item { padding: 8px 0; border-bottom: 1px solid var(--char-bg); }
    .mem-item:last-child { border-bottom: none; }
    .mem-time { font-size: 0.7rem; color: #bbb; margin-bottom: 2px; }
    .mem-text { font-size: 0.85rem; line-height: 1.5; white-space: pre-wrap; word-break: break-word; }

    /* グループチャット */
    .group-tab { background: linear-gradient(135deg, #cab8d9, #fff262) !important; color: #555 !important; border-color: transparent !important; }
    .msg-group { max-width: 85%; align-self: flex-start; border-bottom-left-radius: 4px; padding: 8px 12px; border-radius: 16px; font-size: 0.875rem; line-height: 1.5; white-space: pre-wrap; word-break: break-word; }
    .msg-name { font-size: 0.7rem; font-weight: 700; margin-bottom: 3px; }
    .interact-btn { font-size: 0.8rem; background: none; border: 1px solid #ddd; border-radius: 20px; padding: 5px 14px; cursor: pointer; color: #888; margin-top: 10px; }
    .interact-btn:hover { background: #f9f9f9; }
  </style>
</head>
<body>
  <div class="header">
    <h1><span class="char-dot" id="charDot"></span><span id="pageTitle">プチたち</span></h1>
    <div style="display:flex;gap:4px;">
      <button class="gear-btn" id="mailBtn" onclick="openMailbox()" title="メールボックス">📬</button>
      <button class="gear-btn" id="gearBtn" onclick="openSettings()">⚙️</button>
      <button class="gear-btn" id="logoutBtn" onclick="doLogout()" style="display:none" title="ログアウト">🚪</button>
    </div>
  </div>
  <div class="char-tabs" id="charTabs"></div>
  <div style="display:flex;justify-content:space-between;align-items:center;">
    <div class="updated" id="updated">読み込み中...</div>
    <div style="display:flex;align-items:center;gap:8px;">
      <div id="m5status"></div>
      <button id="sleepBtn" onclick="m5Sleep()" style="display:none;font-size:0.75rem;padding:3px 10px;border-radius:12px;border:1px solid #ddd;background:#f5f5f5;cursor:pointer;">😴 スリープ</button>
      <button id="wakeBtn"  onclick="m5Wake()"  style="display:none;font-size:0.75rem;padding:3px 10px;border-radius:12px;border:1px solid #ddd;background:#f5f5f5;cursor:pointer;">☀️ 起こす</button>
    </div>
  </div>

  <div id="groupStatusPanel" style="display:none;margin-bottom:16px;">
    <section>
      <h2>プチたちの状態</h2>
      <div id="groupCharStatus"></div>
    </section>
  </div>

  <div class="two-col" id="twoColLayout">
    <div class="main-col">
      <section id="desiresSection">
        <h2>欲求</h2>
        <div id="dominant"></div>
        <div id="desires"></div>
      </section>

      <section>
        <h2 id="chatTitle">話す</h2>
        <div class="chat-messages" id="chat"></div>
        <div class="chat-input">
          <input type="text" id="input" placeholder="話しかける..." />
          <button id="send">送信</button>
        </div>
        <div>
          <button class="sub-btn" onclick="openHistory()" id="historyBtn">最近した会話</button>
          <button class="reset-btn" onclick="resetSession()" id="resetBtn">リセット</button>
          <button class="interact-btn" id="interactBtn" onclick="startInteract()" style="display:none">✨ ふたりで話させる</button>
        </div>
      </section>

      <section id="memoriesSection">
        <h2 style="cursor:pointer;user-select:none" onclick="toggleMemories()">今日の記憶 <span id="memoriesCount"></span> <span id="memoriesToggle">▼</span></h2>
        <div id="memories" style="max-height:400px;overflow-y:auto"></div>
      </section>
    </div>

    <div class="diary-col" id="diaryCol">
      <div class="diary-panel">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
          <h3 style="margin:0">📖 日記</h3>
          <button class="diary-nav-btn" id="diaryDetailBtn" onclick="toggleDiaryDetail()">詳細</button>
        </div>
        <div class="diary-nav">
          <button class="diary-nav-btn" id="diaryPrev" onclick="diaryNav(-1)">◀</button>
          <span class="diary-date-label" id="diaryDateLabel">—</span>
          <button class="diary-nav-btn" id="diaryNext" onclick="diaryNav(+1)">▶</button>
        </div>
        <div id="diaryTodayBar" style="display:none;margin-bottom:6px"><button class="diary-nav-btn" style="font-size:0.7rem;width:100%" onclick="diaryGoToday()">↩ 今日に戻る</button></div>
        <div id="diaryContent"><div class="empty">読み込み中...</div></div>
      </div>
    </div>
  </div>

  <!-- 会話ポップアップ -->
  <div class="overlay" id="historyOverlay" onclick="closeIfOverlay(event,'historyOverlay')">
    <div class="popup">
      <div class="popup-header">
        <span class="popup-title">最近した会話</span>
        <button class="popup-close" onclick="closePopup('historyOverlay')">✕</button>
      </div>
      <div class="popup-body" id="historyBody"></div>
    </div>
  </div>

  <!-- 設定ポップアップ -->
  <div class="overlay" id="settingsOverlay" onclick="closeIfOverlay(event,'settingsOverlay')">
    <div class="popup">
      <div class="popup-header">
        <span class="popup-title">設定</span>
        <button class="popup-close" onclick="closePopup('settingsOverlay')">✕</button>
      </div>
      <div class="popup-body">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
          <span style="font-size:0.8rem;color:#9b8ec4;font-weight:600;" id="activeTimeLabel">アクティブタイム（毎回動く時間帯）</span>
          <span id="dayTypeLabel" style="font-size:0.75rem;padding:2px 8px;border-radius:8px;font-weight:600;"></span>
        </div>
        <div class="day-tabs">
          <button class="day-tab active" id="tabWeekday" onclick="switchDayTab('weekday')">平日</button>
          <button class="day-tab" id="tabWeekend" onclick="switchDayTab('weekend')">休日</button>
        </div>
        <div class="hours-list" id="hoursList"></div>
        <button class="add-hour-btn" onclick="addHourRow()">＋ 追加</button>
        <div style="margin-top:16px;">
          <div class="setting-row">
            <span class="setting-label">🕺 今日のスケジュール</span>
            <select id="dayTypeOverride" onchange="updateDayTypeLabel()" style="font-size:0.8rem;padding:4px 8px;border-radius:8px;border:1px solid #555;background:#2a2a3e;color:#ddd;">
              <option value="">自動（曜日通り）</option>
              <option value="weekday">平日扱い</option>
              <option value="weekend">休日扱い</option>
            </select>
          </div>
          <div class="setting-row">
            <span class="setting-label">📷 カメラ</span>
            <label class="toggle"><input type="checkbox" id="allowCamera"><span class="toggle-slider"></span></label>
          </div>
          <div class="setting-row">
            <span class="setting-label">🔊 音</span>
            <label class="toggle"><input type="checkbox" id="allowSound"><span class="toggle-slider"></span></label>
          </div>
          <div class="setting-row">
            <span class="setting-label">🎤 マイク</span>
            <label class="toggle"><input type="checkbox" id="allowMic"><span class="toggle-slider"></span></label>
          </div>
        </div>
        <div style="margin-top:16px;">
          <span style="font-size:0.8rem;color:#9b8ec4;font-weight:600;">M5 接続先（上から順に試す）</span>
          <div id="m5HostsList" style="margin-top:8px;"></div>
          <button class="add-hour-btn" onclick="addM5HostRow('')">＋ 追加</button>
        </div>
        <button class="save-settings-btn" onclick="saveSettings()">保存</button>
      </div>
    </div>
  </div>

  <!-- メールボックスポップアップ -->
  <div class="overlay" id="mailboxOverlay" onclick="closeIfOverlay(event,'mailboxOverlay')">
    <div class="popup">
      <div class="popup-header">
        <span class="popup-title">📬 メールボックス</span>
        <button class="popup-close" onclick="closePopup('mailboxOverlay')">✕</button>
      </div>
      <div class="popup-body">
        <div class="mailbox-tabs">
          <button class="mailbox-tab active" id="mailTabInbox" onclick="switchMailTab('inbox')">受信</button>
          <button class="mailbox-tab" id="mailTabStarred" onclick="switchMailTab('starred')">⭐</button>
          <button class="mailbox-tab" id="mailTabArchived" onclick="switchMailTab('archived')">📦</button>
        </div>
        <div id="mailboxBody"></div>
      </div>
    </div>
  </div>

  <!-- 記憶一覧ポップアップ -->
  <div class="overlay" id="memoriesOverlay" onclick="closeIfOverlay(event,'memoriesOverlay')">
    <div class="popup">
      <div class="popup-header">
        <span class="popup-title">記憶一覧</span>
        <button class="popup-close" onclick="closePopup('memoriesOverlay')">✕</button>
      </div>
      <div class="popup-body" id="memoriesBody"></div>
    </div>
  </div>

  <script>
    // labels と colors は desires.json から動的に取得（desire_config.json 由来）
    let DESIRE_LABELS = {};
    let DESIRE_COLORS = {};

    let currentCharId = "puchiko";
    let characters = [];
    const chatStates = {};
    let _memoryImages = {};
    let _diaryImages = {};
    let _popupImages = {};

    async function savePhoto(btn, idx, source) {
      const store = source === true ? _diaryImages : source === 'popup' ? _popupImages : _memoryImages;
      const imageData = store[idx];
      if (!imageData) return;
      btn.disabled = true;
      btn.textContent = "保存中…";
      try {
        const res = await fetch(`/api/${currentCharId}/photos/save`, {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({image_data: imageData})
        });
        if (res.ok) { btn.textContent = "✅"; }
        else { btn.textContent = "❌"; btn.disabled = false; }
      } catch { btn.textContent = "❌"; btn.disabled = false; }
    }

    function brightness(hex) {
      const r=parseInt(hex.slice(1,3),16),g=parseInt(hex.slice(3,5),16),b=parseInt(hex.slice(5,7),16);
      return (r*299+g*587+b*114)/1000;
    }
    function lighten(hex, f) {
      const r=parseInt(hex.slice(1,3),16),g=parseInt(hex.slice(3,5),16),b=parseInt(hex.slice(5,7),16);
      return `rgb(${Math.round(r+(255-r)*f)},${Math.round(g+(255-g)*f)},${Math.round(b+(255-b)*f)})`;
    }
    function darken(hex, f) {
      const r=parseInt(hex.slice(1,3),16),g=parseInt(hex.slice(3,5),16),b=parseInt(hex.slice(5,7),16);
      return `rgb(${Math.round(r*(1-f))},${Math.round(g*(1-f))},${Math.round(b*(1-f))})`;
    }
    function readableText(hex) {
      return brightness(hex) > 160 ? darken(hex, 0.42) : hex;
    }
    function btnTextColor(hex) {
      return brightness(hex) > 160 ? darken(hex, 0.45) : "white";
    }

    function applyTheme(color) {
      const r = document.documentElement;
      r.style.setProperty("--char", color);
      r.style.setProperty("--char-dark", readableText(color));
      r.style.setProperty("--char-mid", darken(color, brightness(color)>160 ? 0.28 : 0.1));
      r.style.setProperty("--char-bg", lighten(color, 0.92));
      r.style.setProperty("--char-soft", lighten(color, 0.86));
      r.style.setProperty("--char-border", lighten(color, 0.72));
      r.style.setProperty("--char-btn-text", btnTextColor(color));
      document.getElementById("charDot").style.background = color;
    }

    async function loadCharacters() {
      const res = await fetch("/api/characters");
      characters = await res.json();
      const tabs = document.getElementById("charTabs");
      tabs.innerHTML = characters.map(c => {
        const isActive = c.id === currentCharId;
        const col = c.color || "#cab8d9";
        const activeTxt = btnTextColor(col);
        const inactiveTxt = readableText(col);
        return `<button class="char-tab${isActive?" active":""}" data-char-id="${c.id}"
          style="${isActive
            ? `background:${col};border-color:${col};color:${activeTxt}`
            : `border-color:${col};color:${inactiveTxt};background:white`}"
          onclick="switchChar('${c.id}')">
          <span class="m5-dot" style="display:inline-block;width:7px;height:7px;border-radius:50%;background:#ccc;vertical-align:middle;margin-right:4px;"></span>${c.name||c.id}</button>`;
      }).join("");
      // 「みんなで」タブを末尾に追加
      const isGroup = currentCharId === "group";
      tabs.innerHTML += `<button class="char-tab group-tab${isGroup?" active":""}"
        style="${isGroup?"opacity:1":"opacity:0.8"}"
        onclick="switchChar('group')">みんなで 🌟</button>`;
      tabs.innerHTML += `<a href="/kankei" style="text-decoration:none;font-size:1.1rem;padding:4px 8px;opacity:0.5" title="ひみつ">🔒</a>`;

      const cur = characters.find(c=>c.id===currentCharId);
      if (cur) {
        applyTheme(cur.color || "#cab8d9");
        document.getElementById("pageTitle").textContent = cur.name||cur.id;
        document.getElementById("chatTitle").textContent = `${cur.name||cur.id}と話す`;
        document.getElementById("interactBtn").style.display = "none";
        document.getElementById("historyBtn").style.display = "";
        document.getElementById("resetBtn").style.display = "";
      } else if (isGroup) {
        applyTheme("#cab8d9");
        document.getElementById("pageTitle").textContent = "みんな";
        document.getElementById("chatTitle").textContent = "みんなで話す";
        document.getElementById("interactBtn").style.display = "";
        document.getElementById("historyBtn").style.display = "";
        document.getElementById("resetBtn").style.display = "none";
      }
    }

    function switchChar(id) {
      const chatEl = document.getElementById("chat");
      chatStates[currentCharId] = chatEl.innerHTML;
      currentCharId = id;
      chatEl.innerHTML = chatStates[id] || "";
      loadCharacters();
      const isGroup = id === "group";
      document.getElementById("gearBtn").style.display = isGroup ? "none" : "";
      document.getElementById("sleepBtn").style.display = "none";
      document.getElementById("wakeBtn").style.display = "none";
      document.getElementById("m5status").innerHTML = "";
      document.getElementById("twoColLayout").style.display = isGroup ? "block" : "";
      document.getElementById("diaryCol").style.display = isGroup ? "none" : "";
      document.getElementById("desiresSection").style.display = isGroup ? "none" : "";
      document.getElementById("memoriesSection").style.display = isGroup ? "none" : "";
      document.getElementById("groupStatusPanel").style.display = isGroup ? "" : "none";
      if (!isGroup) { update(); updateDiary(); }
      else {
        document.getElementById("updated").textContent = "";
        document.getElementById("diaryContent").innerHTML = "";
        updateGroupStatus();
      }
    }

    async function updateGroupStatus() {
      const panel = document.getElementById("groupCharStatus");
      if (!characters.length) { panel.innerHTML = '<div class="empty">読み込み中...</div>'; return; }
      panel.innerHTML = '<div class="empty">確認中...</div>';
      const rows = await Promise.all(characters.map(async c => {
        try {
          const res = await fetch(`/api/${c.id}/status`);
          const { m5_online } = await res.json();
          const color = c.color || "#cab8d9";
          return `<div style="display:flex;align-items:center;gap:10px;padding:8px 0;border-bottom:1px solid #f0f0f0;">
            <span style="width:10px;height:10px;border-radius:50%;background:${color};display:inline-block;flex-shrink:0;"></span>
            <span style="font-weight:700;flex:1;color:${readableText(color)};">${c.name||c.id}</span>
            <span style="font-size:0.75rem;color:${m5_online?'#4caf50':'#f44336'};">${m5_online?'● M5 接続済':'● M5 未接続'}</span>
          </div>`;
        } catch {
          return `<div style="padding:8px 0;">${c.name||c.id} — 確認失敗</div>`;
        }
      }));
      panel.innerHTML = rows.join("");
    }

    async function update() {
      if (currentCharId === "group") return;
      try {
        const res = await fetch(`/api/${currentCharId}/status`);
        const { desires, memories, m5_online, m5_sleeping } = await res.json();

        // M5オンライン状態をタブに反映
        const tabs = document.querySelectorAll(".char-tab");
        tabs.forEach(tab => {
          if (tab.dataset.charId === currentCharId) {
            const dot = tab.querySelector(".m5-dot");
            if (dot) dot.style.background = m5_online ? "#4caf50" : "#f44336";
          }
        });
        // ステータス表示
        const m5El = document.getElementById("m5status");
        if (m5El) m5El.innerHTML = m5_online
          ? `<span style="color:#4caf50;font-size:0.75rem">● M5 接続済</span>`
          : `<span style="color:#f44336;font-size:0.75rem">● M5 未接続（会話のみ）</span>`;
        document.getElementById("sleepBtn").style.display = (m5_online && !m5_sleeping) ? "" : "none";
        document.getElementById("wakeBtn").style.display  = (m5_online && m5_sleeping)  ? "" : "none";

        // desires.json の labels/colors を動的に取得
        if (desires.labels) DESIRE_LABELS = desires.labels;
        if (desires.colors) DESIRE_COLORS = desires.colors;

        if (desires.updated_at) {
          document.getElementById("updated").textContent = "更新: " + new Date(desires.updated_at).toLocaleString("ja-JP");
        }
        const domEl = document.getElementById("dominant");
        if (desires.dominant) {
          domEl.innerHTML = `<span class="dominant">いちばん強い欲求: ${DESIRE_LABELS[desires.dominant]||desires.dominant}</span>`;
        }
        const desEl = document.getElementById("desires");
        if (desires.desires && Object.keys(desires.desires).length > 0) {
          desEl.innerHTML = Object.entries(desires.desires).sort((a,b)=>b[1]-a[1]).map(([k,v])=>{
            const pct = Math.round(v*100);
            return `<div class="desire"><div class="desire-label"><span>${DESIRE_LABELS[k]||k}</span><span class="desire-level">${pct}%</span></div><div class="bar-bg"><div class="bar-fill" style="width:${pct}%;background:${DESIRE_COLORS[k]||'#cab8d9'}"></div></div></div>`;
          }).join("");
        } else { desEl.innerHTML = '<div class="empty">データなし</div>'; }

        const memEl = document.getElementById("memories");
        const memCount = document.getElementById("memoriesCount");
        if (memories.length > 0) {
          memCount.textContent = `(${memories.length}件)`;
          _memoryImages = {};
          memEl.innerHTML = memories.map((m, i) => {
            const ts = m.metadata?.timestamp ? new Date(m.metadata.timestamp).toLocaleTimeString("ja-JP", {hour:"2-digit",minute:"2-digit"}) : "";
            let imgRow = "";
            if (m.metadata?.image_data) {
              _memoryImages[i] = m.metadata.image_data;
              imgRow = `<div class="memory-img-row"><img class="memory-thumb" src="data:image/jpeg;base64,${m.metadata.image_data}" onclick="window.open(this.src,'_blank')"><button class="photo-save-btn" onclick="savePhoto(this,${i})">💾</button></div>`;
            }
            return `<div class="memory"><div class="memory-time">${ts}</div><div class="memory-text">${m.content}</div>${imgRow}</div>`;
          }).join("");
        } else { memCount.textContent = ""; memEl.innerHTML = '<div class="empty">今日はまだ記憶がありません</div>'; }

        // 日記パネル更新
        updateDiary();
      } catch(e) { document.getElementById("updated").textContent = "取得失敗"; }
    }

    function addMsg(text, role, color, name) {
      const chat = document.getElementById("chat");
      if (role === "group") {
        // グループメッセージ：名前＋色付きバブル
        const div = document.createElement("div");
        div.className = "msg-group";
        div.style.background = lighten(color || "#cab8d9", 0.84);
        if (name) {
          const nameEl = document.createElement("div");
          nameEl.className = "msg-name";
          nameEl.style.color = readableText(color || "#cab8d9");
          nameEl.textContent = name;
          div.appendChild(nameEl);
        }
        const textEl = document.createElement("div");
        textEl.textContent = text;
        div.appendChild(textEl);
        chat.appendChild(div);
        chat.scrollTop = chat.scrollHeight;
        return div;
      }
      const div = document.createElement("div");
      div.className = "msg " + role;
      div.textContent = text;
      chat.appendChild(div);
      chat.scrollTop = chat.scrollHeight;
      return div;
    }

    async function send() {
      const input = document.getElementById("input");
      const btn = document.getElementById("send");
      const text = input.value.trim();
      if (!text) return;
      input.value = "";
      btn.disabled = true;
      addMsg(text, "user");

      if (currentCharId === "group") {
        const thinking = addMsg("みんなに聞いてる…", "thinking");
        try {
          const res = await fetch("/api/group/chat", { method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({message:text}) });
          const data = await res.json();
          thinking.remove();
          for (const r of data.responses) {
            addMsg(r.reply, "group", r.color, r.name);
          }
        } catch(e) { thinking.textContent = "エラーが発生しました"; }
        finally { btn.disabled = false; input.focus(); }
      } else {
        const thinking = addMsg("考え中…", "thinking");
        try {
          const res = await fetch(`/api/${currentCharId}/chat`, { method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({message:text}) });
          const data = await res.json();
          thinking.remove();
          addMsg(data.reply, "char");
          update();
        } catch(e) { thinking.textContent = "エラーが発生しました"; }
        finally { btn.disabled = false; input.focus(); }
      }
    }

    async function startInteract() {
      if (characters.length < 2) { alert("キャラが2人必要です"); return; }
      const btn = document.getElementById("interactBtn");
      btn.disabled = true;
      btn.textContent = "話し合い中…";
      const [a, b] = characters;
      try {
        const res = await fetch("/api/interact", {
          method: "POST", headers:{"Content-Type":"application/json"},
          body: JSON.stringify({from_id: a.id, to_id: b.id, turns: 3})
        });
        const data = await res.json();
        for (const ex of data.exchanges) {
          const char = characters.find(c=>c.id===ex.from_id);
          addMsg(ex.text, "group", ex.color, ex.name);
          await new Promise(r=>setTimeout(r, 400)); // 少し間を置く
        }
      } catch(e) { addMsg("エラーが発生しました", "thinking"); }
      finally { btn.disabled = false; btn.textContent = "✨ ふたりで話させる"; }
    }

    let _diaryDates = [];
    let _diaryIdx = 0;
    let _diaryShowDetail = false;
    let _diaryCache = {};  // date -> {summary, memories}

    function renderDiaryPage() {
      const diaryEl = document.getElementById("diaryContent");
      const labelEl = document.getElementById("diaryDateLabel");
      if (_diaryDates.length === 0) {
        diaryEl.innerHTML = '<div class="empty">まだ記憶がありません</div>';
        labelEl.textContent = "—";
        return;
      }
      const date = _diaryDates[_diaryIdx];
      labelEl.textContent = date;
      document.getElementById("diaryPrev").disabled = _diaryIdx >= _diaryDates.length - 1;
      document.getElementById("diaryNext").disabled = _diaryIdx <= 0;
      document.getElementById("diaryTodayBar").style.display = _diaryIdx === 0 ? "none" : "block";
      loadDiaryDate(date);
    }

    async function loadDiaryDate(date) {
      const diaryEl = document.getElementById("diaryContent");
      if (_diaryCache[date]) {
        renderDiaryContent(_diaryCache[date]);
        return;
      }
      diaryEl.innerHTML = '<div class="empty">読み込み中...</div>';
      try {
        const res = await fetch(`/api/${currentCharId}/diary/${date}`);
        _diaryCache[date] = await res.json();
        renderDiaryContent(_diaryCache[date]);
      } catch(e) { diaryEl.innerHTML = '<div class="empty">取得失敗</div>'; }
    }

    const _today = new Date().toLocaleDateString("sv-SE");

    function renderDiaryContent(data) {
      const diaryEl = document.getElementById("diaryContent");
      if (_diaryShowDetail) {
        _diaryImages = {};
        const items = (data.memories || []).map((m, i) => {
          const t = m.metadata?.timestamp ? new Date(m.metadata.timestamp).toLocaleTimeString("ja-JP", {hour:"2-digit",minute:"2-digit"}) : "";
          let imgRow = "";
          if (m.metadata?.image_data) {
            _diaryImages[i] = m.metadata.image_data;
            imgRow = `<div class="memory-img-row"><img class="memory-thumb" src="data:image/jpeg;base64,${m.metadata.image_data}" onclick="window.open(this.src,'_blank')"><button class="photo-save-btn" onclick="savePhoto(this,${i},true)">💾</button></div>`;
          }
          return `<div class="diary-entry"><div class="diary-time">${t}</div><div class="diary-summary expanded">${m.content}</div>${imgRow}</div>`;
        }).join("") || '<div class="empty">記憶なし</div>';
        diaryEl.innerHTML = items;
      } else if (data.summary) {
        const regen = data.date === _today && data.count > 0
          ? `<button class="diary-nav-btn" style="width:100%;margin-top:8px" onclick="generateTodaySummary()">📝 再生成</button>` : "";
        diaryEl.innerHTML = `<div style="font-size:0.85rem;line-height:1.7;color:#333">${data.summary}</div>
          <div style="font-size:0.7rem;color:#bbb;margin-top:6px">${data.count}件の記憶</div>${regen}`;
      } else if (data.date === _today) {
        // 今日はボタンで手動生成
        const countText = data.count > 0 ? `${data.count}件の記憶` : "まだ記憶がありません";
        diaryEl.innerHTML = `<div style="font-size:0.75rem;color:#aaa;margin-bottom:8px">${countText}</div>`
          + (data.count > 0 ? `<button class="diary-nav-btn" style="width:100%" onclick="generateTodaySummary()">📝 サマリーを生成</button>` : "");
      } else {
        diaryEl.innerHTML = '<div class="empty">記憶なし</div>';
      }
    }

    async function generateTodaySummary() {
      const diaryEl = document.getElementById("diaryContent");
      diaryEl.innerHTML = '<div class="empty">生成中...</div>';
      try {
        const res = await fetch(`/api/${currentCharId}/diary/${_today}/summarize`, {method:"POST"});
        const {summary} = await res.json();
        _diaryCache[_today] = {...(_diaryCache[_today]||{}), summary};
        renderDiaryContent(_diaryCache[_today]);
      } catch(e) { diaryEl.innerHTML = '<div class="empty">生成失敗</div>'; }
    }

    function diaryNav(dir) {
      _diaryIdx = Math.max(0, Math.min(_diaryDates.length - 1, _diaryIdx - dir));
      _diaryShowDetail = false;
      renderDiaryPage();
    }

    function diaryGoToday() {
      _diaryIdx = 0;  // 日付は降順なので0が最新（今日）
      _diaryShowDetail = false;
      renderDiaryPage();
    }

    function toggleDiaryDetail() {
      _diaryShowDetail = !_diaryShowDetail;
      const btn = document.getElementById("diaryDetailBtn");
      btn.textContent = _diaryShowDetail ? "サマリー" : "詳細";
      if (_diaryDates.length > 0) renderDiaryContent(_diaryCache[_diaryDates[_diaryIdx]] || {});
    }

    async function updateDiary(resetToToday = false) {
      if (currentCharId === "group") return;
      const prevDate = _diaryDates.length > 0 ? _diaryDates[_diaryIdx] : null;
      _diaryCache = {};
      try {
        const res = await fetch(`/api/${currentCharId}/memories/all`);
        const byDate = await res.json();
        _diaryDates = Object.keys(byDate).sort().reverse();
        if (resetToToday || !prevDate) {
          _diaryIdx = 0;
          _diaryShowDetail = false;
        } else {
          // 以前見ていた日付を維持
          const found = _diaryDates.indexOf(prevDate);
          _diaryIdx = found >= 0 ? found : 0;
        }
        renderDiaryPage();
      } catch(e) {}
    }

    async function m5Sleep() {
      document.getElementById("sleepBtn").style.display = "none";
      document.getElementById("wakeBtn").style.display = "";
      await fetch(`/api/${currentCharId}/m5/sleep`, {method:"POST"});
    }

    async function m5Wake() {
      document.getElementById("wakeBtn").style.display = "none";
      document.getElementById("sleepBtn").style.display = "";
      await fetch(`/api/${currentCharId}/m5/wake`, {method:"POST"});
    }

    async function resetSession() {
      await fetch(`/api/${currentCharId}/chat/session`, {method:"DELETE"});
      document.getElementById("chat").innerHTML = "";
      chatStates[currentCharId] = "";
    }

    async function openHistory() {
      const body = document.getElementById("historyBody");
      body.innerHTML = '<div class="empty">読み込み中…</div>';
      document.getElementById("historyOverlay").classList.add("open");

      if (currentCharId === "group") {
        const res = await fetch("/api/group/history");
        const log = await res.json();
        if (log.length === 0) {
          body.innerHTML = '<div class="empty">まだ会話がありません</div>';
        } else {
          body.innerHTML = log.map(m => {
            const ts = new Date(m.timestamp).toLocaleString("ja-JP");
            const col = m.color || "#cab8d9";
            const nameColor = readableText(col);
            const typeLabel = m.type === "interact" ? "💬 交流" : "🌟 みんなで";
            return `<div class="history-msg">
              <div class="history-role" style="color:${nameColor}">${m.name} · ${ts} <span style="color:#ccc;font-size:0.65rem">${typeLabel}</span></div>
              <div class="history-text">${m.text}</div>
            </div>`;
          }).join("");
        }
      } else {
        const res = await fetch(`/api/${currentCharId}/chat/history`);
        const log = await res.json();
        const cur = characters.find(c=>c.id===currentCharId);
        const charName = cur ? (cur.name||cur.id) : currentCharId;
        if (log.length === 0) {
          body.innerHTML = '<div class="empty">まだ会話がありません</div>';
        } else {
          body.innerHTML = log.map(m => {
            const role = m.role === "user" ? "ありさん" : charName;
            const ts = new Date(m.timestamp).toLocaleString("ja-JP");
            return `<div class="history-msg"><div class="history-role">${role} · ${ts}</div><div class="history-text">${m.text}</div></div>`;
          }).join("");
        }
      }
    }

    async function openMemories() {
      const res = await fetch(`/api/${currentCharId}/memories/all`);
      const byDate = await res.json();
      const body = document.getElementById("memoriesBody");
      const dates = Object.keys(byDate).sort((a,b)=>b.localeCompare(a));
      if (dates.length === 0) {
        body.innerHTML = '<div class="empty">まだ記憶がありません</div>';
      } else {
        _popupImages = {};
        let imgIdx = 0;
        body.innerHTML = dates.map(date => {
          const items = byDate[date];
          const rows = items.map(m => {
            const ts = m.metadata?.timestamp ? new Date(m.metadata.timestamp).toLocaleTimeString("ja-JP") : "";
            let imgRow = "";
            if (m.metadata?.image_data) {
              const idx = imgIdx++;
              _popupImages[idx] = m.metadata.image_data;
              imgRow = `<div class="memory-img-row"><img class="memory-thumb" src="data:image/jpeg;base64,${m.metadata.image_data}" onclick="window.open(this.src,'_blank')"><button class="photo-save-btn" onclick="savePhoto(this,${idx},'popup')">💾</button></div>`;
            }
            return `<div class="mem-item"><div class="mem-time">${ts}</div><div class="mem-text">${m.content}</div>${imgRow}</div>`;
          }).join("");
          return `<div class="date-group"><div class="date-label">${date}</div>${rows}</div>`;
        }).join("");
      }
      document.getElementById("memoriesOverlay").classList.add("open");
    }

    function closePopup(id) { document.getElementById(id).classList.remove("open"); }
    function toggleMemories() {
      const el = document.getElementById("memories");
      const toggle = document.getElementById("memoriesToggle");
      const isHidden = el.style.maxHeight === "0px";
      if (isHidden) { el.style.maxHeight = "400px"; el.style.overflow = "auto"; toggle.textContent = "▼"; }
      else { el.style.maxHeight = "0px"; el.style.overflow = "hidden"; toggle.textContent = "▶"; }
    }
    function closeIfOverlay(e, id) { if (e.target === e.currentTarget) closePopup(id); }

    let currentSchedule = { weekday: [], weekend: [] };
    let currentDayTab = "weekday";

    function updateDayTypeLabel() {
      const dow = new Date().getDay(); // 0=日,6=土
      const override = document.getElementById("dayTypeOverride").value;
      let isWeekend;
      if (override === "weekday") isWeekend = false;
      else if (override === "weekend") isWeekend = true;
      else isWeekend = (dow === 0 || dow === 6);
      const lbl = document.getElementById("dayTypeLabel");
      if (isWeekend) {
        lbl.textContent = "🏖 今日: 休日スケジュール";
        lbl.style.background = "#2d1f4e"; lbl.style.color = "#c4a8ff";
      } else {
        lbl.textContent = "📅 今日: 平日スケジュール";
        lbl.style.background = "#1f2d4e"; lbl.style.color = "#a8c4ff";
      }
    }

    function switchDayTab(tab) {
      currentDayTab = tab;
      document.getElementById("tabWeekday").classList.toggle("active", tab === "weekday");
      document.getElementById("tabWeekend").classList.toggle("active", tab === "weekend");
      renderHours();
    }

    function makeHourOpts(sel, max) {
      let o = "";
      for (let h = 0; h <= max; h++) o += `<option value="${h}" ${h===sel?"selected":""}>${String(h).padStart(2,"0")}</option>`;
      return o;
    }
    function makeMinOpts(sel) {
      let o = "";
      for (let m = 0; m < 60; m += 10) o += `<option value="${m}" ${m===sel?"selected":""}>${String(m).padStart(2,"0")}</option>`;
      return o;
    }
    function renderHours() {
      const hours = currentSchedule[currentDayTab];
      const list = document.getElementById("hoursList");
      list.innerHTML = hours.map((h, i) => {
        const sh = h[0], sm = h[1], eh = h[2], em = h[3];
        return `<div class="hour-row">
          <div class="time-group">
            <select onchange="currentSchedule[currentDayTab][${i}][0]=+this.value">${makeHourOpts(sh,23)}</select>
            <span>:</span>
            <select onchange="currentSchedule[currentDayTab][${i}][1]=+this.value">${makeMinOpts(sm)}</select>
          </div>
          <span>〜</span>
          <div class="time-group">
            <select onchange="currentSchedule[currentDayTab][${i}][2]=+this.value">${makeHourOpts(eh,24)}</select>
            <span>:</span>
            <select onchange="currentSchedule[currentDayTab][${i}][3]=+this.value">${makeMinOpts(em)}</select>
          </div>
          <button class="hour-del" onclick="removeHour(${i})">✕</button>
        </div>`;
      }).join("");
    }

    function addHourRow() { currentSchedule[currentDayTab].push([8, 0, 12, 0]); renderHours(); }
    function removeHour(i) { currentSchedule[currentDayTab].splice(i, 1); renderHours(); }

    let currentMailTab = "inbox";

    function openMailbox() {
      currentMailTab = "inbox";
      document.querySelectorAll(".mailbox-tab").forEach(t => t.classList.remove("active"));
      document.getElementById("mailTabInbox").classList.add("active");
      document.getElementById("mailboxOverlay").classList.add("open");
      loadMailbox();
    }

    function switchMailTab(filter) {
      currentMailTab = filter;
      document.querySelectorAll(".mailbox-tab").forEach(t => t.classList.remove("active"));
      const tabId = {inbox:"mailTabInbox", starred:"mailTabStarred", archived:"mailTabArchived"}[filter];
      document.getElementById(tabId).classList.add("active");
      loadMailbox();
    }

    async function loadMailbox() {
      const body = document.getElementById("mailboxBody");
      body.innerHTML = "<div class='empty'>読み込み中...</div>";
      try {
        const res = await fetch(`/api/mailbox?filter=${currentMailTab}`);
        const mails = await res.json();
        if (!mails.length) {
          const labels = {inbox:"メールはありません", starred:"スター付きメールはありません", archived:"アーカイブはありません"};
          body.innerHTML = `<div class='empty'>${labels[currentMailTab] || "メールはありません"}</div>`;
          return;
        }
        body.innerHTML = mails.map((m, i) => {
          const bodyText = m.content.replace(/</g,"&lt;").replace(/>/g,"&gt;");
          const starCls = m.starred ? "active" : "";
          const archiveIcon = m.archived ? "📤" : "📥";
          const archiveTitle = m.archived ? "受信に戻す" : "アーカイブ";
          return `<div class="mail-item" id="mail-${i}">
            <div class="mail-header">
              <span class="mail-sender">${m.sender.replace(/</g,"&lt;")}</span>
              <div class="mail-actions">
                <button class="mail-action-btn ${starCls}" title="スター" onclick="toggleStar('${m.filename}',${i})">⭐</button>
                <button class="mail-action-btn" title="${archiveTitle}" onclick="toggleArchive('${m.filename}',${!m.archived},${i})">${archiveIcon}</button>
              </div>
            </div>
            <div style="font-size:0.7rem;color:#aaa;margin-bottom:4px;">${m.date}</div>
            <div class="mail-body">${bodyText}</div>
          </div>`;
        }).join("");
      } catch(e) {
        body.innerHTML = "<div class='empty'>読み込みに失敗しました</div>";
      }
    }

    async function toggleStar(filename, index) {
      const btn = document.querySelector(`#mail-${index} .mail-action-btn`);
      const isActive = btn.classList.contains("active");
      try {
        await fetch(`/api/mailbox/${encodeURIComponent(filename)}/meta`, {
          method: "PATCH",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({starred: !isActive})
        });
        if (currentMailTab === "starred") { loadMailbox(); }
        else { btn.classList.toggle("active"); }
      } catch(e) {}
    }

    async function toggleArchive(filename, archive, index) {
      try {
        await fetch(`/api/mailbox/${encodeURIComponent(filename)}/meta`, {
          method: "PATCH",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({archived: archive})
        });
        loadMailbox();
      } catch(e) {}
    }

    function renderM5Hosts(hosts) {
      const el = document.getElementById("m5HostsList");
      el.innerHTML = hosts.map((h, i) => `<div style="display:flex;gap:6px;align-items:center;margin-bottom:6px;">
        <input type="text" class="m5-host-input" value="${h}" placeholder="IP or hostname" style="flex:1;font-size:0.85rem;padding:6px 10px;border-radius:8px;border:1px solid #555;background:#2a2a3e;color:#ddd;">
        <button onclick="this.parentElement.remove()" style="background:none;border:none;color:#f44336;font-size:1rem;cursor:pointer;">✕</button>
      </div>`).join("");
    }
    function addM5HostRow(val) {
      const el = document.getElementById("m5HostsList");
      const row = document.createElement("div");
      row.style.cssText = "display:flex;gap:6px;align-items:center;margin-bottom:6px;";
      row.innerHTML = `<input type="text" class="m5-host-input" value="${val||''}" placeholder="IP or hostname" style="flex:1;font-size:0.85rem;padding:6px 10px;border-radius:8px;border:1px solid #555;background:#2a2a3e;color:#ddd;">
        <button onclick="this.parentElement.remove()" style="background:none;border:none;color:#f44336;font-size:1rem;cursor:pointer;">✕</button>`;
      el.appendChild(row);
      row.querySelector("input").focus();
    }
    function getM5Hosts() {
      return [...document.querySelectorAll(".m5-host-input")].map(el => el.value.trim()).filter(Boolean);
    }

    async function openSettings() {
      const [res, m5Res] = await Promise.all([
        fetch(`/api/${currentCharId}/settings`),
        fetch(`/api/${currentCharId}/config/m5_hosts`),
      ]);
      const s = await res.json();
      const m5 = await m5Res.json();
      const ah = s.active_hours || {};
      currentSchedule = {
        weekday: JSON.parse(JSON.stringify(ah.weekday || [])),
        weekend: JSON.parse(JSON.stringify(ah.weekend || [])),
      };
      currentDayTab = "weekday";
      document.getElementById("tabWeekday").classList.add("active");
      document.getElementById("tabWeekend").classList.remove("active");
      const cur = characters.find(c=>c.id===currentCharId);
      const charName = cur ? (cur.name||cur.id) : currentCharId;
      document.getElementById("activeTimeLabel").textContent = `${charName}のアクティブタイム（毎回動く時間帯）`;
      renderHours();
      document.getElementById("dayTypeOverride").value = s.day_type_override ?? "";
      document.getElementById("allowCamera").checked = s.allow_camera ?? true;
      document.getElementById("allowSound").checked = s.allow_sound ?? true;
      document.getElementById("allowMic").checked = s.allow_microphone ?? false;
      renderM5Hosts(m5.m5_hosts || []);
      updateDayTypeLabel();
      document.getElementById("settingsOverlay").classList.add("open");
    }

    async function saveSettings() {
      const data = {
        active_hours: currentSchedule,
        day_type_override: document.getElementById("dayTypeOverride").value || null,
        allow_camera: document.getElementById("allowCamera").checked,
        allow_sound: document.getElementById("allowSound").checked,
        allow_microphone: document.getElementById("allowMic").checked,
      };
      await Promise.all([
        fetch(`/api/${currentCharId}/settings`, { method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(data) }),
        fetch(`/api/${currentCharId}/config/m5_hosts`, { method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({m5_hosts: getM5Hosts()}) }),
      ]);
      closePopup("settingsOverlay");
    }

    async function doLogout() {
      await fetch("/api/auth/logout", {method:"POST"});
      location.reload();
    }

    async function checkAuth() {
      try {
        const res = await fetch("/api/auth/me");
        const data = await res.json();
        if (data.auth_enabled && data.authenticated) {
          document.getElementById("logoutBtn").style.display = "";
        }
      } catch {}
    }

    document.getElementById("send").addEventListener("click", send);
    document.getElementById("input").addEventListener("keydown", e => { if (e.key==="Enter"&&!e.shiftKey){e.preventDefault();send();} });

    checkAuth();
    loadCharacters();
    update();
    setInterval(update, 30000);
  </script>
</body>
</html>
"""


KANKEI_HTML = """<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>秘密の相関図</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: -apple-system, sans-serif; background: #1a1a2e; color: #e0e0e0; min-height: 100vh; }
    .top-bar { display: flex; align-items: center; justify-content: center; gap: 16px; padding: 16px 20px 0; }
    .top-bar h1 { font-size: 1.2rem; color: white; }
    .back-btn { background: #16213e; border: 1px solid #0f3460; color: #e0e0e0; padding: 6px 14px; border-radius: 8px; cursor: pointer; font-size: 0.85rem; text-decoration: none; }
    .back-btn:hover { background: #0f3460; }
    .chart-container { display: flex; justify-content: center; padding: 20px; }
    svg { max-width: 700px; width: 100%; height: auto; }
    .tooltip {
      position: fixed; background: #16213e; border: 1px solid #0f3460; border-radius: 8px;
      padding: 10px 14px; font-size: 0.85rem; pointer-events: none; opacity: 0;
      transition: opacity 0.2s; z-index: 100; max-width: 260px; color: #e0e0e0;
      box-shadow: 0 4px 12px rgba(0,0,0,0.4);
    }
    .tooltip .feeling { margin-bottom: 6px; line-height: 1.4; }
    .tooltip .gauge-bar { background: #2a2a4a; border-radius: 4px; height: 8px; overflow: hidden; }
    .tooltip .gauge-fill { height: 100%; border-radius: 4px; transition: width 0.3s; }
    .tooltip .gauge-label { font-size: 0.75rem; color: #888; margin-top: 2px; }
    .mail-section { max-width: 640px; margin: 0 auto; padding: 20px 20px 30px; }
    .mail-section h2 { font-size: 1rem; color: #e0e0e0; margin-bottom: 12px; }
    .mail-thread { display: flex; flex-direction: column; gap: 10px; max-height: 600px; overflow-y: auto; padding-right: 4px; }
    .mail-thread::-webkit-scrollbar { width: 6px; }
    .mail-thread::-webkit-scrollbar-thumb { background: #333; border-radius: 3px; }
    .mail-thread::-webkit-scrollbar-track { background: transparent; }
    .mail-bubble {
      max-width: 80%; padding: 10px 14px; border-radius: 12px; font-size: 0.85rem;
      line-height: 1.5; white-space: pre-wrap; position: relative;
      box-shadow: 0 2px 6px rgba(0,0,0,0.3);
    }
    .mail-bubble.left { align-self: flex-start; background: #16213e; border: 1px solid #0f3460; }
    .mail-bubble.right { align-self: flex-end; background: #2a1a3e; border: 1px solid #4a2a6e; }
    .mail-meta { font-size: 0.7rem; color: #888; margin-top: 4px; }
    .mail-sender { font-size: 0.75rem; font-weight: 600; margin-bottom: 4px; }
    .mail-empty { color: #666; font-size: 0.85rem; text-align: center; padding: 20px; }
    .cards { display: flex; flex-wrap: wrap; gap: 16px; justify-content: center; padding: 0 20px 30px; }
    .card {
      background: #16213e; border-radius: 12px; padding: 16px; width: 260px;
      box-shadow: 0 2px 8px rgba(0,0,0,0.3); border-top: 3px solid #cab8d9;
    }
    .card h3 { font-size: 1rem; margin-bottom: 8px; display: flex; align-items: center; gap: 8px; }
    .card .avatar-small { width: 28px; height: 28px; border-radius: 50%; }
    .card .likes { font-size: 0.8rem; color: #aaa; margin-bottom: 4px; }
    .card .notes { font-size: 0.85rem; color: #ccc; font-style: italic; }
    .detail-overlay {
      position: fixed; inset: 0; background: rgba(0,0,0,0.6); z-index: 200;
      display: none; align-items: center; justify-content: center; padding: 20px;
    }
    .detail-overlay.open { display: flex; }
    .detail-panel {
      background: #16213e; border-radius: 14px; padding: 20px; max-width: 360px; width: 100%;
      box-shadow: 0 8px 30px rgba(0,0,0,0.5);
    }
    .detail-panel .header { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
    .detail-panel .header img { width: 48px; height: 48px; border-radius: 50%; background: white; }
    .detail-panel .header h2 { font-size: 1.1rem; color: white; }
    .detail-panel .rel-item { margin-bottom: 14px; }
    .detail-panel .rel-target { font-size: 0.9rem; color: #ccc; margin-bottom: 2px; }
    .detail-panel .rel-feeling { font-size: 1rem; color: #e0e0e0; margin-bottom: 6px; line-height: 1.5; }
    .detail-panel .rel-gauge { background: #2a2a4a; border-radius: 6px; height: 10px; overflow: hidden; }
    .detail-panel .rel-gauge-fill { height: 100%; border-radius: 6px; }
    .detail-panel .rel-gauge-label { font-size: 0.8rem; color: #888; margin-top: 2px; }
    .detail-panel .close-btn {
      display: block; margin: 12px auto 0; background: #0f3460; border: none; color: white;
      padding: 8px 24px; border-radius: 8px; cursor: pointer; font-size: 0.9rem;
    }
  </style>
</head>
<body>
  <div class="top-bar">
    <a href="/" class="back-btn">← もどる</a>
    <h1>🔒 秘密のそうかんず</h1>
  </div>
  <div class="chart-container"><svg id="chart" viewBox="0 0 700 700"></svg></div>
  <div class="tooltip" id="tip"></div>
  <div class="detail-overlay" id="detailOverlay" onclick="if(event.target===this)this.classList.remove('open')">
    <div class="detail-panel" id="detailPanel"></div>
  </div>
  <div class="cards" id="cards"></div>
  <div class="mail-section">
    <h2>📮 おてがみ</h2>
    <div id="mailThread" class="mail-thread"></div>
  </div>
  <script>
    const SVG_NS = "http://www.w3.org/2000/svg";
    const CX = 350, CY = 350, RADIUS = 220, NODE_R = 40;

    function svgEl(tag, attrs) {
      const el = document.createElementNS(SVG_NS, tag);
      for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
      return el;
    }

    let _nodes, _edges;

    function showDetail(nodeId) {
      const n = _nodes.find(x => x.id === nodeId);
      if (!n) return;
      const outgoing = _edges.filter(e => e.from === nodeId);
      const incoming = _edges.filter(e => e.to === nodeId);
      const panel = document.getElementById("detailPanel");
      let html = `<div class="header"><img src="/api/avatar/${n.id}.png" onerror="this.style.display='none'"><h2 style="color:${n.color}">${n.name}</h2></div>`;

      if (outgoing.length) {
        html += `<div style="font-size:0.8rem;color:#888;margin-bottom:8px">${n.name} → みんなへの気持ち</div>`;
        outgoing.forEach(e => {
          const target = _nodes.find(x => x.id === e.to);
          html += `<div class="rel-item">
            <div class="rel-target">→ ${target?.name || e.to}</div>
            <div class="rel-feeling">${e.feeling || "(まだ何も思っていない)"}</div>
            <div class="rel-gauge-label">♥ ${(e.closeness * 100).toFixed(0)}%</div>
            <div class="rel-gauge"><div class="rel-gauge-fill" style="width:${e.closeness * 100}%;background:${n.color}"></div></div>
          </div>`;
        });
      }
      if (incoming.length) {
        html += `<div style="font-size:0.8rem;color:#888;margin:12px 0 8px">みんな → ${n.name} への気持ち</div>`;
        incoming.forEach(e => {
          const src = _nodes.find(x => x.id === e.from);
          html += `<div class="rel-item">
            <div class="rel-target">← ${src?.name || e.from}</div>
            <div class="rel-feeling">${e.feeling || "(まだ何も思っていない)"}</div>
            <div class="rel-gauge-label">♥ ${(e.closeness * 100).toFixed(0)}%</div>
            <div class="rel-gauge"><div class="rel-gauge-fill" style="width:${e.closeness * 100}%;background:${src?.color || '#e94560'}"></div></div>
          </div>`;
        });
      }
      html += `<button class="close-btn" onclick="document.getElementById('detailOverlay').classList.remove('open')">とじる</button>`;
      panel.innerHTML = html;
      document.getElementById("detailOverlay").classList.add("open");
    }

    async function load() {
      const res = await fetch("/api/relations");
      const data = await res.json();
      const { nodes, edges } = data;
      _nodes = nodes; _edges = edges;

      // circular layout
      const pos = {};
      nodes.forEach((n, i) => {
        const angle = (2 * Math.PI * i) / nodes.length - Math.PI / 2;
        pos[n.id] = { x: CX + RADIUS * Math.cos(angle), y: CY + RADIUS * Math.sin(angle) };
      });

      const svg = document.getElementById("chart");

      // defs for arrowheads
      const defs = svgEl("defs", {});
      edges.forEach((e, i) => {
        const marker = svgEl("marker", {
          id: `arr${i}`, markerWidth: "8", markerHeight: "6",
          refX: "8", refY: "3", orient: "auto", markerUnits: "strokeWidth"
        });
        marker.appendChild(svgEl("path", { d: "M0,0 L8,3 L0,6 Z", fill: "#e94560" }));
        defs.appendChild(marker);
      });
      svg.appendChild(defs);

      // edges
      edges.forEach((e, i) => {
        const from = pos[e.from], to = pos[e.to];
        if (!from || !to) return;

        // offset toward center so arrow doesn't overlap node
        const dx = to.x - from.x, dy = to.y - from.y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        const ux = dx / dist, uy = dy / dist;
        const x1 = from.x + ux * NODE_R, y1 = from.y + uy * NODE_R;
        const x2 = to.x - ux * (NODE_R + 8), y2 = to.y - uy * (NODE_R + 8);

        // parallel offset for bidirectional edges
        const reverse = edges.find(re => re.from === e.to && re.to === e.from);
        let ox = 0, oy = 0;
        if (reverse) { ox = -uy * 8; oy = ux * 8; }

        const strokeW = Math.max(1, e.closeness * 5 + 1);
        const line = svgEl("line", {
          x1: x1 + ox, y1: y1 + oy, x2: x2 + ox, y2: y2 + oy,
          stroke: "#e94560", "stroke-width": strokeW, "stroke-opacity": 0.6,
          "marker-end": `url(#arr${i})`
        });
        svg.appendChild(line);

        // heart at midpoint
        const mx = (x1 + x2) / 2 + ox, my = (y1 + y2) / 2 + oy;
        const heartSize = Math.max(8, e.closeness * 16);
        const heart = svgEl("text", {
          x: mx, y: my, "font-size": heartSize, "text-anchor": "middle",
          "dominant-baseline": "central", fill: "#e94560", "fill-opacity": 0.8,
          style: "cursor:default"
        });
        heart.textContent = "\\u2665";
        svg.appendChild(heart);


        // invisible hover zone
        const hitLine = svgEl("line", {
          x1: x1 + ox, y1: y1 + oy, x2: x2 + ox, y2: y2 + oy,
          stroke: "transparent", "stroke-width": Math.max(strokeW, 20)
        });
        const tip = document.getElementById("tip");
        const showTip = (ev) => {
          const fromNode = nodes.find(n => n.id === e.from);
          const toNode = nodes.find(n => n.id === e.to);
          tip.innerHTML = `<strong>${fromNode?.name || e.from}</strong> → <strong>${toNode?.name || e.to}</strong>`
            + `<div class="feeling">${e.feeling || "(まだ何も思っていない)"}</div>`
            + `<div class="gauge-label">♥ ${(e.closeness * 100).toFixed(0)}%</div>`
            + `<div class="gauge-bar"><div class="gauge-fill" style="width:${e.closeness * 100}%;background:${fromNode?.color || '#e94560'}"></div></div>`;
          tip.style.opacity = 1;
          tip.style.left = ev.clientX + 12 + "px";
          tip.style.top = ev.clientY + 12 + "px";
        };
        const hideTip = () => { tip.style.opacity = 0; };
        hitLine.addEventListener("mouseenter", showTip);
        hitLine.addEventListener("mousemove", (ev) => {
          tip.style.left = ev.clientX + 12 + "px";
          tip.style.top = ev.clientY + 12 + "px";
        });
        hitLine.addEventListener("mouseleave", hideTip);
        heart.addEventListener("mouseenter", showTip);
        heart.addEventListener("mousemove", (ev) => {
          tip.style.left = ev.clientX + 12 + "px";
          tip.style.top = ev.clientY + 12 + "px";
        });
        heart.addEventListener("mouseleave", hideTip);
        svg.appendChild(hitLine);
      });

      // nodes
      nodes.forEach(n => {
        const p = pos[n.id];
        const g = svgEl("g", { style: "cursor:pointer" });
        g.addEventListener("click", () => showDetail(n.id));

        if (n.has_avatar || n.id !== "arisan") {
          // clip for circular avatar
          const clipId = `clip-${n.id}`;
          const clipPath = svgEl("clipPath", { id: clipId });
          clipPath.appendChild(svgEl("circle", { cx: p.x, cy: p.y, r: NODE_R }));
          defs.appendChild(clipPath);

          // background circle (white so avatars are visible)
          g.appendChild(svgEl("circle", {
            cx: p.x, cy: p.y, r: NODE_R, fill: "white", stroke: n.color, "stroke-width": 3
          }));

          const img = svgEl("image", {
            href: `/api/avatar/${n.id}.png`, x: p.x - NODE_R, y: p.y - NODE_R,
            width: NODE_R * 2, height: NODE_R * 2, "clip-path": `url(#${clipId})`
          });
          g.appendChild(img);
        } else {
          // arisan: color circle
          g.appendChild(svgEl("circle", {
            cx: p.x, cy: p.y, r: NODE_R, fill: n.color, stroke: "#e0e0e0", "stroke-width": 2
          }));
          const initials = svgEl("text", {
            x: p.x, y: p.y, "text-anchor": "middle", "dominant-baseline": "central",
            fill: "white", "font-size": "16", "font-weight": "bold"
          });
          initials.textContent = n.name.slice(0, 2);
          g.appendChild(initials);
        }

        // name label
        const label = svgEl("text", {
          x: p.x, y: p.y + NODE_R + 18, "text-anchor": "middle",
          fill: "#e0e0e0", "font-size": "14", "font-weight": "bold"
        });
        label.textContent = n.name;
        g.appendChild(label);

        svg.appendChild(g);
      });

      // self-info cards
      const cardsDiv = document.getElementById("cards");
      nodes.forEach(n => {
        const si = n.self_info;
        if (!si || (!si.likes?.length && !si.notes)) return;
        const card = document.createElement("div");
        card.className = "card";
        card.style.borderTopColor = n.color;
        let html = `<h3><img class="avatar-small" src="/api/avatar/${n.id}.png" onerror="this.style.display='none'"> ${n.name}</h3>`;
        if (si.likes?.length) html += `<div class="likes">♥ ${si.likes.join("、")}</div>`;
        if (si.notes) html += `<div class="notes">${si.notes}</div>`;
        card.innerHTML = html;
        cardsDiv.appendChild(card);
      });
    }

    load();

    function parseMail(mail) {
      const parts = mail.filename.replace(".md", "").split("_");
      const fromIdx = parts.indexOf("from");
      const toIdx = parts.indexOf("to");
      let sender = "", recipient = "";
      if (fromIdx >= 0 && toIdx > fromIdx) {
        sender = parts.slice(fromIdx + 1, toIdx).join("_");
        const afterTo = parts.slice(toIdx + 1);
        const dateIdx = afterTo.findIndex(p => /^\\d{8}$/.test(p));
        recipient = dateIdx > 0 ? afterTo.slice(0, dateIdx).join("_") : afterTo[0];
      }
      const dateMatch = mail.filename.match(/(\\d{8})_(\\d{4})/);
      let dateStr = "", sortKey = "";
      if (dateMatch) {
        const d = dateMatch[1], t = dateMatch[2];
        sortKey = d + t;
        dateStr = d.slice(0,4) + "/" + d.slice(4,6) + "/" + d.slice(6,8) + " " + t.slice(0,2) + ":" + t.slice(2,4);
      }
      return { sender, recipient, dateStr, sortKey, content: mail.content };
    }

    async function loadMails() {
      const thread = document.getElementById("mailThread");
      try {
        const res = await fetch("/api/mailbox/all");
        const mails = await res.json();

        const charMails = mails.filter(m => m.filename.startsWith("from_"));
        if (!charMails.length) {
          thread.innerHTML = '<div class="mail-empty">まだおてがみはありません</div>';
          return;
        }

        const nameMap = {};
        if (_nodes) _nodes.forEach(n => { nameMap[n.id] = n.name; });

        const parsed = charMails.map(m => parseMail(m));
        // Sort by date (oldest first)
        parsed.sort((a, b) => (a.sortKey > b.sortKey ? 1 : a.sortKey < b.sortKey ? -1 : 0));

        parsed.forEach(mail => {
          let body = mail.content.trim();
          const lines = body.split("\\n");
          if (lines[0].startsWith("#")) lines.shift();
          while (lines.length && !lines[0].trim()) lines.shift();
          while (lines.length && !lines[lines.length-1].trim()) lines.pop();
          const lastLine = lines[lines.length-1]?.trim();
          if (lastLine && (lastLine === mail.sender || lastLine === (nameMap[mail.sender] || ""))) lines.pop();
          body = lines.join("\\n").trim();

          const isLeft = mail.sender === "puchiko";
          const senderName = nameMap[mail.sender] || mail.sender;
          const recipientName = nameMap[mail.recipient] || mail.recipient;
          const senderColor = _nodes?.find(n => n.id === mail.sender)?.color || "#cab8d9";

          const bubble = document.createElement("div");
          bubble.className = "mail-bubble " + (isLeft ? "left" : "right");
          bubble.innerHTML =
            '<div class="mail-sender" style="color:' + senderColor + '">' + senderName + ' → ' + recipientName + '</div>' +
            body.replace(/</g, "&lt;").replace(/\\n/g, "<br>") +
            '<div class="mail-meta">' + mail.dateStr + '</div>';
          thread.appendChild(bubble);
        });
      } catch(e) {
        thread.innerHTML = '<div class="mail-empty">読み込めませんでした</div>';
      }
    }
    loadMails();
  </script>
</body>
</html>
"""


def main():
    import uvicorn
    port = int(os.getenv("DASHBOARD_PORT", "8765"))
    host = os.getenv("DASHBOARD_HOST", "0.0.0.0")
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
