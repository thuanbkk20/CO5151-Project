"""End-to-end: a real Streamable HTTP server on localhost, called through the MCP client SDK.

These tests are the evidence for the D2 claim that isolation is enforced in code: identity comes
only from the Bearer token of each HTTP request, never from tool arguments.
"""

import json
import socket
import threading
import time
import urllib.error
import urllib.request

import anyio
import pytest
import uvicorn

from student_server import mcp_compat
from student_server.auth import TokenSigner
from student_server.config import Settings
from student_server.server import build_server, build_service

SECRET = b"e2e-secret"
STUDENTS = {f"sv00{i}": m for i, m in enumerate(["2310001", "2310002", "2310003", "2210004", "2210005",
                                                  "2410006", "2310007", "2510008"], start=1)}  # fmt: skip


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def live():
    settings = Settings(token_secret=SECRET, port=_free_port())
    service = build_service(settings)
    app = mcp_compat.http_app(build_server(service, settings))
    server = uvicorn.Server(uvicorn.Config(app, host=settings.host, port=settings.port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 10
    while not server.started:
        assert time.time() < deadline, "server did not start"
        time.sleep(0.05)
    yield {"url": f"http://{settings.host}:{settings.port}/mcp", "service": service}
    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture(scope="module")
def tokens(live):
    from student_server.auth import login

    svc = live["service"]
    return {u: login(svc.db, svc.signer, u, "demo") for u in [*STUDENTS, "cvht01"]}


def call(url, token, tool, args=None):
    async def go():
        async with mcp_compat.open_session(url, token) as s:
            res = await s.call_tool(tool, args or {})
            return json.loads(res.content[0].text)

    return anyio.run(go)


def raw_post(url, headers):
    """Bare HTTP request (no MCP client) to observe the transport-level status code."""
    init = {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}}
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": init}).encode()
    hdrs = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream", **headers}
    try:
        with urllib.request.urlopen(urllib.request.Request(url, body, hdrs, method="POST"), timeout=10) as r:
            return r.status, dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers)


# ---------------------------------------------------------------- authentication at the transport


def test_missing_token_is_rejected_with_401(live):
    status, headers = raw_post(live["url"], {})
    assert status == 401 and "bearer" in headers.get("www-authenticate", "").lower()


@pytest.mark.parametrize(
    "token",
    [
        "not-a-token",
        TokenSigner(b"attacker-secret").issue({"sub": "sv001", "role": "student", "student_id": "2310002"}),
        TokenSigner(SECRET).issue({"sub": "sv001", "role": "student", "student_id": "2310001"}, ttl=1, now=1),
    ],
    ids=["garbage", "foreign-secret", "expired"],
)
def test_invalid_tokens_are_rejected_with_401(live, token):
    assert raw_post(live["url"], {"Authorization": f"Bearer {token}"})[0] == 401


# ---------------------------------------------------------------- authorization inside tools


def test_lists_six_read_only_tools(live, tokens):
    async def go():
        async with mcp_compat.open_session(live["url"], tokens["sv001"]) as s:
            return (await s.list_tools()).tools

    tools = anyio.run(go)
    assert len(tools) == 6
    assert all(t.annotations.model_dump(by_alias=True)["readOnlyHint"] for t in tools)


def test_student_reads_own_profile(live, tokens):
    res = call(live["url"], tokens["sv002"], "get_my_profile")
    assert res["ok"] and res["data"]["student_id"] == "2310002"


def test_injected_student_id_never_changes_the_target(live, tokens):
    """Whether the SDK drops the extra argument or the contract rejects it, sv001 never sees 2310002."""
    res = call(live["url"], tokens["sv001"], "get_my_academic_summary", {"student_id": "2310002"})
    assert (res["ok"] and res["data"]["student_id"] == "2310001") or res["error"]["code"] == "INVALID_ARGUMENT"


def test_student_cannot_use_advisor_tool(live, tokens):
    res = call(live["url"], tokens["sv001"], "get_advisee_summary", {"student_id": "2310002"})
    assert res["error"]["code"] == "FORBIDDEN"


def test_advisor_scope(live, tokens):
    assert call(live["url"], tokens["cvht01"], "get_advisee_summary", {"student_id": "2310003"})["ok"]
    res = call(live["url"], tokens["cvht01"], "get_advisee_summary", {"student_id": "2210004"})
    assert res["error"]["code"] == "FORBIDDEN"


def test_concurrent_users_are_isolated(live, tokens):
    seen = {}

    async def one(user):
        async with mcp_compat.open_session(live["url"], tokens[user]) as s:
            for _ in range(3):
                res = json.loads((await s.call_tool("get_my_profile", {})).content[0].text)
                seen.setdefault(user, set()).add(res["data"]["student_id"])
                await anyio.sleep(0)

    async def go():
        async with anyio.create_task_group() as tg:
            for user in STUDENTS:
                tg.start_soon(one, user)

    anyio.run(go)
    assert seen == {u: {m} for u, m in STUDENTS.items()}


def test_calls_are_audited_with_pseudonyms(live, tokens):
    call(live["url"], tokens["sv005"], "get_my_academic_decisions")
    ev = live["service"].access_log.events()[-1]
    assert ev.tool == "get_my_academic_decisions" and ev.allowed and ev.target != "2210005"
