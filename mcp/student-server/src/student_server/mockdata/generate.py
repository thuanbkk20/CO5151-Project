"""Generate mock student data in the SAME JSON shape as the university API.

    uv run python -m student_server.mockdata.generate           # deterministic, seed 2026
    uv run python -m student_server.mockdata.generate --check   # verify committed JSON is up to date

Outputs (in this folder):
  profiles.json        {mssv: <profile object>}                 — schema "profile sinh viên"
  diem_mon_hoc.json    {mssv: {"data": [<course row>, ...]}}     — schema "bảng điểm môn học"
  diem_hoc_ky.json     {mssv: [<semester row>, ...]}             — schema "bảng điểm học kỳ" (mới nhất trước)
  xu_ly_hoc_vu.json    {mssv: [<warning row>, ...]}              — schema GIẢ ĐỊNH (chưa có mẫu thật)
  accounts.json        demo logins (username / PBKDF2 password hash → mssv / advisees)
  reference.json       CTĐT mô phỏng, bảng mã điểm đặc biệt, quy đổi chứng chỉ ngoại ngữ

Everything is internally consistent: semester rows and warnings are COMPUTED from course rows,
so tổng tín chỉ / điểm TB / cảnh báo always agree with the transcript.
"""

import argparse
import hashlib
import json
import random
import sys
from pathlib import Path

from student_server.auth.passwords import hash_password

HERE = Path(__file__).resolve().parent
SEED = 2026
TODAY_SEM = "20261"  # học kỳ đang diễn ra (chưa có điểm)

# ---------------------------------------------------------------- CTĐT mô phỏng (128 TC, không tính GDTC/GDQP)
# (học kỳ khuyến nghị, mã, tên, số TC, loại)
CTDT_2023 = [
    (1, "MT1003", "Giải tích 1", 4, "core"),
    (1, "PH1003", "Vật lý 1", 4, "core"),
    (1, "CO1005", "Nhập môn điện toán", 3, "core"),
    (1, "CO1023", "Hệ thống số", 3, "core"),
    (1, "LA1003", "Anh văn 1", 2, "av"),
    (1, "SP1031", "Triết học Mác - Lênin", 3, "core"),
    (1, "PE1003", "Giáo dục thể chất 1", 0, "gdtc"),
    (1, "MI1003", "Giáo dục quốc phòng - an ninh", 0, "gdqp"),
    (2, "MT1005", "Giải tích 2", 4, "core"),
    (2, "MT1007", "Đại số tuyến tính", 3, "core"),
    (2, "CO1007", "Cấu trúc rời rạc cho khoa học máy tính", 4, "core"),
    (2, "CO1027", "Kỹ thuật lập trình", 3, "core"),
    (2, "LA1005", "Anh văn 2", 2, "av"),
    (2, "SP1033", "Kinh tế chính trị Mác - Lênin", 2, "core"),
    (2, "PE1005", "Giáo dục thể chất 2", 0, "gdtc"),
    (3, "CO2003", "Cấu trúc dữ liệu và giải thuật", 4, "core"),
    (3, "CO2007", "Kiến trúc máy tính", 4, "core"),
    (3, "MT2013", "Xác suất và thống kê", 4, "core"),
    (3, "CO2011", "Mô hình hóa toán học", 3, "core"),
    (3, "LA1007", "Anh văn 3", 2, "av"),
    (3, "SP1035", "Chủ nghĩa xã hội khoa học", 2, "core"),
    (3, "PE1007", "Giáo dục thể chất 3", 0, "gdtc"),
    (4, "CO2013", "Hệ cơ sở dữ liệu", 4, "core"),
    (4, "CO2017", "Hệ điều hành", 3, "core"),
    (4, "CO2039", "Lập trình nâng cao", 3, "core"),
    (4, "CO2001", "Kỹ năng chuyên nghiệp cho kỹ sư", 3, "core"),
    (4, "LA1009", "Anh văn 4", 2, "av"),
    (4, "SP1037", "Tư tưởng Hồ Chí Minh", 2, "core"),
    (5, "CO3001", "Công nghệ phần mềm", 3, "core"),
    (5, "CO3005", "Nguyên lý ngôn ngữ lập trình", 4, "core"),
    (5, "CO3093", "Mạng máy tính", 3, "core"),
    (5, "CO3011", "Quản lý dự án phần mềm", 3, "core"),
    (5, "CO3015", "Kiểm thử phần mềm", 3, "core"),
    (5, "SP1039", "Lịch sử Đảng Cộng sản Việt Nam", 2, "core"),
    (6, "CO3013", "Xây dựng chương trình dịch", 4, "core"),
    (6, "CO3061", "Nhập môn trí tuệ nhân tạo", 3, "core"),
    (6, "CO3101", "Đồ án chuyên ngành", 2, "capstone"),
    (6, "CO3021", "Hệ quản trị cơ sở dữ liệu", 3, "core"),
    (6, "CO3029", "Khai phá dữ liệu", 3, "core"),
    (6, "SP1007", "Pháp luật Việt Nam đại cương", 2, "core"),
    (7, "CO3335", "Thực tập ngoài trường", 2, "intern"),
    (7, "CO3065", "Công nghệ phần mềm nâng cao", 3, "core"),
    (7, "CO3117", "Học máy", 3, "core"),
    (7, "CO4031", "Kho dữ liệu và hệ hỗ trợ quyết định", 3, "core"),
    (8, "CO4337", "Luận văn tốt nghiệp", 9, "thesis"),
]
CTDT_2019 = CTDT_2023 + [(7, "CO3103", "Đồ án tổng hợp", 2, "core")]  # 130 TC
COURSE = {c[1]: c for c in CTDT_2019}

