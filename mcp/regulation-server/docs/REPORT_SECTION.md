# Nội dung báo cáo phần 1 — Bùi Tiến Đức

## Mục tiêu và phạm vi

Phần việc xây dựng nền dữ liệu và dịch vụ tra cứu quy chế học vụ HCMUT phục vụ Advisor Agent và Verifier Agent. Phạm vi nghiệp vụ hướng tới hệ chính quy tập trung; kho nguồn có thể chứa nội dung của nhiều chương trình, nên chưa được phép coi toàn bộ đoạn trích là áp dụng cho đối tượng này.

## Thu thập và chuẩn hóa

Kho gồm5 nguồn với193 đơn vị trang/block, trong đó64 đơn vị trích xuất native và129 đơn vị OCR. Mỗi đơn vị lưu SHA-256 nhận dạng nguồn, vị trí trang/block, phương pháp trích xuất và trạng thái kiểm duyệt. Trang trắng đã kiểm tra vẫn được giữ trong kiểm kê. Văn bản OCR gốc được bảo toàn; chưa xác nhận độ chính xác toàn bộ nội dung. Snapshot trong gói cho phép chạy lại phần truy xuất mà không chạy OCR lại.

## Knowledge Graph và truy xuất

Graph phiên bản gồm73 nút và116 cạnh:97 CONTAINS,10 AMENDS,6 REPLACES và3 REPEALS. Các quan hệ phiên bản là ứng viên cần đối chiếu phạm vi áp dụng. Bộ truy xuất tích hợp bổ sung10 mục điều khoản/bảng ngoại ngữ và118 đơn vị sổ tay/FAQ có nhãn bổ trợ. Tìm kiếm dùng lexical BM25, chuẩn hóa dấu, topic gate heuristic và mở rộng graph hữu hạn. Không sử dụng embedding hoặc LLM để sinh câu trả lời trong module này.

Các quan hệ phiên bản được tìm theo hai chiều trong khi giữ nguyên chiều ngữ nghĩa trong output. REFERENCES theo chiều khai báo. Giới hạn tối đa3 bước và24 bằng chứng giúp tránh vòng lặp và mở rộng không giới hạn. Kết quả giữ nguyên văn, vị trí nguồn, đường đi graph và cảnh báo. Không hợp nhất tự động các văn bản thành quy chế có hiệu lực.

## Regulation MCP

Dịch vụ cung cấp search_regulations và get_provision qua local stdio. Input schema đóng, kiểm tra kiểu chặt chẽ, dùng envelope lỗi chung của nhóm. Tool chỉ đọc. Dữ liệu nháp bị chặn mặc định; bật draft ở cấu hình server, không cho caller truyền quyền truy cập nháp trong tham số tool. Context được ghi nhận để bàn giao cho Agent nhưng chưa dùng để phân giải phạm vi áp dụng.

## Kiểm thử và kết quả

15 kiểm thử thành phần đã đạt trên môi trường kiểm tra Python3.12/MCP2.3, bao gồm quan hệ sửa đổi hai chiều, thay thế nhiều bước, bãi bỏ, citation, context, schema, lỗi input và chặn draft. Kiểm tra subprocess MCP thực tế đã đạt initialize, list_tools, gọi hai tool, truyền lỗi và chặn mặc định. Các kiểm thử này dùng dữ liệu phát triển; không phải benchmark độc lập chứng minh độ chính xác tư vấn. Chưa chạy với Agent thật của nhóm hoặc xác nhận môi trường Windows nhận bàn giao.

## Hạn chế và hướng hoàn thiện

OCR còn nhiễu và từ dính; ranh giới trang một số đoạn chưa tinh chỉnh. Bảng thủ công, các quan hệ và nội dung đều chưa được xác minh toàn diện. Chưa giải quyết hiệu lực theo khóa/chương trình/học kỳ, chưa phủ hết dẫn chiếu và chưa đánh giá held-out. Vì vậy hệ thống luôn trả applicability_resolved=false và eligibility_decision=null. Kết quả bàn giao là prototype có thể tích hợp thử nghiệm, chưa phải dịch vụ tư vấn chính thức.
