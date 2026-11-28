"""Deterministic checks: no LLM call, so they run first and cost nothing.

They only flag what can be decided from the text alone. Whether a conclusion follows from the evidence is left to
the LLM judge.
"""

import re
import unicodedata
from collections.abc import Iterable

from co5151_contracts import IssueCode, VerificationIssue, VerificationRequest

from .verifier import Check

# Corpus-style provision ids: QD2933-2021-CL5.5, HCMUT-2749-2026-A2-THESIS, Dieu_24_LVTN
_ID = re.compile(r"(?<![\w.-])[A-Za-z][A-Za-z0-9]*(?:[-_][A-Za-z0-9]+(?:\.[0-9]+)*){2,}(?![\w-])")
# "Điều 24", "khoản 5.5"
_CLAUSE = re.compile(r"\b(?:điều|khoản)\s+(\d+(?:\.\d+)*)", re.IGNORECASE)
_NUMBER = re.compile(r"(?<![\d.])\d+(?:\.\d+)*")
# Session tokens of the Student Record MCP are `<base64url payload>.<signature>`; also catch a pasted header.
_TOKEN = re.compile(r"eyJ[\w-]{16,}\.[\w-]{16,}|Bearer\s+[\w.-]{16,}", re.IGNORECASE)


def _norm(text: str) -> str:
    return unicodedata.normalize("NFC", text).casefold()


def _cited_ids(draft: str) -> list[str]:
    return [m.group(0) for m in _ID.finditer(draft) if any(ch.isdigit() for ch in m.group(0))]


def _is_retrieved(cited: str, retrieved: Iterable[str]) -> bool:
    """The id itself, or the parent of a retrieved id (citing HCMUT-2749-2026-A2 for ...-A2-THESIS)."""
    cited = _norm(cited)
    return any(r == cited or r.startswith((cited + "-", cited + "_")) for r in retrieved)


def _clause_numbers(text: str) -> set[str]:
    return {m.group(1) for m in _CLAUSE.finditer(_norm(text))}


def _with_parts(numbers: Iterable[str]) -> set[str]:
    """`10.1` also supports "Điều 10" and "khoản 1 Điều 10", so add its dot-separated parts."""
    return {part for n in numbers for part in (n, *n.split("."))}


def cited_provisions_are_retrieved(request: VerificationRequest) -> list[VerificationIssue]:
    """Every provision the draft cites, by id or by "Điều/Khoản" number, must be in the retrieved excerpts.

    Numbers the user wrote in the question are not judged here: the draft may be denying them.
    """
    retrieved_ids = [_norm(r.id) for r in request.regulations]
    evidence_text = _norm(" ".join(f"{r.id} {r.title} {r.content}" for r in request.regulations))
    evidence_numbers = _with_parts(_NUMBER.findall(evidence_text))
    asked_numbers = _clause_numbers(request.question)

    unknown_ids = [c for c in dict.fromkeys(_cited_ids(request.draft)) if not _is_retrieved(c, retrieved_ids)]
    unknown_clauses = sorted(_clause_numbers(request.draft) - asked_numbers - evidence_numbers)
    if not unknown_ids and not unknown_clauses:
        return []

    cited = ", ".join([*unknown_ids, *(f"Điều/Khoản {n}" for n in unknown_clauses)])
    if not request.regulations:
        return [
            VerificationIssue(
                code=IssueCode.MISSING_EVIDENCE,
                message=f"Bản nháp trích dẫn {cited} nhưng không có đoạn quy chế nào được tra cứu.",
            )
        ]
    return [
        VerificationIssue(
            code=IssueCode.UNSUPPORTED_CITATION,
            message=f"Trích dẫn không có trong các đoạn quy chế đã tra cứu: {cited}.",
        )
    ]


