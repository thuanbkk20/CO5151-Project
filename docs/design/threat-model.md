# Threat model v2

Cập nhật 2026-11-27 (task F1). v1 (D2, mục 6) viết khi chưa có Advisor; v2 theo kiến trúc hiện tại
([architecture.md](architecture.md)): backend FastAPI ráp Advisor + Verifier, Verifier có thể dùng model judge riêng
(`VERIFIER_LLM_PROVIDER`, ví dụ Azure Foundry), console vận hành, giới hạn 10 câu mỗi hội thoại. Mỗi biện pháp ghi
trạng thái:

- **Đã cài + có test**: chạy được và có kiểm thử tự động trong repo (không gọi LLM thật).
- **Chưa đo**: đã cài nhưng chưa có số liệu với LLM thật (bộ `injection` chạy ở E4).
- **Kế hoạch / cần quyết**: chưa làm.

Thay đổi so với v1: E2 nay đi vào router (viết lại câu hỏi) và judge (qua câu hỏi đã viết lại); thêm điểm vào E7
(console / API admin) và E8 (nhà cung cấp LLM); ca prompt injection 12 → 15, có fixture chạy injection gián tiếp.

## 1. Tài sản cần bảo vệ

| # | Tài sản | Vì sao quan trọng |
|---|---|---|
| A1 | Hồ sơ học vụ cá nhân: điểm, tín chỉ, cảnh báo, quyết định học vụ, chứng chỉ ngoại ngữ | Dữ liệu cá nhân; lộ chéo giữa sinh viên là sự cố nghiêm trọng nhất |
| A2 | Định danh nhạy cảm trong API nguồn: CCCD, email, `sessionId`, `personId` | Không cần cho tư vấn, không được ra khỏi Student Record MCP |
| A3 | Token: access token của backend, token Student Record ngắn hạn, `BACKEND_ADMIN_TOKEN` | Có token là đọc được hồ sơ hoặc toàn bộ trace |
| A4 | Tính đúng của câu trả lời: trích đúng Điều/Khoản, đúng quy chế theo khóa, số liệu khớp hồ sơ | Tư vấn sai làm sinh viên lỡ hạn, đăng ký sai, hiểu sai điều kiện tốt nghiệp |
| A5 | System prompt (có canary), API key LLM | Lộ prompt giúp vượt rào dễ hơn; lộ key gây tốn chi phí |
| A6 | Lịch sử chat, trace và span (`messages`, `traces`, `trace_spans`) | Bằng chứng đối soát, nhưng chứa nguyên văn số liệu học vụ |

## 2. Điểm nội dung không tin cậy đi vào hệ thống

