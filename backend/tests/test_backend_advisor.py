"""Advisor agent with fake gateways and a scripted LLM: no network, no real LLM call."""

import json
from pathlib import Path

import pytest

from co5151_backend.application.agents.advisor import prompts
from co5151_backend.application.agents.advisor.advisor import Advisor
from co5151_backend.application.agents.advisor.memory import MemoryGate, stated_preferences
from co5151_backend.application.agents.advisor.planner import (
    LLMActionRouter,
    Planner,
    looks_like_follow_up,
    parse_action,
    parse_rewrite,
)
from co5151_backend.application.agents.advisor.tools import RegulationSearch
from co5151_backend.application.ports import ChatTurn, Completion
from co5151_backend.domain.errors import LLMError
from co5151_backend.domain.evidence import Action, Evidence, Regulation
from co5151_backend.domain.trace import Outcome
from co5151_backend.infrastructure.laya import LayaActionRouter
from co5151_contracts import ErrorCode, IssueCode, Verdict, VerdictStatus, VerificationIssue, err, ok
from co5151_contracts.student import AcademicDecision, AcademicDecisions, AcademicSummary

pytestmark = pytest.mark.anyio

TOKEN = "student-token-xyz"
GRADUATION = "Với bảng điểm hiện tại em có đủ điều kiện làm luận văn tốt nghiệp kỳ tới không?"
CREDITS = "Em đã tích lũy bao nhiêu tín chỉ?"
SUMMARY = AcademicSummary(student_id="2310001", cohort=2023, ctdt="2023", program_credits=128, credits_earned=113,
                          cgpa=2.52, cgpa10=7.2, capstone_project_passed=True, toeic=None, english_cert=None,
                          gdtc_completed=True, gdqp_completed=True, currently_warned=False, consecutive_warnings=0,
                          retake_credits=0, last_semester="20252")  # fmt: skip
DECISIONS = AcademicDecisions(student_id="2310001", currently_warned=True, consecutive_warnings=1, decisions=[])
RESULT = {"id": "QD-CL5.5", "evidence": {"provision_id": "QD2933-2021-CL5.5", "title": "Khoản 5.5",
          "fragments": [{"text": "5.5 Đăng ký các học phần tốt nghiệp"}]}}  # fmt: skip


class Student:
    def __init__(self, *results):
        self.results = list(results)
        self.calls = []

    async def call(self, tool, token, args=None):
        self.calls.append(tool)
        if self.results:
            return self.results.pop(0)
        return ok(SUMMARY if tool == "get_my_academic_summary" else DECISIONS)


class Regulations:
    def __init__(self, results=None):
        self.results = [RESULT] if results is None else results
        self.calls = []

    async def call(self, tool, args):
        self.calls.append((tool, args))
        return ok({"results": self.results})


class Model:
    """A ChatModel that returns the queued replies (None: the call fails)."""

    provider, model = "fake", "fake-1"

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []

    async def complete(self, prompt, *, system, history=(), max_output_tokens, json_schema=None):
        self.calls.append({"prompt": prompt, "system": system, "history": list(history), "schema": json_schema})
        reply = self.replies.pop(0)
        if reply is None:
            raise LLMError("boom")
        return Completion(reply, input_tokens=100, output_tokens=10)


async def gather(question, *, student=None, regulations=None, token=TOKEN, router=None, history=(), **kw):
    advisor = Advisor(student or Student(), regulations or Regulations())
    seen = []

    async def emit(event):
        seen.append(event.data)

    return await advisor.gather(question, token=token, planner=Planner(router), history=history, emit=emit, **kw), seen


async def test_graduation_question_reads_the_record_then_the_regulations_by_rule():
    router_model = Model()
    g, seen = await gather(GRADUATION, router=LLMActionRouter(router_model))
    assert g.steps == ["SUMMARY", "REGULATIONS", "RESPOND"] and g.final_text is None
    assert g.tool_calls == ["get_my_academic_summary", "search_regulations"]
    assert g.evidence.credits_earned == 113 and g.citations == ["QD2933-2021-CL5.5"]
    assert router_model.calls == [] and g.usage.total == 0
    assert [e["name"] for e in seen] == ["plan", "tool", "plan", "tool", "plan"]


