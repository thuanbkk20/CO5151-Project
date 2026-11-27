# RAG quy chế bằng graph (bản thứ hai, để so với bản BM25)

Cập nhật: 2026-11-27. Nhánh `feat/regulation-graph` (tách từ `feat/foundry-models`). Task B1, B3, B4 trong
[remaining-work.md](../remaining-work.md).

## Mục tiêu

1. Thầy nhận xét: quy chế có nhiều năm, nhiều loại, bản sau sửa bản trước, chương trình này lẫn chương trình kia. RAG
   hiện tại (`mcp/regulation-server`, của Đức) tìm bằng BM25, có graph phiên bản nhưng trả **cả bản cũ lẫn bản mới**
   (`"applicability_resolved": False`, `handoff_retriever.py`), câu hỏi không chứa cụm trong `TOPICS` thì trả rỗng.
2. Dựng **một RAG thứ hai** dựa trên graph, chạy song song, cùng hai tool và cùng contract, để so trên cùng bộ câu
   hỏi (ablation trục truy xuất) và đổi qua lại trên app bằng một biến môi trường.
3. Lỗi Verifier hay gặp (27/11): bản nháp nói "quy chế không nêu ngưỡng TOEIC / đồ án" vì truy xuất không lấy được
   Phụ lục 1 và khoản 5.5 dù kho có. RAG graph phải kéo được các khoản đó qua quan hệ khái niệm.

Không làm lúc này (Kiên, 27/11): workflow GitHub tự nạp văn bản mới. Pipeline nạp chạy tay bằng một lệnh; sau này bọc
vào workflow được vì đầu vào/đầu ra đã là file.

## Văn bản

Nguồn: thư mục `quy chế tham khảo/` Kiên tải (không commit, nằm trong `.git/info/exclude`). Repo chỉ commit **chữ đã
trích** và sha256 của file gốc.

| Văn bản | Lấy chữ bằng | Vai trò |
|---|---|---|
| QĐ 2933/2021 Quy định học vụ và đào tạo bậc ĐH | PDF ảnh: dùng lại chữ OCR của Đức (`regulation-server/.../provisions.json`) | Lõi |
| QĐ 1260/2026 sửa 2933 | Lớp chữ PDF | Sửa đổi |
| QĐ 2749/2026 thay Phụ lục 1 (chuẩn ngoại ngữ) | Lớp chữ PDF | Sửa đổi |
| QĐ 2931/2021 Quy định chung về học vụ và đào tạo | docx | Nền (học lại, cải thiện điểm, nghỉ học tạm thời, kỷ luật...) |
| QĐ 1259/2026 sửa 2931 | Lớp chữ PDF | Sửa đổi |
| QĐ 2932 Hướng dẫn và chấm tốt nghiệp ĐH | PDF ảnh 12 trang: chép tay từ ảnh trang (Claude đọc ảnh), ghi `text_method` | Tốt nghiệp, luận văn |
| Kết luận Hội đồng học vụ HK222–HK261 | Lớp chữ PDF (bỏ HK232, HK241 là ảnh) | Quyết định theo học kỳ, thứ bậc thấp hơn quy định |
| Quy định học vụ — Phiên bản hợp nhất | docx | **Không** dùng để trả lời; đáp án kiểm việc chọn phiên bản |

Để sau (ảnh, ít câu hỏi cần): QĐ 2349 văn bằng (9 trang), TT 08/BGDĐT (22 trang). Không nạp: văn bản thạc sĩ, tiến sĩ,
xây dựng CTĐT (3538, 1862), giảng dạy (2929), lớp sĩ số nhỏ, qd104.

## Thiết kế

Package mới `mcp/regulation-graph` (`regulation_graph`), không sửa code của Đức.

**Graph** (`data/graph.json`, sinh bằng `regulation-graph-build`, có commit):

| Node | Trường chính |
|---|---|
| `Document` | số QĐ, ngày ban hành, cấp (bo / dhqg / truong), loại (quy_dinh / sua_doi / ket_luan_hdhv), bậc (dh), sha256 file gốc, `text_method` |
| `Provision` | Điều / Khoản / Phụ lục (phụ lục dài tách theo mục), chữ nguyên văn, trang, `applies_to` (bậc, chương trình, khóa từ–đến) |
| `Concept` | ~25 khái niệm học vụ, từ đồng nghĩa ("ra trường", "nhận bằng", "LVTN"...) |

| Cạnh | Nghĩa |
|---|---|
| `CONTAINS` | Điều → Khoản |
| `AMENDS` / `REPLACES` / `REPEALS` | bản sửa → bản bị sửa, kèm ngày hiệu lực và khoản làm căn cứ |
| `ABOUT` | Khoản → Khái niệm |
| `REQUIRES` | Khái niệm → Khái niệm (tốt nghiệp → chuẩn ngoại ngữ, luận văn → tín chỉ tích lũy...) |

