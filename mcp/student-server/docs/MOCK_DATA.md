# Mock data sinh viên — theo đúng schema API của Trường

Thư mục `src/student_server/mockdata/` chứa dữ liệu giả lập **giữ nguyên tên trường và kiểu dữ liệu** của 3 endpoint mẫu
(profile, bảng điểm môn học, bảng điểm học kỳ, quyết định học vụ).
Toàn bộ được sinh tất định bởi `uv run python -m student_server.mockdata.generate` (seed 2026); `--check` kiểm tra file JSON đã commit có khớp generator không.

| File | Endpoint tương ứng | Ghi chú |
|---|---|---|
| `profiles.json` | Profile sinh viên | `{mssv: {id, userType:"SINHVIEN", personId, hoVaTen, tenDonVi, maDonVi:"MT", donViId:"15", donViIdList:[], nganhIdList:null, maBoMon:"CQ", boMonId:"1", userId, sessionId, email, soCccd}}` |
| `diem_mon_hoc.json` | Bảng điểm môn học | `{mssv: {"data": [{sinhVienId, namHocHocKyId, maHocKy, monHocId, maMonHoc, tenMonHoc, soTinChi, diemChu, diemSo, diemDat, tinhTrangDiem, diemKhongIn, nhomTo, ghiChu, code, msg}]}}` |
| `diem_hoc_ky.json` | Bảng điểm học kỳ | `{mssv: [{sinhVienId, namHocHocKyId, maNamHocHocKy, namHocHocKyTen, soTCTLHocKy (int), diemTBTLHocKy (string), soTCTLChung (string), diemTBTLChung (string), capNhatCuoi, code, msg}]}` — mới nhất trước |
| `xu_ly_hoc_vu.json` | Quyết định học vụ | `{mssv: {code:"200", msg:"OK", data: [{decisionCode, decisionDate, yearSemesterName, id, type, decisionContent, decisionReason, status, yearSemesterCode, studentCode, lastUpdatedAt}], sign:null}}` — mới nhất trước |
| `accounts.json` | — | Tài khoản demo (mật khẩu `demo`, lưu dạng PBKDF2-SHA256) → MSSV, danh sách cố vấn của CVHT |
| `reference.json` | — | CTĐT ngành KHMT khóa 2019 và 2026 (128 TC), mã điểm đặc biệt, quy đổi chứng chỉ ngoại ngữ |

## Tính nhất quán
- `soTCTLChung`, `diemTBTLChung`, `soTCTLHocKy`, `diemTBTLHocKy` và các quyết định cảnh báo học tập được **tính từ** bảng điểm môn học, không gõ tay.
  Quyết định miễn học ngoại ngữ sinh từ chứng chỉ của persona; tạm dừng / tiếp tục học, giao đề tài TN khai báo tay trong `PERSONAS`.
  Test `tests/test_academic.py::test_cumulative_credits_match_transcript` kiểm tra `soTCTLChung` = tổng TC đạt (lần học được tính) cho mọi sinh viên.
- Học lại: QC2023 lấy điểm cao nhất, QC2019 lấy lần sau cùng (khớp Điều 11 bản mô phỏng).
- Điểm chữ theo thang ở Điều 12 Khoản 2 (A+ ≥ 9.5, A ≥ 8.5 … F < 4.0) — khớp mẫu thật (9.3 → A).
- `maHocKy`: `YYYYK` (K = 1, 2, 3 hè), `BL` = bảo lưu / công nhận (theo mẫu thật, `namHocHocKyId` 603).