async def test_router_is_asked_only_where_the_rules_stop():
    router_model = Model('{"action": "REGULATIONS"}', '{"action": "RESPOND"}')
    g, _ = await gather(CREDITS, router=LLMActionRouter(router_model))
    assert g.steps == ["SUMMARY", "REGULATIONS", "RESPOND"] and len(router_model.calls) == 2
    assert g.usage.total == 220
    first = router_model.calls[0]
    assert first["schema"]["json_schema"]["schema"]["properties"]["action"]["enum"] == [
        "WARNINGS", "REGULATIONS", "CLARIFY", "REFUSE", "RESPOND"
    ]  # fmt: skip
    assert "<question>" in first["prompt"]


HISTORY = [ChatTurn("user", "Thời gian đào tạo tối đa là bao lâu?"), ChatTurn("assistant", "Tối đa 6 năm. " * 60)]


def routed(action="", standalone="", query="", clarify=""):
    reply = {"standalone_question": standalone, "regulation_query": query}
    if action:
        reply |= {"action": action, "clarify_question": clarify}
    return json.dumps(reply, ensure_ascii=False)


async def test_router_reads_the_conversation_and_writes_the_regulation_query():
    model = Model(routed("REGULATIONS", "Quá thời gian đào tạo tối đa thì bị xử lý thế nào?", "quá thời gian đào tạo"),
                  routed("RESPOND"))  # fmt: skip
    regs = Regulations()
    g, _ = await gather("Quá thời gian đó thì sao?", regulations=regs, router=LLMActionRouter(model), history=HISTORY)
    first = model.calls[0]
    assert "<history>\nuser: Thời gian đào tạo tối đa là bao lâu?\nassistant: Tối đa 6 năm." in first["prompt"]
    assert len(first["prompt"].split("assistant: ")[1].split("\n")[0]) == 300  # an answer is cut
    assert set(first["schema"]["json_schema"]["schema"]["required"]) == {
        "action", "standalone_question", "regulation_query", "clarify_question"}  # fmt: skip
    assert regs.calls[0][1]["query"] == "quá thời gian đào tạo" and "context" not in regs.calls[0][1]
    assert g.standalone_question == "Quá thời gian đào tạo tối đa thì bị xử lý thế nào?" and len(model.calls) == 2


async def test_a_follow_up_decided_by_the_rules_is_rewritten_once_before_the_search():
    model = Model(routed(standalone="Nếu rớt Đồ án chuyên ngành thì có được làm luận văn không?", query="luận văn"))
    regs = Regulations()
    question = "Thôi vậy, nếu em rớt đồ án thì có được làm luận văn không?"
    g, _ = await gather(question, regulations=regs, router=LLMActionRouter(model), history=HISTORY)
    assert g.steps == ["SUMMARY", "REGULATIONS", "RESPOND"] and len(model.calls) == 1
    assert model.calls[0]["schema"]["json_schema"]["name"] == "standalone_question"
    assert regs.calls[0][1]["query"] == "luận văn" and regs.calls[0][1]["context"] == {"cohort": 2023}
    assert g.usage.total == 110


async def test_no_rewrite_without_history_or_for_a_question_that_stands_alone():
    for history in ([], HISTORY):
        model = Model()
        g, _ = await gather(GRADUATION, router=LLMActionRouter(model), history=history, need_standalone=True)
        assert model.calls == [] and g.standalone_question is None


async def test_the_judge_gets_a_standalone_question_even_without_a_search():
    model = Model(routed("RESPOND"), routed(standalone="Em còn thiếu mấy tín chỉ để tốt nghiệp?"))
    g, _ = await gather("Cái đó em còn thiếu mấy tín chỉ?", router=LLMActionRouter(model), history=HISTORY,
                        need_standalone=True)  # fmt: skip
    assert g.steps == ["SUMMARY", "RESPOND"] and g.standalone_question == "Em còn thiếu mấy tín chỉ để tốt nghiệp?"
    assert len(model.calls) == 2


