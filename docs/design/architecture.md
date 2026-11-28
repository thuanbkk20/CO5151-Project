# Kiến trúc: frontend Chainlit + backend API (clean architecture)

Quyết định ngày 2026-11-12, thay cho cách cũ: web ráp Advisor trực tiếp, gọi code nội bộ của `student_server`.

## Thành phần

```
frontend/  (Chainlit)  --HTTP/SSE-->  backend/ (FastAPI)  --MCP Streamable HTTP-->  mcp/student-server
                                          |                                       mcp/regulation-server (BM25)
                                          |                                       hoặc mcp/regulation-graph (graph)
                                          +--> LLM (OpenAI-compatible), database (SQLAlchemy)
```

- **frontend** chỉ hiển thị: đăng nhập, chat, sidebar lịch sử, nguyên văn điều khoản được trích dẫn (qua
  `GET /provisions/{id}` của backend). Không biết Advisor, MCP, LLM hay database. Chi tiết: [chat-ui.md](chat-ui.md).
- **backend** là nơi duy nhất ráp mọi thứ (`container.py`). Hai MCP server vẫn là hệ thống riêng.
- **eval** gọi use case của backend trong cùng process (`co5151_eval.backend_agent`), không qua HTTP.
- **console** (cho nhóm, không cho sinh viên; đăng nhập bằng tài khoản vận hành trong `.env`) đọc trace qua API admin của backend (`/admin/*`, token
  `BACKEND_ADMIN_TOKEN`) và chạy đánh giá qua API người dùng như app chat. Chi tiết:
  [eval-console.md](eval-console.md).

## Tầng trong backend (`backend/src/co5151_backend/`)

| Tầng | Nội dung | Được import |
|---|---|---|
| `domain/` | Conversation, Message, Trace, Principal, Evidence, lỗi | không gì ngoài pydantic/contracts |
| `application/ports.py` | Protocol: repository, gateway MCP, `ChatModel`, cấp token, `EventSink` | domain |
| `application/agents/` | Advisor (planner, công cụ, viết câu trả lời), Verifier (luật + judge) | domain, ports |
| `application/usecases/` | đăng nhập, `AskQuestion`, hội thoại, feedback | domain, ports, agents |
| `infrastructure/` | SQLAlchemy, MCP client, LLM, SSO giả lập, JWT | mọi tầng trên |
| `api/` | FastAPI router, DTO, SSE | usecases (qua container) |

Database, MCP và LLM đều là adapter sau một port; đổi adapter không phải sửa use case. Một endpoint có thể phục vụ
nhiều họ model (Azure AI Foundry): tham số khác nhau theo model nằm trong `MODEL_PROFILES` của
`infrastructure/llm.py`. Mỗi provider có danh sách model sửa tay trong `PROVIDERS`; người dùng chỉ chọn trong danh
sách đó ([foundry-models.md](foundry-models.md)).

## Quyết định chính

1. **Agent ≠ use case.** Advisor và Verifier là hai vai trò, chỉ dùng port. `AskQuestion` điều phối: kiểm giới hạn
   câu hỏi → lưu câu hỏi → Advisor thu bằng chứng → Advisor viết nháp → Verifier kiểm, viết lại tối đa 1 lần (tra
   thêm quy chế trước nếu thiếu căn cứ) → lưu câu trả lời + trace. Chi tiết C1–C6, D1–D3:
   [agent-improvements.md](agent-improvements.md).
2. **Stream không phát bản nháp.** SSE phát sự kiện tiến trình (`step`) ngay khi chạy; câu trả lời (`answer`) chỉ
   gửi sau khi Verifier cho qua, vì bản nháp có thể bị từ chối.
3. **Lịch sử do backend đọc từ repository**; client chỉ gửi câu mới. Mọi truy vấn lọc theo chủ hội thoại, hội
   thoại của người khác trả 404.
4. **Token Student Record không rời backend.** Mỗi câu hỏi backend ký một token ngắn hạn (`STUDENT_MCP_TOKEN_TTL`)
   từ claims của tài khoản; frontend chỉ giữ access token của backend (JWT, `BACKEND_TOKEN_SECRET`).
