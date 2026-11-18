# Cố vấn học vụ G3

Trợ lý trả lời câu hỏi về **quy chế đào tạo** và **hồ sơ học vụ của chính người hỏi**, dựa trên điều khoản tra
được. Câu trả lời do LLM soạn được một agent thứ hai (Verifier) kiểm tra lại trước khi gửi.

> Quy chế trong hệ thống là **bản nháp chưa phê duyệt**; dữ liệu sinh viên là **mô phỏng**.

## Tài khoản demo

Mật khẩu của mọi tài khoản sinh viên: `demo`.

| Tài khoản | Tình huống |
|---|---|
| `sv001` | K2023, đủ điều kiện làm luận văn, không bị cảnh báo |
| `sv002` | K2023, thiếu tín chỉ, rớt Đồ án tổng hợp, chưa có chứng chỉ ngoại ngữ |
| `sv003` | K2023, bị cảnh báo học tập HK 20252 (lần 1) |
| `sv004` | K2022 (quy chế 2019), tạm dừng 20231–20232, đủ điều kiện luận văn theo QC2019 |
| `sv005` | K2022, thiếu 4 tín chỉ và GDTC 3 để tốt nghiệp |
| `sv006` | K2024 năm 2, học bình thường |
| `sv007` | K2023, GPA ≥ 3.2 nên được đăng ký 28 tín chỉ |
| `sv008` | K2025, bị cảnh báo HK đầu 20251, HK 20252 đã cải thiện |
| `khach` | Mật khẩu bất kỳ; không có hồ sơ, chỉ hỏi quy chế chung |

## Cách dùng

- Hội thoại mới có sẵn câu gợi ý theo tài khoản; câu **Thử bảo mật** cho thấy trợ lý từ chối yêu cầu vượt quy chế.
- Trợ lý chỉ đọc được hồ sơ của tài khoản đang đăng nhập; hỏi hồ sơ người khác sẽ bị từ chối.
- Mục **Đã xử lý câu hỏi** dưới câu hỏi: các bước trợ lý đã làm; mở ra để xem chi tiết kỹ thuật (tool, trích
  dẫn, Verifier, token, thời gian, trace id).
- Nút cài đặt cạnh ô nhập: chọn nhà cung cấp LLM và model (chỉ hiện nhà cung cấp backend có key).
- 👍/👎 dưới câu trả lời để góp ý; các hội thoại cũ nằm ở thanh bên trái.