# ---------------------------------------------------------------- bảng mã đặc biệt & quy đổi
# diemSo > 10 là MÃ, không phải điểm. Chỉ MT=12 được xác nhận từ mẫu thật; còn lại GIẢ ĐỊNH, cần đối chiếu API.
SPECIAL = {
    "11": {"diemChu": "CT", "nghia": "Cấm thi", "dat": False, "tinhTB": False},
    "12": {"diemChu": "MT", "nghia": "Miễn (miễn thi / miễn học, công nhận)", "dat": True, "tinhTB": False},
    "13": {"diemChu": "VT", "nghia": "Vắng thi", "dat": False, "tinhTB": False},
    "14": {"diemChu": "HT", "nghia": "Hoãn thi (chưa có điểm)", "dat": False, "tinhTB": False},
}
LETTERS = [
    (9.5, "A+", 4.0),
    (8.5, "A", 4.0),
    (8.0, "B+", 3.5),
    (7.0, "B", 3.0),
    (6.5, "C+", 2.5),
    (5.5, "C", 2.0),
    (5.0, "D+", 1.5),
    (4.0, "D", 1.0),
    (0.0, "F", 0.0),
]  # khớp QC2023-D12.2 (bản mô phỏng)
CERT_TO_TOEIC = {  # quy đổi tương đương — MÔ PHỎNG, thay bằng quy định chuẩn ngoại ngữ thật
    "TOEIC": [[450, 450], [500, 500], [600, 600], [650, 650], [785, 785]],
    "IELTS": [[4.5, 450], [5.0, 500], [5.5, 600], [6.0, 650], [6.5, 785]],
    "VSTEP": [[4.0, 450], [5.0, 500], [6.0, 600], [7.0, 650], [8.5, 785]],
}

SEM_ID = {}  # maHocKy -> namHocHocKyId


def sem_id(code):
    if code == "BL":
        return 603  # bảo lưu / công nhận (theo mẫu thật: namHocHocKyId 603)
    if code not in SEM_ID:
        y, k = int(code[:4]), int(code[4])
        SEM_ID[code] = 560 + (y - 2019) * 30 + k * 3  # dạng số nguyên ổn định, giống trường namHocHocKyId
    return SEM_ID[code]


SEM_LABEL = {"1": "1", "2": "2", "3": "3 (Hè)"}


def sem_name(code):
    y, k = int(code[:4]), code[4]
    return f"Năm học {y} - {y + 1} / Học kỳ {SEM_LABEL[k]}"


