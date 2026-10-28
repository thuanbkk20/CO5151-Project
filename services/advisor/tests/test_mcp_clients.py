import pytest

from co5151_advisor.eval_adapter import regulation_source, student_service
from co5151_advisor.executor import StudentExecutor
from co5151_advisor.mcp_clients import McpRegulationService, McpStudentService
from co5151_advisor.regulations import ToolRegulationSource
from co5151_contracts import ErrorCode
from co5151_eval.gold import RecordOracle
from co5151_eval.security import local_server


@pytest.fixture(scope="module")
def student_mcp():
    oracle = RecordOracle()
    with local_server(oracle) as url:
        yield oracle, McpStudentService(url)


def test_student_tools_go_over_http_and_match_the_in_process_service(student_mcp):
    oracle, remote = student_mcp
    token = oracle.token("sv003")
    over_mcp = remote.call("get_my_academic_summary", token)
    assert over_mcp.ok
    assert over_mcp.data == oracle.service.call("get_my_academic_summary", token).data


def test_executor_works_unchanged_on_the_mcp_client(student_mcp):
    oracle, remote = student_mcp
    token = oracle.token("sv003")
    for tool in sorted(StudentExecutor.ALLOWED_TOOLS):
        result = StudentExecutor(remote).call(tool, token=token)
        assert result.ok, f"{tool}: {result.error_code}"


def test_scope_and_auth_errors_survive_the_transport(student_mcp):
    oracle, remote = student_mcp
    assert remote.call("get_my_academic_summary", None).error.code == ErrorCode.UNAUTHENTICATED
    assert remote.call("get_my_academic_summary", "garbage").error.code == ErrorCode.UNAUTHENTICATED
    forbidden = remote.call("get_advisee_summary", oracle.token("sv003"), {"student_id": "2310002"})
    assert forbidden.error.code == ErrorCode.FORBIDDEN
    assert remote.call("no_such_tool", oracle.token("sv003")).error.code == ErrorCode.NOT_FOUND


def test_unreachable_server_is_an_internal_error():
    res = McpStudentService("http://127.0.0.1:9/mcp").call("get_my_academic_summary", "x")
    assert res.error.code == ErrorCode.INTERNAL


def test_regulation_tools_go_through_a_stdio_subprocess():
    service = McpRegulationService()
    try:
        docs = ToolRegulationSource(service).search("Điều kiện làm đồ án tốt nghiệp")
        assert docs and all(d.id and d.content for d in docs)
        assert service.call("get_provision", {"provision_id": docs[0].id}).ok
    finally:
        service.close()


def test_transport_is_selected_by_environment(monkeypatch):
    local = object()
    monkeypatch.delenv("ADVISOR_STUDENT_TRANSPORT", raising=False)
    assert student_service(local) is local
    monkeypatch.setenv("ADVISOR_STUDENT_TRANSPORT", "mcp")
    monkeypatch.setenv("STUDENT_MCP_PORT", "9123")
    monkeypatch.delenv("STUDENT_MCP_URL", raising=False)
    assert student_service(local).url == "http://127.0.0.1:9123/mcp"
    monkeypatch.setenv("ADVISOR_REGULATION_TRANSPORT", "mcp")
    monkeypatch.delenv("ADVISOR_REGULATION_SOURCE", raising=False)
    source = regulation_source()
    assert isinstance(source._service, McpRegulationService)
    source._service.close()
