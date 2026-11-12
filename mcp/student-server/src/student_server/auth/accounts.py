"""Demo login against the mock account table — stands in for the university SSO."""

from typing import Any

from .passwords import hash_password, verify_password
from .tokens import AuthError, TokenSigner

# Verified when the username does not exist, so both failure paths cost the same time.
_DUMMY_HASH = hash_password("dummy", salt="0" * 16)


def authenticate(db, username: str, password: str) -> dict[str, Any]:
    """Return the session claims for valid credentials, else raise AuthError (same message either way)."""
    acc = db.account(username)
    if not verify_password(password, acc["password_hash"] if acc else _DUMMY_HASH) or not acc:
        raise AuthError("invalid credentials")
    return _claims(username, acc)


def claims_for(db, username: str) -> dict[str, Any] | None:
    """Session claims of an account the host has already authenticated (token refresh), or None if it is unknown.

    No password check: only call this for an identity proven another way, e.g. the chat app's signed login session.
    """
    acc = db.account(username)
    return _claims(username, acc) if acc else None


def _claims(username: str, acc: dict[str, Any]) -> dict[str, Any]:
    claims: dict[str, Any] = {"sub": username, "role": acc["role"]}
    if acc["role"] == "student":
        claims["student_id"] = acc["mssv"]
    else:
        claims["advisor_id"] = acc["advisor_id"]
        claims["advisees"] = acc["advisees"]
    return claims


def login(db, signer: TokenSigner, username: str, password: str) -> str:
    return signer.issue(authenticate(db, username, password))
