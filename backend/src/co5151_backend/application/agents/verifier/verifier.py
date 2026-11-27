"""Compliance Verifier: checks the Advisor's draft against the evidence it was written from, returns one verdict.

The free rule checks run first; the LLM judge is only called for a draft that passed all of them, so a draft the
rules already rejected never costs an LLM call.
"""

from collections.abc import Callable, Sequence
from typing import Any, Protocol

from co5151_contracts import IssueCode, Verdict, VerdictStatus, VerificationIssue, VerificationRequest

Check = Callable[[VerificationRequest], list[VerificationIssue]]

# No rewrite can fix these, so the only safe reply is a refusal: nothing was retrieved for what the draft cites (a
# rule check), or the draft could not be verified at all.
REFUSE_CODES = frozenset({IssueCode.MISSING_EVIDENCE, IssueCode.UNVERIFIED})
# From the judge, MISSING_EVIDENCE asks for a rewrite: the Advisor can drop the unsupported conclusion or say the
# evidence is not enough. The judge also reported it for one side claim of an answer the evidence did support (first
# test on the deployment, 27/11). A draft still failing after the last round is refused anyway.
JUDGE_REFUSE_CODES = frozenset({IssueCode.UNVERIFIED})


class Judge(Protocol):
    """A check that costs an LLM call and reports the tokens it used (see `judge.LLMJudge`)."""

    async def review(self, request: VerificationRequest) -> Any: ...


class ComplianceVerifier:
    def __init__(self, checks: Sequence[Check] = (), *, judge: Judge | None = None):
        self._checks = tuple(checks)
        self._judge = judge

    @property
    def judges(self) -> bool:
        """Whether an LLM judge reads the question (then a follow-up question is worth making standalone)."""
        return self._judge is not None

    def describe(self) -> dict[str, Any]:
        describe = getattr(self._judge, "describe", None)
        return {"rule_checks": len(self._checks), "judge": describe() if callable(describe) else None}

    async def verify(self, request: VerificationRequest) -> Verdict:
        issues = [issue for check in self._checks for issue in check(request)]
        if issues or self._judge is None:
            return _verdict(issues, REFUSE_CODES)
        review = await self._judge.review(request)
        return _verdict(review.issues, JUDGE_REFUSE_CODES, input_tokens=review.input_tokens,
                        output_tokens=review.output_tokens)  # fmt: skip


def _verdict(issues: list[VerificationIssue], refuse_codes: frozenset[IssueCode], **tokens: int) -> Verdict:
    if not issues:
        return Verdict(status=VerdictStatus.PASS, **tokens)
    refuse = any(issue.code in refuse_codes for issue in issues)
    return Verdict(status=VerdictStatus.REFUSE if refuse else VerdictStatus.REVISE, issues=issues, **tokens)