async def test_router_words_the_clarifying_question():
    model = Model(routed("CLARIFY", clarify="Bạn đang hỏi về môn nào?"))
    g, _ = await gather("Môn đó em có được học cải thiện không?", router=LLMActionRouter(model), history=HISTORY)
    assert (g.final_outcome, g.final_text) == (Outcome.CLARIFY, "Bạn đang hỏi về môn nào?")
    g, _ = await gather("Môn đó?", router=LLMActionRouter(Model(routed("CLARIFY", clarify="Môn nào"))))
    assert g.final_text == prompts.CLARIFY  # not a question: the fixed one


def test_rewrite_reply_parsing():
    assert parse_rewrite("nonsense") == {"standalone_question": None, "regulation_query": None,
                                         "clarify_question": None}  # fmt: skip
    long = routed(standalone="x" * 501, query=" a \n b ", clarify="Môn nào?")
    assert parse_rewrite(long) == {"standalone_question": None, "regulation_query": "a b", "clarify_question": None}
    assert parse_rewrite(routed("CLARIFY", clarify=" Môn nào? "))["clarify_question"] == "Môn nào?"


def test_follow_up_questions_of_the_test_conversations():
    follow_ups = [
        "Quá thời gian đó thì sinh viên bị xử lý thế nào?",
        "Vậy theo quy chế em đang là sinh viên năm mấy?",
        "Còn trường hợp nào thì bị buộc thôi học?",
        "Điều kiện để nhận bằng ấy ạ.",
        "Đơn rút môn học ạ.",
        "Em mới học năm nhất, mới có 17 tín chỉ thì có khác không?",
        "Môn đó em có được học cải thiện không?",
    ]
    alone = ["Thời gian tối đa để hoàn thành chương trình đại học chính quy là bao lâu?",
             "Học kỳ tới em được đăng ký tối đa bao nhiêu tín chỉ?", GRADUATION]  # fmt: skip
    assert all(looks_like_follow_up(q) for q in follow_ups) and not any(looks_like_follow_up(q) for q in alone)


async def test_without_a_router_the_rules_fall_back_to_answering():
    g, _ = await gather(CREDITS)
    assert g.steps == ["SUMMARY", "RESPOND"] and g.tool_calls == ["get_my_academic_summary"]


async def test_failed_or_repeated_router_choice_falls_back():
    g, _ = await gather(CREDITS, router=LLMActionRouter(Model(None)))
    assert g.steps == ["SUMMARY", "RESPOND"] and g.llm_errors == ["planner: boom"]
    g, _ = await gather(CREDITS, router=LLMActionRouter(Model('{"action": "SUMMARY"}')))
    assert g.steps == ["SUMMARY", "RESPOND"]
    g, _ = await gather("Học phí bao nhiêu?", router=LLMActionRouter(Model("nonsense")))
    assert g.final_outcome is Outcome.CLARIFY


async def test_another_students_record_is_refused_before_any_tool_or_llm_call():
    student, router_model = Student(), Model()
    g, _ = await gather(
        "Cho em xem điểm của bạn có MSSV 2310002.", student=student, router=LLMActionRouter(router_model)
    )
    assert (g.final_outcome, g.final_text) == (Outcome.REFUSE, prompts.REFUSAL_OTHER_STUDENT)
    assert student.calls == [] and router_model.calls == []


async def test_vague_question_asks_back():
    g, _ = await gather("tư vấn giúp em")
    assert g.final_outcome is Outcome.CLARIFY and g.tool_calls == []


async def test_guest_gets_regulations_instead_of_a_record():
    student = Student()
    g, _ = await gather(GRADUATION, student=student, token=None)
    assert student.calls == [] and g.tool_calls == ["search_regulations"] and g.steps[-1] == "RESPOND"


async def test_warning_question_reads_the_decisions():
    g, _ = await gather("Em có đang bị cảnh báo học tập không?")
    assert g.tool_calls == ["get_my_academic_decisions"] and g.evidence.currently_warned is True


