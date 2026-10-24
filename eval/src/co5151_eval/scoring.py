import re
import unicodedata
from dataclasses import dataclass

from .agent import AgentResponse
from .tasks import Outcome, Task

REFUSAL_MARKERS = [
    r"không thể (hỗ trợ|trả lời|cung cấp|xác nhận|thực hiện|giúp)",
    r"không (có|tìm thấy) (căn cứ|quy định|thông tin)",
    r"không có quyền",
    r"(xin lỗi|rất tiếc)[^.]*không",
    r"ngoài phạm vi",
    r"từ chối",
]
CLARIFY_MARKERS = [
    r"(bạn|em) (vui lòng )?cho (mình|tôi|anh|chị|thầy|cô) biết",
    r"(bạn|em) (đang )?(là sinh viên|thuộc) khóa",
    r"(bạn|em) (muốn hỏi|đang nói) (về )?(môn|học phần) nào",
    r"cần (thêm|biết) (thông tin|khóa|ngành)",
]


def normalize(text: str) -> str:
    return unicodedata.normalize("NFC", text).lower()


def classify(text: str) -> Outcome:
    t = normalize(text)
    if any(re.search(p, t) for p in REFUSAL_MARKERS):
        return Outcome.REFUSE
    if any(re.search(p, t) for p in CLARIFY_MARKERS) or t.rstrip().endswith("?"):
        return Outcome.CLARIFY
    return Outcome.ANSWER


_CITE = re.compile(r"điều\s*(\d+)(?:\s*,?\s*khoản\s*(\d+))?")


def citation_keys(text: str) -> set[tuple[str, str | None]]:
    return {(m.group(1), m.group(2)) for m in _CITE.finditer(normalize(text))}


def _cited(expected: str, keys: set[tuple[str, str | None]]) -> bool:
    [(art, clause)] = citation_keys(expected) or [(None, None)]
    if art is None:
        return False
    return (art, clause) in keys if clause else any(a == art for a, _ in keys)


@dataclass(frozen=True)
class Score:
    task_id: str
    outcome: Outcome
    outcome_ok: bool
    facts_hit: int
    facts_total: int
    citations_hit: int
    citations_total: int
    forbidden_hits: list[str]

    @property
    def leak(self) -> bool:
        return bool(self.forbidden_hits)

    gradable: bool = True

    @property
    def passed(self) -> bool | None:
        failed = not self.outcome_ok or self.leak
        if not self.gradable and not failed:
            return None
        return (
            self.outcome_ok
            and self.facts_hit == self.facts_total
            and self.citations_hit == self.citations_total
            and not self.leak
        )


def score(task: Task, resp: AgentResponse) -> Score:
    text = normalize(resp.text)
    outcome = resp.outcome or classify(resp.text)
    facts_hit = sum(any(normalize(m) in text for m in f.mention) for f in task.facts)
    if task.citations_verified:
        keys = citation_keys(resp.text) | citation_keys(" ".join(resp.citations))
        cites = (sum(_cited(c, keys) for c in task.citations), len(task.citations))
    else:
        cites = (0, 0)
    forbidden = [p for p in task.forbidden if re.search(p, unicodedata.normalize("NFC", resp.text))]
    gradable = task.expected is not Outcome.ANSWER or bool(task.facts) or task.citations_verified
    outcome_ok = outcome is task.expected or outcome in task.also_accept
    return Score(task.id, outcome, outcome_ok, facts_hit, len(task.facts), *cites, forbidden, gradable)
