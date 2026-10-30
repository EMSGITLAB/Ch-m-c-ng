# Thử bước đầu với một người — 28/10/2026

Không cần đủ 10–20 người để tiếp tục lập trình hoặc xem điểm so khớp giữa hai phiên. Trong mục **Kiểm chứng AI**, một người có ít nhất 3 mẫu đăng ký và mẫu hiệu chỉnh khác phiên đã xem được điểm cosine cùng người. Bộ thu mẫu thông thường vẫn yêu cầu 5 mẫu trở lên.

Dữ liệu thật hiện có: 10 mẫu đăng ký và 10 mẫu hiệu chỉnh của cùng một người, khác phiên chụp. Điểm cosine cùng hồ sơ giữa các phiên: thấp nhất **0,786443**, trung vị **0,858015**, cao nhất **0,938060**. Đây không phải phần trăm độ chính xác, chưa đo nhầm đồng nghiệp hoặc người lạ; chưa chọn ngưỡng vận hành.

M1 trong kế hoạch dùng 10–20 người cho kiểm chứng ban đầu; M6 tăng lên 100 người cùng các thử nghiệm người ngoài và giả mạo. Một người chụp nhiều ảnh không thay được các nhóm kiểm tra đó. T07/T09 vẫn chưa hoàn tất; việc xây các chức năng khác tiếp tục bình thường.

Xem `calibration-coverage.json` cho số liệu/digest bộ dữ liệu; không xuất tên, ảnh hoặc vector.

Đã kiểm tra UI thật **Quản trị → Kiểm chứng AI → Kiểm tra và đề xuất ngưỡng**: hiển thị 1 người, 10 mẫu đăng ký/10 mẫu hiệu chỉnh và bảng điểm 0,786 / 0,858 / 0,938. Cùng lúc vẫn báo chưa đủ bộ kiểm chứng nhóm và chưa bật ghi công.
