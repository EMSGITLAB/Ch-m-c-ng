# Quy tắc triển khai

- Tuân thủ `KE_HOACH_TRIEN_KHAI.md`; cập nhật checklist, bằng chứng và nhật ký sau mỗi bước có kết quả.
- Toàn bộ ảnh, vector và nhận diện chạy local. Không Docker, cloud API, telemetry hoặc CDN trong luồng sử dụng.
- Không tự thay đổi model hoặc ngưỡng vận hành nếu chưa kiểm thử. Không đánh dấu kiểm thử thiết bị hoặc độ chính xác là đạt bằng dữ liệu giả.
- Không commit mật khẩu, token, dữ liệu cá nhân, ảnh, vector hoặc bản sao lưu.
- Giữ cấu hình và đường dẫn độc lập máy để chuyển từ laptop Windows lên VM.
- Chạy kiểm thử phù hợp: backend `.venv/Scripts/python.exe -m pytest backend/tests`; frontend `npm.cmd run build` trong `frontend`.
- Công việc do Codex thực hiện. Chỉ hỏi người dùng khi cần thông tin thực tế hoặc thao tác vật lý không thể tự làm.

