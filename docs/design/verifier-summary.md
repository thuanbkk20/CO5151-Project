# Tóm tắt: Compliance Verifier (nhánh `feat/verifier`)

Ngày viết: 2026-11-10. Nhánh đã rebase lên `feat/mcp-adapter` của Thuấn (`4112a65`), nên gồm cả phần gọi qua MCP.
CI trên máy (Python 3.12): ruff đạt, hai lệnh `--check` đạt, `439 passed`.

## 1. Verifier làm gì

Trước đây Advisor soạn câu trả lời rồi gửi thẳng cho người dùng. Giờ câu trả lời là **bản nháp**, phải qua Verifier:

```
Advisor soạn bản nháp
        │
        ▼
Verifier kiểm ──► pass   ──► gửi cho người dùng
        │
        ├──────► revise ──► Advisor viết lại 1 lần kèm danh sách lỗi ──► Verifier kiểm lại
        │                                                                 ├─ pass  ──► gửi
        │                                                                 └─ không đạt ──► từ chối
        └──────► refuse ──► từ chối (Strict Refusal)
```

Verifier kiểm theo hai lớp, lớp rẻ chạy trước:

1. **Luật (không gọi LLM)**: trích dẫn trong bản nháp phải nằm trong các đoạn quy chế đã tra; không lộ token/canary.
2. **LLM judge (1 lần gọi)**: số liệu hồ sơ có khớp không, kết luận có suy ra được từ bằng chứng không. Chỉ chạy khi
   lớp luật đã đạt.

## 2. Cây file đã thay đổi

`+` file mới, `~` file sửa.

```
CO5151-Project/
├── ~ .env.example                      thêm ADVISOR_VERIFIER, VERIFIER_LLM_MODEL
├── ~ .gitignore                        bỏ qua CLAUDE.local.md
├── ~ README.md                         mục Verifier trong "Chạy ứng dụng"; sửa đường dẫn services/verifier
├── ~ pyproject.toml                    đăng ký package services/verifier vào workspace
├── ~ uv.lock                           thêm co5151-verifier
├── packages/contracts/
│   ├── + src/co5151_contracts/verification.py     model dữ liệu Advisor ↔ Verifier
│   ├── ~ src/co5151_contracts/__init__.py         export các model mới
│   ├── ~ src/co5151_contracts/export.py           sinh thêm 2 file schema
│   ├── + schemas/verifier/*.json                  (file sinh tự động, không sửa tay)
│   └── + tests/test_verification_models.py
├── services/verifier/                  + PACKAGE MỚI (co5151-verifier)
│   ├── + pyproject.toml
│   ├── + README.md
│   ├── + src/co5151_verifier/__init__.py
│   ├── + src/co5151_verifier/verifier.py          gộp kết quả các check thành verdict
│   ├── + src/co5151_verifier/rules.py             check theo luật
│   ├── + src/co5151_verifier/judge.py             check bằng LLM
│   └── + tests/test_verifier_{core,rules,judge}.py
├── services/advisor/
│   ├── ~ pyproject.toml                           phụ thuộc thêm co5151-verifier
│   ├── ~ README.md                                mục 2.D vòng kiểm chứng
│   ├── ~ src/co5151_advisor/agent.py              vòng lặp Advisor ↔ Verifier
│   ├── ~ src/co5151_advisor/eval_adapter.py       ráp Verifier thật theo biến môi trường
│   ├── ~ src/co5151_advisor/llm.py                structured output (JSON schema)
│   ├── ~ src/co5151_advisor/regulations.py        SỬA LỖI: đoạn quy chế rỗng
│   ├── + tests/test_advisor_verifier_loop.py
│   └── ~ tests/test_llm_providers.py, test_regulation_tool_source.py
├── apps/web/
│   ├── ~ src/co5151_web/backend.py                web dùng Verifier, hiện số lượt kiểm
│   └── ~ tests/test_web_backend.py
├── eval/
│   ├── ~ src/co5151_eval/runner.py                ghi verifier_rounds, 2 cột mới trong summary
│   ├── ~ src/co5151_eval/html_report.py           hiện số lượt kiểm ở từng câu
│   ├── ~ README.md
│   └── ~ tests/test_eval_runner.py
└── docs/                               sắp xếp lại thành design/ và eval/
    ├── + README.md                                mục lục tài liệu
    ├── design/
    │   ├── ~ threat-model.md                      (từ docs/) cập nhật trạng thái biện pháp tầng agent
    │   └── + verifier-summary.md                  file này
    └── eval/
        ├── ~ d2-notes.md                          (từ docs/eval-d2-notes.md) sửa link
        └──   d2-report.html                       (từ docs/eval-d2-report.html) chỉ đổi chỗ
```