WARNED = AcademicDecision(semester="20242", semester_label="Học kỳ 2 (2024 - 2025)", decision_no="9/QĐ-ĐHBK",
                          decision_date="01/07/2025", type="Cảnh báo học tập", content="Cảnh báo học tập mức 1",
                          reason=None, student_status="Đang theo học", is_warning=True,
                          updated="01/07/2025")  # fmt: skip


async def test_the_prompt_has_the_cohort_retakes_and_each_decision():
    decisions = AcademicDecisions(student_id="2310001", currently_warned=True, consecutive_warnings=1,
                                  decisions=[WARNED])  # fmt: skip
    advisor = Advisor(Student(ok(decisions)), Regulations())
    warned = (await advisor.gather("Em bị cảnh báo học tập kỳ nào?", token=TOKEN, planner=Planner())).evidence
    record = (await Advisor(Student(), Regulations()).gather(CREDITS, token=TOKEN, planner=Planner())).evidence
    evidence = warned.model_copy(
        update=record.model_dump(include={"cohort", "ctdt", "retake_credits", "credits_earned", "program_credits"})
    )
    assert evidence.cohort == 2023 and evidence.retake_credits == 0 and evidence.decisions[0].is_warning
    model = Model("ok")
    await advisor.write("q", evidence, model=model, history=[], token=TOKEN)
    prompt = model.calls[0]["prompt"]
    assert "Khóa tuyển sinh: 2023 · CTĐT: 2023" in prompt and "Quy chế áp dụng" not in prompt
    assert "Tín chỉ đã học lại: 0" in prompt and "các học kỳ từng bị cảnh báo: Học kỳ 2 (2024 - 2025)" in prompt
    assert "Học kỳ 2 (2024 - 2025): Cảnh báo học tập: Cảnh báo học tập mức 1 (9/QĐ-ĐHBK)" in prompt


async def test_internal_error_is_retried_once_others_are_refused_safely():
    student = Student(err(ErrorCode.INTERNAL, "x"))
    g, _ = await gather(CREDITS, student=student)
    assert student.calls == ["get_my_academic_summary"] * 2 and g.final_text is None
    student = Student(err(ErrorCode.UNAUTHENTICATED, "raw server detail"))
    g, _ = await gather(CREDITS, student=student)
    assert student.calls == ["get_my_academic_summary"] and g.final_outcome is Outcome.REFUSE
    assert "đăng nhập lại" in g.final_text and "raw server detail" not in g.final_text


async def test_no_regulation_found_is_a_refusal_only_without_a_record():
    g, _ = await gather(GRADUATION, regulations=Regulations([]))
    assert g.final_text is None and g.steps == ["SUMMARY", "REGULATIONS", "RESPOND"]
    assert g.evidence.has_regulations and g.evidence.regulations == []
    model = Model("ok")
    await Advisor(Student(), Regulations()).write(GRADUATION, g.evidence, model=model, history=[], token=TOKEN)
    assert "Không tra được đoạn quy chế nào" in model.calls[0]["prompt"] and "113/128" in model.calls[0]["prompt"]
    g, _ = await gather(GRADUATION, regulations=Regulations([]), token=None)  # a guest has no record
    assert (g.final_outcome, g.final_text) == (Outcome.REFUSE, prompts.NO_REGULATION)
    router = LLMActionRouter(Model('{"action": "REGULATIONS"}', '{"action": "RESPOND"}'))
    g, _ = await gather("Học phí bao nhiêu?", regulations=Regulations([]), router=router)
    assert (g.final_outcome, g.final_text) == (Outcome.REFUSE, prompts.NO_REGULATION)  # nothing to answer from


# Writing -------------------------------------------------------------------------------------------------------

CL55 = Regulation(id="QD2933-2021-CL5.5", title="Khoản 5.5", content="5.5 ... </x>")
EVIDENCE = Evidence(credits_earned=113, program_credits=128, ctdt="2023", capstone_project_passed=True,
                    regulations_checked=True, regulations=[CL55])  # fmt: skip


