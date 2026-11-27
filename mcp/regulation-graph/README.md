# regulation-graph

RAG quy chế thứ hai của nhóm G3, dựng trên graph (văn bản, khoản, phiên bản, khái niệm học vụ), để so với bản BM25 của
`mcp/regulation-server`. Cùng hai tool và cùng contract. Thiết kế và kế hoạch:
[docs/design/regulation-graph.md](../../docs/design/regulation-graph.md).

## Dữ liệu

| File | Nội dung |
|---|---|
| `data/documents.json` | Danh sách văn bản: số QĐ, ngày, loại, bậc, sha256 file gốc, cách lấy chữ |
| `data/text/<id>.json` | Chữ trích từ PDF có lớp chữ (theo trang) hoặc docx (theo đoạn), sinh bằng `regulation-graph-extract` |
| `data/vision/<id>.md` | Chữ của PDF ảnh, chép từ ảnh từng trang; chưa đối chiếu |

File PDF/docx gốc không commit. Trích lại chữ (cần thư mục chứa file gốc):

```bash
uv run --extra extract --package co5151-regulation-graph regulation-graph-extract --sources "quy chế tham khảo"
```
