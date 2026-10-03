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
