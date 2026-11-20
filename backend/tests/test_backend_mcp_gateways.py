"""Gateways against the real MCP servers over HTTP (local ports), so a renamed tool turns these red."""

import pytest

from co5151_backend.infrastructure.mcp.gateways import McpRegulationGateway, McpStudentRecordGateway
from co5151_contracts import ErrorCode
from co5151_contracts.student import AcademicSummary

pytestmark = pytest.mark.anyio


async def test_student_tools_return_typed_data(student_mcp_url, student_token):
    token = student_token
    gateway = McpStudentRecordGateway(student_mcp_url)
    res = await gateway.call("get_my_academic_summary", token("sv003"))
    assert res.ok and isinstance(res.data, AcademicSummary) and res.data.student_id == "2310003"
    decisions = await gateway.call("get_my_academic_decisions", token("sv003"))
    assert decisions.ok and decisions.data.currently_warned is True


async def test_student_errors_survive_the_transport(student_mcp_url, student_token):
    token = student_token
    gateway = McpStudentRecordGateway(student_mcp_url)
    assert (await gateway.call("get_my_academic_summary", "")).error.code is ErrorCode.UNAUTHENTICATED
    assert (await gateway.call("get_my_academic_summary", "garbage")).error.code is ErrorCode.UNAUTHENTICATED
    other = await gateway.call("get_advisee_summary", token("sv003"), {"student_id": "2310002"})
    assert other.error.code is ErrorCode.FORBIDDEN
    assert (await gateway.call("no_such_tool", token("sv003"))).error.code is ErrorCode.NOT_FOUND


async def test_regulation_search_over_http(regulation_mcp_url):
    res = await McpRegulationGateway(regulation_mcp_url).call(
        "search_regulations", {"query": "Điều kiện làm luận văn tốt nghiệp", "top_k": 2, "hops": 1}
    )
    assert res.ok and res.data["results"]


async def test_unreachable_server_is_an_internal_error():
    res = await McpRegulationGateway("http://127.0.0.1:9/mcp").call("search_regulations", {"query": "x"})
    assert res.error.code is ErrorCode.INTERNAL
