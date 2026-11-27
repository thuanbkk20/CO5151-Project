# Cải thiện Advisor và Verifier (task C1–C6, D1–D3)

Cập nhật: 2026-11-27. Nhánh `feat/agent-improvements` (tách từ `feat/regulation-graph`, nên chứa cả
`feat/foundry-models`). Task C1–C6, D1–D3 trong [remaining-work.md](../remaining-work.md). Không chạy eval hay
ablation (Kiên chạy sau).

## Mục tiêu

Lỗi đã rà ngày 27/11 (bảng "Hiện trạng" trong remaining-work): router không thấy lịch sử, evidence thiếu khóa và
quyết định học vụ, câu hỏi lại cố định, từ chối khi truy xuất rỗng dù có hồ sơ, câu trả lời không LLM tự đặt ngưỡng
105 TC, judge chấm câu nối tiếp mà không có ngữ cảnh, viết lại không tra thêm quy chế, chưa giới hạn số câu.

Ràng buộc chi phí (CLAUDE.local.md): mỗi thay đổi **không thêm lời gọi LLM** trừ chỗ ghi rõ dưới đây.

## Thiết kế

**C2 · Evidence.** Thêm `cohort`, `retake_credits` (từ `get_my_academic_summary`) và `decisions` (học kỳ, loại, nội
dung, số quyết định; từ `get_my_academic_decisions`), `warning_semesters` suy ra từ quyết định `is_warning`. Prompt
ghi "Khóa tuyển sinh: 2024 · CTĐT: 2023" thay cho "Quy chế áp dụng". `student_facts()` gửi Verifier đủ các trường này.

**C4.** `template_answer` chỉ liệt kê số liệu hồ sơ và đoạn quy chế, không kết luận "Đủ/Chưa đủ điều kiện".

**C5 · Câu cố định.** R1, R2 đúng nguyên văn [use-cases.md](use-cases.md). Các câu cố định khác xưng "mình", gọi
"bạn". `NO_REGULATION` (không tra được quy chế, không có hồ sơ) = R2 vì UC7 quy định câu R2. System prompt của writer
thêm quy ước xưng hô.

**C6 · Giới hạn câu (UC9).** `AskQuestion` đếm câu người dùng trong hội thoại (đã đọc sẵn khi kiểm quyền, không thêm
truy vấn). Câu thứ `MAX_QUESTIONS_PER_CONVERSATION + 1` trở đi (mặc định 10): lưu câu hỏi, trả R1, kết cục `limit`, ghi
trace, **không gọi planner/LLM**. Câu 8–10: thêm một dòng "còn N câu" vào cuối câu trả lời (sau Verifier, không qua
LLM). `AnswerOut` và `ConversationDetailOut` có `questions_left`; frontend hết lượt thì không gửi câu mới lên backend và
gợi ý mở hội thoại mới (Chainlit không có API khóa ô nhập; chặn ở `on_message`).

**C1 · Router thấy ngữ cảnh.**

- Router nhận tối đa 4 tin gần nhất (câu trả lời cắt 300 ký tự) trong thẻ `<history>`, khai báo là dữ liệu.
- Schema trả thêm `standalone_question`, `regulation_query`, `clarify_question` trong **cùng** lời gọi;
  `ROUTER_MAX_OUTPUT_TOKENS` 32 → 192.
- Luật vẫn chạy trước. Khi luật quyết hết mà lượt này cần quy chế hoặc cần Verifier, có lịch sử **và** câu hỏi trông
  như câu nối tiếp (luật: ít từ, có "đó", "vậy", "thì sao", "còn"...), Advisor gọi `rewrite` một lần (cùng router,
  cùng schema, không có `action`).
  - Đây là **lời gọi LLM thêm duy nhất**, chỉ ở câu nối tiếp.
  - Câu đầu hội thoại và câu đủ ý không tốn thêm.
- Bước sau của planner chạy luật trên `standalone_question`.
- Tra quy chế bằng `regulation_query` (không có thì `standalone_question`, rồi câu gốc), kèm
  `context.cohort` từ hồ sơ nếu đã đọc. Khóa trong lời người dùng chỉ vào chữ truy vấn, không vào `context`.
