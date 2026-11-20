"""Demo login against the mock account table — stands in for the university SSO."""

from typing import Any

from co5151_contracts.security import AuthError, TokenSigner, account_claims, check_account_password


def authenticate(db, username: str, password: str) -> dict[str, Any]:
    """Return the session claims for valid credentials, else raise AuthError (same message either way)."""
    acc = db.account(username)
    if not check_account_password(acc, password):
        raise AuthError("invalid credentials")
    return account_claims(username, acc)


def claims_for(db, username: str) -> dict[str, Any] | None:
    """Session claims of an account the host has already authenticated, or None if it is unknown (no password check)."""
    acc = db.account(username)
    return account_claims(username, acc) if acc else None


def login(db, signer: TokenSigner, username: str, password: str) -> str:
    return signer.issue(authenticate(db, username, password))
