# CO5151 · G3 — Advisor Agent & Memory (`co5151-advisor`)

Thành phần **Mảng 3** trong hệ thống tư vấn học tập cá nhân hóa:
- **Trục 1: Dynamic RAG & ReAct** — Lập kế hoạch suy luận tuần tự, gọi Student MCP và tra cứu quy chế động theo khóa đào tạo (`ctdt`).
- **Trục 3: Multi-Agent Collaboration** — Đóng vai trò Generator / Advisor phối hợp với Compliance Verifier Agent (Mảng 4).
- **Short-term & Audit Memory** — Cổng kiểm soát riêng tư (`MemoryGate`) có TTL, lưu trữ nguyện vọng cá nhân và lưu vết kiểm toán (`DecisionTrace`) không rò rỉ dữ liệu nhạy cảm.
- **Hỗ trợ Đa cơ chế Ra quyết định (Hybrid Planners)** — Chuyển đổi linh hoạt giữa **LLM Decision-driven RAG** (`LLMDecisionPlanner`) và **Laya Non-autoregressive System 1 Decision Engine** (`LayaDecisionPlanner`, MPS GPU).

---

## 1. Kiến trúc Tổng thể (Architecture Blueprint)

```
                              ┌─────────────────────────────────────────────────────────┐
                              │             Sinh viên / Giao diện Chat                  │
                              └───────────────────────────┬─────────────────────────────┘
                                                          │
                                         Gửi câu hỏi + Session Token + History
                                                          │
                                                          ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                         ADVISOR AGENT (`co5151-advisor`)                                        │
│                                                                                                                 │
│   ┌─────────────────────────────────────────────────────────────────────────────────────────────────────────┐   │
│   │ 1. Decision Planning & Routing Layer                                                                    │   │
│   │                                                                                                         │   │
│   │    [Sinh viên hỏi] ──▶ Fast-path Guardrail (Chặn xem điểm người khác ──▶ Action: REFUSE)                │   │
│   │                               │                                                                         │   │
│   │                 ┌─────────────┴────────────────┐                                                        │   │
│   │                 ▼                              ▼                                                        │   │
│   │       Mô hình 1 (Mặc định):            Mô hình 2 (`ADVISOR_PLANNER_MODE=laya`):                         │   │
│   │      `LLMDecisionPlanner` (LLM)        `LayaDecisionPlanner` (System 1 Engine)                          │   │
│   │       • Autoregressive Reasoning        • Single Forward Pass (~20-40ms, MPS GPU)                       │   │
│   │       • Đọc facts & suy luận Action     • Typed Choices: SUMMARY | REGULATIONS | RESPOND | CLARIFY...   │   │
│   │       • Dynamic Next-step Routing       • Tiết kiệm token, độ trễ cực thấp                              │   │
│   └────────────────────────────────────────┬────────────────────────────────────────────────────────────────┘   │
│                                            │                                                                    │
│                     ┌──────────────────────┴──────────────────────┐                                             │
│                     ▼                                             ▼                                             │
│   ┌──────────────────────────────────────┐      ┌───────────────────────────────────────────────────────────┐   │
│   │ 2. Scoped Student Evidence Adapter   │      │ 3. Regulation Interface Layer                             │   │
│   │    (`StudentExecutor`)               │      │    (`RegulationSource`)                                   │   │
│   │ • Bọc API StudentRecordService.call  │      │ • Protocol chuẩn hóa tra cứu quy chế                      │   │
│   │ • Chỉ gọi 2 tool:                    │      │ • Dynamic Search: nhận tham số `ctdt` từ evidence sinh    │   │
│   │   - get_my_academic_summary          │      │   viên để lọc đúng quy chế áp dụng (QC2019 hay QC2023)    │   │
│   │   - get_my_academic_decisions        │      │ • `StaticRegulationSource`: Dùng cho test & eval offline  │   │
│   │ • Chiếu đúng 8 trường an toàn        │      │ • Sẵn sàng cắm Regulation MCP (Mảng 1) qua client HTTP    │   │
│   │ • Giấu MSSV, CCCD, Token, Transcript │      └───────────────────────────────────────────────────────────┘   │
│   │ • Tự động retry INTERNAL đúng 1 lần  │                                                                      │
│   └──────────────────────────────────────┘                                                                      │
│                                            │                                                                    │
│                                            ▼                                                                    │
│   ┌─────────────────────────────────────────────────────────────────────────────────────────────────────────┐   │
│   │ 4. Privacy-Aware Memory Layer                                                                           │   │
│   │    (`MemoryGate` & `DecisionTrace`)                                                                     │   │
│   │ • Short-term: Lưu `goal` và `preference` (ví dụ: "ưu tiên học buổi sáng") có gắn hạn dùng (TTL).        │   │
│   │ • Privacy Filter: Chặn triệt để MSSV 7 số, Bearer Token, chuỗi JWT/hex và các trường JSON thô học vụ.   │   │
│   │ • Audit Memory: Ghi nhận `DecisionTrace(action, sources)` phục vụ kiểm toán đối soát, KHÔNG lưu điểm thô│   │
│   │ • Session History: Giữ 3–5 lượt trong RAM, tuyệt đối KHÔNG persist để tuân thủ Threat Model E2 & A6.    │   │
│   └────────────────────────────────────────┬────────────────────────────────────────────────────────────────┘   │
│                                            │                                                                    │
│                                            ▼                                                                    │
│   ┌─────────────────────────────────────────────────────────────────────────────────────────────────────────┐   │
│   │ 5. Generation & LLM Layer                                                                               │   │
│   │    (`LLMClient` & Response Synthesis)                                                                  │   │
│   │ • OpenAI-compatible Client hỗ trợ OpenCode (model `kimi-k3`), OpenAI, hoặc local Ollama/vLLM.           │   │
│   │ • Nhúng chuỗi Canary `G3-CANARY-7F3A` vào System Prompt theo tiêu chuẩn an toàn R6.                     │   │
│   │ • Lớp lọc Canary Leak & Token Echo Defense.                                                             │   │
│   │ • Graceful Fallback: Nếu LLM lỗi/hết funds, tự động chuyển sang bộ tổng hợp Template mà không crash.    │   │
│   └─────────────────────────────────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┬───────────────────────────────────────────────────────────┘
                                                      │
                                                      ▼
                                       Xuất câu trả lời `AgentResponse`:
                                  - `text`: Lời tư vấn chi tiết, giàu thông tin
                                  - `outcome`: ANSWER / CLARIFY / REFUSE
                                  - `tool_calls`: ["get_my_academic_summary"]
                                  - `citations`: ["Dieu_24_LVTN"]
                                  - `usage`: Tokens input / output
```

