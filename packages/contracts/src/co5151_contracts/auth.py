"""Session claims carried by the bearer token that the host app binds to every MCP request.

The token is issued at login (SSO role) and attached by the application layer — it never travels
in tool arguments, so the LLM can neither read nor swap it.
"""

import time
from enum import Enum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints, model_validator

SCOPE_RECORDS_READ = "records.read"

StudentId = Annotated[str, StringConstraints(pattern=r"^[0-9]{7}$")]


class Role(str, Enum):
    STUDENT = "student"
    ADVISOR = "advisor"  # cố vấn học tập (CVHT)


class SessionClaims(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    sub: str
    role: Role
    student_id: StudentId | None = None
    advisor_id: str | None = None
    advisees: tuple[StudentId, ...] = ()
    iat: int
    exp: int

    @model_validator(mode="after")
    def _role_fields(self):
        if self.role is Role.STUDENT:
            if self.student_id is None:
                raise ValueError("student claims require student_id")
            if self.advisor_id is not None or self.advisees:
                raise ValueError("student claims must not carry advisor fields")
        else:
            if self.advisor_id is None:
                raise ValueError("advisor claims require advisor_id")
            if self.student_id is not None:
                raise ValueError("advisor claims must not carry student_id")
        if self.exp <= self.iat:
            raise ValueError("exp must be after iat")
        return self

    def is_expired(self, now: float | None = None) -> bool:
        return self.exp <= (time.time() if now is None else now)
