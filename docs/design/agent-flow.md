# Luồng agent trên UI (agent flow)

Cập nhật: 2026-11-15. Theo dõi tiến độ: [../ui-and-eval-console.md](../ui-and-eval-console.md).

## Mục tiêu

Gửi một câu hỏi xong thì panel bên phải màn hình chat hiện từng node đã chạy, theo thứ tự: node nhận gì, trả gì,
mất bao lâu, tốn bao nhiêu token. Gồm cả dữ liệu MCP Regulation và Student Record trả về. Dùng để demo.

## Thiết kế

- **Span** (giống span của OpenTelemetry/Langfuse, để phẳng, không lồng): `node`, `name`, `input`, `output`,
  `start_ms`, `duration_ms`, token, `error`.

  | node | name | input | output |
  |---|---|---|---|
  | `planner` | `rules` / `rules+llm` | câu hỏi, đã thu thập gì, đăng nhập chưa | action, quyết bởi (rule/llm/fallback) |
  | `student_record` | tên tool | tool, args (token ghi `(ẩn)`) | `ToolResult` MCP trả về |
  | `regulation` | `search_regulations` | query, top_k, hops | `ToolResult` MCP trả về |
  | `writer` | `draft` / `rewrite` | câu hỏi, student facts, id quy chế, (bản nháp cũ + lỗi Verifier) | câu trả lời, viết bởi LLM nào / template |
  | `verifier` | `round N` | cấu hình kiểm, bản nháp, facts, id quy chế | status, issues |

- **Ghi**: use case tạo một `SpanRecorder` cho mỗi câu trả lời và truyền xuống như `emit`
  (`application/tracing.py`). Không đụng adapter.
- **An toàn**: không ghi system prompt, token; giá trị được cắt độ dài (`clip`) và thay canary bằng `[đã ẩn]`
  trước khi lưu.
- **Lưu**: bảng riêng `trace_spans`, lưu cùng transaction với trace (`TraceRepository.save(trace, spans)`).
  `create_all` tự thêm bảng vào DB cũ; bảng `traces` mà lịch sử và eval đọc vẫn nhỏ.
- **Đọc**: API riêng `GET /traces/{trace_id}/spans`, chỉ chủ hội thoại xem được. Không stream qua SSE, nên quyết
  định "không gửi nháp ra trước khi Verifier duyệt" (`application/events.py`) vẫn giữ: nháp bị loại chỉ thấy sau
  khi đã có câu trả lời cuối.
- **Frontend**: nhận event `answer` xong thì gọi API spans, hiển thị ở sidebar phải của Chainlit
  (`cl.ElementSidebar`) bằng một custom element (JSX) dạng chuỗi node, mỗi node mở ra xem input/output.

## Kế hoạch commit

| # | Commit | Nội dung | Trạng thái |
|---|---|---|---|
| 1 | `feat(backend): span recorder for the nodes of an answer` | `Span` (domain), `SpanRecorder` + `clip` + test | xong `ca015ea` |
| 2 | `feat(backend): store spans with their trace` | port `TraceRepository`, bảng `trace_spans`, memory/SQL + test | xong `64638fc` |
| 3 | `feat(backend): planner, tools, writer and verifier record spans` | Advisor, tools, `AskQuestion`, `Conversations.spans` + test | xong `74de7aa` |
| 4 | `feat(backend): GET /traces/{id}/spans` | route, schema + test API | xong `bd3fbf5` |
| 5 | `feat(web): client reads the spans of an answer` | `BackendClient.spans` + test | xong `7f7d187` |
| 6 | `feat(web): agent flow in the right sidebar` | custom element JSX, `present.py` chuyển spans → props, mở sidebar sau mỗi câu trả lời + test | xong `b6c9f00` |
| 7 | `docs: agent flow` | README backend/frontend, architecture.md | xong |

Sau commit 6: chạy thử 1 câu bằng key thật (báo trước/sau số lần gọi LLM và token).

## Chưa quyết

- Ai được thấy panel: tạm bật/tắt bằng `AGENT_FLOW_PANEL` (mặc định bật); theo role thì chưa làm.
- Nút "Luồng agent" chỉ có trên câu trả lời của phiên hiện tại; mở lại hội thoại cũ thì chưa có nút.
