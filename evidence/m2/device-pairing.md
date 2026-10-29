# Cấp và thu hồi kiosk — 28/10/2026

- Mã ghép 8 chữ số, dùng một lần, hết hạn 5 phút; chỉ quản trị được tạo/cấp lại/thu hồi.
- Cookie kiosk HttpOnly, SameSite Strict; thời hạn 30 ngày, xác minh token đã băm trên máy chủ.
- Cấp lại vô hiệu token cũ; thu hồi chặn truy cập; kiosk không được truy cập API quản trị. Có giới hạn thử mã sai và kiểm tra Origin.
- Test SQLite và SQL Server thử riêng đã đạt các trường hợp ghép một lần, hết hạn, thu hồi, cấp lại, phân quyền và giới hạn thử sai; xem `backend/tests/test_devices.py` và `admin-sqlserver-tests.log`.
- Giao diện thiết bị/ghép kiosk đã build và chạy local. Kiểm tra camera/cookie trên iPad và tablet Android thật còn thuộc KT02/KT03, chưa đánh dấu đạt.
