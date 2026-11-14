"""MCP client adapters: the same `call(...) -> ToolResult` interface as the in-process services.

`AdvisorAgent` and `ToolRegulationSource` only see that interface, so swapping an in-process service for one of
these sends the same tool calls over the real MCP protocol (Streamable HTTP for Student Record, stdio subprocess
for Regulation).
"""

import asyncio
import atexit
import json
import logging
import sys
import threading
from typing import Any, get_args

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from pydantic import BaseModel

from co5151_contracts import STUDENT_RECORD_TOOLS, ErrorCode, ToolResult, err
from student_server import mcp_compat

logger = logging.getLogger(__name__)

CALL_TIMEOUT = 60


def _envelope(result: Any) -> dict[str, Any]:
    data = getattr(result, "structured_content", None) or getattr(result, "structuredContent", None)
    if data is None:
        data = json.loads(next(c.text for c in result.content if c.type == "text"))
    return data


def _restore_nulls(model: type[BaseModel], data: dict[str, Any]) -> dict[str, Any]:
    """The server drops `None` fields (`exclude_none`); put back the ones the model requires as nullable."""
    nullable = {
        n: None for n, f in model.model_fields.items() if f.is_required() and type(None) in get_args(f.annotation)
    }
    return {**nullable, **data}


def _http_status(exc: BaseException) -> int | None:
    for sub in getattr(exc, "exceptions", ()):  # ExceptionGroup (anyio task groups)
        if (status := _http_status(sub)) is not None:
            return status
    response = getattr(exc, "response", None)
    return getattr(response, "status_code", None)


class McpStudentService:
    """Student Record MCP over Streamable HTTP; the session token goes in the Bearer header on every call."""

    def __init__(self, url: str):
        self.url = url

    def call(self, name: str, token: str | None, args: dict[str, Any] | None = None) -> ToolResult:
        spec = STUDENT_RECORD_TOOLS.get(name)
        if spec is None:
            return err(ErrorCode.NOT_FOUND, f"Tool không tồn tại: {name}")
        if not token:
            return err(ErrorCode.UNAUTHENTICATED, "Thiếu phiên đăng nhập.")

        async def go():
            async with mcp_compat.open_session(self.url, token, timeout=CALL_TIMEOUT) as session:
                return _envelope(await session.call_tool(name, args or {}))

        try:
            body = anyio.run(go)
        except Exception as e:
            if _http_status(e) == 401:
                return err(ErrorCode.UNAUTHENTICATED, "Phiên đăng nhập không hợp lệ hoặc đã hết hạn.")
            logger.exception("Student Record MCP call %s failed (%s)", name, self.url)
            return err(ErrorCode.INTERNAL, "Không gọi được Student Record MCP.")
        result = ToolResult.model_validate(body)
        if result.ok:  # rebuild the typed model so callers see the same objects as with the in-process service
            return ToolResult(
                ok=True, data=spec.output_model.model_validate(_restore_nulls(spec.output_model, result.data))
            )
        return result


class McpRegulationService:
    """Regulation MCP as a stdio subprocess, started on first use and kept for the life of this object."""

    def __init__(self, *, allow_draft: bool = True):
        self._args = ["-m", "regulation_server.regulation_mcp_v2"] + (["--allow-draft"] if allow_draft else [])
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._session: ClientSession | None = None
        self._stop: asyncio.Event | None = None
        atexit.register(self.close)

    def _start(self) -> None:
        loop = asyncio.new_event_loop()
        ready = threading.Event()
        failure: list[BaseException] = []

        async def run():
            self._stop = asyncio.Event()
            params = StdioServerParameters(command=sys.executable, args=self._args)
            try:
                async with stdio_client(params) as (read, write):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        self._session = session
                        ready.set()
                        await self._stop.wait()
            except BaseException as e:
                failure.append(e)
            finally:
                self._session = None
                ready.set()

        threading.Thread(target=loop.run_until_complete, args=(run(),), daemon=True, name="regulation-mcp").start()
        ready.wait(CALL_TIMEOUT)
        if self._session is None:
            raise RuntimeError(f"Regulation MCP did not start: {failure[0] if failure else 'timeout'}")
        self._loop = loop

    def call(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        try:
            with self._lock:
                if self._session is None:
                    self._start()
                assert self._loop is not None and self._session is not None
                future = asyncio.run_coroutine_threadsafe(self._session.call_tool(name, arguments), self._loop)
            return ToolResult.model_validate(_envelope(future.result(CALL_TIMEOUT)))
        except Exception:
            logger.exception("Regulation MCP call %s failed", name)
            self.close()  # drop the session so the next call starts a fresh subprocess
            return err(ErrorCode.INTERNAL, "Không gọi được Regulation MCP.")

    def close(self) -> None:
        with self._lock:
            if self._loop is not None and self._stop is not None:
                self._loop.call_soon_threadsafe(self._stop.set)
            self._loop = self._session = self._stop = None
