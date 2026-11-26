# Tài liệu của nhóm G3

Tài liệu dùng chung cho cả hệ thống. Tài liệu của riêng từng thành phần nằm trong README của thành phần đó
(ví dụ [frontend](../frontend/README.md), [eval](../eval/README.md)).

## `design/` — thiết kế

| File | Nội dung |
|---|---|
| [architecture.md](design/architecture.md) | Kiến trúc frontend/backend, các tầng của backend, quyết định chính, Verifier, việc còn mở |
| [eval-console.md](design/eval-console.md) | Console vận hành (trace, đánh giá, bộ câu hỏi, prompt): thiết kế và kế hoạch commit |
| [chat-ui.md](design/chat-ui.md) | Thiết kế lại giao diện chat Chainlit: tiếng Việt, câu gợi ý theo tài khoản, nguồn trích dẫn; kế hoạch commit |
| [agent-flow.md](design/agent-flow.md) | Luồng agent trên UI: span từng node, lưu, API, sidebar; kế hoạch commit |
| [deploy.md](design/deploy.md) | Triển khai lên Azure for Students bằng Terraform: lý do chọn, hạ tầng, bảo mật, chi phí; kế hoạch commit |
| [threat-model.md](design/threat-model.md) | Threat model v1 (D2, mục 6): tài sản, điểm vào, kẻ tấn công, biện pháp và trạng thái từng biện pháp |

## `eval/` — kết quả đánh giá

| File | Nội dung |
|---|---|
| [d2-notes.md](eval/d2-notes.md) | Ghi chú lần chạy đánh giá D2 (25/10/2026): cấu hình, số liệu máy chấm, chấm tay, phân tích thất bại |
| [d2-report.html](eval/d2-report.html) | Report HTML từng câu của lần chạy D2; tải về rồi mở bằng trình duyệt |

## Tiến độ

| File | Nội dung |
|---|---|
| [remaining-work.md](remaining-work.md) | Việc còn lại đến bảo vệ final, chia theo task |
| [ui-and-eval-console.md](ui-and-eval-console.md) | Ý tưởng và các bước: UI hiển thị agent, trang đánh giá/chỉnh prompt |

## Quy ước

- Tài liệu thiết kế đặt trong `design/`; kết quả của một lần chạy đánh giá đặt trong `eval/`, tên file bắt đầu bằng
  mốc nộp (`d2-`, `d3-`...).
- Kết quả thô của `co5151-eval run` (`eval/results/`) không commit; chỉ commit ghi chú và report đã chốt.
