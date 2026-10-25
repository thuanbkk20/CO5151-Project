from co5151_advisor.agent import AdvisorAgent
from co5151_advisor.llm import LLMResult
from co5151_advisor.regulations import StaticRegulationSource
from co5151_eval.agent import Outcome
from co5151_eval.gold import RecordOracle

ROUTER = "You are a strict next-action router"
GRADUATION_Q = "Với bảng điểm hiện tại em có đủ điều kiện đăng ký làm luận văn tốt nghiệp kỳ tới không?"


class ScriptedLLM:
    is_available = True

    def __init__(self, routes: list[str]):
        self.routes = list(routes)
        self.answer_prompts: list[str] = []

    def generate(self, prompt, system_prompt=None, history=None, seed=None):
        if system_prompt and system_prompt.startswith(ROUTER):
            return LLMResult(text=self.routes.pop(0) if self.routes else "RESPOND", input_tokens=7, output_tokens=1)
        self.answer_prompts.append(prompt)
        return LLMResult(text="Câu trả lời từ LLM.", input_tokens=100, output_tokens=20)


def _agent(llm=None):
    oracle = RecordOracle()
    return oracle, AdvisorAgent(oracle.service, StaticRegulationSource(), llm_client=llm)


def test_english_requirement_reaches_the_llm_prompt():
    llm = ScriptedLLM(["SUMMARY", "REGULATIONS", "RESPOND"])
    oracle, agent = _agent(llm)
    agent.answer(GRADUATION_Q, session_token=oracle.token("sv001"), history=[])
    assert "Chuẩn ngoại ngữ: TOEIC 500" in llm.answer_prompts[-1]


def test_template_answer_states_the_english_requirement():
    oracle, agent = _agent()
    resp = agent.answer(GRADUATION_Q, session_token=oracle.token("sv001"), history=[])
    assert "ngoại ngữ: TOEIC 500" in resp.text


def test_not_logged_in_skips_record_tools_and_answers_from_regulations():
    llm = ScriptedLLM(["SUMMARY", "SUMMARY", "WARNINGS"])
    _, agent = _agent(llm)
    resp = agent.answer("Điều kiện để được xét công nhận tốt nghiệp gồm những gì?", session_token=None, history=[])
    assert resp.tool_calls == ["search_regulations"]
    assert resp.text == "Câu trả lời từ LLM."
    assert "chưa đăng nhập" in llm.answer_prompts[-1]


def test_not_logged_in_rule_planner_does_not_refuse_a_general_question():
    _, agent = _agent()
    resp = agent.answer("Điều kiện để được xét công nhận tốt nghiệp gồm những gì?", session_token=None, history=[])
    assert resp.outcome is Outcome.ANSWER
    assert resp.tool_calls == ["search_regulations"]


def test_planner_tokens_are_counted_in_usage():
    llm = ScriptedLLM(["SUMMARY", "REGULATIONS", "RESPOND"])
    oracle, agent = _agent(llm)
    resp = agent.answer(GRADUATION_Q, session_token=oracle.token("sv001"), history=[])
    assert (resp.usage.input_tokens, resp.usage.output_tokens) == (3 * 7 + 100, 3 * 1 + 20)


def test_llm_written_answers_are_left_for_the_harness_to_classify():
    llm = ScriptedLLM(["SUMMARY", "RESPOND"])
    oracle, agent = _agent(llm)
    resp = agent.answer("Em đã tích lũy bao nhiêu tín chỉ?", session_token=oracle.token("sv001"), history=[])
    assert resp.outcome is None
