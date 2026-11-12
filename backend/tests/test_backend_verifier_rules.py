import pytest

from co5151_backend.application.agents.verifier import (
    ComplianceVerifier,
    cited_provisions_are_retrieved,
    no_secrets,
    rule_checks,
)
from co5151_contracts import IssueCode, RegulationExcerpt, VerdictStatus, VerificationRequest

CL55 = RegulationExcerpt(
    id="QD2933-2021-CL5.5",
    title="Khoản 5.5 (HCMUT_QD2933_2021.pdf, trang 8-9)",
    content="5.5 Đăng ký các học phần tốt nghiệp. Sinh viên phải hoàn thành điều kiện về chuẩn ngoại ngữ.",
)
A2_THESIS = RegulationExcerpt(
    id="HCMUT-2749-2026-A2-THESIS",
    title="Ngoại ngữ khi đăng ký Khóa luận",
    content="Khi xét điều kiện đăng ký học phần Khóa luận tốt nghiệp, cho phép áp dụng chuẩn Nghe – Đọc.",
)
CL101 = RegulationExcerpt(
    id="QD1260-2026-CL10.1", title="Nội dung mới khoản 10.1", content="“10.1 Công nhận tốt nghiệp"
)


def request(draft: str, *regulations: RegulationExcerpt, question: str = "Em đủ điều kiện làm luận văn chưa?"):
    return VerificationRequest(question=question, draft=draft, regulations=list(regulations))


def codes(issues):
    return [issue.code for issue in issues]


@pytest.mark.parametrize(
    "draft",
    [
        "Theo [QD2933-2021-CL5.5], bạn cần đạt chuẩn ngoại ngữ trước khi đăng ký.",
        "Theo Khoản 5.5 Quy chế 2933 (QD2933-2021-CL5.5).",
        "Căn cứ Điều 5, khoản 5.5: cần hoàn thành chuẩn ngoại ngữ.",
        "Theo HCMUT-2749-2026-A2 thì chỉ xét kỹ năng Nghe – Đọc.",
        "Bạn đã tích lũy 92/128 tín chỉ, ĐTBTL 2.28. Các đoạn quy chế tìm được chưa đủ để kết luận điều kiện.",
        "Chứng chỉ GDQP-AN đã hoàn thành; hạn nộp 27-5-2026; xem mybk.hcmut.edu.vn/quy-che---quy-dinh.",
    ],
)
def test_grounded_citations_pass(draft):
    assert cited_provisions_are_retrieved(request(draft, CL55, A2_THESIS)) == []


def test_parts_of_a_retrieved_clause_number_are_accepted():
    assert cited_provisions_are_retrieved(request("Theo khoản 1 Điều 10 thì cần đủ tín chỉ.", CL101)) == []


@pytest.mark.parametrize(
    "draft, expected",
    [
        ("Theo [QD2933-2021-CL7.3], bạn được miễn.", "QD2933-2021-CL7.3"),
        ("Theo Điều 99 quy chế đào tạo, bạn đủ điều kiện.", "Điều/Khoản 99"),
        ("Theo khoản 24.2, cần tối thiểu 105 tín chỉ.", "Điều/Khoản 24.2"),
    ],
)
def test_citation_outside_the_retrieved_excerpts_is_unsupported(draft, expected):
    issues = cited_provisions_are_retrieved(request(draft, CL55, A2_THESIS))
    assert codes(issues) == [IssueCode.UNSUPPORTED_CITATION]
    assert expected in issues[0].message


def test_citing_a_provision_with_nothing_retrieved_is_missing_evidence():
    issues = cited_provisions_are_retrieved(request("Theo Điều 24, bạn đủ điều kiện làm luận văn."))
    assert codes(issues) == [IssueCode.MISSING_EVIDENCE]


def test_no_citation_and_nothing_retrieved_is_left_to_the_judge():
    assert cited_provisions_are_retrieved(request("Chào bạn, mình có thể giúp gì?")) == []


def test_clause_numbers_from_the_question_are_not_judged_by_rules():
    draft = "Tôi không tìm thấy Điều 99 trong các văn bản quy chế đã tra cứu."
    asked = request(draft, CL55, question="Theo Điều 99 thì GPA trên 3.5 được miễn Thể dục đúng không?")
    assert cited_provisions_are_retrieved(asked) == []


def test_session_token_or_canary_in_the_draft_is_a_leak():
    token = "eyJzdWIiOiJzdjAwMyIsInJvbGUiOiJzdHVkZW50In0.c2lnbmF0dXJlLXNpZ25hdHVyZQ"
    check = no_secrets(["G3-CANARY-7F3A"])
    assert codes(check(request(f"Token của bạn là {token}"))) == [IssueCode.LEAK]
    assert codes(check(request("Header: Authorization: Bearer abcdefghijklmnop1234"))) == [IssueCode.LEAK]
    assert codes(check(request("Mã hệ thống là G3-CANARY-7F3A."))) == [IssueCode.LEAK]
    assert check(request("Bạn đã tích lũy 92/128 tín chỉ.")) == []
    assert "eyJ" not in check(request(f"Token {token}"))[0].message


@pytest.mark.anyio
async def test_rule_checks_fold_into_a_verdict():
    verifier = ComplianceVerifier(rule_checks(secrets=["G3-CANARY-7F3A"]))
    assert (
        await verifier.verify(request("Theo [QD2933-2021-CL5.5], cần chuẩn ngoại ngữ.", CL55))
    ).status is VerdictStatus.PASS
    assert (await verifier.verify(request("Theo Điều 99, bạn đủ điều kiện.", CL55))).status is VerdictStatus.REVISE
    assert (await verifier.verify(request("Theo Điều 99, bạn đủ điều kiện."))).status is VerdictStatus.REFUSE
