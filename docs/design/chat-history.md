# Lịch sử chat theo người dùng (nhánh `feat/chat-history`)

Ngày viết: 2026-11-12. Nhánh tách từ `feat/verifier` (`5900dde`), nên nằm trên cả Verifier và `feat/mcp-adapter`.
CI trên máy (Python 3.12): ruff đạt, hai lệnh `--check` đạt, `461 passed`. Chưa push.

## 1. Làm được gì

- Mỗi tài khoản thấy danh sách hội thoại cũ của **chính mình** ở thanh bên trái Chainlit; bấm vào để mở lại và hỏi
  tiếp, đổi tên, xóa, tìm theo tên, đánh giá 👍/👎 từng câu trả lời.
- Mở lại một hội thoại thì giữ cài đặt LLM cũ, và Advisor nhận các lượt cũ làm lịch sử.
- Mỗi hội thoại có **conversation id** (UUID). Mỗi câu hỏi có **trace id** (32 ký tự hex, định dạng W3C trace
  context, giống OpenTelemetry), hiện trong "Chi tiết xử lý", trong log server, trong metadata của tin nhắn trả lời,
  và một dòng trong bảng `chat_turns`.
- Đổi database chỉ bằng `CHAT_DATABASE_URL`; mặc định là file SQLite, không cần cài server.

Không tốn thêm lần gọi LLM nào: lưu trữ chỉ ghi lại kết quả đã có.

## 2. Thiết kế

```
Trình duyệt ──► Chainlit (apps/web) ──► history.ChatHistoryDataLayer ──► co5151_chat_store.ChatStore ──► SQLAlchemy ──► SQLite / PostgreSQL / ...
                    │                       (dịch dict của Chainlit)       (API async, dataclass)
                    └─ app.reply ── backend.ask (trace id) ── to_turn ──────► store.record_turn
```

- **Tách lớp**: `packages/chat-store` không biết Chainlit (chỉ có SQLAlchemy). `apps/web/history.py` là lớp mỏng dịch
  giữa Chainlit và store. Đổi giao diện chat, hoặc cho eval / API khác ghi vào cùng store, không phải sửa store.
- **Dùng cơ chế có sẵn của Chainlit** (custom data layer `@cl.data_layer`), không tự vẽ sidebar. Chainlit tự kiểm tra
  chủ hội thoại trước mỗi lần đọc, đổi tên, xóa.
- **Đổi database dễ**: chỉ dùng kiểu dữ liệu chung, tên bảng có tiền tố `chat_` để dùng chung database với service
  khác, engine bật `pool_pre_ping` cho server. SQLite bật WAL và foreign key.
- **Không lưu thứ không nên lưu**: Chainlit mặc định ghi cả user session vào metadata hội thoại (có lịch sử chat,
  object Advisor). Data layer chỉ giữ `chat_settings`, `chat_profile`, `client_type`. Token phiên Student Record
  không bao giờ vào database.

## 3. Bảng

| Bảng | Một dòng là | Cột chính |
|---|---|---|
| `chat_users` | Một tài khoản đã đăng nhập | `id`, `identifier` (tên đăng nhập, unique), `metadata` |
| `chat_conversations` | Một hội thoại | `id` (= thread id của Chainlit), `user_id`, `title`, `metadata`, `tags`, `created_at`, `updated_at` |
| `chat_steps` | Một tin nhắn hoặc bước hiển thị | `id`, `conversation_id`, `parent_id`, `type` (user_message, assistant_message, system_message, tool, run), `output`, `metadata` (có `trace_id`) |
| `chat_turns` | Trace của một câu hỏi | `trace_id`, `conversation_id`, `user_message_id`, `answer_message_id`, `outcome`, `tool_calls`, `citations`, `verifier_rounds`, `input_tokens`, `output_tokens`, `latency_ms`, `llm`, `error` |
| `chat_feedback` | Một đánh giá 👍/👎 | `id`, `step_id` (mỗi bước tối đa một), `value`, `comment` |

## 4. Cây file đã thay đổi

