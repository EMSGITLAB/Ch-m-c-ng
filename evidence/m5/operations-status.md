# Trạng thái vận hành — T33

Quản trị có mục **Vận hành**, API `/api/admin/operations/status` yêu cầu phiên quản trị. Trạng thái chỉ chứa số liệu tổng hợp: DB/model, policy đang bật, bộ giám sát, dung lượng trống và bản sao lưu/tuổi bản sao lưu. Không trả đường dẫn archive, khóa, URL kết nối, tên nhân viên, ảnh/vector hoặc nonce điều khiển tiến trình.

Đã kiểm thử cảnh báo DB không sẵn sàng, model thiếu, ổ gần đầy, backup thiếu/quá hạn/chưa mã hóa/chưa kiểm chứng và lần backup lỗi. Lỗi SQL được trả thành 503 với thông báo chung, không lộ driver/SQL parameters. Camera/quyền âm thanh vẫn thông báo ở từng kiosk.

API truy cập trái phép bị từ chối; frontend đã build. Các ca fault injection là kiểm thử chức năng cảnh báo, không phải phép đo nhận diện hoặc thử làm đầy ổ thực tế. Log giám sát chỉ có mã sự kiện và mã thoát.

Bằng chứng: `backend/tests/test_operations.py`, `backend/tests/test_runtime_supervisor.py`; 247 backend đạt + 6 native-only skipped, 174 ca đạt trên SQL Server cô lập; build frontend/Ruff đạt. Các log đầy đủ nằm trong `.runtime` và `evidence/m2/admin-sqlserver-tests.log`.
