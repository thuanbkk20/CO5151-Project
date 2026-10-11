"""Anti-corruption layer: raw university API payloads → normalized contract models.

The Student Record MCP exposes ONLY these models to agents, so upstream quirks (Vietnamese field
names, string-typed numbers, special grade codes) are absorbed here. Each mapper copies fields
explicitly — sensitive profile fields (soCccd, email, sessionId, personId) are never read.

Raw sources (same shape as the real endpoints):
  profile        {id, userType, personId, hoVaTen, tenDonVi, maDonVi, ..., userId, sessionId, email, soCccd}
  diem_mon_hoc   [{maHocKy, maMonHoc, soTinChi, diemChu, diemSo, diemDat, diemKhongIn, ghiChu, ...}]
  diem_hoc_ky    [{maNamHocHocKy, soTCTLHocKy, diemTBTLHocKy, soTCTLChung, diemTBTLChung, ...}]  (newest first)
  xu_ly_hoc_vu   [{maHocKy, hinhThucXuLy, lanLienTiep, lyDo, ...}]   (schema assumed)
"""

import re
from typing import Literal

from co5151_contracts.student import AcademicSummary, CourseRecord, SemesterRecord, StudentProfile, WarningRecord

LETTER4 = {"A+": 4.0, "A": 4.0, "B+": 3.5, "B": 3.0, "C+": 2.5, "C": 2.0, "D+": 1.5, "D": 1.0, "F": 0.0}
CERT_RE = re.compile(r"\b(TOEIC|IELTS|VSTEP)\s*([0-9]+(?:\.[0-9]+)?)", re.I)
RetakePolicy = Literal["last", "max"]


def cohort_of(mssv: str) -> int:
    """Assumed convention: the first two MSSV digits are the intake year."""
    return 2000 + int(str(mssv)[:2])


def ctdt_of(cohort: int) -> str:
    return "2019" if cohort <= 2022 else "2023"


def retake_policy(ctdt: str) -> RetakePolicy:
    """QC2019: điểm lần học sau cùng; QC2023: điểm cao nhất."""
    return "last" if ctdt == "2019" else "max"


def is_numeric_grade(r: dict) -> bool:
    """diemSo > 10 is a special code (MT, CT, VT, HT), not a score."""
    return r.get("diemSo") is not None and float(r["diemSo"]) <= 10


def counted(r: dict) -> bool:
    """Tính vào ĐTB: có tín chỉ, có điểm số thật (không phải mã đặc biệt), không thuộc diện 'không in'."""
    return int(r["soTinChi"]) > 0 and r.get("diemKhongIn") == "0" and is_numeric_grade(r) and r["diemChu"] in LETTER4


def best_attempts(rows: list[dict], policy: RetakePolicy) -> dict[str, dict]:
    best: dict[str, dict] = {}
    for r in sorted(rows, key=lambda x: x["maHocKy"]):
        if r["maHocKy"] == "BL" or not counted(r):
            continue
        c = r["maMonHoc"]
        if c not in best or policy == "last" or float(r["diemSo"]) > float(best[c]["diemSo"]):
            best[c] = r
    return best


def passed_best(rows: list[dict], policy: RetakePolicy) -> list[dict]:
    return [r for r in best_attempts(rows, policy).values() if r["diemDat"] == "1"]


def gpa4(rows: list[dict]) -> float | None:
    tc = sum(int(r["soTinChi"]) for r in rows)
    return round(sum(LETTER4[r["diemChu"]] * int(r["soTinChi"]) for r in rows) / tc, 2) if tc else None


def toeic_equivalent(cert_type: str, score: float, table: dict) -> int | None:
    best = None
    for lo, toeic in table.get(cert_type.upper(), []):
        if score >= lo:
            best = toeic
    return best


def english_certificate(rows: list[dict], table: dict) -> tuple[str | None, int | None]:
    """Best recognised certificate from `ghiChu` of passed rows → (label, TOEIC or equivalent)."""
    label, toeic = None, None
    for r in rows:
        m = CERT_RE.search(r.get("ghiChu") or "")
        if not (m and r["diemDat"] == "1"):
            continue
        kind, score = m.group(1).upper(), float(m.group(2))
        eq = toeic_equivalent(kind, score, table)
        if eq is not None and (toeic is None or eq > toeic):
            label, toeic = f"{kind} {m.group(2)}", int(score) if kind == "TOEIC" else eq
    return label, toeic


