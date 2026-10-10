"""Mock student data source.

Loads the mock API payloads (mockdata/*.json — same JSON shape as the university endpoints) into
SQLite, keeping the raw columns. After seeding, the connection is switched to `PRAGMA query_only`,
so nothing reachable from a tool can write to the store.
"""

import json
import sqlite3
from pathlib import Path
from typing import Any

from .config import PACKAGE_DIR

MOCK_DIR = PACKAGE_DIR / "mockdata"

COURSE_COLS = ["sinhVienId", "namHocHocKyId", "maHocKy", "monHocId", "maMonHoc", "tenMonHoc", "soTinChi", "diemChu",
               "diemSo", "diemDat", "tinhTrangDiem", "diemKhongIn", "nhomTo", "ghiChu", "code", "msg"]  # fmt: skip
SEM_COLS = ["sinhVienId", "namHocHocKyId", "maNamHocHocKy", "namHocHocKyTen", "soTCTLHocKy", "diemTBTLHocKy",
            "soTCTLChung", "diemTBTLChung", "capNhatCuoi", "code", "msg"]  # fmt: skip
WARN_COLS = ["sinhVienId", "namHocHocKyId", "maHocKy", "namHocHocKyTen", "hinhThucXuLy", "lanLienTiep", "lyDo",
             "soQuyetDinh", "ngayQuyetDinh", "code", "msg"]  # fmt: skip

# table -> (payload file, columns, unwrap payload -> rows, ORDER BY)
_TABLES = {
    "diem_mon_hoc": ("diem_mon_hoc", COURSE_COLS, lambda v: v["data"], "rowid"),
    "diem_hoc_ky": ("diem_hoc_ky", SEM_COLS, lambda v: v, "maNamHocHocKy DESC"),
    "xu_ly_hoc_vu": ("xu_ly_hoc_vu", WARN_COLS, lambda v: v, "maHocKy"),
}


def _load(folder: Path, name: str) -> Any:
    return json.loads((folder / f"{name}.json").read_text("utf-8"))


class StudentDB:
    def __init__(self, path: str = ":memory:", data_dir: Path = MOCK_DIR):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.ref = _load(data_dir, "reference")
        self._create()
        if self.conn.execute("SELECT COUNT(*) FROM profiles").fetchone()[0] == 0:
            self._seed(data_dir)
        self.conn.execute("PRAGMA query_only = ON")

    def _create(self):
        ddl = [
            "CREATE TABLE IF NOT EXISTS accounts(username TEXT PRIMARY KEY, password TEXT, role TEXT, mssv TEXT,"
            " advisor_id TEXT, advisees TEXT, persona TEXT)",
            "CREATE TABLE IF NOT EXISTS profiles(mssv TEXT PRIMARY KEY, raw TEXT)",
        ]
        for table, (_, cols, _, _) in _TABLES.items():
            ddl.append(f"CREATE TABLE IF NOT EXISTS {table}(mssv TEXT, {', '.join(cols)})")
            ddl.append(f"CREATE INDEX IF NOT EXISTS ix_{table}_mssv ON {table}(mssv)")
        self.conn.executescript(";\n".join(ddl) + ";")

    def _seed(self, folder: Path):
        c = self.conn
        for a in _load(folder, "accounts"):
            c.execute(
                "INSERT INTO accounts VALUES (?,?,?,?,?,?,?)",
                (a["username"], a["password"], a["role"], a.get("mssv"), a.get("advisor_id"),
                 json.dumps(a.get("advisees", [])), a.get("persona")),
            )  # fmt: skip
        for mssv, p in _load(folder, "profiles").items():
            c.execute("INSERT INTO profiles VALUES (?,?)", (mssv, json.dumps(p, ensure_ascii=False)))
        for table, (name, cols, unwrap, _) in _TABLES.items():
            marks = ",".join("?" * (len(cols) + 1))
            for mssv, payload in _load(folder, name).items():
                for r in unwrap(payload):
                    c.execute(f"INSERT INTO {table} VALUES ({marks})", [mssv] + [r.get(k) for k in cols])
        c.commit()

    # ---------------- raw (API-shaped) access ----------------
    def _rows(self, table: str, mssv: str) -> list[dict]:
        _, cols, _, order = _TABLES[table]
        cur = self.conn.execute(f"SELECT {', '.join(cols)} FROM {table} WHERE mssv=? ORDER BY {order}", (mssv,))
        return [dict(r) for r in cur]

    def exists(self, mssv: str) -> bool:
        return self.conn.execute("SELECT 1 FROM profiles WHERE mssv=?", (mssv,)).fetchone() is not None

    def raw_profile(self, mssv: str) -> dict | None:
        r = self.conn.execute("SELECT raw FROM profiles WHERE mssv=?", (mssv,)).fetchone()
        return json.loads(r[0]) if r else None

    def raw_transcript(self, mssv: str) -> list[dict]:
        return self._rows("diem_mon_hoc", mssv)

    def raw_semesters(self, mssv: str) -> list[dict]:
        """Newest first, as returned by the API."""
        return self._rows("diem_hoc_ky", mssv)

    def raw_warnings(self, mssv: str) -> list[dict]:
        return self._rows("xu_ly_hoc_vu", mssv)

    # ---------------- accounts ----------------
    def account(self, username: str) -> dict | None:
        r = self.conn.execute("SELECT * FROM accounts WHERE username=?", (username,)).fetchone()
        if not r:
            return None
        d = dict(r)
        d["advisees"] = json.loads(d["advisees"] or "[]")
        return d
