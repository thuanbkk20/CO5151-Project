# Thiết kế lại giao diện chat (Chainlit)

Cập nhật: 2026-11-18. Nhánh `feat/chat-ui`. Người làm: Kiên.

## Mục tiêu

App chat là thứ thầy dùng để chấm demo. Lần đầu mở phải hiểu ngay: đây là trợ lý gì, đăng nhập bằng gì, hỏi được gì,
và câu trả lời dựa trên điều khoản nào. Chỉ sửa `frontend/` (và một API nhỏ của backend cho trích dẫn); không đổi
Advisor, Verifier hay luồng dữ liệu.

## Hiện trạng và vấn đề

| # | Vấn đề | Căn cứ |
|---|---|---|
| H1 | Nút, menu của Chainlit bằng tiếng Anh ("New Chat", "Readme") dù nội dung tiếng Việt | Không có `vi-VN` trong `.chainlit/translations/`; Chainlit lấy ngôn ngữ trình duyệt, mặc định `en-US` |
| H2 | Không có logo, màu, favicon riêng; Chainlit mặc định giao diện tối | `logo_file_url = ""` trong `.chainlit/config.toml`; `default_theme` mặc định `"dark"` (`chainlit/config.py`) |
| H3 | Người mới không biết đăng nhập tài khoản nào, mỗi tài khoản là tình huống gì | Bảng tài khoản chỉ nằm trong `chainlit.md` (nút Readme) |
| H4 | Bốn câu gợi ý giống nhau cho mọi tài khoản; khách (`khach`) cũng thấy câu hỏi về bảng điểm của mình | `STARTERS` trong `frontend/src/co5151_web/app.py` |
| H5 | Tiến trình hiện tên nội bộ: `Gọi tool \`search_regulations\``, `Lập kế hoạch: SUMMARY` | `PROGRESS` trong `present.py` |
| H6 | Trích dẫn chỉ là mã (`QD-Đ22`) nằm trong "Chi tiết xử lý"; không xem được nội dung điều khoản | `details_markdown` trong `present.py`; `TraceOut.citations: list[str]` |
| H7 | Không nói rõ quy chế là bản nháp chưa phê duyệt, dữ liệu sinh viên là mô phỏng | Chỉ có trong `chainlit.md`; Regulation MCP trả `"verified": False` (`regulation_service.py`) |

## Thiết kế

### 1. Tiếng Việt toàn bộ giao diện (H1)
- Thêm `frontend/.chainlit/translations/vi-VN.json` (dịch từ `en-US.json` của Chainlit 2.12), đặt
  `[UI] language = "vi-VN"` để mọi trình duyệt đều thấy tiếng Việt (`config.ui.language` được ưu tiên hơn ngôn
  ngữ trình duyệt, `chainlit/server.py`).
- Commit file dịch; các file dịch khác Chainlit tự sinh thì không commit (như hiện nay).

### 2. Nhận diện và giao diện sáng (H2)
- `frontend/public/theme.json`: bảng màu xanh dương đậm (gần màu trường), font hệ thống; `default_theme = "light"`.
- Logo chữ "G3 · Cố vấn học vụ" dạng SVG (sáng/tối), favicon. Không dùng logo trường (không có quyền dùng).
- `custom_css` nhỏ (`public/style.css`) chỉ cho những gì theme không làm được (khung nguồn trích dẫn, nhãn).

### 3. Màn hình chào theo tài khoản (H3, H4, H7)
- Sau khi đăng nhập, khung chào (không lưu vào hội thoại; là `markdown_description` của chat profile duy nhất, vì
  tin nhắn chào sẽ làm Chainlit ẩn câu gợi ý) cho biết: đang là ai (tên, MSSV hoặc "khách"/"cố vấn"),
  hỏi được gì với tài khoản này, và dòng lưu ý "Quy chế là bản nháp chưa phê duyệt; dữ liệu sinh viên là mô phỏng".
- Câu gợi ý theo vai trò:
  - Sinh viên: câu về hồ sơ của mình (tín chỉ, cảnh báo, luận văn, tốt nghiệp).
  - Khách: chỉ câu về quy chế chung.
  - Cố vấn học tập: như khách. Advisor chưa có tool cho cố vấn (`STUDENT_TOOLS` trong `advisor/tools.py` chỉ
    có `get_my_*`), nên ảnh trang đăng nhập không quảng cáo `cvht01`.
  - Một nhóm "Thử bảo mật" (xem hồ sơ người khác, prompt injection) để thầy thấy hệ thống từ chối đúng.
- Trang Readme (`chainlit.md`) viết lại: bảng tài khoản kèm tình huống của từng `sv00x` (lấy từ
  `mcp/student-server/docs/MOCK_DATA.md`), cách đọc nguồn trích dẫn và nhãn Verifier.

