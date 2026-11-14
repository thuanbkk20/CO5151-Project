import pytest

from co5151_backend.application.agents.verifier import ComplianceVerifier
from co5151_contracts import IssueCode, VerdictStatus, VerificationIssue, VerificationRequest

pytestmark = pytest.mark.anyio

REQUEST = VerificationRequest(question="Em đủ điều kiện làm luận văn chưa?", draft="Bạn đủ điều kiện.")


def reports(*codes: IssueCode):
    return lambda request: [VerificationIssue(code=code, message=code.value) for code in codes]


async def test_no_issue_is_a_pass():
    verdict = await ComplianceVerifier([reports(), reports()]).verify(REQUEST)
    assert verdict.status is VerdictStatus.PASS
    assert verdict.issues == []


async def test_fixable_issues_ask_for_a_revision_and_keep_every_issue():
    verifier = ComplianceVerifier([reports(IssueCode.UNSUPPORTED_CITATION), reports(IssueCode.FACT_MISMATCH)])
    verdict = await verifier.verify(REQUEST)
    assert verdict.status is VerdictStatus.REVISE
    assert [issue.code for issue in verdict.issues] == [IssueCode.UNSUPPORTED_CITATION, IssueCode.FACT_MISMATCH]


async def test_missing_evidence_is_a_refusal_even_next_to_fixable_issues():
    verifier = ComplianceVerifier([reports(IssueCode.FACT_MISMATCH), reports(IssueCode.MISSING_EVIDENCE)])
    verdict = await verifier.verify(REQUEST)
    assert verdict.status is VerdictStatus.REFUSE
    assert len(verdict.issues) == 2


async def test_each_check_receives_the_request():
    seen = []
    await ComplianceVerifier([lambda request: seen.append(request) or []]).verify(REQUEST)
    assert seen == [REQUEST]
