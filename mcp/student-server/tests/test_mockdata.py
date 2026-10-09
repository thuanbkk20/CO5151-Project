import json

from student_server.mockdata import generate


def test_committed_payloads_match_generator():
    assert generate.main(["--check"]) == 0, "run: uv run python -m student_server.mockdata.generate"


def test_generation_is_deterministic():
    assert generate.render(generate.build()) == generate.render(generate.build())


def test_every_student_has_all_payloads():
    p = generate.build()
    mssvs = set(p["profiles"])
    assert len(mssvs) == len(generate.PERSONAS) == 8
    for name in ("diem_mon_hoc", "diem_hoc_ky", "xu_ly_hoc_vu"):
        assert set(p[name]) == mssvs
    students = {a["mssv"] for a in p["accounts"] if a["role"] == "student"}
    assert students == mssvs
    for adv in (a for a in p["accounts"] if a["role"] == "advisor"):
        assert set(adv["advisees"]) <= mssvs


def test_pii_is_obviously_synthetic():
    for prof in generate.build()["profiles"].values():
        assert prof["email"].endswith("@student.example.edu.vn")
        assert prof["soCccd"].startswith("0000000000")


def test_raw_payload_keeps_api_string_typing():
    """diemTBTLChung / soTCTLChung are strings in the real API — the normalization layer must cope."""
    sem = json.loads(generate.render(generate.build())["diem_hoc_ky.json"])["2310001"][0]
    assert isinstance(sem["soTCTLChung"], str) and isinstance(sem["diemTBTLChung"], str)
    assert isinstance(sem["soTCTLHocKy"], int)