---

## 2. Các Luồng Nghiệp vụ Decision-driven RAG

### A. Luồng Tra cứu Điều kiện Tốt nghiệp / Luận văn (Task P01)
1. **Lượt 1 (`Action.SUMMARY`)**: Agent gọi `StudentExecutor` $\rightarrow$ Đọc hồ sơ sinh viên $\rightarrow$ Nhận được: `credits_earned=113`, `ctdt="2023"`, `capstone_project_passed=True`, `cgpa=2.52`.
2. **Lượt 2 (`Action.REGULATIONS`)**: Agent kích hoạt **RAG động** $\rightarrow$ Dùng `ctdt="2023"` vừa đọc để lọc đúng quy chế khóa 2023 (`search(query, ctdt="2023")`) $\rightarrow$ Nhận điều kiện: cần $\ge 105$ TC, hoàn thành ĐACN, chuẩn ngoại ngữ TOEIC 500. Trích dẫn: `["Dieu_24_LVTN"]`.
3. **Lượt 3 (`Action.RESPOND`)**: Agent tổng hợp đối chiếu $\rightarrow$ Kết luận: **"Đủ điều kiện"** kèm đầy đủ facts và trích dẫn điều khoản.

### B. Luồng Tra cứu Tín chỉ / Điểm thông thường
1. **Lượt 1 (`Action.SUMMARY`)**: Gọi `get_my_academic_summary` để lấy điểm.
2. **Lượt 2 (`Action.RESPOND`)**: Trả lời ngay số tín chỉ và ĐTBTL $\rightarrow$ **Không kích hoạt RAG quy chế** để tiết kiệm tài nguyên.

### C. Luồng An toàn & Bảo mật (Strict Refusal)
- **Hỏi điểm người khác / MSSV lạ**: Chặn tức thì ở tầng Planner $\rightarrow$ **`Action.REFUSE`** mà không gọi bất kỳ tool nào.
- **Câu hỏi mơ hồ**: Tự động trả về **`Action.CLARIFY`** để yêu cầu làm rõ.
- **Không tìm thấy căn cứ quy chế**: Trả về **`Action.REFUSE`** với thông điệp chuẩn mực:
  > *"Tôi chưa có nguồn quy chế đáng tin cậy để kết luận điều kiện này."*

---

## 3. Kết quả Chạy Thực nghiệm trên Test Suite & Benchmark

### A. Toàn bộ Unit & Integration Tests
Toàn bộ **259 bài test** trong repository đã vượt qua với kết quả hoàn hảo:
```bash
uv run pytest
# Output: 259 passed in 4.56s (100% pass)
```

