"""Session tokens and demo password hashes, shared by the token issuer (backend) and the verifier (Student Record MCP).

Token format: `base64url(claims).base64url(HMAC-SHA256)`, a minimal JWT-like format signed with a shared secret. In
production the issuer would be the university SSO (JWT, RS256) and the MCP server would only hold its public key.
"""

import base64
import binascii
import hashlib
import hmac
import json
import secrets
import time
from typing import Any

from pydantic import ValidationError

from .auth import SessionClaims

PASSWORD_ITERATIONS = 60_000


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


# Passwords: `pbkdf2_sha256$<iterations>$<salt>$<hex digest>` ---------------------------------------------------


def hash_password(password: str, salt: str | None = None, iterations: int = PASSWORD_ITERATIONS) -> str:
    salt = salt or secrets.token_hex(8)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), iterations).hex()
    return f"pbkdf2_sha256${iterations}${salt}${digest}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algo, iterations, salt, digest = encoded.split("$")
    except (AttributeError, ValueError):
        return False
    if algo != "pbkdf2_sha256":
        return False
    expected = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(iterations)).hex()
    return hmac.compare_digest(expected, digest)


# Checked when the username does not exist, so both failure paths cost the same time.
_DUMMY_HASH = hash_password("dummy", salt="0" * 16)


def check_account_password(account: dict[str, Any] | None, password: str) -> bool:
    """Whether `password` opens `account` (a row of the demo account table); False for a missing account."""
    return verify_password(password, account["password_hash"] if account else _DUMMY_HASH) and account is not None


def account_claims(username: str, account: dict[str, Any]) -> dict[str, Any]:
    """Session claims (without iat/exp) of a demo account row: `role`, then `mssv` or `advisor_id` + `advisees`."""
    claims: dict[str, Any] = {"sub": username, "role": account["role"]}
    if account["role"] == "student":
        claims["student_id"] = account["mssv"]
    else:
        claims["advisor_id"] = account["advisor_id"]
        claims["advisees"] = account["advisees"]
    return claims
