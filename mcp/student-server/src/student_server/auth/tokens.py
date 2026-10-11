"""Session tokens: `base64url(claims).base64url(HMAC-SHA256)` — a minimal JWT-like format.

In production the issuer would be the university SSO (JWT, RS256). Here the host app's login issues
tokens with a shared secret; the Student Record MCP only verifies them.
"""

import base64
import binascii
import hashlib
import hmac
import json
import time
from typing import Any

from pydantic import ValidationError

from co5151_contracts import SessionClaims


class AuthError(Exception):
    pass


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


class TokenSigner:
    def __init__(self, secret: bytes, ttl: int = 3600):
        if not secret:
            raise ValueError("token secret must not be empty")
        self._secret = secret
        self.ttl = ttl

    def _sign(self, payload: str) -> str:
        return _b64(hmac.new(self._secret, payload.encode(), hashlib.sha256).digest())

    def issue(self, claims: dict[str, Any], ttl: int | None = None, now: float | None = None) -> str:
        iat = int(time.time() if now is None else now)
        body = SessionClaims(**claims, iat=iat, exp=iat + (self.ttl if ttl is None else ttl))
        payload = _b64(body.model_dump_json(exclude_none=True).encode())
        return f"{payload}.{self._sign(payload)}"

    def verify(self, token: str, now: float | None = None) -> SessionClaims:
        if not isinstance(token, str) or token.count(".") != 1:
            raise AuthError("malformed token")
        payload, sig = token.split(".")
        if not hmac.compare_digest(self._sign(payload), sig):
            raise AuthError("bad signature")
        try:
            claims = SessionClaims.model_validate(json.loads(_unb64(payload)))
        except (binascii.Error, ValueError, ValidationError):
            raise AuthError("malformed claims") from None
        if claims.is_expired(now):
            raise AuthError("token expired")
        return claims
