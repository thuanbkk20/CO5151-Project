import sqlite3

import pytest

from student_server.db import StudentDB


def test_raw_payloads_round_trip(db):
    assert db.raw_profile("2310001")["hoVaTen"] == "Nguyễn Văn An"
    assert len(db.raw_transcript("2310001")) == 43
    sems = db.raw_semesters("2310001")
    assert [s["maNamHocHocKy"] for s in sems] == sorted((s["maNamHocHocKy"] for s in sems), reverse=True)
    assert [w["maHocKy"] for w in db.raw_warnings("2310003")] == ["20252"]


def test_unknown_student_is_empty(db):
    assert db.raw_profile("9999999") is None and not db.exists("9999999")
    assert db.raw_transcript("9999999") == []


def test_accounts(db):
    assert db.account("sv002")["mssv"] == "2310002"
    adv = db.account("cvht01")
    assert adv["role"] == "advisor" and "2310003" in adv["advisees"]
    assert db.account("nobody") is None


def test_lookup_is_parameterized(db):
    assert db.raw_profile("2310001' OR '1'='1") is None


def test_store_is_read_only_after_seeding(db):
    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        db.conn.execute("DELETE FROM profiles")


def test_file_backed_db_is_seeded_once(tmp_path):
    path = str(tmp_path / "students.sqlite3")
    StudentDB(path).conn.close()
    again = StudentDB(path)
    assert again.conn.execute("SELECT COUNT(*) FROM profiles").fetchone()[0] == 8
