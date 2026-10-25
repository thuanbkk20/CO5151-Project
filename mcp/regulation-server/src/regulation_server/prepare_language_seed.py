"""Build draft foreign-language evidence from corpus; no eligibility decisions.

Run next to build_corpus.py. Does not modify corpus or original documents.
All candidates require human approval; numeric tables are intentionally pending.
"""

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path

from .build_corpus import atomic


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base", type=Path, default=Path(__file__).resolve().parents[2])
    a = p.parse_args()
    base = a.base.resolve()
    folder = base / "data/processed"
    corpus = json.loads((folder / "corpus/corpus.json").read_text(encoding="utf-8"))
    manifest = json.loads((folder / "extraction/source_manifest.json").read_text(encoding="utf-8"))
    # Identify by content, never by the ambiguous filename number 2933.
    matches = [
        r for r in corpus if r.get("pdf_page") == 1 and "2749" in r["text"] and "27 tháng 5 năm 2026" in r["text"]
    ]
    if len(matches) != 1:
        p.error("Expected exactly one QD 2749 dated 2026-05-27; inspect source metadata")
    sid = matches[0]["source_id"]
    pages = {r["pdf_page"]: r for r in corpus if r["source_id"] == sid}
    if set(pages) != set(range(1, 7)):
        p.error("Decision source must contain all six pages")
    candidates = []

    def add(key, title, page, start, end, scope, purpose):
        record = pages[page]
        text = record["text"]
        left = text.index(start)
        right = text.index(end, left) if end else len(text)
        quote = text[left:right].strip()
        candidates.append(
            {
                "provision_id": "HCMUT-2749-2026-" + key,
                "title": title,
                "source_id": sid,
                "unit_id": record["unit_id"],
                "file_name": record["file_name"],
                "pdf_page": page,
                "source_text": quote,
                "source_text_sha256": hashlib.sha256(quote.encode()).hexdigest(),
                "scope_note": scope,
                "purpose": purpose,
                "effective_from_candidate": "2026-05-27",
                "applicability_note": (
                    "Check cohort-specific and semester-specific provisions; decision date "
                    "alone does not resolve scope."
                ),
                "review_status": "candidate",
                "verified": False,
                "approval_required_before_advising": True,
            }
        )

    scope = "Phu luc 1, phan A: chuong trinh giang day bang tieng Viet; check specific program and exceptions."
    add(
        "ART1",
        "Thay the Phu luc 1",
        1,
        "Điều 1.",
        "Điều 2.",
        "Pham vi thay the phu luc, khong phai toan bo quy che",
        "document_versioning",
    )
    add(
        "ART2",
        "Hieu luc quyet dinh",
        1,
        "Điều 2.",
        "Điều 3.",
        "Hieu luc van ban; dieu khoan co the co moc ap dung rieng",
        "document_versioning",
    )
    add(
        "A2-CERT",
        "Chung chi bao gom bon ky nang",
        3,
        "Các chứng chỉ tiếng Anh bao gồm",
        "Tạm thời cho phép",
        scope,
        "graduation_language",
    )
    add(
        "A2-TEMP",
        "Ket qua kiem tra Noi-Viet tai trung tam",
        3,
        "Tạm thời cho phép",
        None,
        scope,
        "graduation_language",
    )
    add(
        "A2-THESIS",
        "Ngoai ngu khi dang ky Khoa luan",
        4,
        "Khi xét điều kiện",
        "3. Quy đổi",
        scope,
        "thesis_registration_language_only",
    )
    add(
        "A31-VALID",
        "Thoi han cong nhan chung chi",
        4,
        "Thời hạn công nhận chứng chỉ:",
        "Bằng tốt nghiệp",
        scope,
        "certificate_recognition_window",
    )
    add(
        "A41-PLACEMENT",
        "Thi xep trinh do khi nhap hoc",
        5,
        "Sau khi nhập học,",
        "Vào cuối học kỳ 1",
        scope,
        "placement_not_course_exemption",
    )
    add(
        "A41-TEST",
        "Kiem tra cuoi hoc ky 1 nam nhat",
        5,
        "Vào cuối học kỳ 1",
        "Sinh viên vừa trúng tuyển,",
        scope,
        "one_time_course_exemption",
    )

    # Store whole-page evidence for tables. No row or cell is inferred from flat text.
    tables = [
        {
            "table_id": "HCMUT-2749-2026-A2",
            "title": "Chuan ngoai ngu tot nghiep",
            "pdf_page": 3,
            "purpose": "graduation_language",
            "required_review": "Reconstruct merged program/cohort/skill cells from PDF. Keep exceptions and notes.",
        },
        {
            "table_id": "HCMUT-2749-2026-A31",
            "title": "Quy doi chung chi tieng Anh",
            "pdf_page": 4,
            "purpose": "certificate_conversion",
            "required_review": (
                "Preserve every row, column, X, dash and footnote. Same IELTS score occurs "
                "in multiple rows; do not collapse to a single TOEIC value."
            ),
        },
    ]
    for table in tables:
        r = pages[table["pdf_page"]]
        table.update(
            source_id=sid,
            unit_id=r["unit_id"],
            raw_page_text=r["text"],
            rows=None,
            review_status="table_pending",
            verified=False,
        )
    links = [
        {
            "source": "HCMUT-2749-2026-A2-CERT",
            "relation": "REFERENCES",
            "target": "HCMUT-2749-2026-A31",
            "evidence": "mục 3.1 của Phụ lục này",
            "verified": False,
        },
        {
            "source": "HCMUT-2749-2026-A41-TEST",
            "relation": "REFERENCES",
            "target": "HCMUT-2749-2026-A31",
            "evidence": "tiểu mục 3.1 mục 3",
            "verified": False,
        },
    ]
    duplicate = defaultdict(list)
    for r in corpus:
        if r["text"].strip():
            duplicate[(r["source_id"], hashlib.sha256(r["text"].encode()).hexdigest())].append(r["unit_id"])
    issues = [
        {
            "id": "R01",
            "priority": "high",
            "note": (
                "Handbook PDF page 23 (printed 21) must be reconciled with decision A.4.1 "
                "on placement versus end-of-semester test. Keep as unresolved; do not "
                "automatically overwrite either source."
            ),
        },
        {
            "id": "R02",
            "priority": "high",
            "note": (
                "Handbook PDF page 27 (printed 25) summarizes graduation-course conditions; "
                "decision PDF page 4 distinguishes thesis language requirements from "
                "graduation. Do not apply the four-skill graduation rule automatically to "
                "thesis registration."
            ),
        },
        {
            "id": "R03",
            "priority": "high",
            "note": "Obtain full QD 2933 and QD 1260 before claiming complete academic-regulation coverage.",
        },
        {
            "id": "R04",
            "priority": "high",
            "note": (
                "Confirm exact program within chinh quy tap trung; do not map every regular "
                "student to chuong trinh tieu chuan."
            ),
        },
        {
            "id": "R05",
            "priority": "medium",
            "note": (
                "Physical PDF pages differ from printed handbook pages. Confirm printed "
                "labels per cited page; do not assume a universal offset."
            ),
        },
    ]
    for ids in duplicate.values():
        if len(ids) > 1:
            issues.append(
                {
                    "id": "DUP-" + str(len(issues)),
                    "priority": "medium",
                    "unit_ids": ids,
                    "note": "Identical text; preserve distinct source pages until original PDF comparison.",
                }
            )
    result = {
        "schema_version": "0.1",
        "document_number_candidate": "2749/QD-DHBK",
        "source_id": sid,
        "source_metadata": next(s for s in manifest if s["source_id"] == sid),
        "provisions": candidates,
        "tables": tables,
        "relations": links,
        "review_issues": issues,
        "ready_for_production_advising": False,
    }
    destination = folder / "language_seed"
    destination.mkdir(parents=True, exist_ok=True)
    atomic(
        destination / "language_seed.json",
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
    )
    print(
        "Candidates:",
        len(candidates),
        "Pending tables:",
        len(tables),
        "Relations:",
        len(links),
    )
    print("All candidates are unverified. Output:", destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