### 4. Tiến trình dễ hiểu (H5)
- Đổi nhãn: "Đang hiểu câu hỏi", "Đang đọc hồ sơ học vụ", "Đang tra quy chế", "Đang soạn câu trả lời",
  "Đang kiểm tra lại câu trả lời (lượt n)". Tên tool gốc vẫn giữ trong "Chi tiết kỹ thuật" (thu gọn sẵn).
- Bảng ánh xạ tool → nhãn đặt trong `present.py`, tool lạ thì hiện tên gốc.

### 5. Nguồn trích dẫn xem được (H6)
- Dưới câu trả lời: các nút nguồn, ví dụ `Điều 22 · QĐ… · tr. 14`. Bấm → panel bên phải (Chainlit `ElementSidebar`)
  hiện nguyên văn điều khoản, văn bản nguồn, trang PDF, nhãn "bản nháp".
- Backend thêm `GET /provisions/{id}` (cần đăng nhập): gọi tool `get_provision` của Regulation MCP qua port có sẵn
  `RegulationGateway`, trả về dữ liệu điều khoản. Frontend chỉ là client của backend, không gọi MCP.
- Không lấy nội dung từ span (`/traces/{id}/spans`): span dùng để debug, bị cắt 2000 ký tự (`tracing.py`).

### 6. Nhãn kiểm chứng (H7)
- Dưới mỗi câu trả lời một dòng nhỏ: "✓ Verifier đã kiểm (n lượt)" hoặc "Trả lời theo mẫu, không qua LLM", và
  "Quy chế: bản nháp". Thay cho danh sách dài "Chi tiết xử lý" (danh sách này chuyển vào "Chi tiết kỹ thuật").

### Không đổi
- Đăng nhập, lịch sử hội thoại, đánh giá 👍/👎, chọn nhà cung cấp LLM (giữ cho demo), không stream nháp
  ("No event carries a draft", `events.py`).

## Kế hoạch commit

| # | Commit | Nội dung | Trạng thái |
|---|---|---|---|
| 1 | `docs(design): chat UI redesign plan` | file này, link trong `docs/README.md` | xong |
| 2 | `feat(web): Vietnamese interface` | `vi-VN.json`, `language = "vi-VN"` + test | xong `d3da21b` |
| 3 | `feat(web): light theme, logo and favicon` | `public/theme.json`, logo SVG, ảnh trang đăng nhập (đã bỏ tài khoản demo khỏi ảnh khi deploy public), `config.toml` | xong `23fd544` |
| 4 | `feat(web): welcome and starters by account` | một chat profile mỗi tài khoản (lời chào + câu gợi ý theo vai trò, lấy từ `tasks.json`), "Thử bảo mật", `chainlit.md` + test | xong `95c7176` |
| 5 | `feat(web): plain progress labels` | step "Đang/Đã xử lý câu hỏi", nhãn tiến trình, "Chi tiết kỹ thuật" bên dưới + test | xong `7843ef3` |
| 6 | `feat(backend): GET /provisions/{id}` | use case `ReadProvision` qua `RegulationGateway`, 404/422/503, schema, test với MCP server thật (fixture có sẵn) | xong `2eb3713` |
| 7 | `feat(web): sources of an answer in the side panel` | nút nguồn (đọc điều khoản một lần mỗi trích dẫn, giữ trong phiên), panel `ElementSidebar`, client + test | xong `dfb0798` |
| 8 | `feat(web): verification line under each answer` | dòng Verifier / theo mẫu / từ chối theo quy tắc / số trích dẫn, chỉ hiển thị (backend giữ nguyên câu trả lời) + test | xong `b0e8c74` |
| 9 | `docs: chat UI` | README frontend, README gốc, architecture (ảnh chụp không commit, để giữ repo nhẹ) | xong |

Mỗi bước: `ruff`, `pytest`, rồi xem tay trên trình duyệt (không cần gọi LLM: tài khoản `khach` hoặc backend không
có key thì Advisor trả lời bằng mẫu).

## Chưa quyết

- Mở lại hội thoại cũ thì chưa có nút nguồn: trích dẫn nằm trong trace, không lưu cùng tin nhắn; muốn có thì phải
  đọc trace của từng câu trả lời khi mở lại (thêm một lời gọi backend mỗi câu).
- Lời chào hiện "Xin chào sv001": backend trả `display_name` là tên đăng nhập, không phải họ tên trong hồ sơ.
- Tài khoản cố vấn (`cvht01`) chưa hỏi được về sinh viên mình phụ trách: cần thêm tool phía Advisor (ngoài phạm vi
  nhánh này).

- Màu chủ đạo và chữ trên logo: tạm "G3 · Cố vấn học vụ", xanh dương đậm. Kiên chốt.
- Có giữ ô chọn nhà cung cấp/model LLM trước mặt thầy không, hay chỉ hiện khi bật chế độ demo bằng biến môi trường.
- Mã trích dẫn hiện tại (`QD-Đ22`) có đủ dữ liệu để ghi "Điều 22 · tên văn bản · trang" không: cần xem kết quả
  thật của `get_provision` ở bước 6.
