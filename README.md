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
| `eval` | Bộ task đánh giá, script benchmark & injection test | — |
| `docs` | Tài liệu kiến trúc, báo cáo | — |

## Bắt đầu

```bash
uv sync                 # cài toàn bộ workspace + dev tools vào .venv
uv run pytest           # chạy test
uv run ruff check .     # lint
```

Yêu cầu: Python ≥ 3.10, [uv](https://docs.astral.sh/uv/) ≥ 0.5.

## Quy ước

- Commit theo [Conventional Commits](https://www.conventionalcommits.org/), scope là tên thành phần, ví dụ `feat(student-server): ...`.
- Giao tiếp giữa các thành phần **chỉ** qua các model trong `packages/contracts`; không import chéo nội bộ của package khác.
- Không commit `.env` hay secret thật; dữ liệu sinh viên trong repo là **dữ liệu mô phỏng**.
