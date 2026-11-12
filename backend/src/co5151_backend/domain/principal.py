"""Who is asking: the signed-in user of one request."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Role(str, Enum):
    STUDENT = "student"
    ADVISOR = "advisor"
    GUEST = "guest"  # asks about regulations only, has no academic record


@dataclass(frozen=True)
class Principal:
    """`user_id` owns conversations: the account username, or `khach-<random>` for one guest sign-in."""

    user_id: str
    role: Role
    display_name: str = ""

    @property
    def is_guest(self) -> bool:
        return self.role is Role.GUEST


@dataclass(frozen=True)
class Account:
    """An account of the identity provider, with the Student Record claims it grants (`sub`, `role`, ...)."""

    username: str
    role: Role
    display_name: str = ""
    claims: dict[str, Any] = field(default_factory=dict)

    def principal(self) -> Principal:
        return Principal(user_id=self.username, role=self.role, display_name=self.display_name or self.username)
