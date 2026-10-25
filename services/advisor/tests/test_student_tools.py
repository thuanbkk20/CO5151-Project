from co5151_advisor.executor import StudentExecutor
from co5151_eval.gold import RecordOracle


def test_every_allowed_tool_exists_on_the_student_record_service():
    oracle = RecordOracle()
    executor = StudentExecutor(oracle.service)
    token = oracle.token("sv003")
    for tool in sorted(StudentExecutor.ALLOWED_TOOLS):
        result = executor.call(tool, token=token)
        assert result.ok, f"{tool}: {result.error_code}"


def test_warning_evidence_comes_from_academic_decisions():
    oracle = RecordOracle()
    result = StudentExecutor(oracle.service).call("get_my_academic_decisions", token=oracle.token("sv003"))
    assert result.evidence.warnings_checked and result.evidence.currently_warned
