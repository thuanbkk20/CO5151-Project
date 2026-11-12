"""Sign-in and token checks."""

import secrets
from dataclasses import dataclass

from ...domain.errors import InvalidCredentials
from ...domain.principal import Principal, Role
from ..ports import AccessTokens, AccountDirectory

GUEST_USERNAME = "khach"


@dataclass(frozen=True)
class Session:
    access_token: str
    expires_in: int
    principal: Principal


class SignIn:
    def __init__(self, accounts: AccountDirectory, tokens: AccessTokens):
        self._accounts = accounts
        self._tokens = tokens

    def execute(self, username: str, password: str) -> Session:
        """`khach` signs in without a password as a new guest, so each guest sign-in has its own history."""
        if username.strip().lower() == GUEST_USERNAME:
            principal = Principal(f"{GUEST_USERNAME}-{secrets.token_hex(6)}", Role.GUEST, "Khách")
        else:
            account = self._accounts.authenticate(username, password)
            if account is None:
                raise InvalidCredentials("invalid credentials")
            principal = account.principal()
        token, ttl = self._tokens.issue(principal)
        return Session(token, ttl, principal)


class Authenticate:
    def __init__(self, tokens: AccessTokens):
        self._tokens = tokens

    def execute(self, token: str) -> Principal:
        """Raises Unauthenticated."""
        return self._tokens.verify(token)
