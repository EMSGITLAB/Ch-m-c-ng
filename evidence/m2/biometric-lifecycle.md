# Vòng đời dữ liệu khuôn mặt — 28/10/2026

- Đã thêm màn hình **Dữ liệu mặt** để xem số mẫu/bộ theo model và xóa toàn bộ dữ liệu sinh trắc của một hồ sơ khi nhập đúng mã, lý do và phiên bản dữ liệu.
- Xóa mẫu, bộ thu thập và tăng `biometric_revision` trong cùng giao dịch với nhật ký. Giữ hồ sơ và lịch sử công. Chưa thực hiện xóa dữ liệu thật trong quá trình triển khai.
- Mọi ghi mẫu/hoàn tất/hủy và sửa trạng thái nhân viên dùng cùng thứ tự khóa: nhân viên trước, bộ mẫu sau. Yêu cầu xử lý ảnh đang chạy bị từ chối nếu người đó bị vô hiệu hoặc đã xóa mẫu trước khi lưu.
- Gallery được tạo mới theo hồ sơ hoạt động, model hiện tại và revision hiện tại; chưa có cache tồn tại lâu. Giao dịch ghi công ở M3 vẫn phải kiểm tra lại trạng thái/revision trước commit.
- Đã kiểm thử rollback khi không ghi được audit, giữ dữ liệu người khác/lịch sử công, từ chối mã xác nhận sai/phiên cũ, chụp lại ở revision mới, lọc model/revision cũ và vector hỏng.
- Migration thêm revision mặc định 0, giữ dữ liệu có sẵn; SQL Server upgrade/downgrade/backup/restore trên DB thử riêng đạt. `mssql_drop_default=True` xử lý default constraint khi downgrade.
- Bộ kiểm thử cuối phiên gồm 91 test backend và 44 test SQL Server (bao gồm cả tự chụp); Ruff và frontend build đạt.

T16 giữ chưa hoàn tất vì T14 còn hiệu chỉnh/kiểm tra trùng danh tính và kiểm thử model vận hành chưa xong. Bản sao lưu không bị xóa bởi API này. T32 còn phải thực hiện cơ chế đối chiếu dấu xóa bên ngoài bản backup khi khôi phục; chỉ revision trong DB không ngăn được việc phục hồi dữ liệu từ một bản sao quá cũ. KT24 chưa đánh dấu đạt.
