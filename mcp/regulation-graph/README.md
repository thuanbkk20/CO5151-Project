# regulation-graph

RAG quy chế thứ hai của nhóm G3, dựng trên graph (văn bản, khoản, phiên bản, khái niệm học vụ), để so với bản BM25 của
`mcp/regulation-server` (của Đức, không sửa). Cùng hai tool, cùng contract; chọn bằng `REGULATION_ENGINE=bm25|graph`.

Lý do: quy chế có nhiều năm, bản sau sửa bản trước. Bản BM25 trả cả bản cũ lẫn bản mới (`applicability_resolved:
false`), câu hỏi không chứa cụm trong `TOPICS` thì trả rỗng, và không kéo được Phụ lục 1 (chuẩn ngoại ngữ) hay khoản
5.5 (đồ án) dù kho có.

## Văn bản

File gốc nằm trong `quy chế tham khảo/` (không commit). Repo chỉ commit chữ đã trích và sha256 của file gốc.

| Văn bản | Lấy chữ bằng | Vai trò |
|---|---|---|
| QĐ 2933/2021 Quy định học vụ và đào tạo bậc ĐH | Chữ OCR của Đức (`regulation-server/.../provisions.json`) | Lõi |
| QĐ 1260/2026 sửa 2933; QĐ 2749/2026 thay Phụ lục 1 | Lớp chữ PDF | Sửa đổi |
| QĐ 2931/2021 Quy định chung về học vụ; QĐ 1259/2026 sửa 2931 | docx; lớp chữ PDF | Nền (học lại, nghỉ học tạm thời...) |
| QĐ 2932 Hướng dẫn và chấm tốt nghiệp | PDF ảnh 12 trang, chép từ ảnh (`data/vision`, chưa đối chiếu) | Tốt nghiệp, luận văn |
| Kết luận Hội đồng học vụ HK222–HK261 | Lớp chữ PDF (bỏ HK232, HK241 là ảnh) | Thứ bậc thấp hơn quy định |
| Quy định học vụ, phiên bản hợp nhất | docx | **Không** dùng để trả lời; chỉ để kiểm việc chọn phiên bản |

## Thiết kế

**Graph** (`data/graph.json`, sinh bằng `regulation-graph-build`, không gọi LLM): 244 khoản (`Provision`: Điều,
Khoản, Phụ lục, chữ nguyên văn, trang, `applies_to`), cạnh `CONTAINS`, `AMENDS` / `REPLACES` / `REPEALS` (tìm bằng luật
trên câu "Sửa đổi / Thay thế / Bãi bỏ ..." rồi rà tay). `data/concepts.json` viết tay: 24 khái niệm học vụ có từ đồng
nghĩa ("ra trường", "LVTN"...), 77 cạnh `ABOUT` (khoản → khái niệm), 5 cạnh `REQUIRES` (tốt nghiệp → chuẩn ngoại
ngữ...).

**Truy xuất** (`search_regulations`, tham số `query, top_k, hops, context`):

1. Khớp khái niệm (không dấu) → khoản qua `ABOUT`; song song BM25 trên khoản; gộp bằng RRF. Ngoài phạm vi = không
   khái niệm nào và BM25 dưới ngưỡng.
2. Lọc phạm vi (song ngành, chương trình tiếng Anh... chỉ giữ khi câu hỏi hoặc `context` nói tới).
3. Chọn phiên bản: theo `AMENDS` / `REPLACES` tới bản mới nhất; bản bị thay chỉ ghi trong `superseded`.
4. Mở rộng `REQUIRES` một bước.

Kết quả giữ đúng hình dạng của bản BM25 (`results[].id`, `evidence`, `citation`), nên backend không phải sửa.

## Kết quả truy xuất (27/11, không gọi LLM)

`uv run co5151-eval retrieval --engine bm25|graph`, 36 lượt của bộ hội thoại, `top_k=3` như Advisor gửi:

| Engine | hit@3 | recall@3 | MRR | Rỗng |
|---|---|---|---|---|
| BM25 (`regulation-server`) | 0.417 | 0.361 | 0.269 | 19% |
| Graph (`regulation-graph`) | 1.00 | 0.921 | 0.838 | 0% |

Khi báo cáo cần nói: khái niệm và từ đồng nghĩa được viết khi đã thấy các câu hỏi test (số của graph lạc quan); khoản
mong đợi chưa đối chiếu PDF; đây chỉ là truy xuất, chất lượng câu trả lời đo ở ablation. `applies_to` theo khóa của
QĐ 1260/2749 mới ghi theo chữ trong khoản, chỗ không rõ để trống.

## Dữ liệu

| File | Nội dung |
|---|---|
| `data/documents.json` | Danh sách văn bản: số QĐ, ngày, loại, bậc, sha256 file gốc, cách lấy chữ |
| `data/text/<id>.json` | Chữ trích từ PDF có lớp chữ (theo trang) hoặc docx (theo đoạn), sinh bằng `regulation-graph-extract` |
| `data/vision/<id>.md` | Chữ của PDF ảnh, chép từ ảnh từng trang; chưa đối chiếu |
| `data/concepts.json` | Khái niệm, từ đồng nghĩa, cạnh `ABOUT` và `REQUIRES` |
| `data/graph.json` | Graph đã dựng |

File PDF/docx gốc không commit. Trích lại chữ (cần thư mục chứa file gốc):

```bash
uv run --extra extract --package co5151-regulation-graph regulation-graph-extract --sources "quy chế tham khảo"
```
