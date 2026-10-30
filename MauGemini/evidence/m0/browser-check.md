# Kiểm tra bản laptop ngày 28/10/2026

- `http://localhost:5173` trả HTTP 200; giao diện tiếng Việt hiển thị và kết nối được backend.
- `/health/live` trả HTTP 200; `/api/system/status` vẫn báo `attendance_enabled=false`.
- Sau khi người dùng cấp quyền, trình duyệt hiển thị “Camera đang hoạt động. Bước nhận diện sẽ được bổ sung tiếp theo.” và phần video trực tiếp.
- Luồng này chỉ xem camera tại trình duyệt; chưa chụp/gửi ảnh lên backend hoặc lưu ảnh.
- Backend và frontend chạy loopback. Chưa mở firewall cho tablet.
- Theo điều chỉnh của người dùng, đã dừng Caddy, bỏ Caddy khỏi script khởi động bản laptop. HTTPS chuyển sang giai đoạn máy chủ ảo.
- Chưa thử iPad/Android: KT02 và KT03 chưa đạt.

T04 được điều chỉnh thành chạy webapp và camera laptop trong M0. Yêu cầu HTTPS/camera tablet vẫn giữ ở phần triển khai máy chủ và KT02, không đánh dấu đã kiểm tra.
