# Tài liệu của nhóm G3

Tài liệu dùng chung cho cả hệ thống. Tài liệu của riêng từng thành phần nằm trong README của thành phần đó
(ví dụ [frontend](../frontend/README.md), [eval](../eval/README.md)).

## `design/` — thiết kế

| File | Nội dung |
|---|---|
| [architecture.md](design/architecture.md) | Kiến trúc frontend/backend, các tầng của backend, quyết định chính, Verifier, việc còn mở |
| [threat-model.md](design/threat-model.md) | Threat model v1 (D2, mục 6): tài sản, điểm vào, kẻ tấn công, biện pháp và trạng thái từng biện pháp |

## `eval/` — kết quả đánh giá

| File | Nội dung |
|---|---|
| [d2-notes.md](eval/d2-notes.md) | Ghi chú lần chạy đánh giá D2 (25/10/2026): cấu hình, số liệu máy chấm, chấm tay, phân tích thất bại |
| [d2-report.html](eval/d2-report.html) | Report HTML từng câu của lần chạy D2; tải về rồi mở bằng trình duyệt |

## Quy ước

- Tài liệu thiết kế đặt trong `design/`; kết quả của một lần chạy đánh giá đặt trong `eval/`, tên file bắt đầu bằng
  mốc nộp (`d2-`, `d3-`...).
- Kết quả thô của `co5151-eval run` (`eval/results/`) không commit; chỉ commit ghi chú và report đã chốt.
