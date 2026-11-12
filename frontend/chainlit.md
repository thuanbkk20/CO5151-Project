# Cố vấn học vụ G3

Trợ lý tư vấn quy chế đào tạo và hồ sơ học vụ cá nhân (dữ liệu sinh viên là **mô phỏng**, quy chế là bản nháp).

## Tài khoản demo

| Tài khoản | Mật khẩu | Ghi chú |
|---|---|---|
| `sv001` … `sv008` | `demo` | 8 sinh viên mô phỏng, mỗi người một tình huống (xem `mcp/student-server/docs/MOCK_DATA.md`) |
| `khach` | để trống hoặc bất kỳ | không có hồ sơ, chỉ hỏi được quy chế chung |

## Cách dùng

- Chọn nhà cung cấp LLM và model ở nút cài đặt cạnh ô nhập. Danh sách chỉ hiện nhà cung cấp đã có key trong `.env`.
- Mỗi câu trả lời có mục **Chi tiết xử lý**: tool đã gọi, trích dẫn, số token, thời gian, model.
- Advisor chỉ đọc được hồ sơ của tài khoản đang đăng nhập.
