from .agent import AgentResponse
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
