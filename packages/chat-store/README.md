# co5151-chat-store

Lưu lâu dài lịch sử chat của từng người dùng: cuộc hội thoại, các tin nhắn, và **một trace cho mỗi câu trả lời**
(trace id, tool đã gọi, trích dẫn, số lượt Verifier, token, độ trễ, model). Không phụ thuộc Chainlit: `apps/web`
nối package này vào giao diện chat.

## Đổi database bằng URL

Mọi thứ đi qua SQLAlchemy 2 (async), chỉ dùng kiểu dữ liệu chung (String, Text, Integer, Boolean, DateTime, JSON),
nên đổi database chỉ cần đổi `CHAT_DATABASE_URL`:

| `CHAT_DATABASE_URL` | Dùng khi |
|---|---|
| để trống | Mặc định: file SQLite `apps/web/.data/chat.db` (không commit) |
| `sqlite+aiosqlite:////đường/dẫn/chat.db` | SQLite ở chỗ khác |
| `postgresql+asyncpg://user:pass@host:5432/co5151` | Server PostgreSQL; cài driver bằng `uv sync --extra postgres` hoặc thêm `co5151-chat-store[postgres]` |
| `off` | Tắt lưu lịch sử |

Tên bảng đều bắt đầu bằng `chat_` để dùng chung một database với service khác.

## Bảng

| Bảng | Một dòng là | Khóa |
|---|---|---|
| `chat_users` | Một tài khoản đã đăng nhập (`identifier` = tên đăng nhập) | `id` (UUID) |
| `chat_conversations` | Một cuộc hội thoại của một người dùng | `id` = conversation id (UUID) |
| `chat_steps` | Một tin nhắn hoặc bước hiển thị trong chat (câu hỏi, câu trả lời, "Chi tiết xử lý") | `id` (UUID) |
| `chat_turns` | Một lượt hỏi đáp: trace của câu trả lời | `trace_id` (32 ký tự hex, định dạng W3C trace context) |
| `chat_feedback` | Đánh giá 👍/👎 của người dùng cho một câu trả lời | `id`, mỗi bước tối đa một |

Trace id được ghi cả vào `metadata` của tin nhắn trả lời, nên từ một tin nhắn tra ngược được trace và ngược lại.

## Dùng

```python
from co5151_chat_store import ChatStore, Turn, new_trace_id

store = ChatStore.from_url("sqlite+aiosqlite:///chat.db")
await store.create_schema()  # tạo bảng còn thiếu, không đụng dữ liệu đã có
user = await store.get_or_create_user("sv001")
await store.upsert_conversation("<uuid>", user_id=user.id, title="Điều kiện làm luận văn")
await store.record_turn(Turn(trace_id=new_trace_id(), conversation_id="<uuid>", outcome="answer"))
page = await store.list_conversations(user.id, limit=20)
```

## Giới hạn

- Bảng được tạo bằng `create_schema()` (tạo nếu chưa có). Chưa có migration: đổi cấu trúc bảng sau này cần thêm
  Alembic hoặc xóa database cũ.
- Dữ liệu chat chứa thông tin học vụ của sinh viên (mô phỏng). Chưa có thời hạn lưu tự xóa.
