# T07 — Bộ tham chiếu khởi đầu, từ một ảnh mỗi người

Điều chỉnh theo yêu cầu người dùng ngày 28/10/2026: dùng tối thiểu **10 người × 1 ảnh đạt** để hoàn thành bước chuẩn bị dữ liệu ban đầu và tiếp tục xây dựng. Tiêu chí hiệu chỉnh, người lạ, giả mạo và đánh giá cuối của toàn dự án vẫn giữ; chuyển trách nhiệm dữ liệu độc lập sang T09/T10/T39, không tuyên bố đã nghiệm thu chất lượng nhận diện.

`scripts/check_initial_dataset.py` chỉ đọc SQL Server thật; kiểm tra ảnh, SHA256, liên kết hồ sơ/sample/collection/model/revision, trạng thái hồ sơ, chất lượng đã lưu, số chiều/độ hữu hạn/chuẩn hóa vector. Báo cáo chỉ xuất số tổng hợp ở `initial-dataset-readiness.json`.

- Hiện còn 19 ảnh nhập; **15 ảnh/15 người** đáp ứng toàn bộ điều kiện; 0 liên kết/vector lỗi trong nhóm kiểm tra. Đủ mức tối thiểu, không cần xóa bớt còn 10 hay thu thêm để qua T07.
- Nhóm ảnh nhập có **0 người với bộ hiệu chỉnh hoàn tất** và **0 người với bộ đánh giá cuối hoàn tất**. Không có cặp cùng người giữa ảnh đăng ký và ảnh chụp độc lập để đo chất lượng cho nhóm này.
- Một ảnh/người đủ tạo vector, lưu, xếp hạng và thử tích hợp. Muốn đo nhận đúng cần ảnh/phiên khác của chính những người đó; muốn đo nhận lạ cần người không có trong gallery. Bản cắt/lật/tăng sáng của ảnh đăng ký không thay thế ảnh chụp độc lập.
- Quy tắc so khớp mới `mean-top3-available-per-person-v2` nhận từ một mẫu/người: lấy trung bình tối đa 3 điểm cao nhất hiện có, không nhân bản vector để đủ số lượng. Tên phiên bản đổi để policy dùng quy tắc cũ không tự được chấp nhận. Không đổi model hoặc bật ngưỡng thật.
- Bộ hiệu chỉnh vẫn yêu cầu ảnh độc lập và độ phủ người ngoài theo kiểm tra trong T09. Kết quả tính với dữ liệu giả chỉ kiểm tra thuật toán, không phải độ chính xác người thật.

[Hướng dẫn chính thức OpenCV](https://docs.opencv.org/4.x/d0/dd4/tutorial_dnn_face.html) minh họa trích đặc trưng từ từng ảnh khuôn mặt và so khớp giữa hai ảnh. Việc chọn 10 người × 1 ảnh làm bộ khởi đầu là quyết định triển khai của dự án, không phải số mẫu được tài liệu này bảo đảm đủ để vận hành.
