# Console vận hành: trace, đánh giá, bộ câu hỏi, prompt

Cập nhật: 2026-11-18. Theo dõi tiến độ: [../ui-and-eval-console.md](../ui-and-eval-console.md).

## Mục tiêu

Một web app riêng cho nhóm (không phải cho sinh viên), sidebar trái có các trang:

| Trang | Làm gì |
|---|---|
| Sessions | Danh sách hội thoại; một session = các lượt hỏi–đáp theo thứ tự, bấm lượt nào mở trace lượt đó |
| Traces | Danh sách câu trả lời gần đây; lọc theo session id (id hội thoại); bấm một trace → panel phải xem luồng node (input/output) |
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
- **Đăng nhập** (P5c): một tài khoản vận hành, tên `CONSOLE_USERNAME` (mặc định `admin`), mật khẩu
  `CONSOLE_PASSWORD`, cả hai trong `.env`, không nằm trong code. `CONSOLE_PASSWORD` trống thì không ai đăng nhập
  được (đóng chứ không mở). Đăng nhập đúng → cookie phiên `HttpOnly`, `SameSite=Lax`, hạn 12 giờ, ký HMAC-SHA256
  bằng secret ngẫu nhiên sinh lúc khởi động (khởi động lại = đăng nhập lại; không thêm biến môi trường, không thêm
  thư viện). Middleware chặn mọi trang trừ `/login`, `/static/`, `/healthz`: trang thường chuyển về
  `/login?next=...`; nội dung panel (`?panel=1`) trả 401 kèm link đăng nhập lại. `next` chỉ nhận đường dẫn nội bộ.
  So mật khẩu bằng `hmac.compare_digest`. Sidebar có tên tài khoản và nút "Đăng xuất" (POST).
- **Prompt** (đợt sau): console lưu các phiên bản, có API `GET /api/prompts/{name}` cho backend. Backend thêm port
  `PromptSource` + adapter HTTP có cache và fallback về prompt trong code; ghi phiên bản prompt vào trace. Canary vẫn
  do code chèn, không nằm trong prompt sửa được.

## Kế hoạch commit

| # | Commit | Nội dung | Trạng thái |
|---|---|---|---|
| | **P0. Bỏ sidebar Chainlit** | | |
| 1 | `revert(web): drop the agent flow sidebar` | revert `7f7d187` `b6c9f00` `87e55d1` `d062328` `23dc521` | xong `74eb425` |
| 2 | `feat(web): show the conversation id in the answer details` | `details_markdown` + test | xong `b1f63d7` |
| 3 | `docs: agent flow moves to the operator console` | agent-flow.md, README, architecture | xong `0fadd8c` |
| | **P1. API admin của backend** | | |
| 4 | `feat(backend): admin token for the operator console` | `BACKEND_ADMIN_TOKEN`, dependency kiểm token, `.env.example` + test | xong `4ef3ada` |
| 5 | `feat(backend): trace log for operators` | port `TraceLog` (gần đây, theo hội thoại; chi tiết có câu hỏi/câu trả lời/spans), memory + SQL + test | xong `0e6066a` |
| 6 | `feat(backend): GET /admin/traces and /admin/traces/{id}` | route, schema + test | xong `e276aa8` |
| | **P2. Khung console** | | |
| 7 | `feat(console): package skeleton with the sidebar layout` | pyproject, workspace, settings, CLI, layout, Procfile + test | xong `0c3da8d` |
| | **P3. Traces** | | |
| 8 | `feat(console): backend admin client` | httpx + test (MockTransport) | xong `18bac6e` |
| 9 | `feat(console): traces page` | danh sách, lọc theo session id, chi tiết luồng node + test | xong `cba2ace` |
| | **P4. Bộ câu hỏi** | | |
| 10 | `feat(console): question set store` | sqlite3, nhập bộ mặc định + test | xong `9e652b2` |
| 11 | `feat(console): question set pages` | danh sách, tạo, sửa, xóa + test | xong `ba43c37` |
| | **P5. Đánh giá** | | |
| 12 | `feat(console): answer a task through the backend API` | agent HTTP: đăng nhập, hội thoại, hỏi + test | xong `b5903ab` |
| 13 | `feat(console): evaluation runs` | chạy nền, chấm điểm, lưu kết quả + test | xong `7308caa` |
| 14 | `feat(console): evaluation pages` | bắt đầu chạy (cảnh báo chi phí), danh sách lần chạy, bảng kết quả | xong `8fa838e` |
| | **P5b. Góp ý của Kiên (15/11)** | | |
| 18 | `fix(console): the sidebar stays put while the page scrolls` | sidebar đứng yên, chỉ phần nội dung cuộn | xong `41330c6` |
| 19 | `feat(console): a trace opens in a side panel` | bấm trace → panel phải ~2/3 màn hình (HTML của trace lấy bằng `fetch`), bấm ra ngoài hoặc Esc để đóng; trang `/traces/{id}` vẫn mở trực tiếp được | xong `e8a801e` |
| 20 | `feat(backend): GET /admin/sessions` | danh sách hội thoại: chủ, tiêu đề, số lượt, lần cuối; port `TraceLog.sessions` + test | xong `4ad395f` |
| 21 | `feat(console): sessions page` | danh sách session; một session = các lượt hỏi–đáp theo thứ tự thời gian, bấm lượt nào mở panel trace lượt đó | xong `346ee65` |
| 22 | `docs: console side panel and sessions` | README console, plan | xong |
| 23 | `feat(console): a session opens in the side panel too` | bấm session → panel; trong panel bấm "Xem trace" thì panel chuyển sang trace, nút "← Quay lại" về session | xong |
| 24 | `feat(console): home lists the features as cards` | trang Tổng quan chỉ còn các thẻ tính năng (bỏ bảng cấu hình) | xong |
| | **P5c. Đăng nhập console** (Kiên, 18/11) | | |
| 25 | `docs(design): console sign-in` | plan dưới đây | xong |
| 26 | `feat(console): sign in with the operator account` | trang `/login`, cookie phiên, chặn mọi trang khi chưa đăng nhập, nút đăng xuất, `.env.example` + test | chưa |
| 27 | `docs: console sign-in` | README gốc, README console, architecture | chưa |
| | **P6. Prompt** (viết plan chi tiết trước khi làm) | | |
| 15 | `feat(console): prompt versions` | lưu, sửa, kích hoạt phiên bản + API cho backend | chưa |
| 16 | `feat(backend): prompts from the console` | port `PromptSource`, adapter HTTP, cache, fallback, ghi phiên bản vào trace | chưa |
| 17 | `docs: operator console` | README, architecture | chưa |

## Chưa quyết

- Đăng nhập vào console: đã có một tài khoản vận hành (P5c), chưa có HTTPS, chưa giới hạn số lần đăng nhập sai.
  Vẫn mặc định chỉ nghe ở `127.0.0.1`; deploy thật thì đặt sau reverse proxy có HTTPS.
- Cách đọc kết cục khi LLM viết câu trả lời (`trace.outcome` rỗng): console theo đúng `co5151_eval.backend_agent`
  (coi là `answer`) để số liệu khớp CLI; nhưng docstring của `Trace` nói kết cục khi đó phải đọc từ câu chữ
  (`scoring.classify`). Cần Kiên quyết định rồi sửa cả hai chỗ cùng lúc.
- Câu hỏi có `history` không chạy được qua API (API không cho chèn lượt cũ); hiện bộ 24 câu không có câu nào như vậy.