```
CO5151-Project/
├── ~ .env.example                      thêm CHAT_DATABASE_URL
├── ~ .gitignore                        bỏ qua .data/
├── ~ README.md                         thêm packages/chat-store, mục lịch sử chat
├── ~ pyproject.toml, uv.lock           đăng ký package mới; thêm sqlalchemy 2.0, aiosqlite, greenlet
├── packages/chat-store/                + PACKAGE MỚI (co5151-chat-store)
│   ├── + pyproject.toml, README.md
│   ├── + src/co5151_chat_store/models.py     5 bảng SQLAlchemy
│   ├── + src/co5151_chat_store/records.py    dataclass trả về cho bên ngoài
│   ├── + src/co5151_chat_store/store.py      ChatStore: API async
│   ├── + src/co5151_chat_store/config.py     đọc CHAT_DATABASE_URL, sinh trace id
│   └── + tests/conftest.py, test_chat_store.py
├── apps/web/
│   ├── ~ pyproject.toml                       phụ thuộc thêm co5151-chat-store
│   ├── ~ .chainlit/config.toml                tắt tải file lên
│   ├── ~ README.md
│   ├── ~ src/co5151_web/backend.py            trace id mỗi câu, to_turn
│   ├── + src/co5151_web/history.py            data layer của Chainlit
│   ├── ~ src/co5151_web/app.py                bật data layer, mở lại hội thoại, ghi trace
│   ├── ~ tests/conftest.py                    chặn chainlit đọc .env (xem mục 7)
│   ├── ~ tests/test_web_backend.py
│   └── + tests/test_web_history.py
└── docs/
    ├── ~ README.md
    ├── ~ design/threat-model.md               dòng A6
    └── + design/chat-history.md               file này
```

## 5. Từng file

**`packages/chat-store`**

- `models.py`: 5 bảng ở mục 3. Kiểu ngày giờ có timezone, JSON cho metadata / danh sách.
- `records.py`: `User`, `Conversation`, `Step`, `Feedback`, `Turn`, `Page`; code bên ngoài chỉ thấy các dataclass này.
- `store.py`: `ChatStore.from_url(url)`, `create_schema()` (tạo bảng còn thiếu). Các nhóm hàm: user
  (`get_or_create_user`), hội thoại (`upsert_conversation` chỉ đổi trường được truyền, `get_conversation`,
  `list_conversations` mới nhất trước, phân trang bằng cursor, tìm theo tên), tin nhắn (`upsert_step`, ghi tin nhắn
  thì hội thoại nhảy lên đầu danh sách), feedback, trace (`record_turn`, `get_turn`, `list_turns`). Mọi giờ lưu UTC.
- `config.py`: `database_url()` đọc `CHAT_DATABASE_URL` (trống → SQLite mặc định, `off` → tắt); `new_trace_id()`.

**`apps/web`**

- `backend.py`: `ask(..., trace_id=None)` tạo trace id nếu chưa có, ghi một dòng log `trace=... outcome=... tools=...`
  và thêm "Trace ID" vào "Chi tiết xử lý". `to_turn(details, ...)` dựng bản ghi `Turn`.
- `history.py`: `ChatHistoryDataLayer` cài đủ interface `BaseDataLayer` của Chainlit bằng `ChatStore`, tạo bảng ở
  lần dùng đầu. `chat_history(thread)` lấy các lượt hỏi đáp của hội thoại cũ cho Advisor. `guest_identifier()` cho
  mỗi lần đăng nhập `khach` một danh tính riêng.
- `app.py`: đăng ký data layer khi `CHAT_DATABASE_URL` khác `off`; `on_chat_resume` khôi phục cài đặt và lịch sử;
  mỗi câu hỏi: tạo trace id, gắn vào tin nhắn trả lời và bước "Chi tiết xử lý", lưu trace (lỗi lưu chỉ ghi log,
  không làm hỏng chat). Thông báo hệ thống là `system_message` nên không lọt vào lịch sử của Advisor.

## 6. Đổi database / deploy

| Môi trường | `CHAT_DATABASE_URL` | Cần thêm |
|---|---|---|
| Máy cá nhân | để trống (file `apps/web/.data/chat.db`) | không |
| Server PostgreSQL | `postgresql+asyncpg://user:pass@host:5432/co5151` | `uv sync --extra postgres` (driver `asyncpg`, đã khai báo và có trong `uv.lock`) |
| Không lưu | `off` | không |

