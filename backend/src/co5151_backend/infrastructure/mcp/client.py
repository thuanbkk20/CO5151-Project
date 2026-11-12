"""Streamable HTTP MCP client shared by the gateways: one initialized session per call, results as ToolResult."""

import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, get_args

from pydantic import BaseModel

from co5151_contracts import ErrorCode, ToolResult, err

logger = logging.getLogger(__name__)

CALL_TIMEOUT_S = 30.0

try:  # mcp >= 2.0
    import httpx2
    from mcp.client.streamable_http import streamable_http_client

    @asynccontextmanager
    async def _streams(url: str, headers: dict[str, str], timeout: float) -> AsyncIterator[Any]:
        async with httpx2.AsyncClient(headers=headers, timeout=timeout) as http:
            async with streamable_http_client(url, http_client=http) as streams:
                yield streams

except ImportError:  # mcp 1.x
    from mcp.client.streamable_http import streamablehttp_client

    @asynccontextmanager
    async def _streams(url: str, headers: dict[str, str], timeout: float) -> AsyncIterator[Any]:
        async with streamablehttp_client(url, headers=headers, timeout=timeout) as streams:
            yield streams


from mcp import ClientSession  # noqa: E402


def _envelope(result: Any) -> dict[str, Any]:
    data = getattr(result, "structured_content", None) or getattr(result, "structuredContent", None)
    if data is None:
        data = json.loads(next(c.text for c in result.content if c.type == "text"))
    return data


def _http_status(exc: BaseException) -> int | None:
    for sub in getattr(exc, "exceptions", ()):  # ExceptionGroup (anyio task groups)
        if (status := _http_status(sub)) is not None:
            return status
    return getattr(getattr(exc, "response", None), "status_code", None)


def restore_nulls(model: type[BaseModel], data: dict[str, Any]) -> dict[str, Any]:
    """Servers drop `None` fields (`exclude_none`); put back the ones the model requires as nullable."""
    nullable = {
        n: None for n, f in model.model_fields.items() if f.is_required() and type(None) in get_args(f.annotation)
    }
    return {**nullable, **data}


async def call_tool(url: str, tool: str, args: dict[str, Any], *, token: str | None = None, server: str) -> ToolResult:
    """Never raises: an HTTP 401 is UNAUTHENTICATED, any other failure INTERNAL (and logged)."""
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        async with _streams(url, headers, CALL_TIMEOUT_S) as streams:
            async with ClientSession(streams[0], streams[1]) as session:
                await session.initialize()
                body = _envelope(await session.call_tool(tool, args))
        return ToolResult.model_validate(body)
    except Exception as e:
        if _http_status(e) == 401:
            return err(ErrorCode.UNAUTHENTICATED, "Phiên đăng nhập không hợp lệ hoặc đã hết hạn.")
        logger.exception("%s MCP call %s failed (%s)", server, tool, url)
        return err(ErrorCode.INTERNAL, f"Không gọi được {server} MCP.")
