"""Uniform result envelope returned by every tool, plus the closed set of error codes.

Agents branch on `ok` and, on failure, on `error.code` — never on the free-text message.
"""

from enum import Enum
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, model_validator

T = TypeVar("T")


class ErrorCode(str, Enum):
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    UNAUTHENTICATED = "UNAUTHENTICATED"
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"
    INTERNAL = "INTERNAL"

    @property
    def retryable(self) -> bool:
        """Whether an agent may retry the same call unchanged."""
        return self is ErrorCode.INTERNAL


class ToolErrorBody(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: ErrorCode
    message: str
    details: dict[str, Any] | None = None


class ToolResult(BaseModel, Generic[T]):
    """`{"ok": true, "data": ...}` or `{"ok": false, "error": {...}}` — exactly one of the two."""

    ok: bool
    data: T | None = None
    error: ToolErrorBody | None = None

    @model_validator(mode="after")
    def _one_of(self):
        if self.ok and self.error is not None:
            raise ValueError("a successful result must not carry an error")
        if not self.ok and self.error is None:
            raise ValueError("a failed result must carry an error")
        return self


class ToolError(Exception):
    """Raised inside tool handlers; converted to a failed ToolResult at the transport boundary."""

    def __init__(self, code: ErrorCode, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details

    def to_result(self) -> ToolResult:
        return err(self.code, self.message, self.details)


def ok(data: Any) -> ToolResult:
    return ToolResult(ok=True, data=data)


def err(code: ErrorCode, message: str, details: dict[str, Any] | None = None) -> ToolResult:
    return ToolResult(ok=False, error=ToolErrorBody(code=code, message=message, details=details))
