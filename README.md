# CO5151 · G3 — Agentic RAG tra cứu quy chế đào tạo & tư vấn học tập cá nhân hóa

Monorepo của nhóm G3 (Application Track · Theme 09). Mỗi thành phần là một package độc lập trong
[uv workspace](https://docs.astral.sh/uv/concepts/projects/workspaces/), do một thành viên phụ trách.

## Cấu trúc

| Thư mục | Thành phần | Mảng phụ trách |
|---|---|---|
| `packages/contracts` | Hợp đồng dùng chung: envelope kết quả tool, mã lỗi, claims phiên đăng nhập, schema input/output của tool | 2. Student Data & MCP |
| `mcp/student-server` | **Student Record MCP**: mock DB điểm/tín chỉ/hồ sơ, scoped read-only, xác thực bằng Bearer token | 2. Student Data & MCP |
| `mcp/regulation-server` | **Regulation MCP**: Knowledge Graph + GraphRAG tra cứu quy chế | 1. Data & GraphRAG & MCP |
| `services/advisor` | Advisor Agent, decision-driven RAG, short-term & audit memory | 3. Advisor Agent & Memory |
| `verifier` | Compliance Verifier, reflection & grounding loop, strict refusal | 4. Verifier & Security |
| `apps/web` | Giao diện chat demo | — |
| `eval` | **Evaluation**: bộ 24 task, metric, baseline, kiểm thử bảo mật & prompt injection | 5. Kiểm thử & đánh giá |
| `docs` | Tài liệu kiến trúc, báo cáo | — |

## Bắt đầu

```bash
uv sync                 # cài toàn bộ workspace + dev tools vào .venv
cp .env.example .env    # điền key LLM và secret, mọi lệnh tự đọc file này
uv run pytest           # chạy test (test không đọc .env)
uv run ruff check .     # lint
```

Cấu hình của cả app nằm trong một file `.env` ở gốc repo, gồm Student Record MCP, Regulation MCP và LLM của Advisor. Các lệnh
`student-mcp` và `co5151-eval` tìm `.env` từ thư mục hiện tại ngược lên tới gốc repo; biến đã `export` trong shell được
ưu tiên. Muốn dùng file khác thì truyền `--env-file <đường dẫn>`. Thành phần mới đọc cấu hình bằng
`co5151_contracts.env.load_env_file(find_env_file())` khi khởi động.

Yêu cầu: Python ≥ 3.10, [uv](https://docs.astral.sh/uv/) ≥ 0.5.

## Chạy ứng dụng

Chỉ cần điền `OPENCODE_API_KEY` trong `.env`; các biến khác đã có giá trị mặc định chạy được. Danh sách đầy đủ và ý
nghĩa từng biến nằm trong [.env.example](.env.example).

```bash
# Advisor end-to-end trên 1 câu: Student Record + Regulation chạy in-process, LLM qua OPENCODE_*
uv run co5151-eval run --agent co5151_advisor.eval_adapter:make_agent --only P01 -v

# Cả bộ 24 câu, 3 seed; so với hệ thống không dùng LLM
uv run co5151-eval run --agent co5151_advisor.eval_adapter:make_agent --seeds 0 1 2
uv run co5151-eval run --agent co5151_eval.baselines:record_template --seeds 0 1 2

# Kiểm thử bảo mật Student Record MCP qua HTTP thật
uv run co5151-eval security
```

Kết quả nằm ở `eval/results/<thời gian>-<agent>/` (`summary.md`, `results.jsonl`). Nếu terminal in
`LLM generation failed, falling back to deterministic template` thì câu đó **không** do LLM trả lời (key sai, hết
tiền, model không hỗ trợ tham số); `tokens` của câu đó là 100.

Chạy từng MCP server riêng để thử bằng MCP client:

```bash
uv run student-mcp serve                 # Streamable HTTP http://127.0.0.1:8102/mcp, cần Bearer token
uv run student-mcp issue-token sv001     # token cho tài khoản demo (mật khẩu: demo)
uv run regulation-mcp --allow-draft      # stdio; dữ liệu quy chế hiện là bản nháp
```

Chưa có giao diện chat (`apps/web`); Advisor hiện được gọi qua `co5151-eval`.

Quy ước khi thêm code (biến môi trường, package, tool mới) nằm trong [CLAUDE.md](CLAUDE.md).

## Quy ước

- Commit theo [Conventional Commits](https://www.conventionalcommits.org/), scope là tên thành phần, ví dụ `feat(student-server): ...`.
- Giao tiếp giữa các thành phần **chỉ** qua các model trong `packages/contracts`; không import chéo nội bộ của package khác.
- Không commit `.env` hay secret thật; dữ liệu sinh viên trong repo là **dữ liệu mô phỏng**.