# ---------------------------------------------------------------- mappers → contract models


def profile(raw: dict) -> StudentProfile:
    mssv = raw["userId"]
    cohort = cohort_of(mssv)
    return StudentProfile(
        student_id=mssv,
        full_name=raw["hoVaTen"],
        faculty=raw["tenDonVi"],
        program_type=raw["maBoMon"],
        cohort=cohort,
        ctdt=ctdt_of(cohort),
    )


def summary(
    raw_profile: dict, rows: list[dict], sem_rows: list[dict], warn_rows: list[dict], ref: dict
) -> AcademicSummary:
    mssv = raw_profile["userId"]
    cohort = cohort_of(mssv)
    ctdt = ctdt_of(cohort)
    best = passed_best(rows, retake_policy(ctdt))
    latest = sem_rows[0] if sem_rows else {}
    program = ref["ctdt"][ctdt]

    def all_passed(kind: str) -> bool:
        codes = [c[1] for c in program if c[4] == kind]
        return all(any(r["maMonHoc"] == code and r["diemDat"] == "1" for r in rows) for code in codes)

    cert, toeic = english_certificate(rows, ref["cert_to_toeic"])

    mains = sorted({r["maHocKy"] for r in rows if r["maHocKy"] != "BL" and r["maHocKy"][4] in "12"})
    w_last = [w for w in warn_rows if mains and w["maHocKy"] == mains[-1]]
    attempts: dict[str, list[dict]] = {}
    for r in rows:
        if r["maHocKy"] != "BL" and int(r["soTinChi"]) > 0:
            attempts.setdefault(r["maMonHoc"], []).append(r)
    retake = sum(int(v[0]["soTinChi"]) * (len(v) - 1) for v in attempts.values() if len(v) > 1)

    return AcademicSummary(
        student_id=mssv,
        cohort=cohort,
        ctdt=ctdt,
        program_credits=ref["program_credits"][ctdt],
        credits_earned=int(latest.get("soTCTLChung", 0)),  # nguồn: bảng điểm học kỳ (API)
        cgpa=gpa4(best),  # thang 4, tính từ điểm chữ (QC Điều 12)
        cgpa10=float(latest.get("diemTBTLChung", 0) or 0),  # nguồn: bảng điểm học kỳ (API)
        capstone_project_passed=any(r["maMonHoc"] == "CO3101" and r["diemDat"] == "1" for r in rows),
        toeic=toeic,
        english_cert=cert,
        gdtc_completed=all_passed("gdtc"),
        gdqp_completed=all_passed("gdqp"),
        currently_warned=bool(w_last),
        consecutive_warnings=w_last[0]["lanLienTiep"] if w_last else 0,
        retake_credits=retake,
        last_semester=latest.get("maNamHocHocKy"),
    )


def course(r: dict, special: dict) -> CourseRecord:
    sp = None if is_numeric_grade(r) else special.get(str(int(float(r["diemSo"]))))
    return CourseRecord(
        semester=r["maHocKy"],
        course=r["maMonHoc"],
        name=r["tenMonHoc"],
        credits=int(r["soTinChi"]),
        letter=r["diemChu"],
        score10=None if sp else float(r["diemSo"]),
        passed=r["diemDat"] == "1",
        status=sp["nghia"] if sp else None,
        in_gpa=counted(r),
        note=r.get("ghiChu"),
    )


def semester(s: dict) -> SemesterRecord:
    return SemesterRecord(
        semester=s["maNamHocHocKy"],
        label=s["namHocHocKyTen"],
        credits_semester=int(s["soTCTLHocKy"]),
        gpa10_semester=float(s["diemTBTLHocKy"]),
        credits_cumulative=int(s["soTCTLChung"]),
        gpa10_cumulative=float(s["diemTBTLChung"]),
        updated=s["capNhatCuoi"],
    )


def warning(w: dict) -> WarningRecord:
    return WarningRecord(
        semester=w["maHocKy"],
        reason=w["lyDo"],
        consecutive=int(w["lanLienTiep"]),
        decision=f"{w['soQuyetDinh']} ngày {w['ngayQuyetDinh']}",
    )