# Record figures the draft states about the student. Only phrasings tied to the student ("bạn đã tích lũy 92",
# "92/128 tín chỉ", "ĐTBTL của bạn là 2.28") are read, never a figure of a regulation ("cần tích lũy 120 tín chỉ",
# "ĐTBTL từ 2.0 trở lên").
_EARNED = re.compile(r"\b(?:bạn|em)\s+(?:hiện\s+)?(?:đã\s+)?tích\s+lũy(?:\s+được)?\s*(?:là|:)?\s*(\d+)(?![\d.,])")
_OF_PROGRAM = re.compile(r"(?<![\d.,])(\d+)\s*/\s*(\d+)\s*(?:tín\s+chỉ|tc)\b")
_REMAINING = re.compile(
    r"\b(?:bạn|em)\s+(?:hiện\s+)?còn\s+thiếu\s+(\d+)\s*(?:tín\s+chỉ|tc)\s+(?:để|so\s+với)\s+(?:hoàn\s+thành|đủ)\s+"
    r"(?:chương\s+trình|ctđt)"
)
_CGPA = re.compile(
    r"(?:đtbtl|điểm\s+trung\s+bình\s+tích\s+lũy|cgpa|gpa)(?:\s*\([^)]{0,30}\))?"
    r"(?:\s+(?:của\s+bạn|của\s+em|hiện\s+tại|hiện\s+nay|hiện))*\s*(?:là|:|=)\s*(\d+[.,]\d+)(?!\s*/\s*10)"
)
CGPA_TOLERANCE = 0.005


def _stated(draft: str, facts: dict) -> list[tuple[str, float]]:
    """(fact name, value) for each record figure the draft states."""
    text = _norm(draft)
    out = [("credits_earned", float(m.group(1))) for m in _EARNED.finditer(text)]
    program = facts.get("program_credits")
    out += [("credits_earned", float(m.group(1))) for m in _OF_PROGRAM.finditer(text) if int(m.group(2)) == program]
    out += [("remaining_credits", float(m.group(1))) for m in _REMAINING.finditer(text)]
    for m in _CGPA.finditer(text):
        value = float(m.group(1).replace(",", "."))
        if value <= 4:  # a figure on the 10-point scale is not the CGPA of the record
            out.append(("cgpa", value))
    return out


LABELS = {"credits_earned": "số tín chỉ tích lũy", "remaining_credits": "số tín chỉ còn thiếu", "cgpa": "ĐTBTL"}


def record_figures_match(request: VerificationRequest) -> list[VerificationIssue]:
    """The record figures in the draft (credits earned, credits remaining, CGPA) equal `student_facts`."""
    facts = request.student_facts
    wrong = {}
    for name, value in _stated(request.draft, facts):
        actual = facts.get(name)
        if isinstance(actual, bool) or not isinstance(actual, int | float):
            continue  # not in the record: the judge decides (FACT_MISMATCH "không có trong đó")
        if abs(value - actual) > (CGPA_TOLERANCE if name == "cgpa" else 0):
            wrong.setdefault(name, (value, actual))
    return [
        VerificationIssue(
            code=IssueCode.FACT_MISMATCH,
            message=f"Bản nháp ghi {LABELS[name]} là {value:g} nhưng hồ sơ ghi {actual:g}.",
        )
        for name, (value, actual) in wrong.items()
    ]


def no_secrets(secrets: Iterable[str] = ()) -> Check:
    """A check that fails when the draft contains a session token or one of `secrets` (e.g. the prompt canary)."""
    forbidden = tuple(s for s in secrets if s)

    def check(request: VerificationRequest) -> list[VerificationIssue]:
        if _TOKEN.search(request.draft) or any(s in request.draft for s in forbidden):
            return [VerificationIssue(code=IssueCode.LEAK, message="Bản nháp chứa token phiên hoặc chuỗi bí mật.")]
        return []

    return check


def rule_checks(secrets: Iterable[str] = ()) -> tuple[Check, ...]:
    return (no_secrets(secrets), cited_provisions_are_retrieved, record_figures_match)