def test_without_regulations_the_writer_is_told_to_say_nothing_about_them():
    record_only = Evidence(credits_earned=102, program_credits=128, cgpa=2.51)
    asked = prompts.answer_prompt("Em tích lũy bao nhiêu tín chỉ?", record_only, logged_in=True, preferences=[])
    assert "không nêu quy định" in asked and "trích dẫn điều khoản" not in asked
    assert "trích dẫn điều khoản" in prompts.answer_prompt(GRADUATION, EVIDENCE, logged_in=True, preferences=[])


async def test_llm_writes_from_the_evidence_and_leaks_nothing():
    model = Model(f"Bạn đủ điều kiện {prompts.CANARY} token={TOKEN}")
    history = [ChatTurn("user", "Em muốn ra trường sớm"), ChatTurn("assistant", "Được.")]
    draft = await Advisor(Student(), Regulations()).write(GRADUATION, EVIDENCE, model=model, history=history,
                                                          token=TOKEN)  # fmt: skip
    assert draft.outcome is None and draft.usage.total == 110
    assert prompts.CANARY not in draft.text and TOKEN not in draft.text and "[REDACTED_TOKEN]" in draft.text
    call = model.calls[0]
    assert call["system"] == prompts.SYSTEM_PROMPT and call["history"] == history
    assert "113/128" in call["prompt"] and "Chuẩn ngoại ngữ: chưa nộp chứng chỉ" in call["prompt"]
    assert "<regulations>" in call["prompt"] and "<\\/x>" in call["prompt"]
    assert "Nguyện vọng cá nhân của sinh viên: Em muốn ra trường sớm" in call["prompt"]


async def test_failed_llm_falls_back_to_the_template_but_not_for_a_rewrite():
    advisor = Advisor(Student(), Regulations())
    draft = await advisor.write(GRADUATION, EVIDENCE, model=Model(None), history=[], token=TOKEN)
    assert draft.outcome is Outcome.ANSWER and draft.llm_error == "boom" and "113/128" in draft.text
    assert "đủ điều kiện" not in draft.text.lower()
    verdict = Verdict(
        status=VerdictStatus.REVISE, issues=[VerificationIssue(code=IssueCode.FACT_MISMATCH, message="x")]
    )
    assert await advisor.write(GRADUATION, EVIDENCE, model=None, history=[], token=TOKEN, revise=("d", verdict)) is None
    rewrite_model = Model("Bản sửa")
    rewritten = await advisor.write(GRADUATION, EVIDENCE, model=rewrite_model, history=[], token=TOKEN,
                                    revise=("bản cũ", verdict))  # fmt: skip
    assert rewritten.text == "Bản sửa" and "[FACT_MISMATCH] x" in rewrite_model.calls[0]["prompt"]


async def test_the_writer_sees_the_standalone_question():
    model = Model("ok")
    await Advisor(Student(), Regulations()).write("Cái đó thì sao?", EVIDENCE, model=model, history=HISTORY,
                                                  token=TOKEN, standalone="Điều kiện tốt nghiệp là gì?")  # fmt: skip
    assert "Câu hỏi đầy đủ (đã điền ngữ cảnh từ hội thoại): Điều kiện tốt nghiệp là gì?" in model.calls[0]["prompt"]


async def test_guest_prompt_asks_for_missing_details():
    model = Model("ok")
    await Advisor(Student(), Regulations()).write("Điều kiện tốt nghiệp?", Evidence(), model=model, history=[],
                                                  token=None)  # fmt: skip
    assert "chưa đăng nhập" in model.calls[0]["prompt"]


# Parts ---------------------------------------------------------------------------------------------------------


def test_router_reply_parsing():
    choices = [Action.REGULATIONS, Action.RESPOND]
    assert parse_action('{"action": "RESPOND"}', choices) is Action.RESPOND
    assert parse_action('```json\n{"action":"regulations"}\n```', choices) is Action.REGULATIONS
    assert parse_action("RESPOND", choices) is Action.RESPOND
    assert parse_action('{"action": "SUMMARY"}', choices) is None and parse_action("{bad", choices) is None