def letter(score):
    for lo, ch, _ in LETTERS:
        if score >= lo:
            return ch
    return "F"


MONHOC_ID = {code: 330000 + i * 137 for i, code in enumerate(sorted(COURSE))}
MONHOC_ID["LA0001"] = 399001


# ---------------------------------------------------------------- personas
def P(**k):
    return k


PERSONAS = [
    P(
        user="sv001",
        mssv="2310001",
        svid=228101,
        name="Nguyễn Văn An",
        cohort=2023,
        mu=6.9,
        sd=0.9,
        sems=["20231", "20232", "20241", "20242", "20251", "20252"],
        summer={"20243": ["CO3335"], "20253": ["CO3117"]},
        cert=("TOEIC 500", "20241"),
        note="K2023, đủ điều kiện LVTN, không cảnh báo",
    ),
    P(
        user="sv002",
        mssv="2310002",
        svid=228102,
        name="Trần Thị Bình",
        cohort=2023,
        mu=6.6,
        sd=1.0,
        sems=["20231", "20232", "20241", "20242", "20251", "20252"],
        force={"CO2007": [3.2], "CO3101": [3.5], "CO3005": [3.6], "CO3029": [2.8]},
        retake={"CO2007": ("20242", 5.8)},
        note="K2023, thiếu TC, rớt Đồ án chuyên ngành, chưa có chứng chỉ NN",
    ),
    P(
        user="sv003",
        mssv="2310003",
        svid=228103,
        name="Lê Văn Cường",
        cohort=2023,
        mu=5.9,
        sd=1.1,
        sems=["20231", "20232", "20241", "20242", "20251", "20252"],
        force={
            "CO2003": [3.5],
            "MT2013": [3.0],
            "CO2017": [3.8],
            "CO3005": [3.4],
            "CO3013": [2.1],
            "CO3061": [3.2],
            "CO3101": [2.5],
            "CO3021": [4.2],
            "CO3029": [2.0],
            "SP1007": [4.6],
        },
        retake={"CO2003": ("20242", 4.8), "MT2013": ("20251", 5.0)},
        note="K2023, bị cảnh báo HK 20252 (lần 1)",
    ),
    P(
        user="sv004",
        mssv="2210004",
        svid=218104,
        name="Phạm Thị Dung",
        cohort=2022,
        mu=8.3,
        sd=0.7,
        sems=["20221", "20222", "20241", "20242", "20251", "20252"],
        note="K2022 (QC2019), tạm dừng 20231–20232, đủ ĐK LVTN theo QC2019",
    ),
    P(
        user="sv005",
        mssv="2210005",
        svid=218105,
        name="Hoàng Minh Em",
        cohort=2022,
        mu=8.8,
        sd=0.6,
        sems=["20221", "20222", "20231", "20232", "20241", "20242", "20251", "20252"],
        skip=["CO3335", "CO3103"],
        force={"PE1007": ["HT"]},
        cert=("TOEIC 650", "20232"),
        note="K2022, thiếu 4 TC và GDTC 3 để tốt nghiệp",
    ),
    P(
        user="sv006",
        mssv="2410006",
        svid=238106,
        name="Đặng Quốc Phong",
        cohort=2024,
        mu=7.2,
        sd=1.0,
        sems=["20241", "20242", "20251", "20252"],
        note="K2024 năm 2, học bình thường",
    ),
    P(
        user="sv007",
        mssv="2310007",
        svid=228107,
        name="Võ Ngọc Giang",
        cohort=2023,
        mu=8.9,
        sd=0.5,
        sems=["20231", "20232", "20241", "20242", "20251", "20252"],
        summer={"20243": ["CO3335"], "20253": ["CO3117"]},
        cert=("IELTS 6.5", "20232"),
        note="K2023 GPA ≥ 3.2 → được đăng ký 28 TC",
    ),
    P(
        user="sv008",
        mssv="2510008",
        svid=248108,
        name="Bùi Thanh Hà",
        cohort=2025,
        mu=6.4,
        sd=0.9,
        sems=["20251", "20252"],
        force={"MT1003": [2.0], "PH1003": [1.5], "CO1005": [3.0], "CO1023": [3.5], "SP1031": [3.2]},
        note="K2025, bị cảnh báo HK đầu 20251, HK 20252 đã cải thiện",
    ),
]
ADVISORS = [
    {
        "username": "cvht01",
        "role": "advisor",
        "advisor_id": "CVHT01",
        "hoVaTen": "TS. Mai Văn Hùng",
        "advisees": ["2310001", "2310002", "2310003", "2310007"],
    }
]


