import json

import anyio
import pytest

from co5151_contracts import STUDENT_RECORD_TOOLS
from student_server.config import Settings
from student_server.server import build_server

SETTINGS = Settings(token_secret=b"test-secret")


def run(coro_fn, *args):
    return anyio.run(coro_fn, *args)


@pytest.fixture
def make_server(service):
    def make(token=None):
        return build_server(service, SETTINGS, token_provider=lambda: token, protected=False)

    return make


def call(server, name, args=None):
    async def go():
        res = await server.call_tool(name, args or {})
        content = res.content if hasattr(res, "content") else res
        return json.loads(content[0].text)

    return run(go)


def test_tools_advertise_contract_schemas_and_read_only_hint(make_server):
    tools = {t.name: t for t in run(make_server().list_tools)}
    assert set(tools) == set(STUDENT_RECORD_TOOLS)
    for name, t in tools.items():
        schema = getattr(t, "input_schema", None) or t.inputSchema
        assert schema == STUDENT_RECORD_TOOLS[name].input_schema()
        hints = t.annotations.model_dump(by_alias=True)  # camelCase on the wire in both SDK majors
        assert hints["readOnlyHint"] is True and hints["destructiveHint"] is False


def test_tool_call_uses_the_provided_token(make_server, token):
    res = call(make_server(token("sv007")), "get_my_profile")
    assert res == {"ok": True, "data": res["data"]} and res["data"]["student_id"] == "2310007"


def test_without_token_tools_answer_unauthenticated(make_server):
    assert call(make_server(None), "get_my_academic_summary")["error"]["code"] == "UNAUTHENTICATED"


def test_contract_validation_applies_through_mcp(make_server, token):
    res = call(make_server(token("sv001")), "get_my_transcript", {"semester": "not-a-semester"})
    assert res["error"]["code"] == "INVALID_ARGUMENT"
