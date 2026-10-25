# Hướng dẫn cho Claude (và cho người viết code trong repo)

Monorepo uv workspace của nhóm G3. Đọc [README.md](README.md) để biết cấu trúc và cách chạy. File này là quy ước
**khi thêm hoặc sửa code**, để các phần ghép được với nhau mà không vỡ.

## Kiểm tra trước khi commit

Chạy đúng các bước của CI (`.github/workflows/ci.yml`, chạy trên Python 3.10 và 3.12):

```bash
uv sync --locked
uv run ruff check .
uv run ruff format --check .
uv run python -m co5151_contracts.export --check
uv run python -m student_server.mockdata.generate --check
uv run pytest
```

## Biến môi trường mới

Cả app dùng **một** file `.env` ở gốc repo và **một** cơ chế đọc: `co5151_contracts.env`.

1. Thêm biến vào [.env.example](.env.example), đặt trong nhóm của thành phần, có một dòng ghi chú ý nghĩa và giá
   trị hợp lệ. Giá trị mẫu phải chạy được ngay, trừ secret/key thì để trống.
2. Trong code chỉ đọc bằng `os.environ.get("TEN_BIEN", <mặc định>)`. Không tự viết hàm đọc `.env` khác, không
   dùng thêm `python-dotenv`.
3. Entry point mới (CLI, server, UI) gọi `load_env_file(a.env_file or find_env_file())` một lần lúc khởi động,
   trước khi đọc cấu hình, và có tùy chọn `--env-file` như `student-mcp` và `co5151-eval`.
4. Không đọc `.env` khi import module và không đọc trong test. Test đặt biến bằng `monkeypatch.setenv` /
   `delenv`; test gọi CLI phải chặn `find_env_file` (xem `eval/tests/conftest.py`), nếu không test có thể gọi LLM
   bằng key thật.
5. Biến làm thay đổi cách chạy app thì ghi thêm vào mục "Chạy ứng dụng" của README.

Tham số gửi lên LLM mà không phải nhà cung cấp nào cũng hỗ trợ (`seed`, `reasoning_effort`, ...) chỉ gửi khi được
cấu hình; nhà cung cấp OpenAI-compatible có thể trả 400 cho tham số lạ.

## Package mới

1. Tạo `pyproject.toml` trong thư mục của package (theo mẫu `mcp/student-server/pyproject.toml`), code nằm trong
   `src/<tên_package>/` có `__init__.py`.
2. Thêm vào `pyproject.toml` gốc: `[tool.uv.workspace] members`, `[tool.ruff] src`,
   `[tool.pytest.ini_options] testpaths`, `[tool.ruff.lint.isort] known-first-party`.
3. Chạy `uv lock` và commit `uv.lock` cùng thay đổi.
4. Import theo tên package (`from regulation_server.x import y`), không chèn `sys.path`. Script chạy bằng
   `uv run python -m <package>.<module>` hoặc khai báo trong `[project.scripts]`.
5. Tên file test phải **khác nhau giữa mọi package** (pytest dùng import mode mặc định).

## Giao tiếp giữa các thành phần

- Dữ liệu đi qua model trong `packages/contracts`. Kết quả tool luôn là envelope `ToolResult` (`{ok, data|error}`).
- Một thành phần dùng thành phần khác qua interface nhỏ `call(tên_tool, tham_số) -> ToolResult`, không import code
  nội bộ của package khác. Chỗ ráp các service thật với nhau (composition root) là adapter, ví dụ
  `services/advisor/src/co5151_advisor/eval_adapter.py`.
- Đổi tên, thêm, bỏ tool hoặc model trong `packages/contracts`:
  1. chạy `uv run python -m co5151_contracts.export` để sinh lại `schemas/`;
  2. tìm mọi chỗ gọi tên cũ (`git grep <tên_tool>`), gồm Advisor, eval (`gold.py`, `tasks.json`) và tài liệu;
  3. có ít nhất một test gọi **service thật** chứ không chỉ mock (ví dụ
     `services/advisor/tests/test_student_tools.py`), để đổi tên tool là test đỏ ngay.
- Đổi mock data của Student Record thì chạy `uv run co5151-eval check-gold` và sửa số liệu trong
  `eval/src/co5151_eval/data/tasks.json`.

## Khác

- Commit theo Conventional Commits, scope là tên thành phần: `feat(advisor): ...`, `fix(eval): ...`.
- Không commit `.env`, key hay secret. Dữ liệu sinh viên là mô phỏng.
- Trả lời và viết tài liệu bằng tiếng Việt; thuật ngữ kỹ thuật giữ tiếng Anh.
