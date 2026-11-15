# UI hiển thị agent và trang đánh giá (Kiên)

Theo dõi ý tưởng, quyết định và từng bước. Cập nhật: 2026-11-15.

## 1. Ý tưởng

### A. UI: thấy các agent nói chuyện với nhau
- Trong một lượt hỏi, hiện ra luồng: Advisor lập kế hoạch → gọi tool nào, nhận gì → soạn nháp → Verifier nhận xét
  gì → Advisor viết lại → câu trả lời cuối. Mục đích: demo dễ hiểu.

### B. Trang đánh giá + nơi chỉnh cấu hình AI
- Web đơn giản (HTML + bảng): chọn bộ câu hỏi, chạy đánh giá, xem điểm từng câu và tổng.
- Sau này là nơi chỉnh instruction (prompt) cho từng agent: mỗi lần gọi LLM, backend lấy prompt từ đây. Về sau
  thêm cấu hình RAG...

Làm A trước.

## 2. Hiện trạng (để biết phải thêm gì)

- UI hiện chỉ có một step "Chi tiết xử lý" liệt kê tên bước (`plan`, `tool`, `write`, `verify`) rồi bảng tóm tắt
  trace (`frontend/src/co5151_web/present.py`, `app.py` hàm `reply`).
- Trace chỉ lưu tên bước và tên tool: `steps: list[str]`, `tool_calls: list[str]`
  (`backend/.../domain/trace.py`). Không lưu nội dung nháp, nhận xét của Verifier hay kết quả tool.
- Có quyết định cố ý không gửi nháp ra ngoài: "No event carries a draft: the answer is only sent once the Verifier
  has passed it." (`backend/.../application/events.py`).
- Eval chạy bằng CLI `co5151-eval run|report|check-gold|security`, report là HTML tĩnh (`eval/src/co5151_eval/`).
- Prompt nằm cứng trong code (`application/agents/advisor/prompts.py`, `verifier/judge.py`).

## 3. Cần quyết định

| # | Câu hỏi | Đề xuất | Chốt |
|---|---|---|---|
| A1 | Hiện nháp + nhận xét Verifier có phá quyết định "không gửi nháp" không? | Chỉ hiện **sau khi** câu trả lời cuối đã qua Verifier, trong khung chi tiết; luồng stream vẫn không có nháp | Hiện input/output từng node ở sidebar phải, lấy qua API riêng sau khi có câu trả lời (Kiên, 15/11) |
| A2 | Ai được xem luồng agent? | Bật bằng biến môi trường (chế độ demo) hoặc theo role; sinh viên thường không thấy | |
| A3 | Lưu luồng agent ở đâu? | Thêm danh sách "agent message" vào Trace, lấy lại qua `GET /traces/{id}` | Bảng `trace_spans` riêng, API riêng `GET /traces/{id}/spans` (Kiên, 15/11) |
| B1 | Trang đánh giá là app riêng hay gắn vào backend? | App riêng (package mới), gọi eval trong process như hiện nay | |
| B2 | Backend lấy prompt từ trang đó thế nào? | Port `PromptSource` + adapter HTTP, có cache và fallback về prompt trong code; ghi phiên bản prompt vào trace | |
| B3 | Bảo vệ trang chỉnh prompt | Cần đăng nhập (sửa prompt = đổi hành vi hệ thống) | |

## 4. Các bước

### A. UI luồng agent
Thiết kế và kế hoạch commit: [design/agent-flow.md](design/agent-flow.md).
- [x] A.1 Backend: ghi span từng node, lưu, API `GET /traces/{id}/spans` (commit 1–4)
- [x] A.2 Frontend: sidebar phải hiện luồng node (commit 5–6)
- [ ] A.3 Chạy thử một câu bằng key thật (báo số lần gọi/token)

### B. Trang đánh giá
- [ ] B.1 Trang chạy bộ câu hỏi và hiện bảng kết quả
- [ ] B.2 Lưu và chỉnh prompt theo phiên bản
- [ ] B.3 Backend lấy prompt qua `PromptSource`
- [ ] B.4 Cấu hình RAG

## 5. Nhật ký

- 2026-11-15: tạo file, ghi ý tưởng và hiện trạng.
- 2026-11-15: chốt A1, A3; viết `design/agent-flow.md`.
- 2026-11-15: xong A.1, A.2 (nhánh `feat/agent-flow-ui`); chờ xem trên trình duyệt.
- 2026-11-15: đợt 2: panel mở sẵn, chọn câu trả lời bất kỳ kể cả hội thoại cũ (commit 8–11).
