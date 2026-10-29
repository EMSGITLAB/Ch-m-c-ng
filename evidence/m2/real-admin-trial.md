# Thử quản trị thực tế ngày 28/10/2026

- Người dùng tự tạo tài khoản quản trị, tự đặt mật khẩu và thêm một hồ sơ nhân viên trên giao diện.
- Kiểm tra database chỉ đếm bản ghi: 1 admin, 1 nhân viên, 1 phiên và 0 mẫu khuôn mặt tại thời điểm kiểm tra.
- Không đọc/ghi mật khẩu, tên đăng nhập, tên nhân viên hoặc vector vào bằng chứng.
- Backend ghi nhận thao tác tạo và sửa hồ sơ trả HTTP 201/200.
- Bộ thử API chạy tách biệt trên SQL Server: `evidence/m2/admin-sqlserver-tests.log`, 8 ca đạt. Các database thử đã được xóa sau khi chạy.
- Chưa đăng ký mẫu khuôn mặt và chưa ghi sự kiện chấm công thực tế.
