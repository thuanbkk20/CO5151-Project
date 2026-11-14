# Backend API (`co5151-api`)

FastAPI, clean architecture. Kiến trúc, các tầng và quyết định: [docs/design/architecture.md](../docs/design/architecture.md).

```bash
uv run student-mcp serve     # :8102
uv run regulation-mcp        # :8103
uv run co5151-api            # :8100, tài liệu API: http://127.0.0.1:8100/docs
```

| API | Việc |
|---|---|
| `POST /auth/login` | Đăng nhập tài khoản demo, trả access token (Bearer) |
| `GET /me`, `GET /llm/providers` | Người đang đăng nhập; provider LLM đã có key |
| `GET/POST /conversations` | Danh sách (cursor, `q`), tạo (id do client chọn, idempotent) |
| `GET/PATCH/DELETE /conversations/{id}` | Hội thoại kèm tin nhắn; đổi tiêu đề / cài đặt LLM; xóa |
| `POST /conversations/{id}/messages` | Hỏi, chờ câu trả lời đã qua Verifier |
| `POST /conversations/{id}/messages/stream` | Như trên qua SSE: `step`* rồi `answer` hoặc `error` |
| `PUT/DELETE /messages/{id}/feedback` | Đánh giá câu trả lời |
| `GET /traces/{id}` | Trace của một câu trả lời (tool, trích dẫn, Verifier, token, thời gian) |

Cấu hình: các nhóm "Backend API" và "LLM" trong [.env.example](../.env.example). Test không gọi LLM thật và không
đọc `.env`; test MCP gateway dựng server thật trên cổng trống.
