# Kiến trúc: frontend Chainlit + backend API (clean architecture)

Quyết định ngày 2026-11-12, thay cho cách cũ: web ráp Advisor trực tiếp, gọi code nội bộ của `student_server`.

## Thành phần

```
frontend/  (Chainlit)  --HTTP/SSE-->  backend/ (FastAPI)  --MCP Streamable HTTP-->  mcp/student-server
                                          |                                       mcp/regulation-server
                                          +--> LLM (OpenAI-compatible), database (SQLAlchemy)
```

- **frontend** chỉ hiển thị: đăng nhập, chat, sidebar lịch sử. Không biết Advisor, MCP, LLM hay database.
- **backend** là nơi duy nhất ráp mọi thứ (`container.py`). Hai MCP server vẫn là hệ thống riêng.
- **eval** gọi use case của backend trong cùng process (`co5151_eval.backend_agent`), không qua HTTP.

## Tầng trong backend (`backend/src/co5151_backend/`)

| Tầng | Nội dung | Được import |
|---|---|---|
| `domain/` | Conversation, Message, Trace, Principal, Evidence, lỗi | không gì ngoài pydantic/contracts |
| `application/ports.py` | Protocol: repository, gateway MCP, `ChatModel`, cấp token, `EventSink` | domain |
| `application/agents/` | Advisor (planner, công cụ, viết câu trả lời), Verifier (luật + judge) | domain, ports |
| `application/usecases/` | đăng nhập, `AskQuestion`, hội thoại, feedback | domain, ports, agents |
| `infrastructure/` | SQLAlchemy, MCP client, LLM, SSO giả lập, JWT | mọi tầng trên |
| `api/` | FastAPI router, DTO, SSE | usecases (qua container) |

Database, MCP và LLM đều là adapter sau một port; đổi adapter không phải sửa use case.

## Quyết định chính

1. **Agent ≠ use case.** Advisor và Verifier là hai vai trò, chỉ dùng port. `AskQuestion` điều phối: lưu câu hỏi
   → Advisor thu bằng chứng → Advisor viết nháp → Verifier kiểm, viết lại tối đa 1 lần → lưu câu trả lời + trace.
2. **Stream không phát bản nháp.** SSE phát sự kiện tiến trình (`step`) ngay khi chạy; câu trả lời (`answer`) chỉ
   gửi sau khi Verifier cho qua, vì bản nháp có thể bị từ chối.
3. **Lịch sử do backend đọc từ repository**; client chỉ gửi câu mới. Mọi truy vấn lọc theo chủ hội thoại, hội
   thoại của người khác trả 404.
4. **Token Student Record không rời backend.** Mỗi câu hỏi backend ký một token ngắn hạn (`STUDENT_MCP_TOKEN_TTL`)
   từ claims của tài khoản; frontend chỉ giữ access token của backend (JWT, `BACKEND_TOKEN_SECRET`).
5. **SSO giả lập**: backend đọc `accounts.json` của student-server và ký token bằng `co5151_contracts.security`
   (secret dùng chung). Sau này thay bằng endpoint đăng nhập của student-server (gọi HTTP).
6. **Planner kiểm luật trước**, chỉ hỏi LLM (structured output, enum) khi luật không quyết được. LLM lỗi thì
   báo lỗi có kiểu; use case chọn template và ghi `llm_error` vào trace thay vì im lặng.
7. **Async từ đầu đến cuối**: FastAPI, `AsyncOpenAI`, MCP client async. Regulation MCP chạy Streamable HTTP như
   Student Record.
8. **Database mới**, không migrate dữ liệu chat cũ (dữ liệu demo). Bảng mới không theo format của Chainlit.
9. **eval dùng gateway trong process** (gọi thẳng service của MCP server) để chạy nhanh; app luôn đi qua MCP.

## Verifier và chi phí LLM

Verifier kiểm bản nháp hai lớp: luật trước (trích dẫn phải nằm trong các đoạn quy chế đã tra, không lộ token/canary),
đạt rồi mới gọi LLM judge (số liệu hồ sơ khớp, kết luận suy ra được từ bằng chứng). `revise` → Advisor viết lại 1
lần rồi kiểm lại; không đạt hoặc `refuse` → từ chối. Lời gọi LLM thêm cho mỗi câu: `llm` 1 (3 nếu viết lại),
`rules` 0 (1 nếu viết lại), `off` 0. Đo một lần trên câu P02 (`gemini-3.1-flash-lite`, có viết lại, code cũ ngày
2026-11-10): 7 lời gọi, 12.264 + 1.675 token, 12,6 s. Chưa có số liệu cả bộ 24 câu với Verifier.

## Còn mở

1. **Dữ liệu điểm trong lịch sử chat** mâu thuẫn với cam kết D1 (threat model A6): giữ, thêm hạn tự xóa, hay chỉ
   lưu câu hỏi + trace?
2. **Đổi cấu trúc bảng**: hiện chỉ tạo bảng còn thiếu; khi deploy thật thì thêm Alembic. PostgreSQL chưa chạy với
   server thật.
3. **Khách**: mỗi lần đăng nhập `khach` là một danh tính mới, đăng xuất là mất lịch sử.
4. Đăng nhập qua endpoint của student-server (quyết định 5) chưa làm.
