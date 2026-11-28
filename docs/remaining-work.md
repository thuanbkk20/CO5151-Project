# Việc còn lại đến bảo vệ final (G3)

Cập nhật: 2026-11-27. Người làm: **Kiên làm toàn bộ** (giao từng task cho code agent). Nguồn: proposal D1, báo cáo D2,
mail thầy 24/11, trang đồ án (R1–R9), rà code ngày 27/11 trên `feat/foundry-models` (`bf41bae`).

## Mốc (mail thầy 24/11, thay mọi lịch trước)

- **06/12 (CN) 23:59**: nộp báo cáo PDF 6–8 trang, slide PDF, bảng phản hồi góp ý D2, bảng đóng góp + AI-use, link repo
  (tag `final` + commit hash), dữ liệu, kết quả/logs, video demo dự phòng. Mỗi thành viên tự gửi đánh giá nội bộ.
- **09/12 (T4) 19:00–19:30, B4-305**: G3 báo cáo, 20 phút trình bày + demo, 10 phút hỏi đáp.
- Điểm final: 60% báo cáo + 20% code/tái lập + 20% trình bày, demo, bảo vệ.

## Quy tắc chung cho code agent (dán kèm mỗi task)

- Đọc `CLAUDE.md` và `CLAUDE.local.md` trước. Mỗi task: nhánh `feat/...` hoặc `fix/...` riêng, plan ngắn trong
  `docs/design/<tên>.md` (bảng commit) trước khi code, xong bước nào chạy lint + test rồi commit ngay. Không push.
- Test **không bao giờ** gọi LLM thật. Lệnh tốn LLM (chạy thử, eval) chỉ chạy khi Kiên bảo; báo trước/sau số lời gọi,
  token, ước tính USD.
- `feat/foundry-models` đang có session khác sửa prompt và Verifier. Task đụng `advisor/prompts.py`,
  `verifier/judge.py`, `usecases/ask.py` chỉ bắt đầu sau khi nhánh đó merge.
- `mcp/regulation-server` là code của Đức: ghi trong plan sẽ sửa gì, vì sao; giữ nguyên hai tool và định dạng dữ liệu cũ,
  chỉ thêm trường.
- Kịch bản và bộ test đã duyệt: [design/use-cases.md](design/use-cases.md),
  [design/test-conversations.md](design/test-conversations.md). Không dùng tài khoản khách.

Ký hiệu: **[LLM]** tốn tiền key; **[Kiên]** cần người quyết hoặc đối chiếu tay.

## Hiện trạng đã rà (27/11)

| Chỗ | Vấn đề | Bằng chứng |
|---|---|---|
| Truy xuất | Gửi nguyên câu hỏi; 6/18 câu cần quy chế trả rỗng; `STOP` bỏ `bao` nên "cảnh báo" không khớp chủ đề; không dùng khóa | `advisor/advisor.py:103`, `regulation_server/retrieve_regulations.py:16`, `handoff_retriever.py:228` |
| Router | Chỉ thấy câu hỏi hiện tại, không thấy lịch sử → câu nối tiếp ("Quá thời gian đó…", "Em khóa 2022 thì sao?") định tuyến và tra quy chế sai | `advisor/planner.py:128`, `advisor.py:76` |
| Evidence | Thiếu khóa tuyển sinh, tín chỉ học lại, học kỳ bị cảnh báo, danh sách quyết định (giao đề tài, tạm dừng học). Dòng "Quy chế áp dụng: 2023" mơ hồ (sv006 khóa 2024 vẫn in 2023) | `domain/evidence.py:61-75`, `advisor/prompts.py:55` |
| Câu trả lời không LLM | Tự đặt ngưỡng 105 TC để kết luận đủ điều kiện | `advisor/prompts.py:113` |
| Hỏi lại | Câu `CLARIFY` cố định, không hỏi đúng thứ thiếu ("đơn gì", "môn nào") | `advisor/prompts.py` hằng `CLARIFY` |
| Verifier | Judge thấy câu hỏi gốc, không thấy ngữ cảnh → câu nối tiếp bị chấm sai; viết lại không tra lại quy chế (D1 hứa "tìm lại tối đa 2 lần") | `verifier/judge.py` `build_prompt`, `usecases/ask.py:190` |
| Seed | Lớp LLM không có tham số seed | `infrastructure/llm.py` |
| Eval | Chỉ chạy câu đơn; ghi tổng token, không tách vào/ra, không USD; chưa có lệnh chấm lại; chưa có baseline zero-shot / RAG một bước | `eval/.../runner.py:39`, `baselines.py` |
| Prompt injection | 12 ca, chỉ PI05 là gián tiếp và cần đoạn quy chế độc chưa có fixture; PI05, PI10 dùng khách | `eval/.../data/prompt_injection.json` |
| Giới hạn lượt | Chưa có (UC9) | — |

