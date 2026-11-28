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
  `GET /provisions/{id}` của backend). Không biết Advisor, MCP, LLM hay database. Chi tiết: [frontend/README.md](../../frontend/README.md).
- **backend** là nơi duy nhất ráp mọi thứ (`container.py`). Hai MCP server vẫn là hệ thống riêng.
- **eval** gọi use case của backend trong cùng process (`co5151_eval.backend_agent`), không qua HTTP.
- **console** (cho nhóm, không cho sinh viên; đăng nhập bằng tài khoản vận hành trong `.env`) đọc trace qua API admin của backend (`/admin/*`, token
  `BACKEND_ADMIN_TOKEN`) và chạy đánh giá qua API người dùng như app chat. Chi tiết:
  [console/README.md](../../console/README.md).

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
sách đó (mục "Model LLM" bên dưới).

## Quyết định chính

1. **Agent ≠ use case.** Advisor và Verifier là hai vai trò, chỉ dùng port. `AskQuestion` điều phối: kiểm giới hạn
   câu hỏi → lưu câu hỏi → Advisor thu bằng chứng → Advisor viết nháp → Verifier kiểm, viết lại tối đa 1 lần (tra
   thêm quy chế trước nếu thiếu căn cứ) → lưu câu trả lời + trace.
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
   khái niệm, [README](../../mcp/regulation-graph/README.md), có kết quả đo) phục vụ cùng hai tool trên cùng cổng; `REGULATION_ENGINE`
   chọn bản chạy. Backend không biết đang dùng bản nào.
10. **eval dùng gateway trong process** (gọi thẳng service của MCP server) để chạy nhanh; app luôn đi qua MCP.
11. **Span từng node** (planner, MCP, writer, Verifier) lưu cùng trace trong bảng `trace_spans`, đọc qua
    `GET /traces/{id}/spans`, không stream: nháp bị Verifier loại chỉ thấy sau khi có câu trả lời cuối. Không lưu system prompt, token;
    canary được thay bằng `[đã ẩn]`.

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
2026-11-10): 7 lời gọi, 12.264 + 1.675 token, 12,6 s. Chưa có số liệu cả bộ hội thoại với Verifier.

## Model LLM

Provider: Gemini (local), Azure OpenAI và Azure AI Foundry ở `koreacentral` (bản deploy, vì Gemini chặn VM ở Hong
Kong; xem [infra/azure/README.md](../../infra/azure/README.md)). Giá dùng cho eval: `eval/src/co5151_eval/data/prices.json`.

| Model | Giá vào / ra mỗi 1M token | Ghi chú (gọi thử 27/11) |
|---|---|---|
| `gpt-4.1-mini` | $0.40 / $1.60 | Model chính trên bản deploy |
| `gpt-5-mini` | $0.25 / $2.00 | Reasoning; không nhận `temperature=0`; cần chừa token cho suy nghĩ (`reasoning_headroom`) |
| `gpt-oss-120b` | $0.15 / $0.60 | Reasoning, rẻ nhất; **judge của Verifier** trên bản deploy |
| `Llama-3.3-70B-Instruct` | $0.71 / $0.71 | Nhận `json_schema` |
| `Phi-4` | $0.125 / $0.50 | Không nhận `json_schema` (tắt structured output) |

Giá lấy từ Azure Retail Prices API ngày 27/11. Mistral không deploy được (bán qua Marketplace, subscription miễn phí
không mua được); DeepSeek, Qwen... có quota bằng 0.

**Judge riêng** (`VERIFIER_LLM_PROVIDER`, `VERIFIER_LLM_MODEL`): judge dùng chính model của hội thoại thì model yếu
chấm yếu (từ chối vì lỗi không có thật) và so sánh model không công bằng. Thử 27/11: judge `gpt-4.1-mini` vẫn từ chối
câu "có thể chưa đạt" của `gpt-5-mini`; judge `gpt-oss-120b` cho cả hai qua, lỗi nó bắt là lỗi thật, và rẻ nhất.

## Còn mở

1. **Dữ liệu điểm trong lịch sử chat** lệch cam kết D1 (threat model A6): `messages` và `trace_spans` lưu nguyên văn
   số liệu học vụ, chưa có hạn tự xóa.
2. Ngoài phạm vi final: migration (Alembic, hiện chỉ tạo bảng còn thiếu), PostgreSQL với server thật, đăng nhập qua
   endpoint của student-server, lịch sử của `khach` (mỗi lần đăng nhập là một danh tính mới).
