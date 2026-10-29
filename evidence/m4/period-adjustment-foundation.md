# T26 — Nền tảng điều chỉnh và khóa kỳ

Trạng thái: **backend, UI và kiểm thử điều chỉnh/khóa kỳ đã có**; T26 vẫn chờ nghiệm thu theo phụ thuộc T25/T23. Kết quả UI và xuất báo cáo mới ở `time-controls.md`, `time-controls-ui-check.json` và `reports-export.md`.

## Đã triển khai

- Điều chỉnh bổ sung lượt vào/ra hoặc loại lượt gốc/lượt bổ sung. Không sửa/xóa `AttendanceEvent` gốc; bộ tính áp dụng lớp điều chỉnh còn hiệu lực.
- Lý do 5–500 ký tự, người quản trị/thời gian, audit có dữ liệu trước/sau; thu hồi giữ lịch sử. UUID yêu cầu và digest ngăn tạo trùng khi thử lại, từ chối nội dung khác cùng UUID.
- Chỉ nhận thời gian có múi giờ, không nhận tương lai; thời gian điều chỉnh được chuẩn hóa UTC.
- Khóa kỳ tháng đã kết thúc, đợi hết cửa sổ ca cuối. Kỳ có ngoại lệ cần xác nhận rõ `allow_unresolved`; ca thiếu giữ `worked_seconds=null`.
- Mỗi lần khóa tạo snapshot bất biến mới, giữ hồ sơ/quy tắc ca/kết quả tại lúc chốt. Mở lại có lý do, không xóa bản chốt trước; phiên bản kỳ ngăn thao tác từ trạng thái cũ.
- `calendar_gate` điều phối ghi công, sửa công, phân/hủy ca và khóa/mở kỳ. Cửa sổ bảo vệ theo nhân viên bao gồm ca qua tháng; thay đổi có thể ảnh hưởng kỳ khóa bị chặn. Ca ngày kế tiếp không giao nhau vẫn phân được.
- API quản trị cho lịch sử điều chỉnh, lượt gốc, trạng thái kỳ, snapshot phân trang/lọc người; phân quyền/CSRF giống phần quản trị hiện có.
- Migration bảo vệ rollback khi đã có lịch sử; SQL Server native đã thử upgrade dữ liệu cũ, rollback guard và backup/restore Unicode.

## Kiểm chứng

- `backend/tests/test_periods_adjustments.py`: bổ sung/loại/thu hồi, nguyên trạng dữ liệu gốc, audit, retry/conflict, quyền, chốt có ngoại lệ, bảo vệ ca đêm/biên tháng, tên hồ sơ trong snapshot, mở lại/chốt phiên bản 2.
- Kiểm thử đồng thời chốt kỳ và bổ sung lượt dùng hai giao dịch SQL Server: hoặc điều chỉnh đã vào bản chốt, hoặc bị từ chối vì kỳ đã khóa. Không trả bản chốt thiếu một điều chỉnh đã được chấp nhận trước đó.
- Tổng toàn backend mới nhất: 182 đạt, 5 native-only được chạy trong bộ 120 SQL Server đạt. Kết quả ở `.runtime/backend-check.log` và `evidence/m2/admin-sqlserver-tests.log`.
- Database thật đã lên migration mới; chưa tạo điều chỉnh/kỳ chốt hoặc sự kiện chấm công thử vào dữ liệu nhân viên thật. Dữ liệu nghiệp vụ thử chỉ ở database tách biệt đã dọn.

## Còn làm

- Màn hình điều chỉnh/khóa kỳ, bản lưu và xuất CSV/XLSX đã kiểm tra trên database nghiệp vụ giả tách biệt. Ca thiếu giữ trống công, bản chốt cũ vẫn giữ giá trị trước khi sửa.
- Hồi quy trực tiếp commit vào kỳ khóa đã đạt; receipt đã ghi trước đó vẫn truy hồi được. T28 còn nghiệm thu đầu-cuối sau khi nối kiosk T18/T19 và hoàn tất T23/T25.