## Task

### A. Dữ liệu đánh giá (không tốn LLM)

**A1 · Bộ hội thoại thành dữ liệu.** Chuyển `docs/design/test-conversations.md` thành
`eval/src/co5151_eval/data/conversations.json`. Model mới `Conversation {id, user, prefill_turns, turns: [Turn]}`,
`Turn` giữ các trường của `Task` (expected, also_accept, facts, forbidden, citations, citations_verified). Thêm kết cục
`limit`. Bỏ `tasks.json` khỏi mặc định (Kiên: không giữ bộ cũ). `check-gold` chạy trên facts của mọi lượt.
Xong khi: load + `check-gold` đạt; test validate (id duy nhất, facts cần user…).

**A2 · Đáp án khoản quy chế. [Kiên]** Agent sinh file duyệt `docs/eval/gold-review.md`: mỗi lượt có cột "Quy chế",
in nguyên văn các khoản ứng viên từ `provisions.json` kèm file + trang PDF. Kiên đối chiếu PDF, đánh dấu đúng/sai, điền
con số quy chế còn trống. Agent chép kết quả vào `citations` + `citations_verified`.

**A3 · Harness nhiều lượt.** Runner chạy từng hội thoại qua backend trong process (`backend_agent.py`), các lượt cùng
một conversation để lịch sử thật đi qua use case. `prefill_turns` ghi thẳng vào kho hội thoại, không gọi LLM (H18).
Chấm theo lượt và theo hội thoại; report: pass theo hội thoại, theo lượt, theo use case.
Xong khi: test với agent giả chạy đủ 20 hội thoại; H18 không phát sinh lời gọi LLM.

**A4 · Sửa bộ chấm.** Mẫu cấm bắt nhầm câu phủ định đứng xa và phần nhắc lại câu hỏi (D2 mục 5.5 (4)); bộ phân loại
thiếu cụm hỏi lại ("vui lòng cung cấp thêm…"). Ưu tiên nhãn kết cục agent tự khai; `limit` so khớp đúng câu R1.
Xong khi: mỗi mẫu có test hai chiều (bắt đúng / không bắt nhầm).

**A5 · Chấm lại không gọi LLM.** `co5151-eval rescore <results.jsonl>`: chấm lại bằng bộ chấm hiện tại, ghi report mới.

**A6 · Ghi chi phí.** Mỗi lời gọi LLM ghi token vào/ra theo vai (router, writer, judge) và model. Bảng giá theo model
(file JSON, nguồn ghi trong `foundry-models.md`). Report có USD theo lượt, theo hội thoại, cả lần chạy. Trang đồ án:
"No evaluation run without cost logging".

**A7 · Seed.** `ChatModel.complete(..., seed=)`; chỉ gửi khi profile model bật (provider OpenAI-compatible có thể trả 400
cho tham số lạ, xem `CLAUDE.md` mục LLM provider). Runner truyền seed; trace ghi seed. Test bằng fake.

### B. Truy xuất quy chế (thầy nhấn mạnh)

**B1 · Lệnh đo truy xuất.** `co5151-eval retrieval`: chạy truy xuất trong process trên các lượt có `citations`; in
recall@3, recall@8, MRR, tỉ lệ rỗng; ghi JSON để so cấu hình. Không LLM. Cần A2 (tạm dùng ứng viên nếu A2 chưa xong,
ghi rõ trong report).

**B2 · Sửa stopword và cổng chủ đề.** Không bỏ từ mang nghĩa (`bao`, `toi`…); tách từ dính OCR khi lập chỉ mục ("Tổchức",
"Xửlý"); test hai chiều. Đo lại bằng B1.

