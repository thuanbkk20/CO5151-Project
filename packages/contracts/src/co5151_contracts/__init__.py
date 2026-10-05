"""Shared contracts for the CO5151 G3 agentic RAG system."""

from .auth import SCOPE_RECORDS_READ, Role, SessionClaims, StudentId
from .envelope import ErrorCode, ToolError, ToolErrorBody, ToolResult, err, ok
from .tools import STUDENT_RECORD_TOOLS, Permission, ToolSpec

__all__ = [
    "SCOPE_RECORDS_READ",
    "Role",
    "SessionClaims",
    "StudentId",
    "ErrorCode",
    "ToolError",
    "ToolErrorBody",
    "ToolResult",
    "err",
    "ok",
    "STUDENT_RECORD_TOOLS",
    "Permission",
    "ToolSpec",
]
__version__ = "0.1.0"
