# Bộ phát hành native — T29

- `scripts/build_release.py` đóng gói theo danh sách cho phép: mã backend/migration, frontend đã build, model/giấy phép, cấu hình mẫu và hướng dẫn.
- Không mang theo `.env`, database, ảnh/vector nhân viên, log, evidence hoặc tài khoản. Cấu hình thử mặc định tắt trên máy mới; chuyển dữ liệu theo quy trình riêng.
- Bản `local-functional-20261028-v1` có 126 tệp trong manifest SHA256, bao gồm wheelhouse cho Windows x64/Python 3.12.
- `scripts/verify_release.py` đã kiểm tra toàn bộ checksum, tạo venv mới, cài bằng `pip --no-index`, nạp hai bộ model CPU và phục vụ frontend/audio từ backend. Python socket ra ngoài loopback bị chặn trong phép thử; đường dẫn bí mật/model/source không được phục vụ công khai.
- Kiểm tra này không di chuyển/sửa database thật và không phải thử trên VM/tablet. Hệ điều hành, Python 3.12, ODBC và SQL Server cần được chuẩn bị trên máy đích.
- `scripts/setup_release.ps1` tạo venv/cài offline; cấu hình SQL và bí mật phiên được tạo riêng trên máy đích. Nâng cấp database có dữ liệu dùng helper backup trước migration.
- Bằng chứng máy đọc: `native-release-check.json`. Log cài đặt/smoke trong `.runtime/release-verify-*.log`.

Kiểm thử hồi quy sau tích hợp: 229 backend đạt, 6 ca chỉ dành cho SQL Server được bỏ qua trên SQLite; 156 ca đạt trên SQL Server cô lập; 26 Node đạt; frontend build/Ruff đạt. Các số này là kiểm thử phần mềm, không phải tỷ lệ nhận diện theo nhóm.

Các bước M5 còn lại vẫn được theo dõi riêng: tự khởi động/phục hồi, kiểm tra ngoại tuyến đầy đủ, sao lưu/khôi phục vận hành, trạng thái/log và thử tải kỹ thuật.

## Bản cập nhật 29/10

`local-functional-20261029-v3`: 139 tệp có manifest, thêm `cryptography` và các helper chạy nền/backup/khởi động. Đã tạo venv mới, cài offline toàn bộ lock, nạp model và phục vụ frontend/audio; các đường dẫn riêng bị từ chối. Phép kiểm tra còn xác nhận các tệp helper cần để snapshot phục hồi có mặt. Không có `.env`, database, ảnh/vector nhân viên hoặc khóa trong bộ phát hành.

Hồi quy hiện tại: 247 backend đạt + 6 native-only skipped trên SQLite; 174 SQL Server; 26 Node; build/Ruff đạt. Việc phát hành cuối và kiểm tra nâng cấp/quay lui vẫn thuộc T36/T42, chưa kết luận từ phép smoke này.