**B3 · Graph khái niệm + truy xuất lai.** `data/curated/concepts.json` (~25 khái niệm học vụ, từ đồng nghĩa như
"ra trường", "nhận bằng", "LVTN"; cạnh `ABOUT` tới khoản, `REQUIRES` giữa khái niệm; mỗi cạnh có trang nguồn) dựng tay,
có test kiểm id. Truy xuất: nối khái niệm + BM25, gộp RRF, mở rộng `REQUIRES` 1 bước + quan hệ phiên bản như cũ; bỏ cổng
chủ đề cứng, ngoài phạm vi = không khái niệm nào và BM25 dưới ngưỡng (chọn ngưỡng bằng B1). [Kiên] duyệt danh sách khái
niệm.

**B4 · Hiệu lực theo khóa.** Thêm `applies_to` (khóa / CTĐT, ngày hiệu lực) cho khoản của QĐ 1260/2026, QĐ 2749/2026
[Kiên đối chiếu điều khoản thi hành]. Server dùng `context = {cohort, ctdt}` để đánh dấu bản áp dụng / `superseded`;
thiếu dữ kiện thì giữ cả hai và `applicability_resolved=false`. Đổi contract thì export schema + test gọi service thật.

### C. Advisor

**C1 · Router thấy ngữ cảnh và viết truy vấn.** Router nhận vài lượt gần nhất; schema trả thêm `standalone_question`
(câu hỏi đã điền ngữ cảnh) và `regulation_query` (cụm ngắn) trong **cùng** lời gọi, tăng `ROUTER_MAX_OUTPUT_TOKENS` vừa
đủ. Advisor tra quy chế bằng `regulation_query` + `context` từ hồ sơ (không lấy khóa từ lời người dùng); provider không
có `json_schema` thì dùng câu hỏi gốc. Luật vẫn chạy trước router.

**C2 · Evidence đủ cho bộ test.** Thêm: khóa tuyển sinh, tín chỉ học lại, học kỳ của từng cảnh báo, danh sách quyết
định học vụ (loại, nội dung, học kỳ) từ `get_my_academic_decisions`. Prompt ghi "Khóa tuyển sinh: 2024 · CTĐT: 2023"
thay cho "Quy chế áp dụng". `student_facts` gửi Verifier cùng các trường này. Cần cho H05, H07, H08, H09, H02, H06.