## 3. Từng file

### packages/contracts — hợp đồng dữ liệu

**`verification.py`** (mới). Advisor và Verifier chỉ nói chuyện qua các model này, không import code của nhau.

- `VerificationRequest`: `question`, `draft`, `student_facts` (số liệu hồ sơ Advisor đã đọc), `regulations` (các đoạn
  quy chế đã tra, mỗi đoạn là `RegulationExcerpt(id, title, content)`).
- `Verdict`: `status` (`pass` / `revise` / `refuse`), `issues`, `input_tokens`, `output_tokens`. Có ràng buộc: `pass`
  không được kèm lỗi, `revise` / `refuse` phải nêu ít nhất một lỗi.
- `IssueCode`: `UNSUPPORTED_CITATION`, `FACT_MISMATCH`, `UNGROUNDED_CLAIM`, `MISSING_EVIDENCE`, `LEAK`, `UNVERIFIED`.

**`export.py`**: sinh thêm `schemas/verifier/verification-request.json` và `verdict.json`.

### services/verifier — package mới

**`verifier.py`** — `ComplianceVerifier(checks, judge=None)`.

- `verify(request)`: chạy các check theo luật. Có lỗi thì trả verdict ngay, **không gọi LLM**. Đạt hết và có judge
  thì gọi judge một lần.
- Gộp lỗi thành `status`: không lỗi → `pass`; có lỗi thuộc `REFUSE_CODES` (`MISSING_EVIDENCE`, `UNVERIFIED`) →
  `refuse`; còn lại → `revise`.

**`rules.py`** — hai check, không tốn token.

- `cited_provisions_are_retrieved`: tìm mã điều khoản (`QD2933-2021-CL5.5`) và số "Điều/Khoản N" trong bản nháp; cái
  nào không có trong các đoạn đã tra thì báo `UNSUPPORTED_CITATION`. Nếu không tra được đoạn nào mà vẫn trích dẫn thì
  báo `MISSING_EVIDENCE`. Số điều khoản do người dùng nêu trong câu hỏi không bị xét (bản nháp có thể đang bác bỏ nó).
- `no_secrets(secrets)`: bản nháp chứa token phiên, header `Bearer ...` hoặc chuỗi canary thì báo `LEAK`.

**`judge.py`** — `LLMJudge(llm, canary=None)`.

- `review(request)`: một lần gọi LLM với system prompt riêng của Verifier. Câu hỏi, số liệu, quy chế, bản nháp đặt
  trong thẻ `<question>`, `<student_facts>`, `<regulations>`, `<draft>` và được khai báo là dữ liệu, không phải lệnh.
  Judge không nhận lịch sử hội thoại.
- Yêu cầu structured output (JSON schema): `{"issues": [{"code", "message"}]}`.
- Gọi LLM lỗi hoặc không đọc được JSON → `UNVERIFIED` (từ chối), không bao giờ ngầm cho qua.
- Nhận LLM qua interface `JudgeLLM`, nên package này không phụ thuộc Advisor.

### services/advisor

**`agent.py`** — phần `RESPOND` tách thành `_respond()`:

1. Soạn bản nháp (LLM; không có LLM thì dùng template như cũ), xoá canary/token.
2. Nếu có Verifier: lặp tối đa `MAX_VERIFIER_ROUNDS = 2` lượt kiểm. `revise` thì gọi LLM viết lại một lần kèm danh
   sách lỗi; `refuse`, hết lượt, hoặc không có LLM để viết lại thì trả `Outcome.REFUSE`.
3. Cộng token của Verifier và lần viết lại vào `usage`; ghi `verifier_rounds`.

Không truyền `verifier` thì hành vi y như trước. Các câu Planner đã từ chối / hỏi lại không qua Verifier.

**`eval_adapter.py`** — chỗ ráp service:

- `make_verifier(llm)`: đọc `ADVISOR_VERIFIER` (`llm` mặc định, `rules`, `off`) và `VERIFIER_LLM_MODEL`.
- `make_agent`: Advisor có Verifier. `make_agent_no_verifier`: baseline "agent đơn không Verifier" của proposal.

**`llm.py`**: `generate()` nhận thêm `response_format`. Chỉ gửi cho provider có cờ `json_schema` (gemini, openai);
kimi giữ nguyên vì endpoint OpenAI-compatible có thể trả 400 với tham số lạ.

