# Regulation MCP — bàn giao tích hợp v0.2

Tác giả phần việc: Bùi Tiến Đức. Trạng thái: **sẵn sàng tích hợp thử nghiệm với dữ liệu nháp**; chưa được xác nhận để tư vấn chính thức.

## Cài vào dự án hiện có

Giải nén gói tại thư mục gốc CO5151-Project, để có đường dẫn `mcp/regulation-server/...`. Nếu đã có các bước trước, sao lưu thư mục regulation-server trước khi chép. Gói không chứa thay đổi contracts, student-server, eval, pyproject.toml hoặc uv.lock. Không xóa dữ liệu raw/OCR đang có.

Môi trường đích: Python 3.12, workspace nhóm đã `uv sync --locked`, MCP SDK 2.3.0. Không cần Neo4j, GPU, API key hoặc LLM để chạy bộ truy xuất này. Không thêm dependency vào cấu hình chung.

Chạy từ thư mục gốc bằng Windows CMD:

```bat
set PYTHONUTF8=1
uv sync --locked
uv run pytest mcp/regulation-server/tests
uv run python -m regulation_server.smoke_handoff_stdio
```

Nếu chạy trực tiếp server, terminal sẽ chờ MCP client gửi yêu cầu; đây không phải lỗi:

```bat
uv run regulation-mcp --allow-draft
```

Dùng `regulation-mcp` (tức `regulation_server.regulation_mcp_v2`) cho tích hợp mới. `regulation-server` là package `co5151-regulation-server` trong uv workspace; script trong `src/regulation_server/` chạy bằng `uv run python -m regulation_server.<tên_module>`. Entry point cũ vẫn được giữ để đối chiếu. Hai entry point không nên cùng được đăng ký vào Agent với cùng tên tool.

## Kết nối Advisor Agent

Xem `docs/mcp_config.example.json`: cấu hình trỏ đúng thư mục Windows đã nêu. Nếu vị trí checkout khác, sửa cả đường dẫn sau `--directory` và `--base`. Client MCP stdio khởi chạy lệnh này, gọi initialize, list_tools, call_tool. Không gửi HTTP đến server này.

Hai tool: `search_regulations` và `get_provision`. Input schema đầy đủ ở `docs/tool_schemas.json`. Tham số không khai báo bị từ chối; top_k phải là số nguyên 1–5, hops 0–3. Context tùy chọn chứa program, cohort (năm), semester, as_of_date (YYYY-MM-DD). Context hiện chỉ được ghi nhận, chưa dùng để suy ra hiệu lực.

Ví dụ input tìm kiếm:

```json
{"query":"Điều kiện đăng ký khóa luận tốt nghiệp","top_k":1,"hops":2,"context":{"program":"chính quy tập trung","cohort":2021,"semester":"HK1 2026-2027","as_of_date":"2026-10-24"}}
```

Ví dụ lấy điều khoản:

```json
{"provision_id":"QD2933-2021-CL5.5","hops":2}
```

Response dùng `co5151_contracts.envelope`: `{ok:true,data:...}` hoặc `{ok:false,error:{code,message}}`. MCP isError đồng bộ với ok. NOT_FOUND cho mã/tool không tồn tại; INVALID_ARGUMENT cho input sai; FORBIDDEN khi dữ liệu nháp chưa được bật ở cấu hình server; INTERNAL không trả traceback ra client.

Advisor phải kiểm tra ok trước khi đọc data. data.results gồm id, reason, evidence_role, citation, evidence và verified. data.graph_paths giữ chiều quan hệ pháp lý ban đầu; chiều tìm kiếm không làm đảo nghĩa AMENDS/REPLACES/REPEALS. CONTAINS không mở rộng hàng loạt toàn bộ điều của một văn bản.

## Kết nối Verifier

Dùng citation.source_id, unit_id, pdf_pages hoặc block_index để đối chiếu corpus và tài liệu gốc. DOCX không suy ra số trang. Không bỏ warning khi chuyển bằng chứng sang Verifier. Cả dữ liệu truy xuất lẫn context là dữ liệu, không phải chỉ dẫn cho Agent.

