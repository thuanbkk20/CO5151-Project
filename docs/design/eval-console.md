# Console vận hành: trace, đánh giá, bộ câu hỏi, prompt

Cập nhật: 2026-11-15. Theo dõi tiến độ: [../ui-and-eval-console.md](../ui-and-eval-console.md).

## Mục tiêu

Một web app riêng cho nhóm (không phải cho sinh viên), sidebar trái có 4 trang:

| Trang | Làm gì |
|---|---|
| Traces | Danh sách câu trả lời gần đây; lọc theo session id (id hội thoại); mở một trace xem luồng node (input/output) |
| Đánh giá | Chạy một bộ câu hỏi qua backend, bảng điểm từng câu và tổng, link sang trace của từng câu |
| Bộ câu hỏi | Tạo, sửa, xóa bộ câu hỏi; nhập bộ mặc định 24 câu của eval |
| Prompt | Sửa prompt của từng agent theo phiên bản; backend lấy prompt từ đây mỗi lần gọi LLM |

App chat Chainlit bỏ sidebar luồng agent, chỉ hiện `Trace ID` và `Conversation ID` để tra trong console.

## Thiết kế

- **Công nghệ**: FastAPI + Jinja2 (HTML render phía server) + một file CSS; form HTML thường, gần như không có
  JavaScript. Lưu dữ liệu riêng của console bằng `sqlite3` của Python. Không thêm thư viện mới (`jinja2`,
  `python-multipart` đã có trong `uv.lock`).
- **Package** `console/` → `co5151_console`, lệnh `co5151-console` (cổng 8200, có `--env-file`), thêm vào Procfile.
- **Tầng** (giống backend, rút gọn):

  | Thư mục | Vai trò |
  |---|---|
  | `ports.py` | Protocol: `BackendAdmin` (đọc trace), `AnswerAgent` (hỏi backend), `QuestionSetStore`, `RunStore`, `PromptStore` |
  | `services/` | Use case: traces, question_sets, evaluation, prompts. Không import FastAPI, httpx, sqlite3 |
  | `adapters/` | `backend_http.py` (httpx), `sqlite_store.py` |
  | `web/` | Route FastAPI + `templates/` + `static/` |
  | `container.py` | Chỗ duy nhất chọn adapter |

- **Đọc trace**: backend thêm API admin `GET /admin/traces?conversation_id=&limit=` và `GET /admin/traces/{id}`
  (trace + câu hỏi + câu trả lời + spans), bảo vệ bằng `BACKEND_ADMIN_TOKEN` (để trống = tắt API admin). Console
  giữ token này; trình duyệt không thấy.
- **Đánh giá chạy end-to-end qua API backend** như người dùng thật: đăng nhập bằng tài khoản demo của câu hỏi (hoặc
  `khach`), tạo hội thoại, hỏi, nhận câu trả lời + trace; chấm bằng `co5151_eval.scoring`. Trace của lần chạy nằm
  trong DB backend nên xem được ở trang Traces. Chạy nền, trang kết quả tự làm mới. Trước khi chạy hiện cảnh báo số
  câu và số lời gọi LLM tối đa (tốn tiền key).
- **Prompt** (đợt sau): console lưu các phiên bản, có API `GET /api/prompts/{name}` cho backend. Backend thêm port
  `PromptSource` + adapter HTTP có cache và fallback về prompt trong code; ghi phiên bản prompt vào trace. Canary vẫn
  do code chèn, không nằm trong prompt sửa được.

## Kế hoạch commit

| # | Commit | Nội dung | Trạng thái |
|---|---|---|---|
| | **P0. Bỏ sidebar Chainlit** | | |
| 1 | `revert(web): drop the agent flow sidebar` | revert `7f7d187` `b6c9f00` `87e55d1` `d062328` `23dc521` | chưa |
| 2 | `feat(web): show the conversation id in the answer details` | `details_markdown` + test | chưa |
| 3 | `docs: agent flow moves to the operator console` | agent-flow.md, README, architecture | chưa |
| | **P1. API admin của backend** | | |
| 4 | `feat(backend): admin token for the operator console` | `BACKEND_ADMIN_TOKEN`, dependency kiểm token, `.env.example` + test | chưa |
| 5 | `feat(backend): trace log for operators` | port `TraceLog` (gần đây, theo hội thoại; chi tiết có câu hỏi/câu trả lời/spans), memory + SQL + test | chưa |
| 6 | `feat(backend): GET /admin/traces and /admin/traces/{id}` | route, schema + test | chưa |
| | **P2. Khung console** | | |
| 7 | `feat(console): package skeleton with the sidebar layout` | pyproject, workspace, settings, CLI, layout, Procfile + test | chưa |
| | **P3. Traces** | | |
| 8 | `feat(console): backend admin client` | httpx + test (MockTransport) | chưa |
| 9 | `feat(console): traces page` | danh sách, lọc theo session id, chi tiết luồng node + test | chưa |
| | **P4. Bộ câu hỏi** | | |
| 10 | `feat(console): question set store` | sqlite3, nhập bộ mặc định + test | chưa |
| 11 | `feat(console): question set pages` | danh sách, tạo, sửa, xóa + test | chưa |
| | **P5. Đánh giá** | | |
| 12 | `feat(console): answer a task through the backend API` | agent HTTP: đăng nhập, hội thoại, hỏi + test | chưa |
| 13 | `feat(console): evaluation runs` | chạy nền, chấm điểm, lưu kết quả + test | chưa |
| 14 | `feat(console): evaluation pages` | bắt đầu chạy (cảnh báo chi phí), danh sách lần chạy, bảng kết quả | chưa |
| | **P6. Prompt** (viết plan chi tiết trước khi làm) | | |
| 15 | `feat(console): prompt versions` | lưu, sửa, kích hoạt phiên bản + API cho backend | chưa |
| 16 | `feat(backend): prompts from the console` | port `PromptSource`, adapter HTTP, cache, fallback, ghi phiên bản vào trace | chưa |
| 17 | `docs: operator console` | README, architecture | chưa |

## Chưa quyết

- Đăng nhập vào console: tạm thời chỉ bind `127.0.0.1`, không có login. Deploy thật thì cần login hoặc reverse
  proxy có xác thực.
- Câu hỏi có `history` không chạy được qua API (API không cho chèn lượt cũ); hiện bộ 24 câu không có câu nào như vậy.
