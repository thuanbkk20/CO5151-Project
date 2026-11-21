# Việc còn lại đến bảo vệ final (G3)

Cập nhật: 2026-11-14. Nguồn: kế hoạch slide D2 (slide 19), `docs/eval/d2-notes.md`, mail thầy 31/10 và 4/11.

## Mốc

- 18/11 (W47): buổi tổng kết, có điểm danh.
- W50: thuyết trình final (G3 ở buổi 1, giờ học thường lệ).
- 11/12: nộp bản cuối (cần xác nhận).

## Task

### 1. Xác minh đáp án và trích dẫn (Đức)
- [ ] Đối chiếu trích dẫn của 24 task với văn bản quy chế
- [ ] Sửa đáp án O01
- [ ] Viết `reference_answer` cho B01, B04, B05, B06

### 2. Truy xuất quy chế
- [ ] Lọc theo khóa / CTĐT
- [ ] Loại phụ lục không liên quan
- [ ] Nhận các cách hỏi khác (vd. "ra trường")

### 3. Advisor
- [ ] Đưa học kỳ cảnh báo vào Evidence (Phương, Kiên)
- [ ] Không tra được quy chế thì hỏi lại hoặc trả lời phần dựa trên hồ sơ, thay vì từ chối
- [ ] Truyền seed
- [x] Bộ nhớ theo người dùng (Phương)

### 4. Verifier (Kiên, Đức)
- [x] Verifier v1
- [ ] Đo trên bộ 24 task

### 5. Bộ đánh giá
- [ ] Sửa mẫu cấm và bộ phân loại kết cục, test hai chiều
- [ ] Lệnh chấm lại từ `results.jsonl`, không gọi lại LLM
- [ ] Mở rộng lên 40 task (Thuấn, Kiên)
- [ ] Đo tỉ lệ khớp giữa bộ chấm và nhãn người
- [ ] Chạy prompt injection end-to-end

### 6. Baseline và ablation
- [ ] Baseline LLM: Zero-shot, Naive RAG, Single Agent không Verifier (Thuấn, Kiên)
- [ ] Ablation (cả nhóm)
- [ ] Chạy đánh giá cuối: 3 seed, chi phí, độ trễ

### 7. Nộp và thuyết trình
- [ ] Cập nhật threat model theo kiến trúc mới
- [ ] Demo đầu cuối và video
- [ ] Báo cáo cuối
- [ ] Chốt commit, gắn tag final
- [ ] Bản kê đóng góp
- [ ] Slide thuyết trình W50