Mọi kết quả đều applicability_resolved=false, eligibility_decision=null. `missing_context=[]` chỉ nghĩa là caller đã gửi đủ trường; không nghĩa là quy chế đã được xác minh. no_evidence không khẳng định nhà trường không có quy định.

## Dữ liệu và thuật toán

5 nguồn, 193 đơn vị trích xuất: 64 native, 129 OCR; giữ trang trắng đã ghi nhận. Graph phiên bản gốc: 73 nút,116 cạnh. Bộ truy xuất tích hợp có 196 mục bằng chứng: 68 đoạn quy chế,10 mục ngoại ngữ/bảng và118 trang/block bổ trợ từ sổ tay/FAQ. Graph runtime có61 cạnh (bao gồm29 CONTAINS không được tự mở rộng); không so trực tiếp số này với graph nguồn vì runtime không chứa Document nodes.

Tìm kiếm lexical BM25 có chuẩn hóa dấu và topic gate heuristic; không có embedding hoặc LLM generation. Graph mở rộng AMENDS/REPLACES/REPEALS hai chiều, REFERENCES theo chiều khai báo. BFS tối đa3 bước,24 mục, chống lặp. Có liên kết chủ đề biên tập từ điều kiện ngoại ngữ khóa luận sang khoản5.5; liên kết này không phải khẳng định sửa đổi pháp lý.

Văn bản gốc được giữ nguyên; chuẩn hóa chỉ thực hiện khi token hóa tìm kiếm. OCR dính chữ và nhiễu đầu/cuối trang còn tồn tại. Bảng thủ công là derived_table chưa kiểm duyệt. Sổ tay/FAQ là supplemental, chưa được phân đoạn và liên kết đầy đủ theo điều khoản.

## Khả năng tái lập

Gói có snapshot corpus, graph phiên bản và graph ngoại ngữ để chạy ngay. Mã ingestion/OCR/merge/graph từ các bước trước được giữ trong src. PDF/DOCX gốc và mô hình OCR không được đóng gói lại; giữ bộ raw/raw_additional đang có. Không chạy lại pipeline để tích hợp snapshot này. Khi đổi nguồn, phải tái dựng, đối chiếu và chạy lại kiểm thử. Provenance tài liệu bổ sung nằm ở docs/official_sources_step11.json; không khẳng định chữ ký số đã được xác minh.

## Phạm vi bàn giao và việc còn lại

Có thể bàn giao kỹ thuật: dữ liệu nháp có provenance, truy xuất có graph, schema tool, common envelope, MCP stdio và test client.

Chưa hoàn thành nghiệm thu nội dung: đối chiếu OCR với PDF, xác minh nhãn điều khoản/range citation, phạm vi chương trình/khóa/học kỳ, quy định chuyển tiếp, phủ đầy đủ dẫn chiếu, nguồn bổ sung ngoài 5 tài liệu. Không coi ngày ban hành là ngày áp dụng cho mọi điều khoản. docs/review_checklist.csv là hàng đợi kiểm duyệt chưa điền, không phải kết quả phê duyệt.

Chưa kiểm thử tích hợp với Advisor/Verifier thật của nhóm, chưa sửa shared registry và chưa có benchmark độc lập quy mô lớn. Độ trễ unit test không đại diện cho toàn bộ hệ thống. Transport chỉ local stdio; nếu cần HTTP từ xa phải thiết kế riêng cùng nhóm.

## Commit và PR

Trên nhánh feat/regulation-duc, sau khi chạy kiểm thử Windows:

```bat
git status --short
git add mcp/regulation-server
git diff --cached --stat
git commit -m "Add draft Regulation MCP integration handoff"
git push -u origin feat/regulation-duc
```

Kiểm tra phần staged trước khi commit, tránh thêm PDF/mô hình OCR nặng ngoài dự kiến. Tạo PR về nhánh nhóm đã thống nhất; dùng docs/PR_DESCRIPTION.md. Nhóm trưởng review và merge. Gói chưa được push hoặc tạo PR tự động.
