from collections.abc import Callable, Sequence
from typing import Any, Protocol

from co5151_contracts import IssueCode, Verdict, VerdictStatus, VerificationIssue, VerificationRequest

Check = Callable[[VerificationRequest], list[VerificationIssue]]

# No rewrite can fix these, so the only safe reply is a refusal: the evidence is missing, or the draft could not
# be verified at all.
REFUSE_CODES = frozenset({IssueCode.MISSING_EVIDENCE, IssueCode.UNVERIFIED})


class Judge(Protocol):
    """A check that costs an LLM call and reports the tokens it used (see `judge.LLMJudge`)."""

    @property
    def is_available(self) -> bool: ...

    def review(self, request: VerificationRequest) -> Any: ...


class ComplianceVerifier:
    """Checks the Advisor's draft against its evidence and folds the issues found into one verdict.

    The free rule checks run first. The judge is only called for a draft that passed all of them, so a draft the
    rules already rejected never costs an LLM call.
    """

    name: str = "verifier"

    def __init__(self, checks: Sequence[Check] = (), *, judge: Judge | None = None):
        self._checks = tuple(checks)
        self._judge = judge

    def describe(self) -> dict[str, Any]:
        describe = getattr(self._judge, "describe", None)
        return {"rule_checks": len(self._checks), "judge": describe() if callable(describe) else None}

    def verify(self, request: VerificationRequest) -> Verdict:
        issues = [issue for check in self._checks for issue in check(request)]
        if issues or self._judge is None or not self._judge.is_available:
            return _verdict(issues)
        review = self._judge.review(request)
        return _verdict(review.issues, input_tokens=review.input_tokens, output_tokens=review.output_tokens)


def _verdict(issues: list[VerificationIssue], **tokens: int) -> Verdict:
    if not issues:
        return Verdict(status=VerdictStatus.PASS, **tokens)
    refuse = any(issue.code in REFUSE_CODES for issue in issues)
    return Verdict(status=VerdictStatus.REFUSE if refuse else VerdictStatus.REVISE, issues=issues, **tokens)
