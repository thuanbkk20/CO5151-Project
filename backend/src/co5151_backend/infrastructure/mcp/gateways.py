"""Gateways to the two MCP servers over Streamable HTTP."""

from typing import Any

from co5151_contracts import STUDENT_RECORD_TOOLS, ErrorCode, ToolResult, err

from .client import call_tool, restore_nulls


class McpStudentRecordGateway:
    """Student Record MCP; the session token goes in the Bearer header, never in tool arguments."""

    def __init__(self, url: str):
        self.url = url

    async def call(self, tool: str, token: str, args: dict[str, Any] | None = None) -> ToolResult:
        spec = STUDENT_RECORD_TOOLS.get(tool)
        if spec is None:
            return err(ErrorCode.NOT_FOUND, f"Tool không tồn tại: {tool}")
        if not token:
            return err(ErrorCode.UNAUTHENTICATED, "Thiếu phiên đăng nhập.")
        result = await call_tool(self.url, tool, args or {}, token=token, server="Student Record")
        if not result.ok:
            return result
        # The same typed objects as the in-process service returns
        return ToolResult(ok=True, data=spec.output_model.model_validate(restore_nulls(spec.output_model, result.data)))


class McpRegulationGateway:
    def __init__(self, url: str):
        self.url = url

    async def call(self, tool: str, args: dict[str, Any]) -> ToolResult:
        return await call_tool(self.url, tool, args, server="Regulation")