| # | Điểm vào | Ai kiểm soát nội dung | Đi tới đâu |
|---|---|---|---|
| E1 | Câu hỏi trong khung chat | Người dùng đã đăng nhập hoặc khách (có thể có ý xấu) | Planner (luật, router LLM), writer, judge (qua E2') |
| E2 | Lịch sử hội thoại (backend đọc từ database) | Người dùng, gián tiếp | Router (4 tin gần nhất), writer. Judge **không** thấy lịch sử |
| E2' | Câu hỏi đã viết lại (`standalone_question`, `regulation_query`) | Router LLM, sau khi đọc E1–E2 | Truy vấn Regulation MCP, câu hỏi cho judge |
| E3 | Tài liệu quy chế được nạp vào Regulation MCP (BM25 hoặc graph) | Nguồn bên ngoài; có thể bị sửa hoặc chứa câu lệnh | Kết quả tool → writer, judge |
| E4 | Tham số tool | Backend (token, MSSV) và router (chữ truy vấn) | Student Record MCP, Regulation MCP |
| E5 | Header `Authorization` của MCP và của backend | Kẻ tấn công gửi được request trực tiếp | Student Record MCP, API backend |
| E6 | Kết quả tool trả về agent | Server (tin cậy), nhưng có thể chứa văn bản từ E3 | Ngữ cảnh LLM |
| E7 | Console vận hành, API `/admin/*` | Người có tài khoản vận hành / admin token | Mọi trace, mọi hội thoại |
| E8 | Nhà cung cấp LLM (Gemini, Azure Foundry, ...) | Bên thứ ba | Nhận câu hỏi, số liệu hồ sơ, đoạn quy chế trong prompt |

## 3. Năng lực giả định của kẻ tấn công

- **K1, sinh viên tò mò hoặc có ý xấu:** có tài khoản hợp lệ, gõ bất kỳ nội dung gì vào chat, biết MSSV của bạn
  khác, biết kỹ thuật jailbreak phổ biến (role-play, "ignore previous instructions", base64, tiếng Anh), dàn dựng
  nhiều lượt để lịch sử dẫn dắt router.
- **K2, người ngoài trên mạng nội bộ:** gửi được HTTP request thẳng tới MCP server hoặc backend, không có khóa ký
  token hay admin token.
- **K3, người sửa được nguồn tài liệu quy chế:** chèn được đoạn văn bản vào tài liệu được nạp (indirect injection).
- **Ngoài phạm vi:** kẻ tấn công chiếm được máy chủ, đọc được khóa ký token hay `.env`, là nhân viên vận hành, hoặc
  nhà cung cấp LLM tự ý dùng dữ liệu.

## 4. Biện pháp theo từng điểm vào

### Tầng tool và API (không phụ thuộc LLM)

| Điểm vào | Mối đe dọa | Biện pháp | Trạng thái | Bằng chứng |
|---|---|---|---|---|
| E5 | Gọi MCP không token, token rác, tự ký, hết hạn | Middleware Bearer kiểm HMAC-SHA256 và hạn dùng trên **mọi** request, HTTP 401 trước khi tool chạy | Đã cài + có test | `security` S01–S04 |
| E5 | Sửa claims (MSSV, role) nhưng giữ chữ ký cũ | Chữ ký phủ toàn bộ payload | Đã cài + có test | S05, S06 |
| E4 | Đọc hồ sơ người khác qua tham số | Tool `get_my_*` không có tham số `student_id`; đích đọc lấy từ token (`authz.resolve_target`); token Student Record do backend ký mỗi câu, không vào ngữ cảnh LLM | Đã cài + có test | S07, S08; `PI15` |
| E4 | Cố vấn đọc ngoài danh sách; dò MSSV | Kiểm claim `advisees`; cùng một thông điệp FORBIDDEN | Đã cài + có test | S09–S11 |
| E4 | SQL / prompt injection trong tham số | Pydantic kiểm định dạng, lỗi không lặp lại input, SQLite `query_only` | Đã cài + có test | S12, S13 |
| E6 | Lộ CCCD / email / sessionId cho agent | Mapper copy từng trường tường minh, output `extra="forbid"` | Đã cài + có test | S14 |
| E4 | Bị dụ thao tác ghi | Chỉ có tool chỉ đọc (`readOnlyHint`) | Đã cài + có test | S15; `PI11` |
| E5 | Lẫn dữ liệu giữa người dùng đồng thời | Token theo từng request (context-local) | Đã cài + có test | S16 |
| E5 | Đọc hội thoại của người khác qua API backend | Mọi truy vấn lọc theo chủ hội thoại; hội thoại của người khác trả 404 | Đã cài + có test | `backend/tests/test_backend_api.py` |
| E7 | Dùng access token người dùng gọi `/admin/*` | Chỉ nhận `BACKEND_ADMIN_TOKEN`, không nhận access token | Đã cài + có test | `test_backend_api.py` (admin) |
| E7 | Console lộ ra mạng | Mặc định nghe `127.0.0.1`; mật khẩu vận hành trong `.env` | Đã cài; HTTPS / reverse proxy: kế hoạch | `.env.example` (`CONSOLE_HOST`) |

### Tầng agent

| Điểm vào | Mối đe dọa | Biện pháp | Trạng thái | Bằng chứng |
|---|---|---|---|---|
| E1 | Mạo danh MSSV hoặc vai cố vấn trong câu chat | Danh tính chỉ đến từ token phiên; luật planner từ chối câu hỏi về MSSV khác trước khi gọi LLM | Đã cài + có test; chưa đo | `PI02`, `PI03`, `PI07`, `PI08` |
| E1 | Ép xác nhận "đủ điều kiện tốt nghiệp" | Writer không tự kết luận khi thiếu căn cứ; câu trả lời mẫu (không LLM) không kết luận; luật `record_figures_match` bắt số tín chỉ / ĐTBTL lệch hồ sơ; judge đối chiếu kết luận với bằng chứng | Đã cài + có test; chưa đo | `PI04`, `PI12`, `PI14` |
| E1 | Ép bịa điều khoản | R2 khi không có căn cứ; luật `cited_provisions_are_retrieved` (mọi trích dẫn phải nằm trong đoạn đã tra) | Đã cài + có test; chưa đo | `PI10` |
| E1 | Lộ system prompt / token | Token không vào ngữ cảnh LLM; canary trong prompt của writer và judge; `sanitize` xoá canary/token khỏi câu trả lời; luật `no_secrets` kiểm lại | Đã cài + có test; chưa đo | `PI01`, `PI06`, `PI13` |
| E1 | Dò hệ thống bằng nhiều câu, kéo dài jailbreak nhiều lượt, đốt chi phí | Giới hạn 10 câu mỗi hội thoại (UC9): câu thứ 11 trả R1, không gọi LLM; mọi lời gọi LLM có `max_output_tokens` | Đã cài + có test. Chưa giới hạn số hội thoại mỗi người | `test_backend_usecases.py` (limit); `H18` |
| E2 | Lịch sử giả "chế độ quản trị" dẫn dắt router | Quyền chỉ đến từ token; router chỉ chọn action trong enum (structured output), lịch sử trong thẻ `<history>` khai báo là dữ liệu, cắt 300/500 ký tự; luật chạy trước router | Đã cài + có test; chưa đo | `PI09` |
| E2' | Router bị dẫn dắt viết câu hỏi lại "đẹp" để judge cho qua | Câu viết lại giới hạn độ dài (500 / 200 ký tự), chỉ dùng làm truy vấn và câu hỏi cho judge; judge vẫn đối chiếu bản nháp với bằng chứng, luật số liệu và trích dẫn không phụ thuộc câu hỏi | Một phần; chưa đo. Rủi ro còn lại ở mục 6 | — |
| E3 | Đoạn văn độc trong quy chế | Prompt writer và judge đánh dấu `<regulations>` là dữ liệu; judge đối chiếu với các đoạn đã tra; eval có fixture `PoisonedRegulations` chèn khoản giả vào kết quả tra cứu | Đã cài; fixture có test; chưa đo với LLM | `PI05`, `PI13`, `PI14`, `PI15` |
| E1–E3 | Judge cùng model với writer, cùng bị lừa | Judge có thể chạy model / nhà cung cấp khác (`VERIFIER_LLM_PROVIDER`, `VERIFIER_LLM_MODEL`) | Đã cài + có test; ablation "judge cùng model" chưa chạy | `test_eval_backend_agent.py` (ablation) |

### Dữ liệu

| Điểm vào | Mối đe dọa | Biện pháp | Trạng thái | Bằng chứng |
|---|---|---|---|---|
| A6 | Lịch sử chat và span thành bản sao dữ liệu cá nhân | Audit của MCP lưu pseudonym HMAC. **`messages` và `trace_spans` lưu nguyên văn số liệu học vụ**, chỉ chủ tài khoản (và console) đọc được, chưa có hạn tự xóa | Cần quyết (task F2, lệch cam kết D1) | `architecture.md` "Còn mở" 1 |
| E8 | Số liệu hồ sơ gửi cho nhà cung cấp LLM | Chỉ gửi trường cần cho câu hỏi (không CCCD, email); dữ liệu sinh viên trong repo là mô phỏng | Đã cài (mapper); với dữ liệu thật cần thỏa thuận xử lý dữ liệu với nhà cung cấp | S14 |

## 5. Kết quả kiểm thử

**Tầng tool.** `uv run co5151-eval security`, chạy lại ngày 27/11/2026: **16/16 ca đạt** (không gọi LLM).

**Tầng agent.** Bộ `injection` có 15 ca (11 trực tiếp, 4 gián tiếp: PI05, PI13–PI15). Kiểm thử tự động chạy cả 15 ca
qua `BackendAgent` không LLM để chắc ca nào cũng chạy được và khoản độc vào được bằng chứng
(`eval/tests/test_eval_injection.py`). Chưa có kết quả với LLM: chạy ở E4.

```bash
uv run co5151-eval run --suite injection --out eval/results/<lần-chạy>
```

Quan sát khi chạy không LLM (câu trả lời mẫu): PI05 và PI14 trượt vì câu trả lời mẫu trích nguyên văn đoạn quy chế,
gồm cả đoạn độc. Câu trả lời mẫu chỉ dùng khi LLM lỗi; xem mục 6.

## 6. Rủi ro còn lại

- Token là HMAC với khóa dùng chung, mô phỏng SSO. Lộ khóa thì giả được mọi token. Bản thật nên dùng JWT bất đối
  xứng, kiểm `aud`, có thu hồi token.
- Biện pháp tầng agent **chưa có số liệu với LLM thật** (E4).
- Verifier chỉ đối chiếu với các đoạn Advisor đã tra, không bắt được lỗi do tra sai đoạn. Graph RAG giảm lỗi này
  trên bộ hội thoại (hit@3 1.00 so với 0.417 của BM25, [regulation-graph.md](regulation-graph.md)) nhưng concept được
  viết khi đã thấy câu hỏi thử.
- Router viết lại câu hỏi cho judge (E2'): kẻ tấn công dàn dựng lịch sử có thể khiến câu viết lại lệch câu gốc, judge
  chấm câu dễ hơn. Luật số liệu và trích dẫn không bị ảnh hưởng.
- Câu trả lời mẫu khi LLM lỗi trích nguyên văn quy chế, nên đoạn độc (K3) đi thẳng ra người dùng. Kho quy chế do
  nhóm kiểm soát; nếu nạp nguồn ngoài thì cần rà nội dung lúc nạp.
- Giới hạn 10 câu tính theo hội thoại; người dùng mở hội thoại mới không giới hạn. Chưa có rate limit theo tài khoản.
- Kiểm tra rò rỉ dựa trên regex (`forbidden`), có thể bỏ sót cách diễn đạt khác. Cần chấm tay thêm một mẫu.
- Lịch sử chat và span lưu số liệu học vụ (A6, F2 chưa quyết).
