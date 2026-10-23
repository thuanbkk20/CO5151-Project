# Threat model v1 (D2, mục 6)

Bản v1, cập nhật từ threat model v0 trong proposal D1. Mỗi biện pháp ghi rõ trạng thái:

- **Đã cài + có test**: chạy được và có kiểm thử tự động trong repo.
- **Kế hoạch**: thành phần chưa có trong repo.

D2 chưa yêu cầu chạy thử prompt injection lên agent. Các ca đã soạn sẵn để chạy khi có Advisor.

## 1. Tài sản cần bảo vệ

| # | Tài sản | Vì sao quan trọng |
|---|---|---|
| A1 | Hồ sơ học vụ cá nhân: điểm, tín chỉ, cảnh báo, chứng chỉ ngoại ngữ | Dữ liệu cá nhân; lộ chéo giữa sinh viên là sự cố nghiêm trọng nhất |
| A2 | Định danh nhạy cảm trong API nguồn: CCCD, email, `sessionId`, `personId` | Không cần cho tư vấn, không được ra khỏi Student Record MCP |
| A3 | Session token của người dùng | Có token là đọc được hồ sơ của người đó |
| A4 | Tính đúng của câu trả lời: trích đúng Điều/Khoản, đúng quy chế theo khóa | Tư vấn sai làm sinh viên lỡ hạn, đăng ký sai, hiểu sai điều kiện tốt nghiệp |
| A5 | System prompt, API key LLM của nhóm | Lộ prompt giúp vượt rào dễ hơn; lộ key gây tốn chi phí |
| A6 | Audit log | Bằng chứng đối soát; không được thành một bản sao dữ liệu cá nhân |

## 2. Điểm nội dung không tin cậy đi vào hệ thống

| # | Điểm vào | Ai kiểm soát nội dung | Đi tới đâu |
|---|---|---|---|
| E1 | Câu hỏi trong khung chat | Người dùng đã đăng nhập (có thể có ý xấu) | Advisor (LLM) |
| E2 | Lịch sử hội thoại / bộ nhớ ngắn hạn 3–5 lượt | Người dùng, gián tiếp | Advisor, Verifier |
| E3 | Tài liệu quy chế được nạp vào Regulation MCP | Nguồn bên ngoài; có thể bị sửa hoặc chứa câu lệnh | Kết quả tool → Advisor, Verifier |
| E4 | Tham số tool do LLM sinh ra | LLM, sau khi bị E1–E3 tác động | Student Record MCP, Regulation MCP |
| E5 | Header HTTP `Authorization` của MCP | Host app; kẻ tấn công có thể gửi request trực tiếp tới server | Student Record MCP |
| E6 | Kết quả tool trả về agent | Server (tin cậy), nhưng có thể chứa văn bản từ E3 | Ngữ cảnh LLM |

## 3. Năng lực giả định của kẻ tấn công

- **K1, sinh viên tò mò hoặc có ý xấu:** có tài khoản hợp lệ, gõ bất kỳ nội dung gì vào chat, biết MSSV của bạn
  khác, biết kỹ thuật jailbreak phổ biến (role-play, "ignore previous instructions", mã hóa base64, tiếng Anh).
- **K2, người ngoài trên mạng nội bộ:** gửi được HTTP request thẳng tới MCP server, nhưng không có khóa ký token.
- **K3, người sửa được nguồn tài liệu quy chế:** chèn được đoạn văn bản vào tài liệu được nạp (indirect injection).
- **Ngoài phạm vi:** kẻ tấn công chiếm được máy chủ, đọc được khóa ký token hay biến môi trường, hoặc là nhân viên
  quản trị hệ thống.

## 4. Biện pháp theo từng điểm vào