Quan hệ sửa đổi: tìm bằng luật trên câu "Sửa đổi / Thay thế / Bãi bỏ khoản x Điều y" rồi rà tay; khái niệm và cạnh
`ABOUT` dựng tay trong `data/concepts.json` (không gọi LLM).

**Truy xuất** (`search_regulations`, cùng tham số `query, top_k, hops, context`):

1. Khớp khái niệm (từ đồng nghĩa, không dấu) → khoản qua `ABOUT`.
2. BM25 trên khoản (stopword chỉ bỏ hư từ; không bỏ `bao`, `toi`).
3. Gộp hai danh sách bằng RRF. Không có cổng chủ đề cứng: ngoài phạm vi = không khái niệm nào và BM25 dưới ngưỡng.
4. Lọc phạm vi: khoản song ngành, chương trình tiếng Anh... chỉ giữ khi câu hỏi hoặc `context` nói tới.
5. Chọn phiên bản: đi theo `AMENDS`/`REPLACES` tới bản mới nhất; bản bị thay chỉ ghi trong trường `superseded`
   (không chiếm chỗ trong top_k). `context.cohort` có thì xét `applies_to`; thiếu thì ghi
   `applicability_resolved=false` như bản cũ.
6. Mở rộng `REQUIRES` một bước: thêm khoản chính của khái niệm cần thiết (giới hạn số khoản).

Kết quả giữ đúng hình dạng bản cũ (`results[].id`, `evidence{provision_id, title, source_text}`, `citation{file_name,
pdf_pages}`) để `RegulationSearch` của backend và `ReadProvision` của Verifier dùng ngay, không sửa backend.

**Chọn RAG:** backend chỉ cần `REGULATION_MCP_URL` trỏ sang server mới (cổng 8104). Eval: biến `REGULATION_ENGINE`
(`bm25` mặc định / `graph`) trong `backend_agent.py`.

**Đo (B1, không LLM):** `co5151-eval retrieval --engine bm25|graph`: các lượt có khoản ứng viên trong
[test-conversations.md](test-conversations.md) (câu nối tiếp được viết lại thành câu đủ ngữ cảnh), in recall@3,
recall@8, MRR, tỉ lệ rỗng. Khoản ứng viên **chưa đối chiếu PDF** (A2), report ghi rõ.

## Kế hoạch commit

| # | Commit | Nội dung | Trạng thái |
|---|---|---|---|
| 1 | `docs: remaining work, use cases and test conversations` | file của Kiên | xong `9810bfc` |
| 2 | `docs(design): regulation graph plan` | file này | xong `35748c4` |
| 3 | `feat(eval): retrieval benchmark` | `retrieval_cases.json` (36 lượt) + lệnh `retrieval`. RAG cũ: hit@3 0.36, recall@3 0.29, MRR 0.22, rỗng 19%, ~4.2k ký tự/câu | xong `5aca27b` |
| 4 | `feat(regulation-graph): package and document registry` | package, `documents.json` (15 văn bản), trích chữ PDF/docx vào `data/text` | xong `34adcad` |
| 5 | `feat(regulation-graph): text of the scanned graduation rules` | chữ QĐ 2932 chép từ ảnh 12 trang (`data/vision`), hai trang biểu mẫu chỉ tóm mục | xong |
| 6 | `feat(regulation-graph): provisions and amendments` | tách Điều/Khoản, quan hệ sửa đổi, `graph.json` | |
| 7 | `feat(regulation-graph): concepts` | `concepts.json`, cạnh `ABOUT`/`REQUIRES` | |
| 8 | `feat(regulation-graph): hybrid retrieval with versions` | truy xuất 6 bước, service hai tool | |
| 9 | `feat(regulation-graph): MCP server` | server HTTP, `.env.example`, README | |
| 10 | `feat(eval): pick the regulation engine` | `REGULATION_ENGINE`, so hai RAG bằng B1 | |
| 11 | `docs: regulation graph results` | số đo, architecture, README | |

Sau 11: hỏi thử vài câu với Verifier (tốn LLM, báo trước), rồi deploy server mới lên VM.

## Chưa quyết

1. `applies_to` theo khóa của QĐ 1260/2749: cần điều khoản thi hành trong PDF; trước mắt ghi theo chữ trong khoản (vd.
   "áp dụng từ học kỳ 1 năm học 2025-2026"), chỗ nào không rõ để trống.
2. Kết luận HĐHV có giá trị như quy định không, hay chỉ là thông tin bổ sung (đang xếp thứ bậc thấp hơn).
3. Danh sách khái niệm: Kiên duyệt sau commit 7.
