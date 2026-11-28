# Tài liệu của nhóm G3

Tài liệu dùng chung cho cả hệ thống. Tài liệu của riêng từng thành phần nằm trong README của thành phần đó
([frontend](../frontend/README.md), [backend](../backend/README.md), [console](../console/README.md),
[eval](../eval/README.md), [regulation-graph](../mcp/regulation-graph/README.md), [infra](../infra/azure/README.md)).

| File | Nội dung |
|---|---|
| [design/architecture.md](design/architecture.md) | Kiến trúc, các tầng của backend, quyết định chính, Verifier và chi phí LLM, model, việc còn mở |
| [design/use-cases.md](design/use-cases.md) | Use case, vai người dùng, câu trả lời cố định |
| [design/test-conversations.md](design/test-conversations.md) | Bộ 20 hội thoại test (dữ liệu chạy: `eval/.../data/conversations.json`) |
| [design/threat-model.md](design/threat-model.md) | Threat model v2: tài sản, điểm vào, kẻ tấn công, biện pháp và trạng thái |
| [eval/d2-notes.md](eval/d2-notes.md), [eval/d2-report.html](eval/d2-report.html) | Lần chạy đánh giá D2 (25/10/2026): cấu hình, số liệu, chấm tay, phân tích thất bại |
| [remaining-work.md](remaining-work.md) | Việc còn lại đến bảo vệ final |

Quy ước: không viết file plan; kết quả một lần chạy đánh giá đặt trong `eval/`, tên bắt đầu bằng mốc nộp (`d2-`,
`final-`); kết quả thô (`eval/results/`) không commit.
