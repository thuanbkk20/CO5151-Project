"""Regulation MCP over Streamable HTTP: JSON-RPC requests to the ASGI app (in-process, no socket)."""

import json
from pathlib import Path

from starlette.testclient import TestClient

from regulation_server.regulation_mcp_v2 import http_app
from regulation_server.regulation_service_v2 import RegulationServiceV2

BASE = Path(__file__).resolve().parents[1]


def _rpc(client, method, params, id_=1):
    headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
    body = {"jsonrpc": "2.0", "id": id_, "method": method, "params": params}
    return client.post("/mcp", content=json.dumps(body), headers=headers)


def test_tools_over_http():
    with TestClient(http_app(RegulationServiceV2(BASE, allow_draft=True))) as client:
        init = {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "test", "version": "0"}}
        assert _rpc(client, "initialize", init).status_code == 200
        tools = _rpc(client, "tools/list", {}, 2).json()["result"]["tools"]
        assert {t["name"] for t in tools} == {"search_regulations", "get_provision"}
        res = _rpc(client, "tools/call", {"name": "get_provision", "arguments": {"provision_id": "missing"}}, 3)
        body = res.json()["result"]["structuredContent"]
        assert body["ok"] is False and body["error"]["code"] == "NOT_FOUND"