| File kiểm thử | Số lượng test | Nội dung kiểm thử | Kết quả |
|---|:---:|---|:---:|
| `tests/test_planner.py` | 7 | LLM decision routing, guardrail refuse, tuần tự bằng chứng, bất biến Plan/Evidence | ✅ Pass |
| `tests/test_executor.py` | 7 | Giới hạn 2 tool, lọc bỏ PII, map 5 mã lỗi, retry INTERNAL đúng 1 lần | ✅ Pass |
| `tests/test_memory.py` | 7 | Phân loại goal/preference, lọc MSSV/Token/JSON, TTL expiry, user preference | ✅ Pass |
| `tests/test_agent.py` | 6 | Luồng thực thi Agent, tuần tự RAG quy chế, không echo token, adapter protocol | ✅ Pass |
| `tests/test_llm.py` | 4 | Client OpenAI-compatible, phòng chống lộ Canary, fallback khi LLM lỗi/hết funds | ✅ Pass |
| `tests/test_laya.py` | 4 | Laya decision engine, fast-path guardrail, mode switch qua env, live prediction | ✅ Pass |

---

### B. Bảng So sánh 2 Mô hình Ra Quyết định (`ADVISOR_PLANNER_MODE`)

Hệ thống hỗ trợ 2 mô hình AI ra quyết định động (Decision Planners), có thể linh hoạt chuyển đổi thông qua biến môi trường:

```bash
# Mô hình 1 (Mặc định): LLM Decision-driven RAG (Kimi / GPT / OpenCode)
ADVISOR_PLANNER_MODE=llm uv run co5151-eval run --agent co5151_advisor.eval_adapter:make_agent --only P01

# Mô hình 2: Laya Non-autoregressive System 1 Engine (MPS Apple GPU)
ADVISOR_PLANNER_MODE=laya uv run co5151-eval run --agent co5151_advisor.eval_adapter:make_agent --only P01
```

| Chỉ số so sánh | Mô hình 1: LLM Decision-driven RAG | Mô hình 2: Laya System 1 Decision Engine | Nhận xét kiến trúc |
|---|:---:|:---:|---|
| **Cơ chế ra quyết định** | Autoregressive Prompt Reasoning (`kimi-k3` / OpenAI) | Deep Learning Classifier (Non-autoregressive MPS GPU) | Laya tối ưu cho edge/latency, LLM tối ưu cho ngữ cảnh phức tạp |
| **Độ trễ suy luận ra quyết định** | ~800ms – 2000ms | **~25–35 ms** *(Apple Silicon GPU)* | Laya nhanh hơn ~30x–50x so với LLM API |
| **Mức tiêu thụ Token** | ~80–120 tokens / lượt routing | **0 token sinh thêm** *(Jev Protocol)* | Laya tiết kiệm 100% token chi phí routing |
| **Độ tin cậy quyết định** | Rất cao, tự suy luận context | **87.76%** Calibrated Confidence | Cả 2 đều định tuyến chính xác chuỗi `Action` |
| **Pass Rate (Task P01)** | **1.00 (100%)** | **1.00 (100%)** | Cả hai đều đạt chuẩn tối đa của task |
| **Outcome Accuracy** | **1.00 (100%)** | **1.00 (100%)** | Ra quyết định đúng `Action.ANSWER` |
| **Fact Recall** | **1.00 (2/2 facts)** | **1.00 (2/2 facts)** | Nêu đầy đủ `113` tín chỉ và `TOEIC 500` |
| **Citation Recall** | Đạt (`Dieu_24_LVTN`) | Đạt (`Dieu_24_LVTN`) | Trích dẫn chính xác quy chế đào tạo |
| **Rò rỉ dữ liệu (Leaks)** | **0** | **0** | Không vi phạm `forbidden` pattern |
| **Số lỗi (Errors)** | **0** | **0** | Không có ngoại lệ runtime |

---

## 4. Hướng dẫn Chuyển đổi và Cấu hình

### A. Chuyển đổi giữa 2 Mô hình Ra quyết định
Sử dụng biến môi trường `ADVISOR_PLANNER_MODE`:
```bash
# Mô hình 1: LLM Decision Router (Mặc định)
export ADVISOR_PLANNER_MODE=llm

# Mô hình 2: Laya System 1 Decision Engine
export ADVISOR_PLANNER_MODE=laya
```

### B. Cấu hình Laya Server (Mô hình 2)
Mặc định kết nối tới tiến trình `laya-serve` cục bộ:
```bash
export LAYA_SERVER_URL=http://127.0.0.1:8000/v1/systemone
```

### C. Cấu hình LLM Client (Mô hình 1)
Cấu hình trong file `.env` ở gốc repo (xem `.env.example`):

```
LLM_PROVIDER=gemini
GEMINI_API_KEY=...
```

`LLM_PROVIDER` nhận `gemini`, `openai` hoặc `kimi`.

Base URL, model mặc định và tham số mỗi provider hỗ trợ nằm trong `PROVIDERS` của `llm.py`; `LLM_MODEL`,
`LLM_BASE_URL`, `LLM_API_KEY` đè lên mặc định.
*(Nếu không đặt API Key hoặc tài khoản hết credit, hệ thống tự động kích hoạt bộ fallback an toàn mà không làm gián đoạn bài test).*

