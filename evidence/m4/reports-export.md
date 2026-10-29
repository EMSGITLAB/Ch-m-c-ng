# T27 — CSV/XLSX local, theo bản đang xem

## Đã xây và kiểm tra

- Nút **Xuất CSV / Xuất Excel (.xlsx)** ở bản xem trước và từng phiên bản bản chốt.
- Xuất toàn bộ các ca và lượt ngoại lệ trong bộ lọc; không giới hạn ở trang đang hiển thị. Báo cáo lớn vẫn dùng các giới hạn số nhân viên/lịch/lượt của bộ tính để tránh trả file một phần.
- Báo cáo xem trước ràng buộc với thời điểm tính và digest dữ liệu đang hiển thị. Sự kiện, điều chỉnh hoặc tên hồ sơ đổi sau khi xem sẽ yêu cầu tải lại trước khi xuất. Không âm thầm xuất số liệu khác màn hình. Bản xem trước quá 24 giờ phải tính lại.
- Bản chốt yêu cầu tháng và phiên bản cụ thể; xuất từ snapshot đã lưu, giữ tên và quy tắc cũ. File thể hiện bản hiện hành hoặc bản lưu đối chiếu.
- CSV UTF-8 BOM, có dòng thông tin và các loại dòng ca/lượt ngoại lệ; dữ liệu có nguy cơ được Excel hiểu thành công thức được thêm dấu nháy để xuất an toàn.
- XLSX gồm **Bảng công**, **Ngoại lệ**, **Thông tin**, **Lượt tính công**. Mã nhân viên lưu dạng text giữ số 0 đầu; tên/lý do luôn là text, không phải công thức. Thời gian có offset UTC; múi giờ nghiệp vụ được ghi trong thông tin báo cáo.
- Ca thiếu/mơ hồ giữ ô công trống, không điền 0 hoặc đủ ca. Phút/giây được tính từ cùng dữ liệu với UI; định dạng hiển thị không thay số liệu gốc. Lượt bổ sung được ghi rõ nguồn.
- Chỉ quản trị đăng nhập mới tải được. Không xuất ảnh/vector và không có phụ thuộc dịch vụ/cloud trong lúc sử dụng.

## Kết quả

`backend/tests/test_timesheet_exports.py` đã kiểm tra:

- CSV/XLSX khớp UI, xuất đủ dữ liệu ngoài trang 1, ô thiếu trống, Unicode.
- Mã `000123` còn nguyên dưới dạng text; tên bắt đầu `=` không trở thành công thức trong XLSX và được bảo vệ trong CSV.
- Nguồn thay đổi bị từ chối; snapshot giữ tên trước khi sửa hồ sơ.
- Ca đêm 31/12 → 01/01 có lượt bổ sung ngày kế tiếp: đúng ngày ca, **470 phút** trong cả CSV và XLSX bản chốt.
- Phân quyền, dữ liệu đầu vào, hạn báo cáo và giới hạn số lượt xuất đồng thời.

Trên trình duyệt/database giả tách biệt đã tải hai định dạng thật: bản v1 có **480 phút**, bản v2 thiếu lượt ra giữ ô giây/phút trống. Xem `ui-export-download-check.json` và `time-controls-ui-check.json`.

Toàn bộ kiểm tra mới nhất: **182 backend đạt, 5 native-only được chạy trong 120 SQL Server đạt; 5 Node, build và Ruff đạt**.

T27 giữ chưa hoàn tất theo phụ thuộc T26/T25/T23; còn nghiệm thu bộ quy tắc T28 khi nối luồng chấm công đầy đủ.