async def test_regulation_text_is_read_from_whichever_field_the_evidence_carries():
    regs = Regulations(
        [
            {
                "id": "a",
                "evidence": {"provision_id": "QD-CL5.5", "fragments": [{"text": "5.5 Đăng ký"}, {"text": "hp"}]},
            },
            {"id": "b", "evidence": {"provision_id": "A2", "fragments": None, "source_text": "Khi xét\n\nđiều kiện"}},
            {
                "id": "c",
                "evidence": {"provision_id": "FAQ-6", "text": "Hỏi đáp"},
                "citation": {"file_name": "f.pdf", "pdf_pages": [3, 4]},
            },  # fmt: skip
        ]
    )
    docs = await RegulationSearch(regs).search("luận văn")
    assert [d.content for d in docs] == ["5.5 Đăng ký hp", "Khi xét điều kiện", "Hỏi đáp"]
    assert docs[2].title == "c (f.pdf, trang 3-4)" and regs.calls[0][1]["top_k"] == 3


async def test_regulation_tool_error_yields_nothing():
    class Forbidden:
        async def call(self, tool, args):
            return err(ErrorCode.FORBIDDEN, "draft")

    assert await RegulationSearch(Forbidden()).search("tốt nghiệp") == []


async def test_every_eval_question_finds_regulations_with_text_in_the_real_corpus():
    import regulation_server
    from co5151_eval.tasks import load_tasks
    from regulation_server.regulation_service_v2 import RegulationServiceV2

    service = RegulationServiceV2(Path(regulation_server.__file__).resolve().parents[2], allow_draft=True)

    class Local:
        async def call(self, tool, args):
            return service.call(tool, args)

    search = RegulationSearch(Local())
    docs = [d for task in load_tasks() for d in await search.search(task.question)]
    assert docs and all(d.content and len(d.content) <= 1500 for d in docs)


async def test_laya_unreachable_is_no_decision():
    routed = await LayaActionRouter("http://127.0.0.1:9/v1/systemone", timeout=0.2).route("q", {}, list(Action))
    assert routed.action is None and routed.error.startswith("laya")


def test_memory_gate_keeps_preferences_and_rejects_identifiers():
    gate = MemoryGate()
    with pytest.raises(ValueError):
        gate.store("transcript", "x", source="user")
    for bad in ["MSSV 2310001", "Bearer abc.def-ghi", "diemso 9", "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0"]:
        with pytest.raises(ValueError):
            gate.store("preference", bad, source="user")
    assert gate.store("goal", "ra trường", source="user", ttl=10, current_time=0).is_expired(11)
    assert stated_preferences(["Em ưu tiên học hè", "Em muốn xem MSSV 2310002", "chào"]) == ["Em ưu tiên học hè"]


def test_english_certificate_is_said_once():
    assert prompts.english_status(Evidence(toeic=500, english_cert="TOEIC 500")) == "TOEIC 500"
    assert prompts.english_status(Evidence(toeic=500, english_cert="IELTS 6.0")) == "TOEIC 500, IELTS 6.0"
    assert prompts.english_status(Evidence()) == "chưa nộp chứng chỉ"


def test_fixed_replies_r1_r2_follow_the_use_cases():
    doc = (Path(__file__).parents[2] / "docs/design/use-cases.md").read_text("utf-8")
    assert f'"{prompts.LIMIT_REACHED}"' in doc and f'"{prompts.REFUSAL_UNGROUNDED}"' in doc
    for text in (prompts.CLARIFY, prompts.INCOMPLETE, prompts.REFUSAL_OTHER_STUDENT, prompts.REFUSAL_UNVERIFIED):
        assert "Tôi" not in text and "bạn" in text.lower()


def test_the_writer_span_keeps_the_seed_of_the_run():
    from co5151_backend.application.agents.advisor.advisor import Draft, _writer_output

    model = Model()
    model.seed = 1
    assert _writer_output(Draft("x", None), model) == {"text": "x", "by": "fake/fake-1", "seed": 1}
    assert "seed" not in _writer_output(Draft("x", Outcome.ANSWER), model)  # a template uses no LLM
