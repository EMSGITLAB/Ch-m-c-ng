# T31 — Kiểm chứng ngoại tuyến phần mềm, 29/10/2026

- `scripts/check_admin_sqlserver.py --offline` tạo database SQL Server tách biệt, chạy 184 ca API/nghiệp vụ; tất cả đạt trong 175,42 giây. Plugin `backend/tests/network_guard.py` được nạp trước ứng dụng, chặn DNS/TCP/UDP Python ngoài loopback, báo 0 lần thử kết nối ngoài. Không sửa database đang dùng.
- Bao gồm đăng nhập/phân quyền, ghép kiosk, thu mẫu, nhận diện/chuỗi ảnh, commit/idempotency, lịch/ca, khóa kỳ, xuất CSV/XLSX, xóa mẫu và khóa phục hồi. Các ca nhận diện giao thức dùng fixture kỹ thuật, không chứng minh độ chính xác AI.
- `scripts/check_offline_models.py` chạy riêng YuNet/SFace/PAD CPU thật từ model local, phát hiện mặt, tính vector 128 chiều và so khớp local trên fixture công khai có giấy phép. 0 lần thử kết nối Python ngoài; không xuất ảnh/vector. Không phải phép đo độ chính xác hay PAD.
- Đọc mã frontend/backend hiện tại: fetch về `/api` hoặc `/health`, tài nguyên JS/CSS nằm trong build, âm thanh `/audio/hop-le.wav`; Vite chỉ proxy loopback khi phát triển. Không có speech cloud/CDN/model tải động trong luồng dùng. URL giấy phép/tài liệu trong mã hoặc thư viện không đồng nghĩa có kết nối khi chạy.
- SQL dùng ODBC native trỏ localhost; Python socket guard không chặn mọi lời gọi mạng trong mã native hoặc tiến trình con. Chưa ngắt WAN thật, chưa ghi lưu lượng của trình duyệt thực; KT01 vẫn mở. Không đổi firewall hay mạng của người dùng, không suy diễn rằng đã có tường lửa toàn máy.

Kết quả chi tiết: `../m2/offline-sqlserver-tests.log`, `offline-models-check.json`. T31 tiếp tục cho đến khi kiểm chứng KT01 trên phiên vận hành thực.
