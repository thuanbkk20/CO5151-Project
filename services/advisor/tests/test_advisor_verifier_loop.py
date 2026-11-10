from unittest.mock import MagicMock

import pytest

from co5151_advisor.agent import MAX_VERIFIER_ROUNDS, REFUSAL_UNGROUNDED, REFUSAL_UNVERIFIED, AdvisorAgent
from co5151_advisor.eval_adapter import make_agent, make_agent_no_verifier, make_verifier
from co5151_advisor.llm import CANARY_STRING, PROVIDERS, LLMClient, LLMResult
from co5151_advisor.planner import DecisionPlanner
from co5151_advisor.regulations import RegulationDocument
from co5151_contracts import IssueCode, Verdict, VerdictStatus, VerificationIssue, ok
from co5151_contracts.student import AcademicSummary
from co5151_eval.agent import Outcome
from co5151_eval.gold import RecordOracle
from co5151_verifier import ComplianceVerifier

QUESTION = "Với bảng điểm hiện tại em có đủ điều kiện đăng ký làm luận văn tốt nghiệp kỳ tới không?"
TOKEN = "valid-token-xyz"
PASS = Verdict(status=VerdictStatus.PASS, input_tokens=300, output_tokens=10)


def verdict(status: VerdictStatus, code: IssueCode, message: str = "lý do") -> Verdict:
    issue = VerificationIssue(code=code, message=message)
    return Verdict(status=status, issues=[issue], input_tokens=300, output_tokens=20)


REVISE = verdict(VerdictStatus.REVISE, IssueCode.UNGROUNDED_CLAIM, "Quy chế không nêu ngưỡng 105 tín chỉ.")
REFUSE = verdict(VerdictStatus.REFUSE, IssueCode.MISSING_EVIDENCE)
UNVERIFIED = verdict(VerdictStatus.REFUSE, IssueCode.UNVERIFIED)


class ScriptedVerifier:
    def __init__(self, *verdicts: Verdict):
        self.verdicts = list(verdicts)
        self.requests = []

    def verify(self, request):
        self.requests.append(request)
        return self.verdicts.pop(0)

    def describe(self):
        return {"rule_checks": 0, "judge": None}


def student_service():
    service = MagicMock()
    service.call.return_value = ok(
        AcademicSummary(
            student_id="2310001",
            cohort=2023,
            ctdt="2023",
            program_credits=128,
            credits_earned=113,
            cgpa=2.52,
            cgpa10=7.2,
            capstone_project_passed=True,
            toeic=500,
            english_cert=None,
            gdtc_completed=True,
            gdqp_completed=True,
            currently_warned=False,
            consecutive_warnings=0,
            retake_credits=0,
            last_semester="20252",
        )
    )
    return service


def regulations():
    source = MagicMock()
    source.search.return_value = [
        RegulationDocument(id="QD2933-2021-CL5.5", title="Khoản 5.5", content="5.5 Đăng ký các học phần tốt nghiệp")
    ]
    return source


def llm(*texts: str | None):
    client = MagicMock(spec=LLMClient)
    client.is_available = True
    client.generate.side_effect = [
        LLMResult(text=t, input_tokens=1000, output_tokens=100) if t is not None else None for t in texts
    ]
    return client


def agent(verifier, client=None) -> AdvisorAgent:
    # Rule planner, so the scripted LLM replies are only used for writing and rewriting the answer.
    return AdvisorAgent(
        student_service(), regulations(), llm_client=client, planner=DecisionPlanner(), verifier=verifier
    )


def test_passed_draft_is_sent_unchanged_and_counts_the_verifier_tokens():
    verifier, client = ScriptedVerifier(PASS), llm("Bạn đã tích lũy 113 tín chỉ.")
    resp = agent(verifier, client).answer(QUESTION, session_token=TOKEN, history=[])
    assert resp.text == "Bạn đã tích lũy 113 tín chỉ."
    assert (resp.outcome, resp.verifier_rounds) == (None, 1)
    assert (resp.usage.input_tokens, resp.usage.output_tokens) == (1000 + 300, 100 + 10)
    assert client.generate.call_count == 1


def test_verifier_sees_only_the_evidence_the_draft_was_written_from():
    verifier = ScriptedVerifier(PASS)
    agent(verifier, llm("Bạn đã tích lũy 113 tín chỉ.")).answer(QUESTION, session_token=TOKEN, history=[])
    request = verifier.requests[0]
    assert (request.question, request.draft) == (QUESTION, "Bạn đã tích lũy 113 tín chỉ.")
    assert request.student_facts["credits_earned"] == 113
    assert request.student_facts["english_cert"] is None
    assert "currently_warned" not in request.student_facts  # warnings were not looked up for this question
    assert [(r.id, r.content) for r in request.regulations] == [
        ("QD2933-2021-CL5.5", "5.5 Đăng ký các học phần tốt nghiệp")
    ]
    assert TOKEN not in request.model_dump_json() and "2310001" not in request.model_dump_json()