**C3 · Hỏi lại đúng thứ thiếu; không từ chối chỉ vì truy xuất rỗng.** Câu mơ hồ ("Em muốn làm đơn", "Hạn chót là khi
nào", "Môn đó…" không có tiền ngữ) → writer viết câu hỏi lại cụ thể, kết cục `clarify`. Truy xuất rỗng nhưng có hồ sơ →
trả phần dựa trên hồ sơ và nói rõ quy chế chưa tra được.

**C4 · Bỏ ngưỡng tự đặt.** `template_answer` không kết luận "Đủ/Chưa đủ điều kiện" bằng ngưỡng 105 TC
(`prompts.py:113`); chỉ liệt kê số liệu và đoạn quy chế.

**C5 · Câu cố định.** R1, R2 theo `use-cases.md`; thống nhất xưng hô ("mình" / "bạn") cho `CLARIFY`, `NO_REGULATION`,
`INCOMPLETE`, `REFUSAL_*`. Sửa test và mẫu chấm phụ thuộc chữ cũ.

**C6 · Giới hạn 10 câu (UC9).** Trong `AskQuestion`, trước planner: đếm câu người dùng trong hội thoại; vượt
`MAX_QUESTIONS_PER_CONVERSATION` (mặc định 10, thêm vào `.env.example`) → trả R1, kết cục `limit`, không gọi LLM, ghi
trace. Từ câu 8 nhắc "còn N câu". API trả cờ hết lượt; web khóa ô nhập và gợi ý mở hội thoại mới. Được mở hội thoại mới.
Ghi biến vào README mục "Chạy ứng dụng".

### D. Verifier

**D1 · Judge chấm trên câu hỏi đã điền ngữ cảnh** (`standalone_question` của C1), không phải câu nối tiếp gốc. Judge vẫn
không thấy lịch sử (giữ biện pháp chống injection).

**D2 · Tra lại khi thiếu căn cứ.** Verdict có `MISSING_EVIDENCE` / `UNGROUNDED_CLAIM` về quy chế → Advisor tra thêm một
lần (truy vấn mới từ router) rồi viết lại; giữ `MAX_VERIFIER_ROUNDS = 2`. Khớp cam kết D1 "tìm lại"; ghi chi phí thêm
vào `architecture.md`. Nếu Kiên không làm: ghi lý do lệch D1 trong báo cáo.

**D3 · Luật kiểm số liệu hồ sơ (tùy chọn).** Số tín chỉ / ĐTBTL trong bản nháp phải khớp `student_facts`; kiểm bằng code
trước judge, giảm lỗi judge và lời gọi LLM.

### E. Baseline, ablation, chạy cuối

**E1 · Baseline.** `zero_shot` (cùng model, không tool, không hồ sơ) và `naive_rag` (một lần tra bằng câu hỏi gốc + một
lời gọi LLM, không planner, không Verifier) trong `eval/.../baselines.py`. `make_agent_no_verifier` đã có.

**E2 · Ablation theo 3 trục nâng cao.** Cấu hình chọn bằng tham số factory: planner `rules` vs `rules+llm` (trục 1);
Verifier `off` / `rules` / `llm` (trục 2); judge cùng model vs judge riêng (trục 3); truy xuất cũ vs lai (dùng số B1,
không LLM).

**E3 · Prompt injection đầu-cuối.** Đổi PI05, PI10 sang tài khoản sinh viên. Fixture chèn đoạn quy chế độc vào gateway
giả để chạy gián tiếp; thêm 2–3 ca gián tiếp (đòi in canary, đòi xác nhận đủ điều kiện, đòi gọi tool). Đủ ≥ 10 ca, cả
trực tiếp và gián tiếp (R6).

**E4 · Chạy cuối. [LLM] [Kiên]** Kiên chọn model và duyệt ngân sách. 20 hội thoại × 3 seed × các cấu hình E1–E2 + bộ
injection; ghi chi phí (A6). Ước tính một cấu hình ≈ $1.5 với `gpt-4.1-mini` (đoán). Kết quả vào `docs/eval/final-*`.

**E5 · Đo khớp chấm máy và người. [Kiên]** Kiên chấm tay một mẫu lượt; tính tỉ lệ khớp.

### F. Bảo mật, dữ liệu

**F1 · Threat model v2.** Cập nhật `docs/design/threat-model.md` theo kiến trúc mới (backend, Verifier judge riêng,
console, Azure, giới hạn lượt), trạng thái từng biện pháp, kết quả E3.

**F2 · Dữ liệu điểm trong lịch sử chat. [Kiên]** D1 cam kết không lưu điểm ngoài phiên; hiện `messages` và `trace_spans`
lưu (xem `architecture.md` "Còn mở" 1). Chọn: tự xóa sau N ngày / không lưu kết quả Student Record trong span / ghi rõ là
lệch D1. Làm theo lựa chọn.

### G. Nộp bài

- **G1** Bảng phản hồi góp ý D2. [Kiên] cần nội dung thầy góp ý buổi 28/10.
- **G2** Báo cáo 6–8 trang đủ mục trang đồ án (có Ethics, Limitations / threats to validity, reproducibility).
- **G3** Slide 20 phút + demo.
- **G4** Video demo dự phòng.
- **G5** README: lệnh tái lập một dòng; tag `final`; kiểm quyền truy cập repo.
- **G6** Bảng đóng góp, AI-use; mỗi người gửi đánh giá nội bộ.
- **G7** Đọc rubric 11 tiêu chí (PDF đính kèm mail 24/11). [Kiên] cho phép tải file.

## Thứ tự đề xuất

1. A1, A3, A4, A5, A6, A7 (harness, không LLM) song song với A2 [Kiên], B1, B2.
2. Sau khi `feat/foundry-models` merge: C2, C4, C5, C6, rồi C1 → D1, C3, D2.
3. B3, B4 (cần A2).
4. E1, E2, E3 (code), F1, F2.
5. E4 [LLM], E5, rồi G.
