# Giao diện chat (`co5151-web`)

Giao diện Chainlit, chỉ là client của backend API (`co5151-api`): không chứa Advisor, MCP, LLM hay database.

## Chạy

```bash
uv sync                    # ở gốc repo
cp .env.example .env       # điền CHAINLIT_AUTH_SECRET (uv run chainlit create-secret); BACKEND_URL nếu khác mặc định
uv run co5151-api          # backend, cần Student Record và Regulation MCP đang chạy (xem README gốc)
uv run co5151-web          # http://localhost:8000
```

Tài khoản: `sv001` … `sv008` mật khẩu `demo` (sinh viên mô phỏng), `khach` (không có hồ sơ).

## Cấu trúc

| File | Vai trò |
|---|---|
| `src/co5151_web/client.py` | `BackendClient`: gọi API backend (đăng nhập, hội thoại, đánh giá, stream SSE câu trả lời, điều khoản trích dẫn) |
| `src/co5151_web/history.py` | Data layer của Chainlit chuyển tiếp sang backend: sidebar, mở lại, đổi tên, xóa, đánh giá |
| `src/co5151_web/present.py` | Chuyển dữ liệu backend sang dạng hiển thị: lời chào và câu gợi ý theo vai trò, nhãn tiến trình, dòng kiểm chứng, nút và panel điều khoản, thread của Chainlit |
| `src/co5151_web/app.py` | Handler Chainlit: đăng nhập, chat profile (lời chào + câu gợi ý), cài đặt LLM, chat (hiện từng bước khi backend stream), nút nguồn → panel bên phải |
| `src/co5151_web/cli.py` | Lệnh `co5151-web`: nạp `.env`, kiểm tra secret, chạy Chainlit với `frontend` làm thư mục gốc |
| `.chainlit/config.toml` | Cấu hình Chainlit: `language = "vi-VN"`, giao diện sáng, ảnh trang đăng nhập, tắt tải file |
| `.chainlit/translations/vi-VN.json` | Chữ của Chainlit bằng tiếng Việt (file dịch khác Chainlit tự sinh, không commit); test báo đỏ khi Chainlit thêm chữ mới chưa dịch |
| `public/` | `theme.json` (màu), logo sáng/tối, `favicon.svg` (cũng là avatar trợ lý), `login.svg` (nửa phải trang đăng nhập: tài khoản demo) |
| `chainlit.md` | Trang "Hướng dẫn": tài khoản demo và tình huống của từng tài khoản, cách dùng |

## Bảo mật

- Access token của backend nằm trong metadata của cookie đăng nhập Chainlit (ký bằng `CHAINLIT_AUTH_SECRET`) và
  trong bộ nhớ server; data layer không trả token về trình duyệt qua API user. Token chỉ mở được dữ liệu của chính
  người đăng nhập. Hạn token (`BACKEND_TOKEN_TTL`) nên bằng `user_session_timeout` trong `.chainlit/config.toml`
  (1 ngày); hết hạn thì giao diện báo đăng nhập lại.
- Token Student Record và key LLM chỉ nằm ở backend. Backend kiểm tra chủ hội thoại ở mọi API.
- Tin nhắn do backend lưu khi trả lời; data layer không ghi step. Tắt tải file lên.
- Hội thoại hết lượt (`questions_left = 0` từ backend, UC9): `on_message` không gửi câu mới lên backend, nhắc mở
  hội thoại mới (Chainlit không có API khóa ô nhập). Backend vẫn tự chặn nếu client bỏ qua.
