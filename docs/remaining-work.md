# Việc còn lại đến bảo vệ final (G3)

Cập nhật 2026-11-28. Code (harness đánh giá, RAG graph, cải thiện Advisor/Verifier, threat model
v2) đã xong; lịch sử nằm trong git.

**Mốc** (mail thầy 24/11):

- **06/12 (CN) 23:59**: nộp báo cáo PDF 6–8 trang, slide PDF, bảng phản hồi góp ý D2, bảng đóng góp + AI-use, link repo
  (tag `final` + commit hash), dữ liệu, kết quả/logs, video demo dự phòng. Mỗi thành viên tự gửi đánh giá nội bộ.
- **09/12 (T4) 19:00–19:30, B4-305**: 20 phút trình bày + demo, 10 phút hỏi đáp.
- Điểm: 60% báo cáo + 20% code/tái lập + 20% trình bày, demo, bảo vệ.

| Việc | Ghi chú |
|---|---|
| Duyệt khoản quy chế mong đợi của 20 hội thoại | Soạn file duyệt (nguyên văn khoản + trang PDF), đối chiếu PDF, đánh dấu đúng/sai. Chưa duyệt thì không chấm trích dẫn |
| Chạy eval cuối: hệ thống đầy đủ, 3 baseline, 3 ô ablation, bộ injection; 3 seed | Tốn tiền key. Lệnh trong [eval/README.md](../eval/README.md); ước tính khoảng $1.5 mỗi cấu hình với `gpt-4.1-mini` (đoán) |
| Chấm tay một mẫu lượt, tính độ khớp với máy chấm | |
| Không lưu kết quả Student Record trong `trace_spans`; báo cáo ghi rõ lịch sử chat vẫn lưu câu trả lời | Lệch cam kết D1 (threat model A6) |
| Báo cáo (có Ethics, Limitations, reproducibility), slide, video demo, bảng phản hồi D2, bảng đóng góp + AI-use, tag `final` | Bảng phản hồi cần góp ý của thầy buổi 28/10; đọc rubric 11 tiêu chí (PDF mail 24/11) |

**Ghi chú cho báo cáo:**

- Số truy xuất của RAG graph lạc quan: khái niệm được viết khi đã thấy câu hỏi test
  ([mcp/regulation-graph](../mcp/regulation-graph/README.md)).
- Chạy không LLM thì ca injection gián tiếp PI05, PI14 trượt: câu trả lời mẫu (dự phòng khi LLM lỗi) trích nguyên văn
  quy chế ([threat-model.md](design/threat-model.md) mục 6).
- Số liệu báo cáo dùng bộ hội thoại; `tasks.json` (24 câu đơn của D2) chỉ còn cho console và test.