Bảng tự tạo ở lần chạy đầu. Database khác (MySQL...) dùng được nếu có driver async của SQLAlchemy, nhưng chưa thử.

## 7. Đã kiểm tra

- Test: 11 test store, 9 test data layer và helper, 2 test trace id ở backend. Không test nào gọi LLM.
- **Chạy app thật** (không có key LLM, database tạm), lái bằng client socket.io như trình duyệt: `sv001` hỏi 2 câu →
  2 trace id khác nhau, khớp giữa log, metadata tin nhắn và `chat_turns`; sidebar của `sv001` có hội thoại, của
  `sv002` rỗng; `sv002` mở hội thoại của `sv001` bị trả HTTP 401; mở lại khôi phục đủ tin nhắn; metadata hội thoại
  chỉ còn `chat_settings`, `client_type`.
- **Lỗi đã gặp và sửa** (`c830ad2`): `import chainlit` tự đọc `.env` ở thư mục hiện tại. Khi chạy pytest ở gốc repo,
  key LLM thật bị nạp cho cả phiên test và vài test cũ của Advisor đã gọi Gemini thật (đếm được 14 lời gọi khi chặn).
  Conftest của web giờ đặt `CHAINLIT_ENV_FILE=/dev/null`, và có test kiểm tra không có key nào bị nạp.

## 8. Cần Kiên quyết (hỏi ngày mai)

1. **Mâu thuẫn với cam kết D1 / threat model A6.** Proposal ghi bộ nhớ dài hạn "tuyệt đối không lưu dữ liệu điểm
   nhạy cảm ra ngoài phiên", nhưng lịch sử chat lưu nguyên văn câu trả lời (có tín chỉ, ĐTBTL). Chọn một:
   (a) giữ như hiện tại, chỉ chủ tài khoản đọc được, ghi rõ trong báo cáo; (b) thêm thời hạn tự xóa
   (ví dụ `CHAT_RETENTION_DAYS`); (c) chỉ lưu câu hỏi và trace, không lưu nội dung câu trả lời.
2. **Migration**: hiện tạo bảng bằng `create_all`. Có cần thêm Alembic ngay (để đổi cấu trúc bảng trên server mà
   không mất dữ liệu) hay để sau khi chốt nơi deploy?
3. **Deploy ở đâu** (PostgreSQL tự dựng, Neon / Supabase, hay chỉ demo trên máy)? Tôi đã thử SQLite, chưa thử
   PostgreSQL thật.
4. **Bộ nhớ dài hạn của Advisor**: hiện chỉ lưu hội thoại. `MemoryGate` (nguyện vọng người dùng tự nói) vẫn chỉ nằm
   trong RAM. Có muốn lưu nó theo user luôn không?
5. **Thời hạn đăng nhập**: đã sửa lỗi "Server vừa khởi động lại nên phiên đã hết" (token Student Record được cấp
   lại cho tài khoản đã đăng nhập, không lưu token vào database). Hệ quả: cookie đăng nhập còn hạn thì đọc được hồ
   sơ, mà hạn hiện là 15 ngày (`user_session_timeout`, mặc định của Chainlit). Có muốn rút ngắn, ví dụ 1 ngày?
6. **Khách**: mỗi lần đăng nhập `khach` là một người mới nên đăng xuất là mất lịch sử. Được không?
7. **Thứ tự merge**: nhánh này nằm trên `feat/verifier`, nhánh đó nằm trên `feat/mcp-adapter`. Ba PR phải merge theo
   thứ tự đó.

## 9. Danh sách commit

| Commit | Nội dung |
|---|---|
| `02ed099` | feat(chat-store): long-term chat history per user on any SQLAlchemy database |
| `3633607` | feat(web): a trace id for every chat turn |
| `bf5f282` | feat(web): Chainlit data layer on the chat store |
| `c830ad2` | fix(web): tests must not load the developer's .env through chainlit |
| `3dc96ed` | feat(web): chat history per user in the sidebar, resume and a trace per turn |
