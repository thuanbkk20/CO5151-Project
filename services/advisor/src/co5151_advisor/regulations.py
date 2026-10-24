import unicodedata
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict


class RegulationDocument(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    title: str
    content: str
    ctdt: str | None = None


@runtime_checkable
class RegulationSource(Protocol):
    def search(self, query: str, *, ctdt: str | None = None) -> list[RegulationDocument]: ...


DEFAULT_REGULATIONS: list[RegulationDocument] = [
    RegulationDocument(
        id="Dieu_24_LVTN",
        title="Quy định về Đăng ký và Thực hiện Luận văn tốt nghiệp",
        content=(
            "Điều 24. Điều kiện làm Luận văn tốt nghiệp: "
            "1. Sinh viên tích lũy tối thiểu 105 tín chỉ (với CTĐT 128 tín chỉ). "
            "2. Đã hoàn thành và đạt học phần Đồ án chuyên ngành. "
            "3. Đạt chuẩn trình độ ngoại ngữ theo quy định (TOEIC 500 điểm trở lên hoặc chứng chỉ tương đương)."
        ),
        ctdt="2023",
    ),
    RegulationDocument(
        id="Dieu_24_LVTN_2019",
        title="Quy định Luận văn tốt nghiệp khóa 2019",
        content=(
            "Điều kiện làm Luận văn tốt nghiệp theo QC2019: Tích lũy tối thiểu 105 tín chỉ và đạt chuẩn ngoại ngữ."
        ),
        ctdt="2019",
    ),
    RegulationDocument(
        id="Dieu_26_TotNghiep",
        title="Điều kiện xét công nhận tốt nghiệp",
        content=(
            "Điều 26. Điều kiện xét tốt nghiệp: "
            "Sinh viên được công nhận tốt nghiệp khi tích lũy đủ số tín chỉ của chương trình đào tạo, "
            "ĐTBTL từ 2.00 trở lên, hoàn thành các chứng chỉ GDTC và GDQP-AN, đạt chuẩn ngoại ngữ."
        ),
        ctdt=None,
    ),
    RegulationDocument(
        id="Dieu_15_CanhBao",
        title="Quy chế cảnh báo học tập và buộc thôi học",
        content=(
            "Điều 15. Cảnh báo học tập: "
            "Sinh viên bị cảnh báo học tập nếu ĐTB học kỳ hoặc ĐTB tích lũy không đạt chuẩn tối thiểu. "
            "Sinh viên bị cảnh báo 3 lần liên tiếp sẽ bị buộc thôi học."
        ),
        ctdt=None,
    ),
]


def _normalize(text: str) -> str:
    return unicodedata.normalize("NFC", text).lower()


class StaticRegulationSource:
    """In-memory regulation knowledge source for tests and local evaluation."""

    def __init__(self, documents: list[RegulationDocument] | None = None):
        self._documents = documents if documents is not None else DEFAULT_REGULATIONS

    def search(self, query: str, *, ctdt: str | None = None) -> list[RegulationDocument]:
        norm_q = _normalize(query)
        results: list[RegulationDocument] = []

        for doc in self._documents:
            # Check CTDT compatibility if specified
            if ctdt and doc.ctdt and doc.ctdt != ctdt:
                continue

            doc_text = _normalize(f"{doc.id} {doc.title} {doc.content}")

            # Check matching keywords
            is_match = False
            if any(k in norm_q for k in ["luận văn", "lvtn"]) and ("luận văn" in doc_text or "lvtn" in doc_text):
                is_match = True
            elif "tốt nghiệp" in norm_q and "tốt nghiệp" in doc_text:
                is_match = True
            elif any(k in norm_q for k in ["cảnh báo", "cảnh cáo"]) and "cảnh báo" in doc_text:
                is_match = True

            if is_match:
                results.append(doc)

        return results