# ---------------------------------------------------------------- generation
def gen_student(p, rng):
    ctdt = CTDT_2019 if p["cohort"] <= 2022 else CTDT_2023
    force, retake, skip = p.get("force", {}), p.get("retake", {}), set(p.get("skip", []))
    rows = []

    def add(sem, code, value, ghiChu=None, sem_label=None):
        _, _, name, tc, kind = COURSE[code] if code in COURSE else (0, code, "Chuẩn ngoại ngữ đầu ra", 0, "cert")
        if isinstance(value, str):  # special code
            num = [k for k, v in SPECIAL.items() if v["diemChu"] == value][0]
            dchu, dso, dat = value, int(num), SPECIAL[num]["dat"]
        else:
            dso = round(max(0.0, min(10.0, value)), 1)
            dchu, dat = letter(dso), dso >= 4.0
        rows.append(
            {
                "sinhVienId": p["svid"],
                "namHocHocKyId": sem_id(sem_label or sem),
                "maHocKy": sem_label or sem,
                "monHocId": MONHOC_ID[code],
                "maMonHoc": code,
                "tenMonHoc": name,
                "soTinChi": tc,
                "diemChu": dchu,
                "diemSo": dso,
                "diemDat": "1" if dat else "0",
                "tinhTrangDiem": None,
                "diemKhongIn": "1" if kind in ("gdtc", "gdqp") else "0",
                "nhomTo": None if sem_label == "BL" else f"L{rng.randint(1, 12):02d}",
                "ghiChu": ghiChu,
                "code": "0",
                "msg": "done",
            }
        )

    for i, sem in enumerate(p["sems"], start=1):
        for k, code, _name, _tc, _kind in ctdt:
            if k != i or code in skip:
                continue
            if any(code in v for v in p.get("summer", {}).values()):
                continue
            v = force.get(code, [None])[0]
            add(sem, code, v if v is not None else rng.gauss(p["mu"], p["sd"]))
        for code, (rsem, score) in retake.items():
            if rsem == sem:
                add(sem, code, score)
        for ssem, codes in p.get("summer", {}).items():
            if ssem[:4] == sem[:4] and sem[4] == "2":  # hè nằm sau HK2 cùng năm học
                for code in codes:
                    add(ssem, code, rng.gauss(p["mu"] + 0.3, p["sd"]))
    if p.get("cert"):
        txt, _ = p["cert"]
        add("BL", "LA0001", "MT", ghiChu=txt, sem_label="BL")
    return rows


POINTS4 = {ch: pts for _, ch, pts in LETTERS}


def gpa4(rows):
    pts = sum(POINTS4[r["diemChu"]] * r["soTinChi"] for r in rows)
    tc = sum(r["soTinChi"] for r in rows)
    return round(pts / tc, 2) if tc else None


def counted(r):
    return r["soTinChi"] > 0 and r["diemKhongIn"] == "0" and r["diemSo"] <= 10


def best_attempts(rows, policy="max"):
    best = {}
    for r in sorted(rows, key=lambda r: r["maHocKy"]):
        if not counted(r):
            continue
        c = r["maMonHoc"]
        if c not in best or (policy == "last") or r["diemSo"] > best[c]["diemSo"]:
            best[c] = r
    return best


