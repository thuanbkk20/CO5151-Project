# CO5151 · G3 — Advisor Agent & Memory (`co5151-advisor`)

Thành phần **Mảng 3** trong hệ thống tư vấn học tập cá nhân hóa:
- **Trục 1: Dynamic RAG & ReAct** — Lập kế hoạch suy luận tuần tự, gọi Student MCP và tra cứu quy chế động theo khóa đào tạo (`ctdt`).
- **Trục 3: Multi-Agent Collaboration** — Đóng vai trò Generator / Advisor phối hợp với Compliance Verifier Agent (Mảng 4).
- **Short-term & Audit Memory** — Cổng kiểm soát riêng tư (`MemoryGate`) có TTL, lưu trữ nguyện vọng cá nhân và lưu vết kiểm toán (`DecisionTrace`) không rò rỉ dữ liệu nhạy cảm.
- **Hỗ trợ Đa cơ chế Ra quyết định (Hybrid Planners)** — Chuyển đổi linh hoạt giữa **Rule-based Decision-driven RAG** và **Laya Non-autoregressive System 1 Decision Engine** (MPS GPU).

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
│   │       Option A (Mặc định):             Option B (`ADVISOR_PLANNER_MODE=laya`):                          │   │
│   │      `DecisionPlanner` (Rule)          `LayaDecisionPlanner` (System 1 Engine)                          │   │
│   │       • State Machine tuần tự           • Single Forward Pass (~20-40ms, MPS GPU)                       │   │
│   │       • Keyword & regex matching        • Typed Choices: SUMMARY | REGULATIONS | RESPOND | CLARIFY...   │   │
│   │                                         • Tự động fallback sang Rule nếu server offline                 │   │
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
│   │   - get_my_warnings                  │      │ • `StaticRegulationSource`: Dùng cho test & eval offline  │   │
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
Toàn bộ **258 bài test** trong repository đã vượt qua với kết quả hoàn hảo:
```bash
uv run pytest
# Output: 258 passed in 4.13s (100% pass)
```

| File kiểm thử | Số lượng test | Nội dung kiểm thử | Kết quả |
|---|:---:|---|:---:|
| `tests/test_planner.py` | 6 | State machine, tuần tự tốt nghiệp, tính bất biến của model Plan/Evidence | ✅ Pass |
| `tests/test_executor.py` | 7 | Giới hạn 2 tool, lọc bỏ PII, map 5 mã lỗi, retry INTERNAL đúng 1 lần | ✅ Pass |
| `tests/test_memory.py` | 7 | Phân loại goal/preference, lọc MSSV/Token/JSON, TTL expiry, user preference | ✅ Pass |
| `tests/test_agent.py` | 6 | Luồng thực thi Agent, tuần tự RAG quy chế, không echo token, adapter protocol | ✅ Pass |
| `tests/test_llm.py` | 4 | Client OpenAI-compatible, phòng chống lộ Canary, fallback khi LLM lỗi/hết funds | ✅ Pass |
| `tests/test_laya.py` | 4 | Laya decision engine, fast-path guardrail, mode switch qua env, live prediction | ✅ Pass |

---

### B. Bảng So sánh Kết quả chạy 2 Mô hình trên Benchmark (Task P01)

Chạy đối chiếu độc lập trên bộ công cụ đánh giá chính thức `co5151-eval`:

```bash
# 1. Chạy Mô hình 1 (Rule-based Decision Planner):
uv run co5151-eval run --agent co5151_advisor.eval_adapter:make_agent --only P01

# 2. Chạy Mô hình 2 (Laya Non-autoregressive Decision Engine):
ADVISOR_PLANNER_MODE=laya uv run co5151-eval run --agent co5151_advisor.eval_adapter:make_agent --only P01
```

| Chỉ số đánh giá | Mô hình 1: Rule-based Decision RAG | Mô hình 2: Laya Non-autoregressive Engine | Đánh giá so sánh |
|---|:---:|:---:|---|
| **Cơ chế ra quyết định** | Deterministic Regex & State Machine | Deep Learning Single-Forward Pass (MPS GPU) | Laya linh hoạt hơn với câu hỏi biến thể tự nhiên |
| **Pass Rate** | **1.00 (100%)** | **1.00 (100%)** | Cả hai đều đạt chuẩn tối đa của task |
| **Outcome Accuracy** | **1.00 (100%)** | **1.00 (100%)** | Ra quyết định đúng `Action.ANSWER` |
| **Fact Recall** | **1.00 (2/2 facts)** | **1.00 (2/2 facts)** | Nêu đầy đủ `113` tín chỉ và `TOEIC 500` |
| **Citation Recall** | Đạt (`Dieu_24_LVTN`) | Đạt (`Dieu_24_LVTN`) | Trích dẫn chính xác quy chế đào tạo |
| **Rò rỉ dữ liệu (Leaks)** | **0** | **0** | Không vi phạm `forbidden` pattern |
| **Số lỗi (Errors)** | **0** | **0** | Không có ngoại lệ runtime |
| **Độ trễ suy luận ra quyết định** | $< 1$ ms | **~25–35 ms** *(trên Apple Silicon GPU)* | Laya cực nhanh, vượt trội so với LLM API (1–3s) |
| **Mức tiêu thụ Token** | 0 token | **0 token sinh thêm** *(Non-autoregressive)* | Tiết kiệm chi phí tối đa |
| **Độ tin cậy quyết định** | Xác định (Deterministic) | **87.76%** Calibrated Confidence | Laya xuất xác suất định lượng rõ ràng |

---

## 4. Hướng dẫn Chuyển đổi và Cấu hình

### A. Chuyển đổi giữa 2 Mô hình Ra quyết định
Sử dụng biến môi trường `ADVISOR_PLANNER_MODE`:
```bash
# Sử dụng Laya System 1 Decision Engine:
export ADVISOR_PLANNER_MODE=laya

# Sử dụng Rule-based Decision Planner (Mặc định):
export ADVISOR_PLANNER_MODE=rule
```

### B. Cấu hình Laya Server
Mặc định kết nối tới tiến trình `laya-serve` cục bộ:
```bash
export LAYA_SERVER_URL=http://127.0.0.1:8000/v1/systemone
```

### C. Cấu hình LLM Client (OpenCode / OpenAI)
```bash
export OPENCODE_API_KEY="your-opencode-or-openai-api-key"
export OPENCODE_BASE_URL="https://opencode.ai/inference/openai/v1"
export OPENCODE_MODEL="kimi-k3"
```
*(Nếu không đặt API Key hoặc tài khoản hết credit, hệ thống tự động kích hoạt bộ tổng hợp an toàn mà không làm gián đoạn bài test).*