**`regulations.py`** — sửa lỗi có sẵn: `ToolRegulationSource` chỉ đọc `evidence.fragments`, nên đoạn chuẩn ngoại ngữ
(chỉ có `source_text`) và sổ tay/FAQ (chỉ có `text`) tới LLM với nội dung rỗng: 12/75 kết quả của 24 câu eval. Giờ
đọc `fragments`, rồi `text`, rồi `source_text`.

### apps/web

**`backend.py`**: `new_advisor` gắn Verifier; mục "Chi tiết xử lý" thêm dòng **Verifier** (số lượt kiểm, có viết lại
hay không).

### eval

**`runner.py`**: `results.jsonl` có thêm `verifier_rounds`; summary thêm hai cột "Verifier viết lại" và "Verifier từ
chối". **`html_report.py`**: hiện số lượt kiểm ở từng câu; kết quả cũ không có trường này vẫn hiển thị được.

## 4. Chi phí LLM

| `ADVISOR_VERIFIER` | Lần gọi LLM thêm cho mỗi câu trả lời |
|---|---|
| `llm` (mặc định) | 1 khi đạt; 3 khi phải viết lại (kiểm + viết lại + kiểm lại) |
| `rules` | 0; 1 khi phải viết lại |
| `off` | 0 |

Đo thật một lần (câu P02, `gemini-3.1-flash-lite`, đường tốn nhất vì có viết lại): 7 lần gọi LLM, 12.264 token vào +
1.675 token ra, 12,6 giây. Riêng hai lượt kiểm của Verifier: 3.116+196 và 3.204+5 token. Verifier bắt đúng ba lỗi ở
bản nháp đầu (hai điều kiện tiên quyết không có trong quy chế đã tra, một trích dẫn "Quy chế 2023/QĐ-1260" bịa), bản
viết lại đạt.

Chưa chạy cả bộ 24 câu × 3 seed với Verifier, nên **chưa có số liệu Pass / từ chối nhầm mới**.

## 5. Cách chạy

```bash
uv run pytest                                     # không gọi LLM
uv run co5151-web                                 # Verifier bật sẵn (llm)
ADVISOR_VERIFIER=rules uv run co5151-web          # chỉ kiểm bằng luật, không tốn thêm LLM
uv run co5151-eval run --agent co5151_advisor.eval_adapter:make_agent --only P02 -v
uv run co5151-eval run --agent co5151_advisor.eval_adapter:make_agent_no_verifier --only P02 -v
```

## 6. Giới hạn đã biết

- Verifier chỉ đối chiếu với các đoạn Advisor đã tra. Tra sai đoạn thì Verifier không phát hiện được, chỉ khiến câu
  trả lời thành "chưa đủ căn cứ".
- Check số "Điều/Khoản" chỉ so con số, bắt được trích dẫn bịa rõ ràng chứ không chứng minh nội dung điều khoản.
- 12 ca prompt injection (`PI01`–`PI12`) chưa chạy.
- Prompt của Advisor chưa đánh dấu ranh giới dữ liệu cho đoạn quy chế (threat model E3); mới làm ở prompt Verifier.
- Nhánh này nằm trên `feat/mcp-adapter`, nên PR của nhánh này phải merge sau PR đó (hoặc mở PR vào thẳng
  `feat/mcp-adapter`). Verifier không phụ thuộc cách gọi tool: `inprocess` hay `mcp` đều đi qua cùng interface.

## 7. Danh sách commit

| Commit | Nội dung |
|---|---|
| `11df924` | feat(contracts): verification request and verdict models for the Verifier |
| `44e4534` | feat(verifier): package skeleton that folds check results into a verdict |
| `fa986fd` | chore: ignore CLAUDE.local.md |
| `04fce45` | feat(verifier): rule checks for unsupported citations and leaked secrets |
| `0983ead` | feat(contracts): UNVERIFIED issue code for a check that could not run |
| `1acc391` | feat(advisor): LLMClient can request JSON-schema structured output |
| `4f350cd` | feat(verifier): LLM judge that checks the draft against its evidence |
| `96fbfb3` | fix(advisor): regulation excerpts without fragments reached the LLM empty |
| `c3dc7c9` | feat(advisor): answer through the Verifier with one bounded rewrite |
| `9fbdf2f` | feat(web): chat answers go through the Verifier and show its rounds |
| `f000efc` | feat(eval): record Verifier rounds and count rewrites and refusals |
| `dd0d1f8` | docs(threat-model): agent-level mitigations now implemented by the Verifier |
| `5e48c81` | docs: group docs into design/ and eval/ with an index |
