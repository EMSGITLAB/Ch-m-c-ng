# Điều chỉnh công, khóa/mở kỳ và bản chốt — 28/10/2026

## Chức năng đang có

Trong **Quản trị → Bảng công**, có ba mục:

1. **Xem trước:** lọc ngày/nhân viên, tính theo lịch và điều chỉnh còn hiệu lực; xem từng lượt và nguồn camera/bổ sung; xuất toàn bộ kết quả theo bộ lọc.
2. **Điều chỉnh công:** xem lượt gốc/lịch sử phân trang, bổ sung vào/ra có lý do, loại lượt gốc hoặc lượt bổ sung, thu hồi điều chỉnh. Không sửa/xóa sự kiện gốc. Giờ nhập được máy chủ chuyển từ múi giờ nghiệp vụ sang UTC; không lấy múi giờ tablet. Giờ DST không tồn tại hoặc mơ hồ bị từ chối.
3. **Chốt kỳ & bản lưu:** chọn tháng, xem trước cả kỳ, khóa/mở lại có lý do, xác nhận riêng nếu chốt kèm ngoại lệ, chọn đọc từng phiên bản. Bản chốt sử dụng tên hồ sơ/quy tắc đã lưu, không lấy tên mới từ danh sách hiện tại.

Audit điều chỉnh ghi dữ liệu trước/sau, ID quản trị, lý do và thời điểm. Mở lại/chốt lại có phiên bản và audit trạng thái trước/sau. Kỳ khóa chặn điều chỉnh và các thay đổi lịch/lượt có thể ảnh hưởng ca, kể cả cửa sổ ca qua tháng.

## Giao diện đã thử thật, dữ liệu giả tách biệt

Chạy `scripts/run_ui_sandbox.py`: tạo SQL Server database tạm có tên và dấu riêng, backend/proxy trên loopback riêng; chỉ có hai hồ sơ giả và một lượt vào lúc 08:00 ngày 31/12/2025. Không đưa dữ liệu nhân viên thật vào môi trường này.

Luồng đã thao tác bằng trình duyệt:

1. Bổ sung lượt ra 17:00 kèm lý do. Bảng công tính **480 phút** cho ca 08:00–17:00 nghỉ không công 12:00–13:00.
2. Chốt **v1**, tải CSV và XLSX từ đúng nút trên UI. Đọc lại hai file: cùng 480 phút/28.800 giây.
3. Thử thu hồi lượt bổ sung khi kỳ đang khóa: bị từ chối, thông báo yêu cầu mở lại kỳ.
4. Mở lại kỳ có lý do, thu hồi lượt bổ sung. Lượt vào gốc còn nguyên.
5. Thử chốt khi thiếu lượt mà chưa xác nhận ngoại lệ: bị từ chối. Xác nhận chốt kèm ngoại lệ rồi tạo **v2**.
6. v2 hiển thị **Chưa xác định/Thiếu dữ liệu**; ô giây/phút trong XLSX để trống. Đọc lại v1 vẫn **480 phút**.
7. Đọc database thử: một sự kiện gốc, điều chỉnh thu hồi còn lịch sử, hai snapshot cùng tồn tại. Dừng tiến trình và xóa đúng database thử theo tên/dấu bảo vệ; bản tải thử được chuyển về `.runtime/ui-check/downloads`, dọn các bản thử khỏi Downloads.

Bằng chứng vô danh: `time-controls-ui-check.json`, `ui-export-download-check.json`, `time-controls-live-state.json`. Không có ảnh/vector thật trong báo cáo này.

## Kiểm tra mã và giới hạn

- **182 test backend đạt**; 5 kiểm thử giao dịch đồng thời chạy riêng trên SQL Server, nằm trong **120 test SQL Server native đạt**.
- 5 test Node, frontend build và Ruff đạt. Phụ thuộc xuất XLSX dùng `openpyxl==3.1.5`, đã khóa phiên bản và cập nhật danh mục giấy phép MIT.
- Unit/native kiểm tra audit trước/sau, quyền/CSRF, UUID retry, đổi giờ DST, biên kỳ, ca đêm, snapshot giữ tên cũ, khóa/mở kỳ và export.
- Hệ thống thật hiện chưa có sự kiện chấm công/điều chỉnh/bản chốt do bộ thử tạo. Trạng thái thực tế lưu riêng trong `time-controls-live-state.json`.
- T25/T26/T27 chưa đánh dấu hoàn tất vì T23 và nghiệm thu toàn luồng camera → nhận diện → ghi công còn thiếu. Không dùng kết quả nghiệp vụ giả để tuyên bố đã đạt nhận diện/PAD hoặc kiểm thử tablet thật.