| Điểm vào | Mối đe dọa | Biện pháp | Trạng thái | Bằng chứng |
|---|---|---|---|---|
| E5 | Gọi MCP không token, token rác, token tự ký, hết hạn | Middleware Bearer kiểm tra HMAC-SHA256 và hạn dùng trên **mọi** request, trả HTTP 401 trước khi tool chạy | Đã cài + có test | `security` S01–S04 |
| E5 | Sửa claims (MSSV, role) trong token nhưng giữ chữ ký cũ | Chữ ký phủ toàn bộ payload | Đã cài + có test | S05, S06 |
| E4 | LLM chèn `student_id` để đọc hồ sơ người khác | Tool `get_my_*` không có tham số `student_id`; đích đọc lấy từ token tại `authz.resolve_target` | Đã cài + có test | S07, S08 |
| E4 | Cố vấn đọc ngoài danh sách; dò MSSV có tồn tại không | Kiểm tra claim `advisees` trước khi tra cứu; cùng một thông điệp FORBIDDEN | Đã cài + có test | S09, S10, S11 |
| E4 | SQL / prompt injection trong tham số | Pydantic kiểm tra định dạng (`^([0-9]{4}[123]\|BL)$`), lỗi không lặp lại input, SQLite `query_only` | Đã cài + có test | S12, S13 |
| E6 | Lộ CCCD / email / sessionId cho agent | Mapper copy từng trường tường minh, model output `extra="forbid"` | Đã cài + có test | S14 |
| E4 | Agent bị dụ thực hiện thao tác ghi | Chỉ có tool chỉ đọc (`readOnlyHint`), không có handler ghi | Đã cài + có test | S15; ca agent `PI11` |
| E5 | Lẫn dữ liệu giữa các người dùng đồng thời | Token đọc theo từng request (context-local) | Đã cài + có test | S16 |
| E1 | Mạo danh MSSV hoặc vai cố vấn trong câu chat | Danh tính chỉ đến từ token phiên, không từ nội dung chat | Tầng tool: đã cài. Tầng agent: kế hoạch | `PI02`, `PI03`, `PI07`, `PI08`, `O02` |
| E1 | Jailbreak ép xác nhận "đủ điều kiện tốt nghiệp" | Verifier đối chiếu kết luận với dữ liệu tool và quy chế, được quyền từ chối | Kế hoạch | `PI04`, `PI12`, `O05` |
| E1 | Ép bịa điều khoản | Strict Refusal khi không có căn cứ; Verifier kiểm tra mọi trích dẫn có trong kết quả Regulation MCP | Kế hoạch | `PI10`, `O01`, `O03` |
| E1 | Lộ system prompt / token | Token chỉ ở host, không vào ngữ cảnh LLM (đã cài ở tầng MCP); chuỗi canary trong system prompt | Một phần | `PI01`, `PI06` |
| E2 | Lịch sử hội thoại giả "chế độ quản trị" | Quyền chỉ đến từ token; bộ nhớ ngắn hạn không mang quyền | Kế hoạch | `PI09` |
| E3 | Đoạn văn độc trong tài liệu quy chế | Coi kết quả Regulation MCP là dữ liệu, không phải lệnh (đánh dấu ranh giới trong prompt); Verifier đối chiếu văn bản gốc | Kế hoạch | `PI05` |
| A6 | Audit log thành bản sao dữ liệu cá nhân | Actor/target lưu dạng pseudonym HMAC; bộ nhớ dài hạn không lưu điểm | Tầng MCP: đã cài. Tầng agent: kế hoạch | `test_service.py::test_every_call_is_audited` |

## 5. Kết quả kiểm thử tầng tool

Lệnh chạy:

```bash
uv run co5151-eval security
```

Lần chạy ngày 24/10/2026 trên nhánh này: **16/16 ca đạt**. Bảng chi tiết (điểm vào, tấn công, kỳ vọng, quan sát)
do lệnh trên in ra, dán thẳng vào báo cáo được.

## 6. Rủi ro còn lại

- Token là HMAC với khóa dùng chung, mô phỏng SSO. Lộ khóa thì giả được mọi token. Bản thật nên dùng JWT bất đối
  xứng và kiểm tra `aud`.
- Chưa thu hồi được token trước khi hết hạn.
- Mọi biện pháp ở tầng agent (E1–E3) còn là kế hoạch, chưa có số liệu. 12 ca `PI` sẽ chạy khi có Advisor:

  ```bash
  uv run co5151-eval run --agent <adapter> --suite injection
  ```
- Kiểm tra rò rỉ dựa trên regex (`forbidden`), nên có thể bỏ sót cách diễn đạt khác. Cần chấm tay thêm một mẫu.
