# Console vận hành (`co5151-console`)

Web app cho nhóm (không phải cho sinh viên): xem trace, chạy đánh giá, sửa bộ câu hỏi và prompt. FastAPI + Jinja2,
HTML render phía server. Thiết kế và tiến độ: [docs/design/eval-console.md](../docs/design/eval-console.md).

## Chạy

```bash
# .env: BACKEND_ADMIN_TOKEN giống bên backend (để đọc trace), BACKEND_URL nếu backend không ở :8100
uv run co5151-console          # http://127.0.0.1:8200
```

Chưa có đăng nhập: console chỉ nghe ở `127.0.0.1`.

## Cấu trúc

| File | Vai trò |
|---|---|
| `src/co5151_console/config.py` | `Settings` đọc từ biến môi trường |
| `src/co5151_console/container.py` | Chỗ duy nhất chọn adapter cho từng port |
| `src/co5151_console/web/` | Route FastAPI, `templates/` (Jinja2), `static/style.css` |
| `src/co5151_console/cli.py` | Lệnh `co5151-console`: nạp `.env`, chạy uvicorn |
