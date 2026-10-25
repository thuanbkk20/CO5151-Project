# Student Record MCP (`co5151-student-server`)

MCP server cho phép agent đọc hồ sơ học vụ (điểm, tín chỉ, cảnh báo, hồ sơ cơ bản) của **đúng tài khoản đang đăng nhập**.
Chỉ đọc (read-only) và giới hạn theo token (scoped). Một tiến trình phục vụ nhiều người dùng qua Streamable HTTP.

> Dữ liệu là **mô phỏng**, giữ nguyên schema API của Trường. Xem [docs/MOCK_DATA.md](docs/MOCK_DATA.md).

## Chạy nhanh

```bash
uv sync                                         # ở thư mục gốc repo
cp mcp/student-server/.env.example .env         # đặt STUDENT_MCP_TOKEN_SECRET
uv run student-mcp accounts                     # 8 sinh viên sv001…sv008 + cố vấn cvht01 (mật khẩu: demo)
uv run student-mcp serve                        # http://127.0.0.1:8102/mcp, bắt buộc Bearer token
uv run student-mcp issue-token sv001            # in token để thử bằng MCP Inspector / curl
uv run student-mcp serve --stdio --as sv001     # chỉ để debug một người dùng (Claude Desktop, Inspector stdio)
```

Thử bằng [MCP Inspector](https://github.com/modelcontextprotocol/inspector): transport *Streamable HTTP*, URL
`http://127.0.0.1:8102/mcp`, header `Authorization: Bearer <token>`.

## Tools

Định nghĩa duy nhất ở `co5151_contracts.tools.STUDENT_RECORD_TOOLS`; JSON Schema ở
[`packages/contracts/schemas/student-record/`](../../packages/contracts/schemas/student-record/).

| Tool | Tham số | Role | Mức quyền | Trả về (`data`) |
|---|---|---|---|---|
| `get_my_profile` | — | student | read-only | `StudentProfile`: MSSV, họ tên, khoa, hệ, khóa, CTĐT |
| `get_my_academic_summary` | — | student | read-only | `AcademicSummary`: TC tích lũy, ĐTBTL thang 4/10, đồ án, ngoại ngữ, GDTC/GDQP, cảnh báo |
| `get_my_transcript` | `semester?` (`^([0-9]{4}[123]\|BL)$`) | student | read-only | `Transcript`: danh sách môn, mã điểm đặc biệt đã giải mã |
| `get_my_semester_summary` | — | student | read-only | `SemesterSummary`: TC và điểm TB từng học kỳ, mới nhất trước |
| `get_my_academic_decisions` | — | student | read-only | `AcademicDecisions`: mọi quyết định học vụ (cảnh báo, tạm dừng / tiếp tục học, miễn học, giao đề tài TN, ...) + trạng thái cảnh báo hiện tại |
| `get_advisee_summary` | `student_id` (`^[0-9]{7}$`) | advisor | read-only | `AcademicSummary` của một sinh viên **thuộc danh sách cố vấn** |

Mọi tool khai báo MCP annotation `readOnlyHint=true, destructiveHint=false, idempotentHint=true, openWorldHint=false`.

### Envelope & lỗi

Mỗi lần gọi trả về một text content là JSON:

```json
{"ok": true, "data": {"student_id": "2310001", "...": "..."}}
{"ok": false, "error": {"code": "FORBIDDEN", "message": "Không có quyền truy cập hồ sơ sinh viên khác."}}
```

| Tình huống | Kết quả |
|---|---|
| HTTP request không có / sai / hết hạn token | **HTTP 401** từ middleware, tool không được chạy |
| Gọi trong tiến trình (`service.call`) không có token hợp lệ | `UNAUTHENTICATED` |
| Tham số sai định dạng (`semester="abc"`) | `INVALID_ARGUMENT` (kèm `details.problems`, không lặp lại giá trị đầu vào) |
| Sinh viên gọi `get_advisee_summary`, cố vấn gọi `get_my_*`, cố vấn đọc ngoài danh sách | `FORBIDDEN` (cùng một thông điệp, không tiết lộ MSSV có tồn tại hay không) |
| Token hợp lệ nhưng không có hồ sơ | `NOT_FOUND` |
| Lỗi nội bộ | `INTERNAL` (thông điệp chung, chi tiết chỉ ghi vào log server) |

## Bảo đảm ở mức mã nguồn (cho mục R2 của D2)

Hệ thống chỉ có công cụ **chỉ đọc**. Các giới hạn dưới đây được áp **trong code**, không dựa vào prompt:

| Bảo đảm | Cơ chế | Ở đâu | Test |
|---|---|---|---|
| Không ghi được dữ liệu | Không tool nào có handler ghi; connection SQLite bật `PRAGMA query_only` sau khi seed | `db.py` | `test_db.py::test_store_is_read_only_after_seeding` |
| Xác thực mỗi request | Bearer token HMAC-SHA256 được kiểm tra ở middleware cho **mọi** HTTP request, rồi kiểm tra lại trong service | `mcp_compat.SessionTokenVerifier`, `authz.authenticate` | `test_e2e_http.py::test_invalid_tokens_are_rejected_with_401` |
| Không đọc chéo sinh viên | Danh tính lấy từ claims của token. Tool `get_my_*` **không có** tham số `student_id`; target luôn là `claims.student_id` | `authz.resolve_target` (điểm quyết định duy nhất) | `test_authz.py`, `test_e2e_http.py::test_injected_student_id_never_changes_the_target` |
| Cố vấn chỉ đọc sinh viên mình phụ trách | `student_id` phải thuộc claim `advisees`; kiểm tra trước khi tra cứu | `authz.resolve_target` | `test_e2e_http.py::test_advisor_scope` |
| Cô lập giữa người dùng đồng thời | Token được đọc theo request hiện tại (`get_access_token()` là context-local) | `server.request_token` | `test_e2e_http.py::test_concurrent_users_are_isolated` |
| LLM không thấy và không đổi được token | Token do host app gắn vào header của transport, không bao giờ nằm trong tham số tool hay kết quả trả về | `server.py` | — |
| Tối thiểu hóa dữ liệu | Mapper copy từng trường một cách tường minh; model output `extra="forbid"`; service kiểm tra kiểu kết quả theo contract | `academic.py`, `co5151_contracts.student`, `service.call` | `test_service.py::test_no_pii_ever_leaves_the_service` |
| Truy vết | Mọi lần gọi (được phép hoặc bị từ chối) được ghi lại, actor/target là pseudonym HMAC | `audit.py` | `test_service.py::test_every_call_is_audited` |

Về tham số chèn thêm: schema được quảng bá có `additionalProperties: false`. Khi gọi qua MCP, SDK bỏ các tham số không khai báo
trước khi tool chạy. Khi gọi trực tiếp `service.call`, contract từ chối với `INVALID_ARGUMENT`. Trong cả hai trường hợp,
target vẫn lấy từ token.

## Tích hợp với Agent

**Qua MCP (khuyến nghị, đa người dùng):** host app đăng nhập người dùng, giữ token trong phiên, rồi mở session với header Bearer:

```python
from student_server.mcp_compat import open_session

async with open_session("http://127.0.0.1:8102/mcp", token=session_token) as s:
    tools = (await s.list_tools()).tools  # name, description, inputSchema → function-calling schema
    res = await s.call_tool("get_my_academic_summary", {})
    envelope = json.loads(res.content[0].text)  # {"ok": ..., "data" | "error": ...}
```

**Trong tiến trình (test, eval offline):**

```python
from student_server.config import Settings
from student_server.server import build_service
from student_server.auth import login

svc = build_service(Settings.from_env())
token = login(svc.db, svc.signer, "sv001", "demo")
svc.call("get_my_transcript", token, {"semester": "20252"})  # → ToolResult
```

Gợi ý cho Advisor Agent:
- Lấy function-calling schema từ `STUDENT_RECORD_TOOLS[name].input_schema()` hoặc `list_tools()`; **không** thêm `student_id` vào tool `get_my_*`.
- Rẽ nhánh theo `error.code`, không theo `message`. Chỉ `INTERNAL` mới nên thử lại (`ErrorCode.retryable`).
- Gặp `FORBIDDEN` thì trả lời rằng không có quyền, không thử lại với MSSV khác.
- Kết quả tool là dữ liệu cá nhân: không ghi nguyên văn vào long-term/audit memory.

## Cấu hình

| Biến | Mặc định | Ghi chú |
|---|---|---|
| `STUDENT_MCP_TOKEN_SECRET` | `dev-secret-change-me` (có cảnh báo) | Khóa HMAC cho token; dùng chung với host app cấp token |
| `STUDENT_MCP_TOKEN_TTL` | `3600` | Giây |
| `STUDENT_MCP_HOST` / `STUDENT_MCP_PORT` | `127.0.0.1` / `8102` | |
| `STUDENT_MCP_DB_PATH` | `:memory:` | Đường dẫn file để giữ DB giữa các lần chạy |
| `STUDENT_MCP_DATA_DIR` | `src/student_server/mockdata` | Thư mục payload mock |
| `STUDENT_MCP_SESSION_TOKEN` | — | Chỉ cho `serve --stdio` |

## Cấu trúc

```
src/student_server/
  mockdata/      generate.py (seed 2026) + *.json theo schema API
  db.py          nạp payload vào SQLite (query_only, có lock)
  academic.py    anti-corruption layer: payload thô → model contracts
  auth/          tokens.py (HMAC) · passwords.py (PBKDF2) · accounts.py (login demo)
  authz.py       quyết định target của mỗi lần gọi
  audit.py       access log có pseudonym
  service.py     pipeline: authenticate → validate → authorize → read → audit
  server.py      đăng ký tool MCP, token theo từng request
  mcp_compat.py  tương thích mcp 1.x / 2.x, verifier, client open_session
  cli.py         student-mcp serve | issue-token | accounts
```

## Phát triển

```bash
uv run python -m pytest mcp/student-server                         # unit + e2e (server HTTP thật trên cổng ngẫu nhiên)
uv run python -m student_server.mockdata.generate        # sinh lại mock data
uv run python -m student_server.mockdata.generate --check
```

## Giới hạn đã biết

- Token là HMAC với khóa dùng chung, mô phỏng SSO. Bản thật nên dùng JWT bất đối xứng (RS256/ES256) và kiểm tra `aud`.
- Chưa thu hồi được token trước khi hết hạn.
- Access log nằm trong bộ nhớ (tối đa 10.000 sự kiện) và được ghi ra logger `student_server.audit`; chưa lưu bền vững.
- Một số quy ước dữ liệu là giả định, xem mục "GIẢ ĐỊNH" trong `docs/MOCK_DATA.md`.
