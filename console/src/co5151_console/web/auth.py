"""Sign-in of the operator account (CONSOLE_USERNAME / CONSOLE_PASSWORD from `.env`): a session cookie signed with
HMAC-SHA256, required by every page except the sign-in page, static files and the health check."""

import base64
import binascii
import hashlib
import hmac
import json
import secrets
import time
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, FastAPI, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from .render import render

COOKIE = "co5151_console_session"
SESSION_SECONDS = 12 * 3600
OPEN_PATHS = ("/login", "/healthz")


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


class Sessions:
    """Checks the operator's password and issues / reads session cookies.

    The signing key is random per process, so restarting the console signs everyone out. No password set = nobody
    can sign in (closed, not open).
    """

    def __init__(self, username: str, password: str | None, ttl: int = SESSION_SECONDS, key: bytes | None = None):
        self.username = username
        self._password = password or None
        self.ttl = ttl
        self._key = key or secrets.token_bytes(32)

    @property
    def enabled(self) -> bool:
        return self._password is not None

    def check(self, username: str, password: str) -> bool:
        if self._password is None:
            return False
        same_user = hmac.compare_digest(username.encode(), self.username.encode())
        same_password = hmac.compare_digest(password.encode(), self._password.encode())
        return same_user and same_password

    def _sign(self, payload: str) -> str:
        return _b64(hmac.new(self._key, payload.encode(), hashlib.sha256).digest())

    def issue(self, now: float | None = None) -> str:
        exp = int(time.time() if now is None else now) + self.ttl
        payload = _b64(json.dumps({"sub": self.username, "exp": exp}).encode())
        return f"{payload}.{self._sign(payload)}"

    def user(self, cookie: str | None, now: float | None = None) -> str | None:
        """The signed-in username, or None for a missing, forged or expired cookie."""
        if not cookie or cookie.count(".") != 1:
            return None
        payload, sig = cookie.split(".")
        if not hmac.compare_digest(self._sign(payload), sig):
            return None
        try:
            claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
            sub, exp = claims["sub"], int(claims["exp"])
        except (binascii.Error, ValueError, TypeError, KeyError):
            return None
        return sub if exp > (time.time() if now is None else now) else None


def safe_next(target: str) -> str:
    """Only a path of this console: never `//other.host` or a full URL (open redirect)."""
    return target if target.startswith("/") and not target.startswith(("//", "/\\")) else "/"


def install(app: FastAPI, sessions: Sessions) -> None:
    """Put every page behind the sign-in and add the /login and /logout routes."""
    app.state.sessions = sessions

    @app.middleware("http")
    async def require_sign_in(request: Request, call_next):
        path = request.url.path
        if path in OPEN_PATHS or path.startswith("/static/"):
            return await call_next(request)
        user = sessions.user(request.cookies.get(COOKIE))
        if user is None:
            if request.query_params.get("panel"):  # content fetched into the side panel: no redirect to a page
                return HTMLResponse('<div class="notice error">Phiên đăng nhập đã hết. '
                                    '<a href="/login">Đăng nhập lại</a></div>', status_code=401)  # fmt: skip
            target = path + (f"?{request.url.query}" if request.url.query else "")
            back = target if request.method == "GET" else "/"
            return RedirectResponse(f"/login?next={quote(back, safe='')}", status_code=303)
        request.state.user = user
        return await call_next(request)

    app.include_router(router)


router = APIRouter()


def _sessions(request: Request) -> Sessions:
    return request.app.state.sessions


@router.get("/login")
def login_page(request: Request, target: Annotated[str, Query(alias="next")] = "/"):
    return render(request, "login.html", target=safe_next(target), enabled=_sessions(request).enabled,
                  username="", error="")  # fmt: skip


@router.post("/login")
def login(
    request: Request,
    username: Annotated[str, Form()] = "",
    password: Annotated[str, Form()] = "",
    target: Annotated[str, Form(alias="next")] = "/",
):
    sessions = _sessions(request)
    if not sessions.check(username, password):
        return render(request, "login.html", status_code=401, target=safe_next(target), enabled=sessions.enabled,
                      username=username, error="Sai tên đăng nhập hoặc mật khẩu.")  # fmt: skip
    response = RedirectResponse(safe_next(target), status_code=303)
    response.set_cookie(COOKIE, sessions.issue(), max_age=sessions.ttl, path="/", httponly=True, samesite="lax",
                        secure=request.url.scheme == "https")  # fmt: skip
    return response


@router.post("/logout")
def logout():
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(COOKIE, path="/")
    return response