def semester_rows(p, rows):
    out = []
    sems = sorted({r["maHocKy"] for r in rows if r["maHocKy"] != "BL"})
    policy = "last" if p["cohort"] <= 2022 else "max"
    for s in sems:
        in_sem = [r for r in rows if r["maHocKy"] == s and counted(r) and r["diemDat"] == "1"]
        upto = [r for r in rows if r["maHocKy"] != "BL" and r["maHocKy"] <= s]
        best = {c: r for c, r in best_attempts(upto, policy).items() if r["diemDat"] == "1"}
        tc_hk = sum(r["soTinChi"] for r in in_sem)
        avg_hk = sum(r["diemSo"] * r["soTinChi"] for r in in_sem) / tc_hk if tc_hk else 0
        tc_all = sum(r["soTinChi"] for r in best.values())
        avg_all = sum(r["diemSo"] * r["soTinChi"] for r in best.values()) / tc_all if tc_all else 0
        y, k = int(s[:4]), int(s[4])
        upd = {1: f"17/01/{y + 1} 01:18", 2: f"30/06/{y + 1} 18:10", 3: f"25/08/{y + 1} 09:30"}[k]
        out.append(
            {
                "sinhVienId": p["svid"],
                "namHocHocKyId": sem_id(s),
                "maNamHocHocKy": s,
                "namHocHocKyTen": sem_name(s),
                "soTCTLHocKy": tc_hk,
                "diemTBTLHocKy": f"{avg_hk:.2f}",
                "soTCTLChung": str(tc_all),
                "diemTBTLChung": f"{avg_all:.2f}",
                "capNhatCuoi": upd,
                "code": "0",
                "msg": "done",
            }
        )
    return sorted(out, key=lambda r: r["maNamHocHocKy"], reverse=True)


def warnings(p, rows):
    """Áp dụng Điều 14 Khoản 1 (bản mô phỏng) cho từng học kỳ CHÍNH."""
    qc2023 = p["cohort"] >= 2023
    policy = "max" if qc2023 else "last"
    out, lan = [], 0
    mains = [s for s in sorted({r["maHocKy"] for r in rows if r["maHocKy"] != "BL"}) if s[4] in "12"]
    for idx, s in enumerate(mains):
        sem_rows = [r for r in rows if r["maHocKy"] == s and counted(r)]
        g_sem = gpa4(sem_rows) or 0
        best = [
            r
            for r in best_attempts([r for r in rows if r["maHocKy"] != "BL" and r["maHocKy"] <= s], policy).values()
            if r["diemDat"] == "1"
        ]
        g_cum = gpa4(best) or 0
        year = int(s[:4]) - p["cohort"] + 1
        cum_min = {1: 1.2, 2: 1.4, 3: 1.6}.get(year, 1.8)
        sem_min = 0.8 if (qc2023 and idx == 0) else 1.0
        reg = sum(r["soTinChi"] for r in sem_rows)
        fail = sum(r["soTinChi"] for r in sem_rows if r["diemDat"] == "0")
        reason = None
        if g_sem < sem_min:
            reason = f"Điểm trung bình học kỳ {g_sem:.2f} (thang 4), dưới {sem_min:.1f}"
        elif g_cum < cum_min:
            reason = f"Điểm trung bình tích lũy {g_cum:.2f} (thang 4), dưới {cum_min:.1f} (năm thứ {year})"
        elif qc2023 and reg and fail / reg > 0.5:
            reason = f"Không đạt {fail}/{reg} tín chỉ đăng ký (trên 50%)"
        lan = lan + 1 if reason else 0
        if reason:
            y = int(s[:4])
            out.append(
                {
                    "sinhVienId": p["svid"],
                    "namHocHocKyId": sem_id(s),
                    "maHocKy": s,
                    "namHocHocKyTen": sem_name(s),
                    "hinhThucXuLy": "Cảnh báo học tập",
                    "lanLienTiep": lan,
                    "lyDo": reason,
                    "soQuyetDinh": f"{1000 + int(s) % 997}/QĐ-ĐHBK-ĐT",
                    "ngayQuyetDinh": f"20/02/{y + 1}" if s[4] == "1" else f"15/08/{y + 1}",
                    "code": "0",
                    "msg": "done",
                }
            )
    return out


