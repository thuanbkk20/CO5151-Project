"""Add manually transcribed draft tables and export an evidence graph.

Transcribed from QD 2749/QD-DHBK (2026-05-27), PDF pages 3 and 4.
No numeric eligibility decision is implemented. All data remain unapproved.
"""

import argparse
import hashlib
import json
from pathlib import Path

from build_corpus import atomic

CONVERSION_COLUMNS = [
    "toeic_listening_reading",
    "toefl_ibt",
    "toefl_ibt_2026_overall",
    "ielts",
    "pet",
    "fce",
    "cae",
    "pte_academic",
    "linguaskill",
    "aptis_esol",
    "vstep",
    "vept",
    "english_basic",
    "english_1",
    "english_2",
    "english_3",
    "english_4",
]

# Strings retain source symbols and decimal notation. '-' and 'X' are not
# converted into zero, null or an invented equivalence.
CONVERSION_ROWS = [
    [
        "400",
        "40",
        "2.5",
        "-",
        "-",
        "-",
        "-",
        "-",
        "-",
        "-",
        "-",
        "-",
        "Đạt",
        "-",
        "-",
        "-",
        "-",
    ],
    [
        "450",
        "49",
        "3",
        "-",
        "-",
        "-",
        "-",
        "-",
        "140",
        "-",
        "4.0",
        "43",
        "Đạt",
        "Đạt",
        "-",
        "-",
        "-",
    ],
    [
        "500",
        "54",
        "3",
        "4.0",
        "Grade C",
        "-",
        "-",
        "-",
        "143",
        "-",
        "4.5",
        "51",
        "Đạt",
        "Đạt",
        "Đạt",
        "-",
        "-",
    ],
    [
        "550",
        "59",
        "3.5",
        "4.5",
        "Grade B",
        "-",
        "-",
        "-",
        "146",
        "-",
        "5.0",
        "59",
        "Đạt",
        "Đạt",
        "Đạt",
        "Đạt",
        "-",
    ],
    [
        "600",
        "64",
        "3.5",
        "5.0",
        "Grade B",
        "-",
        "-",
        "41",
        "149",
        "B1",
        "5.5",
        "67",
        "Đạt",
        "Đạt",
        "Đạt",
        "Đạt",
        "Đạt",
    ],
    [
        "650",
        "70",
        "3.5",
        "5.0",
        "Grade A",
        "-",
        "-",
        "43",
        "152",
        "-",
        "X",
        "X",
        "Đạt",
        "Đạt",
        "Đạt",
        "Đạt",
        "Đạt",
    ],
    [
        "700",
        "79",
        "4",
        "5.5",
        "Grade A",
        "-",
        "-",
        "45",
        "155",
        "B1",
        "X",
        "X",
        "Đạt",
        "Đạt",
        "Đạt",
        "Đạt",
        "Đạt",
    ],
    [
        "785",
        "85",
        "4",
        "5.5",
        "X",
        "Grade C, Grade B, Grade A",
        "Level B2 Grade C, Grade B, Grade A",
        "48",
        "160",
        "B2",
        "X",
        "X",
        "Đạt",
        "Đạt",
        "Đạt",
        "Đạt",
        "Đạt",
    ],
]


