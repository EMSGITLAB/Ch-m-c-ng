# Hướng dẫn và phản hồi từng ảnh — 28/10/2026

- Phiên mới dùng `relative-pose-v1`: nhìn thẳng → trái của người chụp → phải của người chụp → nâng cằm → hạ cằm. Có thể lặp vòng thứ hai, tối đa 10 mẫu; tối thiểu 5 mẫu.
- Trước khi chụp: hiển thị số mẫu, hướng mặt, mô tả điều chỉnh và mũi tên trên hình xem trước dạng gương. Ảnh gửi lên máy chủ không bị lật.
- Sau mỗi lần chụp: hiện Đạt kiểm tra sơ bộ/Chưa đạt. Lỗi chất lượng hoặc sai hướng có lý do và hướng dẫn chụp lại; không tăng số mẫu. Ảnh trùng không được tính.
- Backend kiểm tra tỷ lệ vị trí mắt–mũi–miệng có dấu, so với mẫu nhìn thẳng đầu phiên. Đây là bộ lọc tư thế sơ bộ, chưa phải góc đầu đã hiệu chuẩn, phép đo độ chính xác nhận diện hoặc chống giả mạo.
- Lưu mã tư thế và phiên bản hướng dẫn cùng chỉ số chất lượng; không lưu ảnh gốc và không trả vector về trình duyệt.
- UPDATE bộ đếm yêu cầu số mẫu vẫn bằng số đã đọc trước khi kiểm tra ảnh, tránh chấp nhận ảnh dưới hướng dẫn khác khi có hai yêu cầu đồng thời.
- Migration thêm cột nullable; bộ cũ giữ nguyên, có nhãn chưa kiểm tra tư thế. Sau migration, dữ liệu thật vẫn có một bộ đăng ký hoàn tất, 10 mẫu; 0 template vận hành và 0 sự kiện ghi công.

## Kiểm chứng

- Ruff: đạt.
- Toàn bộ backend: **58 passed**, 1 cảnh báo deprecation từ thư viện TestClient.
- API quản trị/thiết bị/thu mẫu trên database SQL Server thử riêng đã migration: **20 passed**; xem `admin-sqlserver-tests.log` và `admin-sqlserver-check.json`.
- `npm.cmd run build`: đạt TypeScript và Vite.
- Model OpenCV thật trên fixture có giấy phép: phát hiện/căn chỉnh/vector, loại nhiều mặt và không có mặt đều đạt; `evidence/m1/quality-pipeline.json` có tỷ lệ landmark mới. Fixture không thay thế kiểm chứng camera người dùng.
- Đã migrate database ứng dụng, khởi động lại backend và kiểm tra UI thật: có chuỗi hướng dẫn mẫu 1 nhìn thẳng, bộ cũ giữ nhãn chưa kiểm tra tư thế.
- Cập nhật: camera laptop đã hoàn tất bộ hiệu chỉnh **10 mẫu**, mỗi hướng 2 mẫu. UI đã hiển thị từ chối ở mẫu hạ cằm khi chưa đạt, sau đó chấp nhận và lưu đủ bộ. Chưa kiểm chứng tự chụp ở thời điểm hoàn tất bộ này; xem `auto-capture.md` cho phần triển khai tiếp theo.

Các test giao thức dùng dữ liệu giả chỉ chứng minh luồng chấp nhận/từ chối và lưu dữ liệu. T07/T09/T14 và kiểm thử độ chính xác/PAD chưa hoàn tất.
