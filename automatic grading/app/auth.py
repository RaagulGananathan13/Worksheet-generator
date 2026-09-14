"""Password hashing, opaque sessions, CSRF, and role dependencies."""

import hashlib
import hmac
import secrets
import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import HTTPException, Request, Response


COOKIE_NAME = "ag_session"
SESSION_SECONDS = 12 * 60 * 60


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=16384, r=8, p=1)
    return f"scrypt:16384:8:1:{salt.hex()}:{digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, n, r, p, salt, expected = encoded.split(":")
        if algorithm != "scrypt" or (int(n), int(r), int(p)) != (16384, 8, 1):
            return False
        digest = hashlib.scrypt(password.encode("utf-8"), salt=bytes.fromhex(salt), n=16384, r=8, p=1)
        return hmac.compare_digest(digest.hex(), expected)
    except (ValueError, TypeError, MemoryError):
        return False


def session_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def public_user(user: dict) -> dict:
    result = {key: user[key] for key in ("id", "name", "username", "role")}
    if user["role"] == "teacher":
        result["class_code"] = user["class_code"]
    return result


def create_session(request: Request, response: Response, user: dict) -> dict:
    token, csrf = secrets.token_urlsafe(40), secrets.token_urlsafe(32)
    now = time.time()
    with request.app.state.database.transaction() as connection:
        connection.execute("DELETE FROM sessions WHERE expires_at <= ?", (now,))
        old = request.cookies.get(COOKIE_NAME)
        if old:
            connection.execute("DELETE FROM sessions WHERE token_hash = ?", (session_hash(old),))
        connection.execute(
            "INSERT INTO sessions(token_hash,user_id,csrf_token,expires_at) VALUES (?,?,?,?)",
            (session_hash(token), user["id"], csrf, now + SESSION_SECONDS),
        )
    response.set_cookie(
        COOKIE_NAME, token, max_age=SESSION_SECONDS, httponly=True,
        secure=request.app.state.secure_cookies, samesite="strict", path="/",
    )
    return {"user": public_user(user), "csrf_token": csrf}


def lookup_session(request: Request):
    token = request.cookies.get(COOKIE_NAME, "")
    if not token or len(token) > 128:
        return None
    return request.app.state.database.one(
        "SELECT users.*, sessions.csrf_token FROM sessions "
        "JOIN users ON users.id=sessions.user_id WHERE token_hash=? AND expires_at>?",
        (session_hash(token), time.time()),
    )


def require_user(request: Request) -> dict:
    user = lookup_session(request)
    if user is None:
        raise HTTPException(401, "Please log in to continue.")
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        supplied = request.headers.get("x-csrf-token", "")
        if not supplied or not hmac.compare_digest(supplied.encode("utf-8"), user["csrf_token"].encode("utf-8")):
            raise HTTPException(403, "Your session token changed. Refresh and try again.")
    return user


def require_teacher(request: Request) -> dict:
    user = require_user(request)
    if user["role"] != "teacher":
        raise HTTPException(403, "This action is available to teachers only.")
    return user


def require_student(request: Request) -> dict:
    user = require_user(request)
    if user["role"] != "student":
        raise HTTPException(403, "This action is available to students only.")
    return user


class LoginLimiter:
    """Process-local abuse guard; deployments can add an ingress limiter."""

    def __init__(self):
        self.entries = defaultdict(deque)
        self.lock = Lock()

    def check(self, key: str, maximum=12):
        now = time.monotonic()
        with self.lock:
            if len(self.entries) > 5000:
                self.entries = defaultdict(deque, {
                    item: times for item, times in self.entries.items()
                    if times and times[-1] > now - 900
                })
            attempts = self.entries[key]
            while attempts and attempts[0] <= now - 900:
                attempts.popleft()
            if len(attempts) >= maximum:
                raise HTTPException(429, "Too many sign-in attempts. Try again in 15 minutes.")
            attempts.append(now)

    def clear(self, key: str):
        with self.lock:
            self.entries.pop(key, None)
