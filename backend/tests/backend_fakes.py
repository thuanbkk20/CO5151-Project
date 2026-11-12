"""Fakes shared by the use-case and API tests: gateways, a scripted LLM, a scripted Verifier. No network, no LLM."""

from co5151_backend.application.agents.advisor.advisor import Advisor
from co5151_backend.application.ports import Completion
from co5151_backend.application.usecases.ask import AskQuestion
from co5151_backend.application.usecases.auth import Authenticate, SignIn
from co5151_backend.application.usecases.conversations import Conversations
from co5151_backend.domain.errors import LLMError
from co5151_backend.infrastructure.identity import DemoAccountDirectory, JwtAccessTokens, SignedStudentTokens
from co5151_backend.infrastructure.persistence.memory import InMemoryChatRepository, InMemoryTraceRepository
from co5151_contracts import IssueCode, Verdict, VerdictStatus, VerificationIssue, ok
from co5151_contracts.student import AcademicDecisions, AcademicSummary

GRADUATION = "Với bảng điểm hiện tại em có đủ điều kiện làm luận văn tốt nghiệp kỳ tới không?"
SUMMARY = AcademicSummary(student_id="2310001", cohort=2023, ctdt="2023", program_credits=128, credits_earned=113,
                          cgpa=2.52, cgpa10=7.2, capstone_project_passed=True, toeic=500, english_cert=None,
                          gdtc_completed=True, gdqp_completed=True, currently_warned=False, consecutive_warnings=0,
                          retake_credits=0, last_semester="20252")  # fmt: skip
DECISIONS = AcademicDecisions(student_id="2310001", currently_warned=False, consecutive_warnings=0, decisions=[])
REGULATION = {"id": "r", "evidence": {"provision_id": "QD2933-2021-CL5.5", "title": "Khoản 5.5",
              "fragments": [{"text": "5.5 Đăng ký các học phần tốt nghiệp"}]}}  # fmt: skip
PASS = Verdict(status=VerdictStatus.PASS, input_tokens=300, output_tokens=10)


def verdict(status: VerdictStatus, code: IssueCode, message: str = "lý do") -> Verdict:
    issue = VerificationIssue(code=code, message=message)
    return Verdict(status=status, issues=[issue], input_tokens=300, output_tokens=20)


REVISE = verdict(VerdictStatus.REVISE, IssueCode.UNGROUNDED_CLAIM, "Quy chế không nêu ngưỡng 105 tín chỉ.")
REFUSE = verdict(VerdictStatus.REFUSE, IssueCode.MISSING_EVIDENCE)
UNVERIFIED = verdict(VerdictStatus.REFUSE, IssueCode.UNVERIFIED)


class Student:
    def __init__(self, fail: Exception | None = None):
        self.calls: list[tuple[str, str]] = []
        self.fail = fail

    async def call(self, tool, token, args=None):
        if self.fail:
            raise self.fail
        self.calls.append((tool, token))
        return ok(SUMMARY if tool == "get_my_academic_summary" else DECISIONS)


class Regulations:
    async def call(self, tool, args):
        return ok({"results": [REGULATION]})


class Model:
    provider, model = "fake", "fake-1"

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls: list[dict] = []

    async def complete(self, prompt, *, system, history=(), max_output_tokens, json_schema=None):
        self.calls.append({"prompt": prompt, "history": list(history)})
        reply = self.replies.pop(0)
        if reply is None:
            raise LLMError("boom")
        return Completion(reply, input_tokens=1000, output_tokens=100)


class Models:
    """ChatModels with one fake provider; `model` is returned for every conversation (None: no key)."""

    def __init__(self, model: Model | None):
        self.model = model

    def providers(self):
        return ["fake"] if self.model else []

    def default_provider(self):
        return "fake"

    def create(self, provider, model):
        return self.model


class ScriptedVerifier:
    def __init__(self, *verdicts: Verdict):
        self.verdicts = list(verdicts)
        self.requests = []

    async def verify(self, request):
        self.requests.append(request)
        return self.verdicts.pop(0)


class App:
    """The use cases wired to in-memory and fake adapters."""

    def __init__(self, *replies, verifier=None, student=None, use_llm=True):
        self.model = Model(*replies) if use_llm else None
        self.models = Models(self.model)
        self.chats = InMemoryChatRepository()
        self.traces = InMemoryTraceRepository(self.chats)
        self.student = student or Student()
        self.verifier = verifier
        accounts = DemoAccountDirectory()
        self.tokens = JwtAccessTokens(b"backend-test-secret-of-32-bytes!", ttl=600)
        self.sign_in = SignIn(accounts, self.tokens)
        self.authenticate = Authenticate(self.tokens)
        self.conversations = Conversations(self.chats, self.traces, self.models)
        self.ask = AskQuestion(
            chats=self.chats,
            traces=self.traces,
            accounts=accounts,
            student_tokens=SignedStudentTokens(b"student-secret", ttl=60),
            models=self.models,
            advisor=Advisor(self.student, Regulations()),
            router_for=lambda model: None,  # rule planner: the scripted replies only write answers
            verifier_for=lambda model: self.verifier,
            history_messages=4,
        )
