import pytest

from co5151_advisor.agent import AdvisorAgent
from co5151_advisor.llm import LLMResult
from co5151_advisor.planner import Action, Evidence, LLMDecisionPlanner
from co5151_advisor.regulations import StaticRegulationSource
from co5151_eval.gold import RecordOracle

GRADUATION_Q = "Với bảng điểm hiện tại em có đủ điều kiện đăng ký làm luận văn tốt nghiệp kỳ tới không?"
ROUTER = "You are a strict next-action router"


class StubbornLLM:
    is_available = True

    def __init__(self, route: str):
        self.route = route
        self.prompts: list[str] = []

    def generate(self, prompt, system_prompt=None, history=None, seed=None):
        self.prompts.append(prompt)
        if system_prompt and system_prompt.startswith(ROUTER):
            return LLMResult(text=self.route)
        return LLMResult(text="Câu trả lời từ LLM.", input_tokens=10, output_tokens=5)

    def describe(self):
        return {"provider": "stub"}


@pytest.mark.parametrize(
    "picked, evidence, expected",
    [
        ("SUMMARY", Evidence(), Action.SUMMARY),
        ("REGULATIONS", Evidence(regulations_checked=True), Action.SUMMARY),
        ("REGULATIONS", Evidence(regulations_checked=True, credits_earned=102), Action.RESPOND),
        ("SUMMARY", Evidence(credits_earned=102, regulations_checked=True), Action.RESPOND),
    ],
)
def test_a_step_already_done_is_not_repeated(picked, evidence, expected):
    planner = LLMDecisionPlanner(llm_client=StubbornLLM(picked))
    assert planner.next_action(GRADUATION_Q, evidence) is expected


def test_prompt_lists_completed_steps():
    llm = StubbornLLM("RESPOND")
    LLMDecisionPlanner(llm_client=llm).next_action(GRADUATION_Q, Evidence(regulations_checked=True))
    assert "Already completed, never choose again: REGULATIONS" in llm.prompts[-1]


def test_advisor_answers_even_when_the_llm_keeps_picking_the_same_step():
    oracle = RecordOracle()
    llm = StubbornLLM("REGULATIONS")
    agent = AdvisorAgent(oracle.service, StaticRegulationSource(), llm_client=llm)
    resp = agent.answer(GRADUATION_Q, session_token=oracle.token("sv001"), history=[])
    assert resp.outcome is None
    assert resp.text == "Câu trả lời từ LLM."
    assert "get_my_academic_summary" in resp.tool_calls