5. **SSO giả lập**: backend đọc `accounts.json` của student-server và ký token bằng `co5151_contracts.security`
   (secret dùng chung). Sau này thay bằng endpoint đăng nhập của student-server (gọi HTTP).
6. **Planner kiểm luật trước**, chỉ hỏi LLM (structured output, enum) khi luật không quyết được. Router đọc 4 tin
   gần nhất và trong cùng lời gọi viết câu hỏi đủ ngữ cảnh, truy vấn quy chế, câu hỏi lại. LLM lỗi thì báo lỗi có
   kiểu; use case chọn template và ghi `llm_error` vào trace thay vì im lặng.
7. **Async từ đầu đến cuối**: FastAPI, `AsyncOpenAI`, MCP client async. Regulation MCP chạy Streamable HTTP như
   Student Record.
8. **Database mới**, không migrate dữ liệu chat cũ (dữ liệu demo). Bảng mới không theo format của Chainlit.
9. **Hai RAG quy chế cùng contract**: `regulation-server` (BM25, của Đức) và `regulation-graph` (graph phiên bản +
   khái niệm, [regulation-graph.md](regulation-graph.md)) phục vụ cùng hai tool trên cùng cổng; `REGULATION_ENGINE`
   chọn bản chạy. Backend không biết đang dùng bản nào.
10. **eval dùng gateway trong process** (gọi thẳng service của MCP server) để chạy nhanh; app luôn đi qua MCP.
11. **Span từng node** (planner, MCP, writer, Verifier) lưu cùng trace trong bảng `trace_spans`, đọc qua
    `GET /traces/{id}/spans`, không stream: nháp bị Verifier loại chỉ thấy sau khi có câu trả lời cuối. Chi tiết:
    [agent-flow.md](agent-flow.md).

## Verifier và chi phí LLM

Verifier kiểm bản nháp hai lớp: luật trước (trích dẫn phải nằm trong các đoạn quy chế đã tra, không lộ token/canary,
số tín chỉ/ĐTBTL nói về sinh viên khớp hồ sơ), đạt rồi mới gọi LLM judge (kết luận suy ra được từ bằng chứng). Judge
chấm câu hỏi đã điền ngữ cảnh, không thấy lịch sử. `revise` vì thiếu căn cứ → tra thêm quy chế (MCP, không LLM) →
Advisor viết lại 1 lần rồi kiểm lại; không đạt hoặc `refuse` → từ chối.

Lời gọi LLM mỗi câu (27/11, sau C1–D3):

| Bước | Số lời gọi |
|---|---|
| Câu thứ 11 trở đi của hội thoại | 0 (câu cố định R1) |
| Planner | 0 khi luật quyết; 1 mỗi bước luật không quyết (tối đa 192 token ra, thêm ~4 tin lịch sử vào đầu vào) |
| Viết lại câu nối tiếp | +1 chỉ khi có lịch sử, câu trông như câu nối tiếp, luật quyết hết, và cần tra quy chế hoặc judge |
| Viết câu trả lời | 1 |
| Verifier `llm` | 1; viết lại: +2 (viết lại + judge); luật bắt lệch số liệu: judge vòng đó không chạy |
| Verifier `rules` / `off` | 0 (+1 nếu viết lại) / 0 |

Đo một lần trên câu P02 (`gemini-3.1-flash-lite`, có viết lại, code cũ ngày
2026-11-10): 7 lời gọi, 12.264 + 1.675 token, 12,6 s. Chưa có số liệu cả bộ 24 câu với Verifier.

## Còn mở

1. **Dữ liệu điểm trong lịch sử chat** mâu thuẫn với cam kết D1 (threat model A6): giữ, thêm hạn tự xóa, hay chỉ
   lưu câu hỏi + trace? Span (`trace_spans`) cũng lưu kết quả Student Record và nháp, nên cùng quyết định này.
2. **Đổi cấu trúc bảng**: hiện chỉ tạo bảng còn thiếu; khi deploy thật thì thêm Alembic. PostgreSQL chưa chạy với
   server thật.
3. **Khách**: mỗi lần đăng nhập `khach` là một danh tính mới, đăng xuất là mất lịch sử.
4. Đăng nhập qua endpoint của student-server (quyết định 5) chưa làm.
