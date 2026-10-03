"""Shared contracts for the CO5151 G3 agentic RAG system."""

from .envelope import ErrorCode, ToolError, ToolErrorBody, ToolResult, err, ok

__all__ = ["ErrorCode", "ToolError", "ToolErrorBody", "ToolResult", "err", "ok"]
__version__ = "0.1.0"
