from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from pathlib import Path
from threading import Lock

from app.config import ROOT_DIR

DEFAULT_USERNAME = "admin"
DEFAULT_PASSWORD = "admin"
DATA_DIR = ROOT_DIR / "data"
ADMIN_PATH = DATA_DIR / "admin.json"
SESSION_KEY_PATH = DATA_DIR / "session.key"
PBKDF2_ROUNDS = 200_000
_lock = Lock()


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ROUNDS)
    return f"{salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, digest_hex = stored.split("$", 1)
        salt = bytes.fromhex(salt_hex)
    except ValueError:
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ROUNDS)
    return hmac.compare_digest(digest.hex(), digest_hex)


def get_session_secret() -> str:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if SESSION_KEY_PATH.exists():
        secret = SESSION_KEY_PATH.read_text(encoding="utf-8").strip()
        if secret:
            return secret
    secret = secrets.token_hex(32)
    SESSION_KEY_PATH.write_text(secret + "\n", encoding="utf-8")
    return secret


def load_admin(path: Path | None = None) -> dict:
    target = path or ADMIN_PATH
    ensure_admin(target)
    with _lock:
        return json.loads(target.read_text(encoding="utf-8"))


def save_admin(data: dict, path: Path | None = None) -> None:
    target = path or ADMIN_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    with _lock:
        target.write_text(payload, encoding="utf-8")


def ensure_admin(path: Path | None = None) -> dict:
    target = path or ADMIN_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        save_admin(
            {
                "username": DEFAULT_USERNAME,
                "password_hash": hash_password(DEFAULT_PASSWORD),
                "must_change": True,
            },
            target,
        )
    return json.loads(target.read_text(encoding="utf-8"))


def authenticate(username: str, password: str) -> dict | None:
    admin = load_admin()
    if username != admin.get("username"):
        return None
    if not verify_password(password, admin.get("password_hash", "")):
        return None
    return admin


def update_account(current_password: str, username: str, password: str) -> dict:
    admin = load_admin()
    if not verify_password(current_password, admin.get("password_hash", "")):
        raise ValueError("当前密码不正确")
    username = username.strip()
    password = password.strip()
    if len(username) < 3 or len(username) > 32:
        raise ValueError("账号长度需要 3 到 32 个字符")
    if any(ch in username for ch in " \r\n\t"):
        raise ValueError("账号不能包含空白字符")
    if len(password) < 8:
        raise ValueError("新密码至少 8 位")
    same_user = username == admin.get("username")
    same_pass = verify_password(password, admin.get("password_hash", ""))
    if admin.get("must_change"):
        if same_user:
            raise ValueError("首次登录必须更换账号")
        if same_pass:
            raise ValueError("首次登录必须更换密码")
    elif same_user and same_pass:
        raise ValueError("账号或密码需要至少改一项")
    updated = {
        "username": username,
        "password_hash": hash_password(password),
        "must_change": False,
    }
    save_admin(updated)
    return updated
