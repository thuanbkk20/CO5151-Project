# CO5151 · G3 — Agentic RAG tra cứu quy chế đào tạo & tư vấn học tập cá nhân hóa

Monorepo của nhóm G3 (Application Track · Theme 09). Mỗi thành phần là một package độc lập trong
[uv workspace](https://docs.astral.sh/uv/concepts/projects/workspaces/), do một thành viên phụ trách.

## Cấu trúc

| Thư mục | Thành phần | Mảng phụ trách |
|---|---|---|
| `packages/contracts` | Hợp đồng dùng chung: envelope kết quả tool, mã lỗi, claims phiên đăng nhập, schema input/output của tool, ký token | 2. Student Data & MCP |
| `mcp/student-server` | **Student Record MCP**: mock DB điểm/tín chỉ/hồ sơ, scoped read-only, xác thực bằng Bearer token | 2. Student Data & MCP |
| `mcp/regulation-server` | **Regulation MCP**: Knowledge Graph + GraphRAG tra cứu quy chế | 1. Data & GraphRAG & MCP |
| `backend` | **Backend API** (FastAPI, clean architecture): đăng nhập, chat (thường và SSE), lịch sử hội thoại; Advisor Agent (planner, memory) và Compliance Verifier | 3. Advisor Agent & Memory, 4. Verifier & Security |
| `frontend` | **Giao diện chat** Chainlit, chỉ gọi backend API | 5. Kiểm thử & đánh giá |
| `eval` | **Evaluation**: bộ 24 task, metric, baseline, kiểm thử bảo mật & prompt injection | 5. Kiểm thử & đánh giá |
| `docs` | Tài liệu thiết kế và báo cáo đánh giá, mục lục ở [docs/README.md](docs/README.md) | — |

## Bắt đầu

```bash
uv sync                 # cài toàn bộ workspace + dev tools vào .venv
cp .env.example .env    # điền key LLM và secret, mọi lệnh tự đọc file này
uv run pytest           # chạy test (test không đọc .env)
uv run ruff check .     # lint
```

Cấu hình của cả app nằm trong một file `.env` ở gốc repo (hai MCP server, backend, LLM, frontend). Mọi lệnh
(`co5151-api`, `co5151-web`, `student-mcp`, `regulation-mcp`, `co5151-eval`) tìm `.env` từ thư mục hiện tại ngược
lên tới gốc repo; biến đã `export` trong shell được ưu tiên. Muốn dùng file khác thì truyền `--env-file <đường dẫn>`. Thành phần mới đọc cấu hình bằng
`co5151_contracts.env.load_env_file(find_env_file())` khi khởi động.

Yêu cầu: Python ≥ 3.10, [uv](https://docs.astral.sh/uv/) ≥ 0.5.

## Chạy ứng dụng

```
frontend (Chainlit :8000) --HTTP/SSE--> backend (co5151-api :8100) --MCP HTTP--> student-mcp :8102, regulation-mcp :8103
```

Điền trong `.env`: key của provider LLM đang chọn (mặc định `LLM_PROVIDER=gemini`, điền `GEMINI_API_KEY`),
`BACKEND_TOKEN_SECRET`, `STUDENT_MCP_TOKEN_SECRET`, `CHAINLIT_AUTH_SECRET`; các biến khác có mặc định chạy được
([.env.example](.env.example)). Chạy cả 4 process bằng [Procfile](Procfile):

```bash
uvx honcho start           # hoặc từng lệnh: student-mcp serve, regulation-mcp, co5151-api, co5151-web
```

Mở http://localhost:8000, đăng nhập `sv001` … `sv008` (mật khẩu `demo`) hoặc `khach` (chỉ hỏi quy chế). Nút cài
đặt cạnh ô nhập chọn provider (chỉ bên đã có key) và model. Dưới mỗi câu trả lời có "Chi tiết xử lý": từng bước,
tool, trích dẫn, Verifier, token, thời gian, trace id. Lịch sử chat theo tài khoản do backend lưu
(`CHAT_DATABASE_URL`, mặc định SQLite `backend/.data/chat.db`). API: [backend/README.md](backend/README.md).

Biến làm đổi cách chạy:

| Biến | Giá trị | Ý nghĩa |
| --- | --- | --- |
| `ADVISOR_PLANNER_MODE` | `llm` (mặc định) / `laya` / `rule` | Planner kiểm luật trước; khi luật không quyết được thì hỏi LLM (1 lời gọi ngắn), Laya (`LAYA_SERVER_URL`), hoặc dùng bước mặc định |
| `ADVISOR_VERIFIER` | `llm` (mặc định) / `rules` / `off` | Lời gọi LLM thêm mỗi câu: `llm` 1 (3 nếu viết lại), `rules` 0 (1 nếu viết lại), `off` 0 (agent đơn) |
| `VERIFIER_LLM_MODEL` | tên model | Model riêng (rẻ hơn) cho Verifier, cùng provider |
| `CHAT_DATABASE_URL` | trống / `off` / `postgresql+asyncpg://...` | SQLite mặc định / chỉ trong bộ nhớ / PostgreSQL (`uv sync --extra postgres`) |

Provider OpenAI-compatible khác dùng được ngay bằng `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`; muốn có tên riêng
thì thêm vào `PROVIDERS` trong `backend/src/co5151_backend/infrastructure/llm.py`.

### Đánh giá

eval gọi use case `AskQuestion` của backend trong cùng process (không cần chạy server), cấu hình đọc từ cùng `.env`:

```bash
uv run co5151-eval run --agent co5151_eval.backend_agent:make_agent --only P01 -v          # 1 câu
uv run co5151-eval run --agent co5151_eval.backend_agent:make_agent --seeds 0 1 2          # 24 câu × 3 seed
uv run co5151-eval run --agent co5151_eval.backend_agent:make_agent_no_verifier --seeds 0 1 2  # baseline agent đơn
uv run co5151-eval run --agent co5151_eval.baselines:record_template --seeds 0 1 2         # không dùng LLM
uv run co5151-eval security                                                                # bảo mật Student Record MCP
```

Kết quả ở `eval/results/<thời gian>-<agent>/` (`report.html`, `summary.md`, `results.jsonl`); provider, model,
planner, Verifier của lần chạy ghi trong `agent_config`. Nếu terminal in `answer LLM call failed, falling back` thì
câu đó **không** do LLM viết (key sai, hết tiền, model không nhận tham số) mà là template; `tokens` = 0 nghĩa là không
gọi LLM lần nào. Xem [eval/README.md](eval/README.md).

Thử từng MCP server bằng MCP client:

```bash
uv run student-mcp issue-token sv001     # token cho tài khoản demo (mật khẩu: demo), gửi trong header Bearer
uv run regulation-mcp --stdio            # Regulation MCP qua stdio thay vì HTTP
```

Quy ước khi thêm code (biến môi trường, package, tool mới) nằm trong [CLAUDE.md](CLAUDE.md).

## Quy ước

- Commit theo [Conventional Commits](https://www.conventionalcommits.org/), scope là tên thành phần, ví dụ `feat(student-server): ...`.
- Giao tiếp giữa các thành phần **chỉ** qua các model trong `packages/contracts`; không import chéo nội bộ của package khác.
- Không commit `.env` hay secret thật; dữ liệu sinh viên trong repo là **dữ liệu mô phỏng**.