def graduation_rows():
    rows = []
    for program, cohorts, scores, sw in [
        (
            "Chương trình tiêu chuẩn",
            ["<=2018", "2019", ">=2020"],
            ["500", "550", "600"],
            "200",
        ),
        (
            "Chương trình tài năng",
            ["<=2018", "2019", ">=2020"],
            ["600", "650", "700"],
            "245",
        ),
        ("PFIEV", ["<=2018", "2019", ">=2020"], ["600", "650", "700"], "245"),
    ]:
        for cohort, score in zip(cohorts, scores, strict=False):
            rows.append(
                {
                    "program_label": program,
                    "cohort_expression": cohort,
                    "toeic_listening_reading": score,
                    "toeic_speaking_writing": sw,
                    "other_certificate_text": "DELF B1; TCF B1 (tiếng Pháp)" if program == "PFIEV" else "",
                    "combination_logic": "unresolved_from_table" if program == "PFIEV" else "see_source_and_exceptions",
                }
            )
    rows.append(
        {
            "program_label": "Chương trình Định hướng Nhật Bản",
            "cohort_expression": "not_stated_in_this_row",
            "english_cell": "Không áp dụng",
            "other_certificate_text": "JLPT N3 (tiếng Nhật)",
        }
    )
    for cohort, score in zip(["<=2017", "2018", "2019", ">=2020"], ["400", "450", "500", "600"], strict=False):
        rows.append(
            {
                "program_label": "Vừa làm vừa học, Đào tạo từ xa",
                "cohort_expression": cohort,
                "toeic_listening_reading": score,
                "toeic_speaking_writing_source_cell": "200 (từ khoá 2021)",
                "scope_note": "Outside requested regular full-time scope; retain for source fidelity",
            }
        )
    rows.append(
        {
            "program_label": "Chính quy Bằng thứ hai",
            "source_rule": "Học chương trình đào tạo chính quy của khóa nào thì áp dụng chuẩn của khóa đó.",
            "scope_note": "Do not treat this as the default program for regular students",
        }
    )
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    folder = args.base.resolve() / "data/processed"
    seed = json.loads((folder / "language_seed/language_seed.json").read_text(encoding="utf-8"))
    corpus = json.loads((folder / "corpus/corpus.json").read_text(encoding="utf-8"))
    by_id = {r["unit_id"]: r for r in corpus}
    for provision in seed["provisions"]:
        if provision["source_text"] not in by_id[provision["unit_id"]]["text"]:
            parser.error("Seed excerpt does not match corpus: " + provision["provision_id"])
    tables = {r["table_id"]: r for r in seed["tables"]}
    graduation = tables["HCMUT-2749-2026-A2"]
    conversion = tables["HCMUT-2749-2026-A31"]
    for table in (graduation, conversion):
        source = by_id[table["unit_id"]]
        if table["raw_page_text"] != source["text"] or table["source_id"] != seed["source_id"]:
            parser.error("Table source mismatch; inspect input")
        table.update(
            review_status="transcribed_pending_human_review",
            verified=False,
            transcription_method="manual_from_rendered_pdf",
            page_text_sha256=hashlib.sha256(source["text"].encode()).hexdigest(),
        )
    graduation["rows"] = graduation_rows()
    graduation["scope_context"] = (
        "Phụ lục 1 phần A: chương trình giảng dạy bằng tiếng Việt; read introductory exceptions on PDF page 2."
    )
    graduation["required_related_evidence"] = [
        {
            "pdf_page": 2,
            "note": (
                "Exemption for Lao/Cambodian international students in the stated "
                "Vietnamese-taught standard program; course requirements remain."
            ),
        },
        {
            "pdf_page": 3,
            "note": "Four-skill certificates and temporary speaking-writing test provision",
        },
        {
            "pdf_page": 4,
            "note": (
                "Thesis registration language rule differs from graduation; certificate "
                "conversion and recognition window"
            ),
        },
    ]
    conversion["columns"] = CONVERSION_COLUMNS
    conversion["rows"] = [dict(zip(CONVERSION_COLUMNS, row, strict=False)) for row in CONVERSION_ROWS]
    conversion["interpretation_notes"] = [
        "Keep duplicate IELTS values across source rows; no unique IELTS-to-TOEIC function is inferred.",
        "Source marks X and - have not been semantically resolved.",
        "Exclusion of TOEFL iBT Home Edition and certificate recognition window are separate source provisions.",
        "VSTEP and VEPT columns in the conversion table do not by themselves prove acceptance for graduation.",
        "Academic program, cohort, exceptions and purpose must be checked before applying any row.",
    ]
    seed["schema_version"] = "0.2"
    seed["ready_for_production_advising"] = False

    nodes = [
        {
            "id": seed["source_id"],
            "type": "Document",
            "document_number": seed["document_number_candidate"],
            "verified": False,
        }
    ]
    edges = []
    for kind, key, records in [
        ("Provision", "provision_id", seed["provisions"]),
        ("Table", "table_id", seed["tables"]),
    ]:
        for record in records:
            nodes.append({"id": record[key], "type": kind, "data": record})
            edges.append(
                {
                    "source": seed["source_id"],
                    "relation": "CONTAINS",
                    "target": record[key],
                    "source_unit_id": record["unit_id"],
                    "verified": False,
                }
            )
    edges.extend(seed["relations"])
    ids = {n["id"] for n in nodes}
    assert len(ids) == len(nodes)
    assert all(e["source"] in ids and e["target"] in ids for e in edges)
    assert all(len(row) == len(CONVERSION_COLUMNS) for row in CONVERSION_ROWS)
    graph = {
        "schema_version": "0.1",
        "status": "draft_evidence_graph",
        "ready_for_production_advising": False,
        "nodes": nodes,
        "edges": edges,
    }
    out = folder / "language_structured"
    out.mkdir(parents=True, exist_ok=True)
    for name, value in [
        ("language_structured.json", seed),
        ("evidence_graph.json", graph),
    ]:
        atomic(out / name, json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    print(f"Graduation rows: {len(graduation['rows'])}; conversion rows: {len(conversion['rows'])}")
    print(f"Graph nodes: {len(nodes)}; edges: {len(edges)}")
    print(
        "Draft only; program/cohort filtering and retrieval are not implemented. Output:",
        out,
    )


if __name__ == "__main__":
    main()