## Chương trình đào tạo
`CTDT_2019` và `CTDT_2026` trong `generate.py` lấy từ CTĐT thật ngành Khoa học Máy tính (chuyên ngành Khoa học Máy tính):
CTĐT cử nhân khóa 2019 (ban hành 08/08/2020) và CTĐT `DH_CQ_MT_NG_7480101_2026`. Mã môn, tên, số TC và khối kiến thức theo CTĐT;
với nhóm tự chọn, mock chọn sẵn một tổ hợp hợp lệ (ví dụ tự chọn chuyên ngành: CO3061, CO3029, CO3117, CO3021, CO4031).
- Học kỳ khuyến nghị theo Kế hoạch giảng dạy CTĐT 2026. CTĐT 2019 không kèm kế hoạch nên được xếp theo cùng khung đó.
- Khóa ≤ 2022 dùng CTĐT 2019; khóa ≥ 2023 dùng CTĐT 2026 (bản CTĐT thật gần nhất hiện có; khóa `ctdt` vẫn là `"2023"` vì nó
  cũng quyết định quy chế áp dụng). Khác biệt chính: CTĐT 2026 có Học kỳ thực tập doanh nghiệp CO4359 (11 TC) ở HK7 thay cho
  Thực tập ngoài trường CO3335 (2 TC), Nguyên lý NNLT CO3019 (3 TC) thay CO3005 (4 TC), Pháp luật đại cương SP1073 (3 TC) thay SP1007 (2 TC).
- `capstone_project_passed` = đã đạt Đồ án chuyên ngành CO4029 (tiên quyết của Đồ án tốt nghiệp CO4337).

## Các quy ước GIẢ ĐỊNH cần nhóm xác nhận với API thật
| Quy ước | Giá trị đang dùng |
|---|---|
| Mã điểm đặc biệt (`diemSo` > 10) | 12 = MT Miễn (xác nhận từ mẫu); 11 = CT Cấm thi, 13 = VT Vắng thi, 14 = HT Hoãn thi (giả định) |
| `diemKhongIn = "1"` | Học phần không tính vào ĐTB (GDTC, GDQP-AN) |
| Khóa tuyển sinh | `2000 + int(MSSV[:2])` (profile không có trường khóa) |
| Chứng chỉ ngoại ngữ | Dòng `MT` có `ghiChu` dạng `TOEIC 500` / `IELTS 6.5` / `VSTEP 7.5`, quy đổi TOEIC theo `reference.json` |
| Quyết định cảnh báo | `type` hoặc `decisionContent` chứa "Cảnh báo học tập"; số lần liên tiếp = số HK chính liền nhau (tính ngược từ HK chính gần nhất có điểm) có quyết định cảnh báo |
| Email, CCCD | Domain `example.edu.vn`, CCCD dạng `0000000000NN` — cố ý không trùng dữ liệu thật |

## Bảo vệ dữ liệu nhạy cảm
Profile thật chứa `soCccd`, `email`, `sessionId`, `personId`. Student Record MCP **không bao giờ** trả các trường này cho agent:
`get_my_profile` chỉ trả MSSV, họ tên, khoa, hệ, khóa, CTĐT (data minimization). Ràng buộc này được áp ở hai lớp: whitelist trường trong `service.py` và model output `extra="forbid"` trong `co5151-contracts`.

## 8 persona
| User | MSSV | Khóa | Tình huống demo |
|---|---|---|---|
| sv001 | 2310001 | 2023 | 102 TC, ĐTBTL 2.51, TOEIC 500, học hè 2 kỳ; HK 20261 được giao đề tài, đang học Đồ án chuyên ngành + thực tập doanh nghiệp |
| sv002 | 2310002 | 2023 | 92 TC (kém sv001 10 TC), rớt Đồ án tổng hợp, chưa có chứng chỉ NN, có học lại |
| sv003 | 2310003 | 2023 | Bị cảnh báo HK 20252 (lần 1) → 14 TC, nguy cơ buộc thôi học |
| sv004 | 2210004 | 2022 | QC2019, tạm dừng 20231–20232 (có QĐ tạm dừng / tiếp tục học), đủ ĐK LVTN theo QC2019 (100 TC), đã được giao đề tài TN HK 20261 |
| sv005 | 2210005 | 2022 | 124/128 TC — thiếu Thực tập ngoài trường + Pháp luật VN đại cương (4 TC) và GDTC 3 (hoãn thi), TOEIC 650 |
| sv006 | 2410006 | 2024 | Năm 2, học bình thường |
| sv007 | 2310007 | 2023 | ĐTBTL 3.90 → được đăng ký 28 TC, IELTS 6.5 |
| sv008 | 2510008 | 2025 | Bị cảnh báo HK đầu 20251, HK 20252 đã thoát cảnh báo |
| cvht01 | — | — | Cố vấn của 2310001, 2310002, 2310003, 2310007 |
