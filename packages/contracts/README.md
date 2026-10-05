# co5151-contracts

Hợp đồng dùng chung giữa các MCP server và các agent. Mọi tool trong hệ thống trả về cùng một envelope:

```json
{"ok": true,  "data": { ... }}
{"ok": false, "error": {"code": "FORBIDDEN", "message": "...", "details": null}}
```

| Mã lỗi | Ý nghĩa | Agent nên làm gì |
|---|---|---|
| `INVALID_ARGUMENT` | Tham số sai kiểu / sai định dạng / có trường lạ | Sửa tham số rồi gọi lại |
| `UNAUTHENTICATED` | Thiếu, sai hoặc hết hạn token phiên | Yêu cầu người dùng đăng nhập lại; **không** thử lại |
| `FORBIDDEN` | Token hợp lệ nhưng không có quyền với tài nguyên | Báo không có quyền; **không** thử lại với ID khác |
| `NOT_FOUND` | Tài nguyên không tồn tại | Báo không có dữ liệu |
| `INTERNAL` | Lỗi phía server | Có thể thử lại một lần |

```python
from co5151_contracts import ErrorCode, ToolError, ok, err

ok({"x": 1}).model_dump()
err(ErrorCode.FORBIDDEN, "Không có quyền").model_dump()
```

## Registry tool & JSON Schema

`co5151_contracts.tools` là nguồn sự thật duy nhất cho mỗi tool: tên, mô tả (dùng làm prompt cho LLM), model input/output,
mức quyền (`read-only` / `write-reversible` / `write-irreversible` / `execute`) và role được phép gọi.
MCP server đăng ký tool từ registry này; agent dùng `input_schema()` để dựng function-calling schema.

```bash
uv run python -m co5151_contracts.export          # sinh lại schemas/*.json sau khi sửa model
uv run python -m co5151_contracts.export --check  # CI: báo lỗi nếu schemas/ đã cũ
```

`schemas/` dành cho thành phần không viết bằng Python (ví dụ `apps/web`). **Không sửa tay** các file trong đó.
