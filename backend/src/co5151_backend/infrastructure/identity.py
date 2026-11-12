"""Identity adapters: the demo SSO, the backend's access tokens (JWT) and Student Record tokens."""

import json
import time
from importlib import resources
from pathlib import Path
from typing import Any

import jwt

from co5151_contracts.security import TokenSigner, account_claims, check_account_password

from ..domain.errors import Unauthenticated
from ..domain.principal import Account, Principal, Role

JWT_ALGORITHM = "HS256"
JWT_AUDIENCE = "co5151-backend"


def default_accounts_file() -> Path:
    return Path(str(resources.files("student_server.mockdata").joinpath("accounts.json")))


class DemoAccountDirectory:
    """The demo account table of student-server (`accounts.json`), standing in for the university SSO."""

    def __init__(self, path: Path | None = None):
        rows: list[dict[str, Any]] = json.loads((path or default_accounts_file()).read_text("utf-8"))
        self._rows = {row["username"]: row for row in rows}

    def authenticate(self, username: str, password: str) -> Account | None:
        row = self._rows.get(username)
        return self._account(username, row) if check_account_password(row, password) else None

    def get(self, username: str) -> Account | None:
        row = self._rows.get(username)
        return self._account(username, row) if row else None

    @staticmethod
    def _account(username: str, row: dict[str, Any]) -> Account:
        return Account(username=username, role=Role(row["role"]), claims=account_claims(username, row))


class JwtAccessTokens:
    def __init__(self, secret: bytes, ttl: int):
        self._secret = secret
        self._ttl = ttl

    def issue(self, principal: Principal) -> tuple[str, int]:
        now = int(time.time())
        claims = {"sub": principal.user_id, "role": principal.role.value, "name": principal.display_name,
                  "aud": JWT_AUDIENCE, "iat": now, "exp": now + self._ttl}  # fmt: skip
        return jwt.encode(claims, self._secret, algorithm=JWT_ALGORITHM), self._ttl

    def verify(self, token: str) -> Principal:
        try:
            claims = jwt.decode(token, self._secret, algorithms=[JWT_ALGORITHM], audience=JWT_AUDIENCE,
                                options={"require": ["sub", "role", "exp"]})  # fmt: skip
            return Principal(user_id=claims["sub"], role=Role(claims["role"]), display_name=claims.get("name", ""))
        except (jwt.PyJWTError, ValueError) as e:
            raise Unauthenticated(str(e)) from None


class SignedStudentTokens:
    """Student Record session tokens signed with the secret student-mcp verifies (`STUDENT_MCP_TOKEN_SECRET`)."""

    def __init__(self, secret: bytes, ttl: int):
        self._signer = TokenSigner(secret, ttl)

    def issue(self, account: Account) -> str:
        return self._signer.issue(account.claims)
