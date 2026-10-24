import time
from typing import Any

from co5151_eval.agent import AgentResponse, Outcome, Usage

from .executor import StudentExecutor
from .memory import DecisionTrace, MemoryGate
from .planner import Action, DecisionPlanner, Evidence
from .regulations import RegulationDocument, RegulationSource, StaticRegulationSource


class AdvisorAgent:
    """Decision-driven Advisor Agent that coordinates evidence retrieval, regulations, and safe responses."""

    name: str = "advisor"

    def __init__(
        self,
        service: Any,
        regulation_source: RegulationSource | None = None,
        memory_gate: MemoryGate | None = None,
    ):
        self.service = service
        self.executor = StudentExecutor(service)
        self.regulation_source = regulation_source or StaticRegulationSource()
        self.memory_gate = memory_gate or MemoryGate()
        self.planner = DecisionPlanner()
        self.traces: list[DecisionTrace] = []

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
                tool_calls.append("get_my_warnings")
                res = self.executor.call("get_my_warnings", token=session_token)
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
                response_text = self._synthesize_response(question, evidence, matched_regulations)
                # Sanitize to guarantee session token is NEVER echoed
                if session_token and session_token in response_text:
                    response_text = response_text.replace(session_token, "[REDACTED_TOKEN]")
                return AgentResponse(
                    text=response_text,
                    outcome=Outcome.ANSWER,
                    tool_calls=tool_calls,
                    citations=citations,
                    usage=Usage(input_tokens=50, output_tokens=50),
                )

        return AgentResponse(
            text="Không thể hoàn tất quy trình ra quyết định tư vấn.",
            outcome=Outcome.REFUSE,
            tool_calls=tool_calls,
            citations=citations,
        )

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
