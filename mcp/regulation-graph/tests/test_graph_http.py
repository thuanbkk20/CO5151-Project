"""Graph Regulation MCP over Streamable HTTP: JSON-RPC requests to the ASGI app (in-process, no socket)."""

import json

from starlette.testclient import TestClient

from regulation_graph.server import http_app
from regulation_graph.service import RegulationGraphService


def _rpc(client, method, params, id_=1):
    headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
    body = {"jsonrpc": "2.0", "id": id_, "method": method, "params": params}
    return client.post("/mcp", content=json.dumps(body), headers=headers)


def test_same_tools_as_the_bm25_server_over_http():
    with TestClient(http_app(RegulationGraphService())) as client:
        init = {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "test", "version": "0"}}
        assert _rpc(client, "initialize", init).status_code == 200
        tools = _rpc(client, "tools/list", {}, 2).json()["result"]["tools"]
        assert {t["name"] for t in tools} == {"search_regulations", "get_provision"}
        args = {"query": "Điều kiện để nhận bằng tốt nghiệp", "top_k": 3, "hops": 1}
        body = _rpc(client, "tools/call", {"name": "search_regulations", "arguments": args}, 3).json()
        data = body["result"]["structuredContent"]["data"]
        assert "QD1260-2026-CL10.1" in [r["id"] for r in data["results"]]