def profile(p, i):
    return {
        "id": "%08x-mock" % (0x5A000000 + p["svid"]),
        "userType": "SINHVIEN",
        "personId": str(900000 + p["svid"]),
        "hoVaTen": p["name"],
        "tenDonVi": "Khoa Khoa học và Kỹ thuật Máy tính",
        "maDonVi": "MT",
        "donViId": "15",
        "donViIdList": [],
        "nganhIdList": None,
        "maBoMon": "CQ",
        "boMonId": "1",
        "userId": p["mssv"],
        "sessionId": 7300000 + i * 911,
        "email": f"{p['mssv']}.mock@student.example.edu.vn",
        "soCccd": f"0000000000{i:02d}",
    }


DEMO_PASSWORD = "demo"


def demo_hash(username):
    """Salt derived from the username so regenerated files stay byte-identical."""
    return hash_password(DEMO_PASSWORD, salt=hashlib.sha256(f"co5151-mock:{username}".encode()).hexdigest()[:16])


def build():
    """Return {file stem: JSON object} for every mock API payload."""
    rng = random.Random(SEED)
    profiles, dmh, dhk, xlhv, accounts = {}, {}, {}, {}, []
    for i, p in enumerate(PERSONAS, start=1):
        rows = gen_student(p, rng)
        profiles[p["mssv"]] = profile(p, i)
        dmh[p["mssv"]] = {"data": rows}
        dhk[p["mssv"]] = semester_rows(p, rows)
        xlhv[p["mssv"]] = warnings(p, rows)
        accounts.append(
            {
                "username": p["user"],
                "password_hash": demo_hash(p["user"]),
                "role": "student",
                "mssv": p["mssv"],
                "persona": p["note"],
            }
        )
    accounts += [{**a, "password_hash": demo_hash(a["username"])} for a in ADVISORS]
    ref = {
        "_note": (
            "Dữ liệu tham chiếu MÔ PHỎNG cho mock API. Mã môn/CTĐT mang tính minh họa — đối chiếu CTĐT thật trước D3."
        ),
        "today_semester": TODAY_SEM,
        "ctdt": {"2019": [list(c) for c in CTDT_2019], "2023": [list(c) for c in CTDT_2023]},
        "program_credits": {"2019": sum(c[3] for c in CTDT_2019), "2023": sum(c[3] for c in CTDT_2023)},
        "special_codes": SPECIAL,
        "letters": LETTERS,
        "cert_to_toeic": CERT_TO_TOEIC,
        "cohort_from_mssv": "cohort = 2000 + int(mssv[:2]) (giả định theo quy ước MSSV)",
    }
    return {
        "profiles": profiles,
        "diem_mon_hoc": dmh,
        "diem_hoc_ky": dhk,
        "xu_ly_hoc_vu": xlhv,
        "accounts": accounts,
        "reference": ref,
    }


def render(payloads):
    return {f"{name}.json": json.dumps(obj, ensure_ascii=False, indent=2) + "\n" for name, obj in payloads.items()}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Generate the mock university API payloads.")
    ap.add_argument("--out", type=Path, default=HERE)
    ap.add_argument("--check", action="store_true", help="verify instead of writing")
    a = ap.parse_args(argv)

    payloads = build()
    files = render(payloads)
    if a.check:
        stale = [f for f, text in files.items() if not (a.out / f).is_file() or (a.out / f).read_text("utf-8") != text]
        for f in stale:
            print(f"stale: {f}", file=sys.stderr)
        return 1 if stale else 0

    for f, text in files.items():
        (a.out / f).write_text(text, "utf-8")
    for p in PERSONAS:
        sems = payloads["diem_hoc_ky"][p["mssv"]]
        top = sems[0] if sems else {}
        print(
            f"{p['user']} {p['mssv']} K{p['cohort']}  TC={top.get('soTCTLChung')}  ĐTBTL10={top.get('diemTBTLChung')}  "
            f"courses={len(payloads['diem_mon_hoc'][p['mssv']]['data'])}  "
            f"warnings={[w['maHocKy'] for w in payloads['xu_ly_hoc_vu'][p['mssv']]]}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
