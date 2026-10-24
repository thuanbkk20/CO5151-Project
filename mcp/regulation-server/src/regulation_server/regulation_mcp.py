"""Read-only Regulation MCP over local stdio. Tested with mcp==2.3.0.

Uses explicit low-level callbacks so service validation controls the shared
error envelope. Do not print diagnostics on stdout: it carries MCP messages.
"""

import argparse
import json
import logging
from pathlib import Path

import anyio
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    CallToolResult,
    ListToolsResult,
    TextContent,
    Tool,
    ToolAnnotations,
)
from regulation_service import INPUTS, RegulationService

DESCRIPTIONS = {
    "search_regulations": "Tra cứu bằng chứng quy chế ngoại ngữ và mở rộng dẫn chiếu. Bản nháp; chưa lọc chương trình, khóa hoặc hiệu lực; không kết luận đạt chuẩn.",
    "get_provision": "Lấy nguyên văn điều khoản theo mã cùng vị trí nguồn. Bản nháp chưa được phê duyệt.",
}


def build_server(service):
    async def list_tools(context, params):
        return ListToolsResult(
            tools=[
                Tool(
                    name=name,
                    description=DESCRIPTIONS[name],
                    inputSchema=model.model_json_schema(),
                    annotations=ToolAnnotations(
                        readOnlyHint=True,
                        destructiveHint=False,
                        idempotentHint=True,
                        openWorldHint=False,
                    ),
                )
                for name, model in INPUTS.items()
            ]
        )

    async def call_tool(context, params):
        result = service.call(
            params.name, params.arguments if params.arguments is not None else {}
        )
        body = result.model_dump(mode="json", exclude_none=True)
        return CallToolResult(
            content=[
                TextContent(type="text", text=json.dumps(body, ensure_ascii=False))
            ],
            structuredContent=body,
            isError=not result.ok,
        )

    return Server(
        "regulation-mcp",
        version="0.1.0",
        instructions="Read-only draft foreign-language evidence. Never infer student eligibility. Check envelope ok and evidence verification state.",
        on_list_tools=list_tools,
        on_call_tool=call_tool,
    )


async def serve(base, allow_draft=False):
    service = RegulationService(
        base / "data/processed/language_structured/evidence_graph.json", allow_draft
    )
    server = build_server(service)
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base", type=Path, default=Path(__file__).resolve().parents[2])
    p.add_argument("--allow-draft", action="store_true")
    a = p.parse_args()
    logging.basicConfig(level=logging.WARNING)
    anyio.run(serve, a.base.resolve(), a.allow_draft)


if __name__ == "__main__":
    main()
