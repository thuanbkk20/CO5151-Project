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

## Trạng thái

- Đã có: bộ khung gộp verdict.
- Chưa có: các check cụ thể, vòng lặp Advisor ↔ Verifier. Verifier không có check nào thì mọi bản nháp đều `pass`.
