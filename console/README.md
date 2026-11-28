# Console vận hành (`co5151-console`)

Web app cho nhóm (không phải cho sinh viên): xem trace, chạy đánh giá, sửa bộ câu hỏi và prompt. FastAPI + Jinja2,
HTML render phía server. Đánh giá chạy end-to-end qua API backend như người dùng thật (đăng nhập bằng tài khoản demo
của câu hỏi, hỏi, nhận câu trả lời + trace) rồi chấm bằng `co5151_eval.scoring`.

## Chạy

```bash
# .env: BACKEND_ADMIN_TOKEN giống bên backend (để đọc trace), CONSOLE_PASSWORD (mật khẩu đăng nhập),
#       BACKEND_URL nếu backend không ở :8100
uv run co5151-console          # http://127.0.0.1:8200
```

Trang: Sessions (các lượt của một hội thoại), Traces (bấm một trace → panel bên phải, `static/panel.js`), Đánh giá, Bộ câu
hỏi. Cần backend bật API admin.

Đăng nhập bằng tài khoản vận hành `CONSOLE_USERNAME` (mặc định `admin`) / `CONSOLE_PASSWORD` trong `.env`; mật
khẩu trống thì chưa ai đăng nhập được. Phiên giữ 12 giờ, khởi động lại console thì đăng nhập lại. Chạy HTTP thường
nên chỉ nghe ở `127.0.0.1`. Chạy đánh giá tốn lời gọi LLM thật (trang xác nhận ghi số tối đa);
trace của từng câu xem ở trang Traces.

## Cấu trúc

| File | Vai trò |
|---|---|
| `src/co5151_console/config.py` | `Settings` đọc từ biến môi trường |
| `src/co5151_console/ports.py`, `models.py` | Port (Protocol) và dữ liệu mà service dùng |
| `src/co5151_console/services/` | Use case: `sessions`, `traces`, `question_sets`, `evaluation` (không import FastAPI, httpx, sqlite3) |
| `src/co5151_console/adapters/` | `backend_http` (API admin), `backend_agent` (hỏi như người dùng), `sqlite_store` |
| `src/co5151_console/container.py` | Chỗ duy nhất chọn adapter cho từng port |
| `src/co5151_console/web/auth.py` | Đăng nhập: cookie phiên ký HMAC, middleware chặn trang khi chưa đăng nhập |
| `src/co5151_console/web/` | Mỗi trang một router (`sessions`, `traces`, `question_sets`, `evaluation`), `templates/` (Jinja2), `static/style.css` |
| `src/co5151_console/cli.py` | Lệnh `co5151-console`: nạp `.env`, chạy uvicorn |
