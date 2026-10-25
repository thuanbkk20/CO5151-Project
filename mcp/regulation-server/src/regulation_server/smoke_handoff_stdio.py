"""Launch a real MCP subprocess, initialize it and exercise both tools.

Uses the same Python interpreter/environment as this client; no HTTP port.
"""

import argparse
import json
import os
import sys
from pathlib import Path

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def envelope(result):
    # Both spellings are accepted because the SDK renamed Python attributes.
    data = getattr(result, "structured_content", None)
    if data is None:
        data = getattr(result, "structuredContent", None)
    if data is None:
        data = json.loads(next(c.text for c in result.content if c.type == "text"))
    return data


async def check(base, draft):
    args = ["-m", "regulation_server.regulation_mcp_v2", "--base", str(base)]
    if draft:
        args.append("--allow-draft")
    parameters = StdioServerParameters(command=sys.executable, args=args, env={**os.environ, "PYTHONUTF8": "1"})
    async with stdio_client(parameters) as (read, write):  # noqa: SIM117 - keep client lifecycle explicit
        async with ClientSession(read, write, read_timeout_seconds=30) as session:
            await session.initialize()
            print("PASS initialize", "draft" if draft else "default", flush=True)
            listed = await session.list_tools()
            tools = {t.name: t for t in listed.tools}
            if set(tools) != {"search_regulations", "get_provision"}:
                raise AssertionError("Unexpected tools")
            for tool in tools.values():
                schema = getattr(tool, "input_schema", None)
                if schema is None:
                    schema = tool.inputSchema
                if schema.get("additionalProperties") is not False:
                    raise AssertionError("Tool schema must forbid extra fields")
                hint = getattr(tool.annotations, "read_only_hint", None)
                if hint is None:
                    hint = tool.annotations.readOnlyHint
                if hint is not True:
                    raise AssertionError("Tool must advertise read-only")
            print("PASS list_tools and schemas", flush=True)
            response = await session.call_tool(
                "search_regulations",
                {
                    "query": "Các chứng chỉ tiếng Anh gồm đầy đủ kỹ năng xét tốt nghiệp",
                    "top_k": 1,
                },
            )
            found = envelope(response)
            if not draft:
                if found["ok"] is not False or found["error"]["code"] != "FORBIDDEN":
                    raise AssertionError("Draft should be blocked by default")
                print("PASS default draft denial", flush=True)
                return
            if found["ok"] is not True:
                raise AssertionError("Search failed")
            results = {r["id"]: r for r in found["data"]["results"]}
            if results["HCMUT-2749-2026-A31"]["reason"] != "graph_related":
                raise AssertionError("Expected referenced conversion table")
            print("PASS search + graph reference", flush=True)
            r = envelope(await session.call_tool("get_provision", {"provision_id": "HCMUT-2749-2026-A2-THESIS"}))
            if not r["ok"] or r["data"]["results"][0]["citation"]["pdf_pages"] != [4]:
                raise AssertionError("Unexpected provision citation")
            print("PASS get_provision citation", flush=True)
            r = envelope(await session.call_tool("get_provision", {"provision_id": "QD2933-2021-CL5.5"}))
            if not r["ok"] or "QD1260-2026-CL5.5" not in {x["id"] for x in r["data"]["results"]}:
                raise AssertionError("Missing amendment")
            print("PASS version expansion through MCP", flush=True)
            for name, args, code in [
                ("get_provision", {"provision_id": "missing"}, "NOT_FOUND"),
                (
                    "search_regulations",
                    {"query": "test", "student_id": "2310001"},
                    "INVALID_ARGUMENT",
                ),
                (
                    "search_regulations",
                    {"query": "test", "top_k": "1"},
                    "INVALID_ARGUMENT",
                ),
            ]:
                response = await session.call_tool(name, args)
                r = envelope(response)
                if r["ok"] is not False or r["error"]["code"] != code:
                    raise AssertionError("Unexpected error envelope")
                flag = getattr(response, "is_error", None)
                if flag is None:
                    flag = response.isError
                if flag is not True:
                    raise AssertionError("MCP isError should match envelope")
                print("PASS error envelope", code, flush=True)


async def main_async(base):
    with anyio.fail_after(55):
        await check(base, True)
        await check(base, False)
    print("ALL MCP STDIO CHECKS PASSED", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=Path(__file__).resolve().parents[2])
    options = parser.parse_args()
    anyio.run(main_async, options.base.resolve())
