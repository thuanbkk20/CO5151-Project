import os
import time
from typing import Any

from co5151_eval.agent import AgentResponse, Outcome, Usage

from .executor import StudentExecutor
from .llm import CANARY_STRING, LLMClient
from .memory import DecisionTrace, MemoryGate
from .planner import Action, DecisionPlanner, Evidence, LayaDecisionPlanner, LLMDecisionPlanner
from .regulations import RegulationDocument, RegulationSource, StaticRegulationSource


class AdvisorAgent:
    """Decision-driven Advisor Agent that coordinates evidence retrieval, regulations, and safe responses."""

    name: str = "advisor"

    def __init__(
        self,
        service: Any,
        regulation_source: RegulationSource | None = None,
        memory_gate: MemoryGate | None = None,
        llm_client: LLMClient | None = None,
        planner: DecisionPlanner | LayaDecisionPlanner | LLMDecisionPlanner | None = None,
    ):
        self.service = service
        self.executor = StudentExecutor(service)
        self.regulation_source = regulation_source or StaticRegulationSource()
        self.memory_gate = memory_gate or MemoryGate()
        self.llm_client = llm_client
        if planner is not None:
            self.planner = planner
        else:
            mode = os.environ.get("ADVISOR_PLANNER_MODE", "llm").strip().lower()
            if mode == "laya":
                self.planner = LayaDecisionPlanner()
            elif mode == "rule":
                self.planner = DecisionPlanner()
            else:
                self.planner = LLMDecisionPlanner(llm_client=self.llm_client)
        self.traces: list[DecisionTrace] = []

    def describe(self) -> dict[str, Any]:
        return {
            "llm": self.llm_client.describe() if self.llm_client else None,
            "planner": type(self.planner).__name__,
            "regulation_source": type(self.regulation_source).__name__,
        }

    def answer(
        self,
        question: str,
        *,
        session_token: str | None,
        history: list[dict[str, str]],
    ) -> AgentResponse:
        # Check and safely store user-stated preferences
        self.memory_gate.process_user_statement(question)

        tool_calls: list[str] = []
        citations: list[str] = []
        matched_regulations: list[RegulationDocument] = []
        evidence = Evidence()

        # Execute decision planning loop (step-by-step state machine)
        max_steps = 5
        for _ in range(max_steps):
            action = self.planner.next_action(question, evidence, history)

            if action == Action.REFUSE:
                self.traces.append(DecisionTrace(action="REFUSE", sources=[], created_at=time.time()))
                return AgentResponse(
                    text="Yêu cầu bị từ chối: Hệ thống không cho phép tra cứu thông tin của sinh viên khác.",
                    outcome=Outcome.REFUSE,
                    tool_calls=tool_calls,
                    citations=citations,
                )

            if action == Action.CLARIFY:
                self.traces.append(DecisionTrace(action="CLARIFY", sources=[], created_at=time.time()))
                return AgentResponse(
                    text="Bạn vui lòng cho mình biết nội dung cần tư vấn (ví dụ: tín chỉ, tốt nghiệp, cảnh báo)?",
                    outcome=Outcome.CLARIFY,
                    tool_calls=tool_calls,
                    citations=citations,
                )

            if action == Action.SUMMARY:
                self.traces.append(DecisionTrace(action="SUMMARY", sources=["student_mcp"], created_at=time.time()))
                tool_calls.append("get_my_academic_summary")
                res = self.executor.call("get_my_academic_summary", token=session_token)
                if not res.ok:
                    return AgentResponse(
                        text=res.error or "Không thể đọc dữ liệu học vụ.",
                        outcome=Outcome.REFUSE,
                        tool_calls=tool_calls,
                        citations=citations,
                    )
                # Keep existing regulations if any, merge academic summary evidence
                evidence = res.evidence.model_copy(
                    update={
                        "regulations_checked": evidence.regulations_checked,
                        "regulations": evidence.regulations,
                        "warnings_checked": evidence.warnings_checked,
                    }
                )
                continue

            if action == Action.WARNINGS:
                self.traces.append(DecisionTrace(action="WARNINGS", sources=["student_mcp"], created_at=time.time()))
                tool_calls.append("get_my_academic_decisions")
                res = self.executor.call("get_my_academic_decisions", token=session_token)
                if not res.ok:
                    return AgentResponse(
                        text=res.error or "Không thể đọc dữ liệu cảnh báo.",
                        outcome=Outcome.REFUSE,
                        tool_calls=tool_calls,
                        citations=citations,
                    )
                evidence = res.evidence.model_copy(
                    update={
                        "credits_earned": evidence.credits_earned,
                        "program_credits": evidence.program_credits,
                        "remaining_credits": evidence.remaining_credits,
                        "cgpa": evidence.cgpa,
                        "capstone_project_passed": evidence.capstone_project_passed,
                        "gdtc_completed": evidence.gdtc_completed,
                        "gdqp_completed": evidence.gdqp_completed,
                        "ctdt": evidence.ctdt,
                    }
                )
                continue

            if action == Action.REGULATIONS:
                self.traces.append(
                    DecisionTrace(action="REGULATIONS", sources=["regulation_source"], created_at=time.time())
                )
                docs = self.regulation_source.search(question, ctdt=evidence.ctdt)
                if not docs:
                    return AgentResponse(
                        text="Tôi chưa có nguồn quy chế đáng tin cậy để kết luận điều kiện này.",
                        outcome=Outcome.REFUSE,
                        tool_calls=tool_calls,
                        citations=citations,
                    )
                matched_regulations.extend(docs)
                citations.extend([doc.id for doc in docs])
                evidence = evidence.model_copy(
                    update={
                        "regulations_checked": True,
                        "regulations": [doc.id for doc in docs],
                    }
                )
                continue

            if action == Action.RESPOND:
                self.traces.append(DecisionTrace(action="RESPOND", sources=[], created_at=time.time()))
                usage = Usage(input_tokens=50, output_tokens=50)
                response_text = ""

                if self.llm_client and self.llm_client.is_available:
                    prompt = self._build_llm_prompt(question, evidence, matched_regulations)
                    llm_res = self.llm_client.generate(prompt, history=history)
                    if llm_res and llm_res.text:
                        response_text = llm_res.text
                        usage = Usage(input_tokens=llm_res.input_tokens, output_tokens=llm_res.output_tokens)

                if not response_text:
                    response_text = self._synthesize_response(question, evidence, matched_regulations)

                # Defense against canary leak (R6)
                if CANARY_STRING in response_text:
                    response_text = response_text.replace(CANARY_STRING, "")

                # Sanitize to guarantee session token is NEVER echoed
                if session_token and session_token in response_text:
                    response_text = response_text.replace(session_token, "[REDACTED_TOKEN]")

                return AgentResponse(
                    text=response_text,
                    outcome=Outcome.ANSWER,
                    tool_calls=tool_calls,
                    citations=citations,
                    usage=usage,
                )

        return AgentResponse(
            text="Không thể hoàn tất quy trình ra quyết định tư vấn.",
            outcome=Outcome.REFUSE,
            tool_calls=tool_calls,
            citations=citations,
        )

    def _build_llm_prompt(
        self,
        question: str,
        evidence: Evidence,
        regulations: list[RegulationDocument],
    ) -> str:
        prompt_parts = [f"Câu hỏi của sinh viên: {question}\n\nBằng chứng học vụ cá nhân đã xác thực:"]
        if evidence.has_academic_summary:
            prompt_parts.append(
                f"- Tín chỉ tích lũy: {evidence.credits_earned}/{evidence.program_credits}\n"
                f"- Điểm TB tích lũy (CGPA thang 4): {evidence.cgpa}\n"
                f"- Quy chế áp dụng: {evidence.ctdt}\n"
                f"- Đồ án chuyên ngành: {'Đã đạt' if evidence.capstone_project_passed else 'Chưa đạt'}\n"
                f"- GDTC: {'Hoàn thành' if evidence.gdtc_completed else 'Chưa hoàn thành'}\n"
                f"- GDQP-AN: {'Hoàn thành' if evidence.gdqp_completed else 'Chưa hoàn thành'}"
            )
        if evidence.has_warnings:
            prompt_parts.append(
                f"- Trạng thái cảnh báo: {'Đang bị cảnh báo' if evidence.currently_warned else 'Không bị cảnh báo'} "
                f"(số lần: {evidence.consecutive_warnings})"
            )
        if regulations:
            prompt_parts.append("\nVăn bản quy chế đào tạo trích dẫn:")
            for doc in regulations:
                prompt_parts.append(f"[{doc.id}] {doc.title}: {doc.content}")

        prefs = self.memory_gate.get_items(kind="preference")
        if prefs:
            prompt_parts.append(f"\nNguyện vọng cá nhân của sinh viên: {', '.join([p.value for p in prefs])}")

        prompt_parts.append(
            "\nHãy trả lời câu hỏi của sinh viên một cách rõ ràng, chính xác, nêu cụ thể các số liệu facts "
            "và trích dẫn điều khoản quy chế tương ứng."
        )
        return "\n".join(prompt_parts)

    def _synthesize_response(
        self,
        question: str,
        evidence: Evidence,
        regulations: list[RegulationDocument],
    ) -> str:
        parts: list[str] = []

        if evidence.has_warnings:
            status = "đang bị cảnh báo học tập" if evidence.currently_warned else "không bị cảnh báo học tập"
            parts.append(
                f"Trạng thái cảnh báo: Bạn {status} (số lần cảnh báo liên tiếp: {evidence.consecutive_warnings})."
            )

        if evidence.has_academic_summary:
            capstone_status = "đã đạt" if evidence.capstone_project_passed else "chưa đạt"
            parts.append(
                f"Hồ sơ học vụ của bạn: Đã tích lũy {evidence.credits_earned}/{evidence.program_credits} tín chỉ, "
                f"ĐTBTL {evidence.cgpa}, {capstone_status} Đồ án chuyên ngành, quy chế {evidence.ctdt}."
            )

        if regulations:
            reg_notes = " ".join([d.content for d in regulations])
            parts.append(f"Căn cứ theo quy chế đào tạo: {reg_notes}")

        if any(k in question.lower() for k in ["đủ điều kiện", "luận văn", "lvtn", "tốt nghiệp"]):
            is_eligible = bool(
                evidence.credits_earned and evidence.credits_earned >= 105 and evidence.capstone_project_passed
            )
            verdict = "Đủ điều kiện" if is_eligible else "Chưa đủ điều kiện"
            parts.insert(0, f"{verdict}:")

        return " ".join(parts) if parts else "Đã hoàn thành tra cứu thông tin học vụ theo yêu cầu của bạn."
