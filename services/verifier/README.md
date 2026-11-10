# CO5151 · G3 — Compliance Verifier (`co5151-verifier`)

Thành phần **Mảng 4**: nhận bản nháp câu trả lời của Advisor cùng bằng chứng đã dùng để viết, trả về một `Verdict`.

| `status` | Ý nghĩa | Advisor làm gì |
|---|---|---|
| `pass` | Bản nháp khớp bằng chứng | Gửi cho người dùng |
| `revise` | Có lỗi sửa được (trích dẫn sai, số liệu lệch...) | Viết lại theo `issues` |
| `refuse` | Bằng chứng không đủ để kết luận | Từ chối (Strict Refusal) |

Dữ liệu vào/ra là `VerificationRequest` và `Verdict` trong `packages/contracts`
(`co5151_contracts.verification`). Verifier không import code của Advisor và ngược lại.

```python
from co5151_contracts import VerificationRequest
from co5151_verifier import ComplianceVerifier

verdict = ComplianceVerifier(checks=[...]).verify(VerificationRequest(question="...", draft="..."))
```

Mỗi check là một hàm `(VerificationRequest) -> list[VerificationIssue]`. `ComplianceVerifier` chạy lần lượt các
check rồi gộp kết quả: không có issue thì `pass`; có issue thuộc `REFUSE_CODES` thì `refuse`; còn lại `revise`.

## Check theo luật (`rules.py`, không gọi LLM)

Chạy trước mọi thứ khác vì không tốn token. Chỉ bắt những gì quyết định được từ chữ:

| Check | Bắt gì | Kết quả |
|---|---|---|
| `cited_provisions_are_retrieved` | Mã điều khoản (`QD2933-2021-CL5.5`) hoặc số "Điều/Khoản" trong bản nháp không có trong các đoạn quy chế đã tra | `UNSUPPORTED_CITATION` → `revise`; nếu không tra được đoạn nào thì `MISSING_EVIDENCE` → `refuse` |
| `no_secrets(secrets)` | Token phiên, header `Bearer ...`, hoặc chuỗi bí mật (canary) trong bản nháp | `LEAK` → `revise` |

Giới hạn đã biết: số "Điều/Khoản" chỉ so với các con số xuất hiện trong bằng chứng nên bắt được trích dẫn bịa rõ ràng
("Điều 99") chứ không chứng minh điều khoản đó nói đúng nội dung. Số điều khoản do chính người dùng nêu trong câu hỏi
không bị xét ở đây. Kết luận có suy ra được từ bằng chứng hay không là việc của bước kiểm bằng LLM.

## Trạng thái

- Đã có: bộ khung gộp verdict, check theo luật.
- Chưa có: kiểm bằng LLM, vòng lặp Advisor ↔ Verifier.
