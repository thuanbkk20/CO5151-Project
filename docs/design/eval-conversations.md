# Đánh giá theo hội thoại, chi phí, seed, baseline (task A1, A3–A7, E1–E3, F1)

Cập nhật: 2026-11-27. Nhánh `feat/eval-conversations` (tách từ `feat/agent-improvements`). Chỉ viết code và dữ liệu;
**không chạy eval hay ablation** bằng key thật (Kiên chạy sau, task E4).

## Mục tiêu

Bộ test mới là 20 hội thoại / 62 câu ([test-conversations.md](test-conversations.md)), thay 24 câu đơn. Harness phải
chạy nhiều lượt qua backend thật, chấm theo lượt / hội thoại / use case, ghi chi phí USD, truyền seed, có baseline và
cấu hình ablation, có ca prompt injection gián tiếp.

## Thiết kế

**A1 · `conversations.json`.** `Conversation {id, user, title, use_cases, prefill_turns, turns}`; `Turn` giữ các
trường chấm của `Task` (`expected`, `also_accept`, `facts`, `forbidden`, `citations`, `citations_verified`) và thêm
`new_conversation` (H18 câu 12). `prefill_turns` là cặp hỏi/đáp viết sẵn (H18). `Fact.value` nhận `null` ("chưa có
chứng chỉ"). Oracle tính thêm `remaining_credits`. `run` và `check-gold` mặc định dùng bộ hội thoại; `tasks.json` chỉ
còn cho console và test cũ (xem "Chưa quyết").

**A3 · Harness.** Runner giữ lịch sử của từng hội thoại và gọi `agent.answer(câu, history=…)`; `BackendAgent` ghi lịch
sử vào kho hội thoại rồi gọi `AskQuestion`, nên lịch sử đi qua use case như app (giới hạn 10 câu cũng đếm đúng). Lượt
dựng sẵn không gọi LLM. Report: pass theo hội thoại (đạt khi mọi lượt chấm được đều đạt), theo lượt, theo use case.

**A4 · Bộ chấm.** Mẫu cấm bỏ qua khi cùng mệnh đề có từ phủ định đứng trước (trong 8 từ) hoặc câu đó chỉ nhắc lại câu
hỏi; thêm cụm hỏi lại; `limit` chỉ đạt khi câu trả lời đúng mẫu R1.

**A5.** `co5151-eval rescore <results.jsonl>`: chấm lại bằng bộ chấm hiện tại, không gọi agent.

**A6 · Chi phí.** `BackendAgent` đọc span của trace: token vào/ra theo vai (`router`, `writer`, `judge`) và model.
Giá ở `eval/.../data/prices.json` (nguồn: bảng giá trong [foundry-models.md](foundry-models.md)); model chưa có giá thì
ghi "chưa có giá", không đoán. Report có USD theo lượt, hội thoại, cả lần chạy.

**A7 · Seed.** `ChatModel.complete(..., seed=)`; adapter chỉ gửi `seed` khi provider/model bật cờ `seed`. Biến
`LLM_SEED` (eval đặt theo `--seeds`). Trace không thêm cột (tránh migrate DB trên VM): seed ghi vào span `writer`.

**E1.** `zero_shot` (cùng model, không tool, không hồ sơ) và `naive_rag` (một lần tra bằng câu hỏi gốc + một lời gọi
LLM) trong `baselines.py`, dùng adapter LLM của backend.

**E2.** Factory ablation: `make_agent_config(planner=..., verifier=..., judge=...)` và các factory đặt tên sẵn cho
`--agent`. Trục truy xuất dùng `REGULATION_ENGINE` và lệnh `retrieval` (không LLM).

**E3.** PI05, PI10 sang tài khoản sinh viên; fixture chèn đoạn quy chế độc vào kết quả tra cứu (gateway bọc); thêm ca
gián tiếp (đòi in canary, đòi xác nhận đủ điều kiện, đòi gọi tool).
Cách làm: task có `injected_regulation` → runner gọi `agent.inject_regulation(text)`; `BackendAgent` bọc gateway quy chế
bằng `PoisonedRegulations`, thêm một khoản giả `QD2933-2021-CL99.9` vào cuối mọi kết quả `search_regulations`. Ca trả
lời không có fact vẫn được chấm khi có mẫu cấm (đạt = kết cục chấp nhận và không lộ).

**F1.** Threat model v2 theo kiến trúc hiện tại.

## Kế hoạch commit

| # | Commit | Nội dung | Trạng thái |
|---|---|---|---|
| 1 | `docs(design): eval conversations plan` | file này | xong `b77d0f9` |
| 2 | `feat(eval): the test conversations as data` | A1 | xong `7bb1eca` |
| 3 | `fix(eval): forbidden patterns, clarify phrases and the R1 reply` | A4 | xong `a49484d` |
| 4 | `feat(eval): run the conversations turn by turn` | A3 + CLI | xong `a9aa0f9` |
| 5 | `feat(backend): seed for the LLM calls` | A7 | xong `b780dae` |
| 6 | `feat(eval): cost of every run by role and model` | A6 | xong `1454384` |
| 7 | `feat(eval): rescore a run without calling the agent` | A5 | xong `16a71a9` |
| 8 | `feat(eval): zero-shot and naive RAG baselines` | E1 | xong `11c1ff5` |
| 9 | `feat(eval): ablation factories` | E2 | xong `b5fadeb` |
| 10 | `feat(eval): indirect prompt injection fixtures` | E3 | xong `275088b` |
| 11 | `docs: threat model v2` | F1 | xong |
| 12 | `docs: eval conversations in README` | README eval, remaining-work | |

## Chưa quyết

1. Xóa hẳn `tasks.json`: console (bộ câu mặc định, chạy đánh giá qua API) và nhiều test còn dùng. Đề xuất: console nhập
   bộ hội thoại sau, rồi mới xóa.
2. Câu hỏi dựng sẵn của H18 do agent viết (10 câu ngắn của sv006), Kiên duyệt.
3. Giá Gemini chưa có trong tài liệu nhóm: lần chạy bằng Gemini sẽ ghi "chưa có giá".
4. Chạy không LLM (câu trả lời mẫu) thì PI05, PI14 trượt: câu trả lời mẫu trích nguyên văn đoạn quy chế, gồm cả đoạn
   độc. Đường này chỉ dùng khi LLM lỗi; kho quy chế do nhóm kiểm soát. Kết quả thật với LLM: chờ Kiên chạy (E4).
