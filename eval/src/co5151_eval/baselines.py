"""Baselines to compare the Advisor with: fixed replies, a record template, and two LLM baselines (E1).

`zero_shot` is the same LLM with the Advisor's system prompt and nothing else: no tool, no record, no regulation.
`naive_rag` searches the regulations once with the question as asked and makes one LLM call: no planner, no record,
no Verifier. Both use the backend's LLM adapter and environment (`LLM_PROVIDER`, keys, `LLM_SEED`), so they run on
the same model as the Advisor.
"""

import asyncio
import os

from co5151_backend.application.agents.advisor import prompts
from co5151_backend.application.agents.advisor.advisor import ANSWER_MAX_OUTPUT_TOKENS
from co5151_backend.application.agents.advisor.tools import REGULATION_TOOL, RegulationSearch
from co5151_backend.application.ports import ChatModel, ChatTurn
from co5151_backend.infrastructure.llm import ProviderChatModels

from .agent import AgentResponse, RoleUsage, Usage
from .gold import RecordOracle
from .tasks import Outcome


class RefuseAll:
    name = "refuse_all"

    def answer(self, question, *, session_token, history):
        return AgentResponse(text="Xin lỗi, mình không thể trả lời câu hỏi này.", outcome=Outcome.REFUSE)


class RecordTemplate:
    name = "record_template"

    def __init__(self, oracle: RecordOracle | None = None):
        self._service = (oracle or RecordOracle()).service

    def answer(self, question, *, session_token, history):
        if session_token is None:
            return AgentResponse(text="Theo quy chế đào tạo hiện hành, bạn cần đáp ứng các điều kiện chung.",
                                 outcome=Outcome.ANSWER)  # fmt: skip
        res = self._service.call("get_my_academic_summary", session_token)
        calls = ["get_my_academic_summary"]
        if not res.ok:
            return AgentResponse(text=res.error.message, outcome=Outcome.REFUSE, tool_calls=calls)
        s = res.data
        text = (
            f"Hồ sơ của bạn: đã tích lũy {s.credits_earned}/{s.program_credits} tín chỉ, ĐTBTL {s.cgpa} "
            f"(thang 10: {s.cgpa10}), quy chế {s.ctdt}. "
            f"Đồ án chuyên ngành: {'đã đạt' if s.capstone_project_passed else 'chưa đạt'}. "
            f"Ngoại ngữ: {s.english_cert or 'chưa nộp chứng chỉ'}"
            f"{f' (TOEIC {s.toeic})' if s.toeic else ''}. "
            f"Giáo dục thể chất: {'đã hoàn thành' if s.gdtc_completed else 'chưa hoàn thành'}. "
            f"Cảnh báo học tập: {'đang bị cảnh báo' if s.currently_warned else 'không bị cảnh báo'}."
        )
        return AgentResponse(text=text, outcome=Outcome.ANSWER, tool_calls=calls)


def refuse_all(seed: int) -> RefuseAll:
    return RefuseAll()


def record_template(seed: int) -> RecordTemplate:
    return RecordTemplate()


def _model(seed: int | None) -> ChatModel:
    env = {**os.environ, "LLM_SEED": str(seed)} if seed is not None else None
    models = ProviderChatModels(env)
    model = models.create(models.default_provider(), None)
    if model is None:
        raise RuntimeError("no LLM key for LLM_PROVIDER: the LLM baselines need one")
    return model


NAIVE_RAG_INSTRUCTION = (
    "\nTrả lời câu hỏi chỉ dựa trên các đoạn quy chế trong <regulations>; không có căn cứ thì nói là chưa đủ căn cứ."
)


class LLMBaseline:
    """One LLM call per question; `naive_rag` adds one regulation search before it."""

    def __init__(self, name: str, model: ChatModel, regulations=None):
        self.name = name
        self._model = model
        self._search = RegulationSearch(regulations) if regulations is not None else None

    def describe(self) -> dict:
        return {"baseline": self.name, "llm": f"{self._model.provider}/{self._model.model}",
                "regulations": self._search is not None}  # fmt: skip

    def answer(self, question, *, session_token, history):
        return asyncio.run(self._answer(question, history))

    async def _answer(self, question: str, history: list[dict[str, str]]) -> AgentResponse:
        prompt, calls, citations = f"Câu hỏi của sinh viên: {question}", [], []
        if self._search is not None:
            docs = await self._search.search(question)
            calls, citations = [REGULATION_TOOL], [d.id for d in docs]
            text = "\n".join(f"[{d.id}] {d.title}: {d.content}" for d in docs) or "(không tìm thấy)"
            data = text.replace("</", "<\\/")  # a closing tag in retrieved text must not end the block
            prompt += f"\n\n<regulations>\n{data}\n</regulations>{NAIVE_RAG_INSTRUCTION}"
        turns = [ChatTurn(t["role"], t["content"]) for t in history]
        done = await self._model.complete(prompt, system=prompts.SYSTEM_PROMPT, history=turns,
                                          max_output_tokens=ANSWER_MAX_OUTPUT_TOKENS)  # fmt: skip
        llm = f"{self._model.provider}/{self._model.model}"
        usage = RoleUsage(role="writer", model=llm, input_tokens=done.input_tokens, output_tokens=done.output_tokens)
        return AgentResponse(text=prompts.sanitize(done.text, None), citations=citations, tool_calls=calls,
                             usage=Usage(input_tokens=done.input_tokens, output_tokens=done.output_tokens),
                             usage_by_role=[usage])  # fmt: skip


def zero_shot(seed: int) -> LLMBaseline:
    return LLMBaseline("zero_shot", _model(seed))


def naive_rag(seed: int) -> LLMBaseline:
    from .backend_agent import InProcessRegulations, _engine, regulation_service

    return LLMBaseline("naive_rag", _model(seed), InProcessRegulations(regulation_service(_engine())))
