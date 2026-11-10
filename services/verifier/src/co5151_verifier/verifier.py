from collections.abc import Callable, Sequence

from co5151_contracts import IssueCode, Verdict, VerdictStatus, VerificationIssue, VerificationRequest

Check = Callable[[VerificationRequest], list[VerificationIssue]]

# No rewrite can fix these: the evidence itself is missing, so the only safe reply is a refusal.
REFUSE_CODES = frozenset({IssueCode.MISSING_EVIDENCE})


class ComplianceVerifier:
    """Runs every check on the Advisor's draft and folds the issues they report into one verdict."""

    name: str = "verifier"

    def __init__(self, checks: Sequence[Check] = ()):
        self._checks = tuple(checks)

    def verify(self, request: VerificationRequest) -> Verdict:
        issues = [issue for check in self._checks for issue in check(request)]
        if not issues:
            return Verdict(status=VerdictStatus.PASS)
        refuse = any(issue.code in REFUSE_CODES for issue in issues)
        return Verdict(status=VerdictStatus.REFUSE if refuse else VerdictStatus.REVISE, issues=issues)