- Provider không trả JSON đúng → dùng câu gốc, như hiện nay.

**C3 · Hỏi lại và truy xuất rỗng.** Router chọn `CLARIFY` thì trả `clarify_question` của chính lời gọi đó (đã kiểm: có
dấu "?", ≤ 300 ký tự, bỏ canary); thiếu thì dùng câu `CLARIFY` cố định. Lệch remaining-work ("writer viết câu hỏi
lại"): làm trong router để khỏi tốn thêm một lời gọi. Truy xuất rỗng nhưng đã có hồ sơ → không từ chối; writer được dặn
chỉ trả lời phần dựa trên hồ sơ và nói rõ chưa tra được quy chế.

**D1.** `VerificationRequest.question` = `standalone_question` (không có thì câu gốc). Judge vẫn không thấy lịch sử.

**D2 · Tra thêm khi thiếu căn cứ.** Verdict `REVISE` có `MISSING_EVIDENCE` / `UNGROUNDED_CLAIM` → trước khi viết lại,
tra thêm một lần bằng `standalone_question` với `top_k` gấp đôi, chỉ thêm khoản chưa có (tối đa 6 khoản). Giữ
`MAX_VERIFIER_ROUNDS = 2`. Lệch remaining-work ("truy vấn mới từ router"): không gọi LLM để viết truy vấn mới; tra
thêm là lời gọi MCP, không tốn token. Prompt viết lại nhận cả khoản mới.

**D3 · Luật kiểm số liệu hồ sơ.** Trước judge: số tín chỉ tích lũy ("đã tích lũy X", "X/Y tín chỉ" với Y = tổng
chương trình), số tín chỉ còn thiếu, ĐTBTL thang 4 trong bản nháp phải khớp `student_facts`. Lệch → `FACT_MISMATCH`
(viết lại, không gọi judge ở vòng đó). Chỉ bắt mẫu gắn với sinh viên, không bắt số trong quy chế ("cần tích lũy 120").

## Kế hoạch commit

| # | Commit | Nội dung | Trạng thái |
|---|---|---|---|
| 1 | `docs(design): agent improvements plan` | file này | xong `0c4a80e` |
| 2 | `feat(backend): cohort, retakes and decisions in the evidence` | C2 | xong `fc4a1fe` |
| 3 | `fix(backend): the template answer draws no conclusion` | C4 | xong `4671cfc` |
| 4 | `fix(backend): fixed replies R1, R2 and one form of address` | C5 | xong `317f03c` |
| 5 | `feat(backend): ten questions per conversation` | C6 backend: biến, kết cục `limit`, `questions_left` trong API, eval/console biết `limit` | xong `33b96c4` |
| 6 | `feat(web): stop asking when the conversation is full` | C6 frontend | xong `417046d` |
| 7 | `feat(backend): the router reads the conversation and rewrites the question` | C1 | xong `56e9a64` |
| 8 | `feat(backend): the Verifier judges the standalone question` | D1 | xong `b182fef` |
| 9 | `feat(backend): answers without regulations` | C3 phần truy xuất rỗng (câu hỏi lại cụ thể đã nằm trong 7 vì cùng lời gọi router) | xong `381c913` |
| 10 | `feat(backend): search again before a rewrite` | D2 | xong `f67ede4` |
| 11 | `feat(backend): rule check of the record numbers` | D3 | xong `3307e52` |
| 12 | `docs: agent improvements in architecture and README` | chi phí LLM mỗi câu, luồng mới | xong |

## Chưa quyết

1. R2 trong use-cases.md xưng "Tôi", các câu khác "mình". Giữ nguyên văn R2 như Kiên đã duyệt; Kiên muốn đổi thì sửa
   một chỗ trong `prompts.py`.
2. D2, C3 lệch cách viết trong remaining-work để không tốn thêm lời gọi (xem trên). Nếu báo cáo cần đúng cam kết D1
   "tìm lại tối đa 2 lần" bằng truy vấn mới từ LLM thì đổi sau.
3. Luật nhận câu nối tiếp (C1) có thể sót; sót thì câu đó dùng câu gốc như trước, không sai thêm.
