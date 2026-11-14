# Lịch sử chat theo người dùng (nhánh `feat/chat-history`)

Cập nhật: 2026-11-12. Nhánh tách từ `feat/verifier`, nên nằm trên cả Verifier và `feat/mcp-adapter`. Chưa push.

## Dùng

```bash
uv sync
uvx honcho start        # http://localhost:8000
```

- Thanh bên trái liệt kê hội thoại của **tài khoản đang đăng nhập**; bấm để mở lại và hỏi tiếp, đổi tên, xóa, tìm.
- Mỗi câu trả lời có **trace id** (32 ký tự hex) ở cuối "Chi tiết xử lý" và trong log `web.1`.
- Dữ liệu nằm ở `apps/web/.data/chat.db` (SQLite, không commit). Xem bằng `sqlite3 apps/web/.data/chat.db`.
- Đăng nhập giữ 1 ngày. Khởi động lại server không cần đăng nhập lại.

| `CHAT_DATABASE_URL` | Ý nghĩa |
|---|---|
| để trống | SQLite `apps/web/.data/chat.db` |
| `postgresql+asyncpg://user:pass@host:5432/co5151` | Server PostgreSQL, cần `uv sync --extra postgres` |
| `off` | Không lưu lịch sử |

Lưu lịch sử không gọi LLM.

## Thiết kế

```
Chainlit (apps/web) ──► history.ChatHistoryDataLayer ──► co5151_chat_store.ChatStore ──► SQLite / PostgreSQL
```

- `packages/chat-store`: không biết Chainlit. 5 bảng `chat_users`, `chat_conversations`, `chat_steps`,
  `chat_turns` (một dòng mỗi câu hỏi, khóa là trace id), `chat_feedback`. Bảng tự tạo ở lần chạy đầu.
- `apps/web/history.py`: data layer của Chainlit, dịch giữa dict của Chainlit và store.
- `apps/web/app.py`: bật data layer, mở lại hội thoại (giữ cài đặt LLM, Advisor nhận lại lịch sử), ghi trace.

Ba quy tắc giữ cho dữ liệu đúng:

1. **Mọi lệnh ghi mang chủ** là user đã đăng nhập của phiên; chủ chỉ gán khi trống, không bao giờ đổi.
2. **Tạo dòng bằng `INSERT ... ON CONFLICT`**, không đọc rồi mới insert.
3. **Không lưu thứ không thuộc hội thoại**: thông báo của app, token Student Record, object Advisor. Metadata hội
   thoại chỉ giữ cài đặt LLM.

Token Student Record ngắn hạn, chỉ ở RAM server; khi thiếu hoặc sắp hết hạn thì cấp lại cho đúng tài khoản đã đăng
nhập (cookie Chainlit đã ký là bằng chứng danh tính).

## Các lỗi đã gặp và cách sửa

| Hiện tượng | Nguyên nhân | Sửa |
|---|---|---|
| "Server vừa khởi động lại nên phiên đã hết" | Token chỉ cấp lúc gõ mật khẩu, mất khi restart | Cấp lại token cho user đã đăng nhập (`4953f52`) |
| Thông báo cũ hiện lại mỗi lần mở thread | Thông báo được lưu như tin nhắn | Không lưu thông báo, ẩn cái đã lưu (`d34a29b`) |
| Mất câu hỏi đầu tiên | Tin nhắn đầu và tạo thread tranh nhau tạo cùng một dòng | `INSERT ... ON CONFLICT` (`cd81c8f`) |
| `Authorization for the thread failed`, `Session is disconnected` | Xóa thread đang mở rồi chat tiếp: thread bị tạo lại không có chủ | Mọi lệnh ghi mang chủ; thread không chủ bị ẩn và tự về tay người chat tiếp (`cd81c8f`, `d28acdf`) |
| Test gọi Gemini thật | `import chainlit` tự đọc `.env` của máy | Chặn trong conftest + test canh (`c830ad2`) |

## Đã kiểm tra

- `uv run pytest`: không test nào gọi LLM.
- Chạy app thật, không key LLM, lái bằng client socket.io như trình duyệt: hội thoại mới có chủ và tiêu đề; nối lại,
  mở lại, hỏi tiếp; xóa thread đang mở rồi chat tiếp rồi nối lại; `sv002` không thấy, không mở được và không gắn
  socket được vào hội thoại của `sv001`; mỗi câu một trace trỏ đúng tin nhắn đã lưu. Cũng chạy trên bản sao database
  của Kiên: thread hỏng `95cb853c` nối được lại và về tay `sv001` sau một câu hỏi.
- PostgreSQL: chỉ kiểm tra câu SQL sinh ra, **chưa chạy với server thật**.

## Còn cần Kiên quyết

1. **Dữ liệu điểm trong lịch sử** mâu thuẫn với cam kết D1 ("không lưu dữ liệu điểm ra ngoài phiên", threat model
   A6): giữ như hiện tại, thêm thời hạn tự xóa, hay chỉ lưu câu hỏi và trace?
2. **Đổi cấu trúc bảng sau này**: hiện chỉ tạo bảng còn thiếu. Khi deploy thật và cần sửa bảng thì thêm Alembic.
3. **Khách**: mỗi lần đăng nhập `khach` là một người mới, đăng xuất là mất lịch sử.
4. **Thứ tự merge**: `feat/mcp-adapter` → `feat/verifier` → `feat/chat-history`.
