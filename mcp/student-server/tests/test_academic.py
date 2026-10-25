import pytest

from student_server import academic

ALL = ["2310001", "2310002", "2310003", "2210004", "2210005", "2410006", "2310007", "2510008"]


def summary(db, mssv):
    return academic.summary(
        db.raw_profile(mssv), db.raw_transcript(mssv), db.raw_semesters(mssv), db.raw_decisions(mssv), db.ref
    )


@pytest.mark.parametrize("mssv", ALL)
def test_cumulative_credits_match_transcript(db, mssv):
    """soTCTLChung from the semester API must equal the credits recomputed from course rows."""
    ctdt = academic.ctdt_of(academic.cohort_of(mssv))
    best = academic.passed_best(db.raw_transcript(mssv), academic.retake_policy(ctdt))
    assert summary(db, mssv).credits_earned == sum(int(r["soTinChi"]) for r in best)


def test_cohort_and_program_version():
    assert academic.cohort_of("2210004") == 2022 and academic.ctdt_of(2022) == "2019"
    assert academic.ctdt_of(2023) == "2023"


def test_retake_policy_last_vs_max():
    base = {"maMonHoc": "X", "soTinChi": 3, "diemDat": "1", "diemKhongIn": "0"}
    rows = [
        dict(base, maHocKy="20231", diemChu="B", diemSo=7.5),
        dict(base, maHocKy="20232", diemChu="C", diemSo=6.0),
    ]
    assert academic.best_attempts(rows, "max")["X"]["diemSo"] == 7.5
    assert academic.best_attempts(rows, "last")["X"]["diemSo"] == 6.0


def test_gpa4_weighted_by_credits():
    rows = [{"soTinChi": 4, "diemChu": "A"}, {"soTinChi": 2, "diemChu": "C"}]
    assert academic.gpa4(rows) == round((4 * 4.0 + 2 * 2.0) / 6, 2)
    assert academic.gpa4([]) is None


@pytest.mark.parametrize(
    "mssv, expected",
    [
        ("2310001", {"credits_earned": 102, "toeic": 500, "capstone_project_passed": False, "currently_warned": False}),
        ("2310002", {"capstone_project_passed": False, "english_cert": None}),
        ("2310003", {"currently_warned": True, "consecutive_warnings": 1}),
        ("2210004", {"ctdt": "2019", "credits_earned": 100}),
        ("2210005", {"gdtc_completed": False, "toeic": 650, "capstone_project_passed": True}),
        ("2310007", {"english_cert": "IELTS 6.5", "toeic": 750}),
    ],
)
def test_persona_summaries(db, mssv, expected):
    s = summary(db, mssv).model_dump()
    assert {k: s[k] for k in expected} == expected


def test_program_follows_real_curriculum(db):
    for ctdt in ("2019", "2023"):
        program = db.ref["ctdt"][ctdt]
        assert db.ref["program_credits"][ctdt] == sum(c[3] for c in program) == 128
        assert [c[1] for c in program if c[4] in ("capstone", "thesis")] == ["CO4029", "CO4337"]


@pytest.mark.parametrize(
    "kind, score, toeic",
    [
        ("IELTS", 3.0, None),
        ("IELTS", 4.5, 550),
        ("IELTS", 6.5, 750),
        ("TOEFL ITP", 500, 550),
        ("TOEFL iBT", 79, 700),
        ("PET", "Merit", 500),
        ("FCE", "grade b", 750),
        ("CAE", "Level B2", 700),
        ("VSTEP", 8.0, None),
    ],
)
def test_toeic_equivalent_follows_conversion_table(db, kind, score, toeic):
    assert academic.toeic_equivalent(kind, score, db.ref["cert_to_toeic"]) == toeic


def test_english_certificate_picks_best_passed(db):
    rows = [
        {"ghiChu": "PET Distinction", "diemDat": "1"},
        {"ghiChu": "TOEFL  iBT 80", "diemDat": "1"},
        {"ghiChu": "CAE Grade A", "diemDat": "0"},
    ]
    assert academic.english_certificate(rows, db.ref["cert_to_toeic"]) == ("TOEFL iBT 80", 700)


def test_retakes_are_counted(db):
    assert summary(db, "2310002").retake_credits > 0
    assert summary(db, "2410006").retake_credits == 0


def test_special_grade_codes_are_decoded(db):
    rows = [academic.course(r, db.ref["special_codes"]) for r in db.raw_transcript("2210005")]
    deferred = next(c for c in rows if c.course == "PE1007")
    assert deferred.letter == "HT" and deferred.score10 is None and deferred.status.startswith("Hoãn thi")
    assert not deferred.passed and not deferred.in_gpa


def test_profile_mapping_drops_sensitive_fields(db):
    p = academic.profile(db.raw_profile("2310001")).model_dump()
    assert set(p) == {"student_id", "full_name", "faculty", "program_type", "cohort", "ctdt"}


def test_semester_and_decision_mapping(db):
    sem = academic.semester(db.raw_semesters("2310001")[0])
    assert sem.semester == "20253" and isinstance(sem.gpa10_cumulative, float)
    w = academic.decision(db.raw_decisions("2310003")[0])
    assert w.semester == "20252" and w.is_warning and "QĐ" in w.decision_no
    d = academic.decision(db.raw_decisions("2310001")[0])
    assert d.content == "Giao đề tài Đồ án/Đề án tốt nghiệp" and not d.is_warning


def test_consecutive_warnings_counts_back_from_latest_main_semester():
    rows = [{"maHocKy": s} for s in ("20241", "20242", "20243", "20251", "20252")]

    def warn(s):
        return {"yearSemesterCode": s, "type": "Cảnh báo học tập", "decisionContent": "Cảnh báo học tập"}

    other = {"yearSemesterCode": "20252", "type": "Quyết định khác", "decisionContent": "Miễn môn học"}
    assert academic.consecutive_warnings(rows, [warn("20251"), warn("20252")]) == 2
    assert academic.consecutive_warnings(rows, [warn("20241"), warn("20252")]) == 1
    assert academic.consecutive_warnings(rows, [warn("20251"), other]) == 0
