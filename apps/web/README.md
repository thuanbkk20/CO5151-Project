# Giao diện chat (`co5151-web`)

Giao diện Chainlit để cả nhóm thử Advisor trên máy mình: đăng nhập tài khoản demo, chọn LLM, chat nhiều lượt.

## Chạy

```bash
uv sync                    # ở gốc repo
cp .env.example .env       # điền key LLM và CHAINLIT_AUTH_SECRET (uv run chainlit create-secret)
uv run co5151-web          # http://localhost:8000
```

Tài khoản: `sv001` … `sv008` mật khẩu `demo` (sinh viên mô phỏng), `khach` (không có hồ sơ).

## Cấu trúc

| File | Vai trò |
|---|---|
| `src/co5151_web/backend.py` | Logic không phụ thuộc Chainlit, có test: đăng nhập, provider đã có key, tạo Advisor, chạy một lượt chat |
| `src/co5151_web/app.py` | Phần Chainlit: đăng nhập, cài đặt LLM, lịch sử hội thoại, hiển thị chi tiết |
| `src/co5151_web/cli.py` | Lệnh `co5151-web`: nạp `.env`, kiểm tra secret, chạy Chainlit với `apps/web` làm thư mục gốc |
| `chainlit.md` | Trang chào (nút Readme) |
| `.chainlit/config.toml` | Cấu hình giao diện Chainlit (tên ứng dụng, ...) |

## Bảo mật

- Session token của Student Record chỉ nằm ở server (theo phiên đăng nhập), không gửi xuống trình duyệt và không vào
  prompt của LLM; Advisor chỉ đọc được hồ sơ của tài khoản đang đăng nhập.
- Key LLM chỉ nằm trong `.env` ở server; giao diện chỉ hiện tên nhà cung cấp.
- Token phiên giữ trong bộ nhớ: khởi động lại server thì cần đăng nhập lại.