def test_revise_makes_the_advisor_rewrite_once_with_the_issues():
    verifier = ScriptedVerifier(REVISE, PASS)
    client = llm("Bạn đủ điều kiện vì đã đạt 105 tín chỉ.", "Bạn đã tích lũy 113 tín chỉ; quy chế chưa nêu ngưỡng.")
    resp = agent(verifier, client).answer(QUESTION, session_token=TOKEN, history=[])
    assert resp.text == "Bạn đã tích lũy 113 tín chỉ; quy chế chưa nêu ngưỡng."
    assert resp.verifier_rounds == 2
    assert client.generate.call_count == 2
    rewrite_prompt = client.generate.call_args_list[1].args[0]
    assert "[UNGROUNDED_CLAIM] Quy chế không nêu ngưỡng 105 tín chỉ." in rewrite_prompt
    assert "Bạn đủ điều kiện vì đã đạt 105 tín chỉ." in rewrite_prompt
    assert verifier.requests[1].draft == resp.text
    assert resp.usage.total == 2 * 1100 + 320 + 310


def test_a_rewrite_that_still_fails_is_refused_without_a_third_llm_call():
    verifier = ScriptedVerifier(REVISE, REVISE)
    client = llm("Bạn đủ điều kiện.", "Bạn vẫn đủ điều kiện.")
    resp = agent(verifier, client).answer(QUESTION, session_token=TOKEN, history=[])
    assert (resp.outcome, resp.text) == (Outcome.REFUSE, REFUSAL_UNGROUNDED)
    assert resp.verifier_rounds == MAX_VERIFIER_ROUNDS == 2
    assert client.generate.call_count == 2
    assert resp.citations == ["QD2933-2021-CL5.5"]


def test_refuse_verdict_is_a_strict_refusal_with_no_rewrite():
    verifier, client = ScriptedVerifier(REFUSE), llm("Bạn đủ điều kiện.")
    resp = agent(verifier, client).answer(QUESTION, session_token=TOKEN, history=[])
    assert (resp.outcome, resp.text, resp.verifier_rounds) == (Outcome.REFUSE, REFUSAL_UNGROUNDED, 1)
    assert client.generate.call_count == 1


def test_unverified_draft_is_refused_with_its_own_message():
    resp = agent(ScriptedVerifier(UNVERIFIED), llm("Bạn đủ điều kiện.")).answer(
        QUESTION, session_token=TOKEN, history=[]
    )
    assert (resp.outcome, resp.text) == (Outcome.REFUSE, REFUSAL_UNVERIFIED)


def test_revise_without_an_llm_to_rewrite_is_refused():
    for client in (None, llm(None, None)):
        resp = agent(ScriptedVerifier(REVISE), client).answer(QUESTION, session_token=TOKEN, history=[])
        assert (resp.outcome, resp.verifier_rounds) == (Outcome.REFUSE, 1)


def test_draft_is_sanitized_before_the_verifier_reads_it():
    verifier = ScriptedVerifier(PASS)
    agent(verifier, llm(f"Mã {CANARY_STRING}, token {TOKEN}.")).answer(QUESTION, session_token=TOKEN, history=[])
    assert CANARY_STRING not in verifier.requests[0].draft and TOKEN not in verifier.requests[0].draft


def test_refusals_and_clarifications_of_the_planner_are_not_verified():
    verifier = ScriptedVerifier()
    resp = agent(verifier).answer("Cho em xem điểm của sinh viên 2310002", session_token=TOKEN, history=[])
    assert (resp.outcome, resp.verifier_rounds) == (Outcome.REFUSE, None)
    assert verifier.requests == []


def test_without_a_verifier_nothing_changes():
    resp = agent(None, llm("Bạn đã tích lũy 113 tín chỉ.")).answer(QUESTION, session_token=TOKEN, history=[])
    assert (resp.text, resp.verifier_rounds, resp.usage.total) == ("Bạn đã tích lũy 113 tín chỉ.", None, 1100)


@pytest.fixture
def clean_env(monkeypatch):
    names = ["ADVISOR_VERIFIER", "VERIFIER_LLM_MODEL", "LLM_PROVIDER", "LLM_MODEL", "LLM_API_KEY", "LLM_BASE_URL"]
    for name in names + [p.key_env for p in PROVIDERS.values()]:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def test_verifier_mode_is_selected_by_environment(clean_env):
    client = LLMClient(provider="openai", model="advisor-model", api_key="k")
    assert make_verifier(client).describe()["judge"]["model"] == "advisor-model"
    clean_env.setenv("ADVISOR_VERIFIER", "rules")
    assert make_verifier(client).describe() == {"rule_checks": 2, "judge": None}
    clean_env.setenv("ADVISOR_VERIFIER", "off")
    assert make_verifier(client) is None


def test_verifier_can_use_its_own_model_of_the_same_provider(clean_env):
    clean_env.setenv("VERIFIER_LLM_MODEL", "small-model")
    judge = make_verifier(LLMClient(provider="openai", model="advisor-model", api_key="k")).describe()["judge"]
    assert (judge["provider"], judge["model"]) == ("openai", "small-model")


def test_eval_factories_differ_only_by_the_verifier(clean_env):
    with_verifier, single = make_agent(), make_agent_no_verifier()
    assert isinstance(with_verifier.verifier, ComplianceVerifier)
    assert with_verifier.describe()["verifier"] == {"rule_checks": 2, "judge": with_verifier.llm_client.describe()}
    assert single.verifier is None and single.describe()["verifier"] is None


def test_real_services_answer_through_the_rule_checks_without_an_llm(clean_env):
    oracle = RecordOracle()
    resp = make_agent().answer(QUESTION, session_token=oracle.token("sv002"), history=[])
    assert (resp.outcome, resp.verifier_rounds) == (Outcome.ANSWER, 1)
    assert "search_regulations" in resp.tool_calls
