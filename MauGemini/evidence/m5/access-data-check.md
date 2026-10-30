# T35 — Kiểm thử truy cập và dữ liệu, 29/10/2026

Đạt trong phạm vi ứng dụng local hiện tại. Đây là kiểm thử hợp đồng và các tình huống lỗi có chủ đích; không phải kết luận kiểm toán bảo mật toàn hệ thống hay độ chính xác AI.

| Yêu cầu | Bằng chứng đã chạy |
| --- | --- |
| KT10: phiên, replay, binding kiosk/nonce/thời hạn | `test_recognition_sequence.py`, `test_functional_trial.py`: sai thứ tự/ảnh lặp/đổi mặt/đổi kiosk/hết hạn bị từ chối; thu hồi mẫu vô hiệu ngay |
| KT21: phân quyền | `test_admin.py`, `test_devices.py`, `test_recovery_key_api.py`: không đăng nhập/kiosk không được quản trị hoặc xuất khóa; mutations bắt buộc CSRF, Origin/intent đúng |
| KT22: tài khoản/phiên | `test_admin.py`: băm mật khẩu, setup một lần/local, cookie, giới hạn đăng nhập sai, logout/hết hạn vô hiệu phiên |
| KT23: upload | `test_capture_api.py`, `test_photo_import.py`, `test_collections.py`: giới hạn dung lượng/định dạng/kích thước ảnh, hủy/giải phóng slot, từ chối dữ liệu không hợp lệ |
| KT31: xóa và phục hồi | `test_biometrics.py`, `test_recovery_privacy.py`: purge nguyên tử, bảo toàn lịch sử công/người khác, sổ xóa mã hóa tăng đơn điệu, USB không có thì không báo xóa thành công; khôi phục không hồi sinh mẫu |
| Khóa khôi phục | `test_recovery_key.py`, `test_recovery_key_api.py`: mật khẩu không bị trả ra, sai mật khẩu/tamper bị từ chối, giới hạn tệp/KDF cố định, tệp bảo vệ được kiểm tra trước khi báo đã bảo quản |
| Không lộ dữ liệu qua public/log | `test_frontend_serving.py`, `test_access_logging.py`, `test_operations.py`: đường dẫn riêng bị từ chối, loại query trong log, lỗi SQL/trạng thái không trả URL/khóa/vector |

Kết quả mới nhất: full backend **261 passed, 6 skipped** (6 ca cần SQL native); suite database SQL Server cô lập **184 passed**, bao gồm các ca native, 0 lần thử kết nối Python ra ngoài. Xem `../m2/offline-sqlserver-tests.log`. Ruff đạt. Không sửa database đang dùng để tạo dữ liệu kiểm thử. Thử tablet/reboot/ngắt WAN thực tế vẫn ở checklist riêng.
