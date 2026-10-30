# Giữ kết quả thu mẫu khi phiên hết hạn — 28/10/2026

Kiểm tra database thật phát hiện một phiên tự chụp đã có **5 mẫu auto** nhưng còn trạng thái open và đã hết thời hạn nhận ảnh. Mẫu vẫn còn trong database; chưa bị mất hoặc tự đưa vào hiệu chỉnh.

- Hết hạn vẫn chặn mọi ảnh mới, kể cả tự chụp.
- Khi đã đủ ít nhất 5 mẫu đạt, quản trị được hoàn tất bộ đã chụp sau thời hạn. Vẫn kiểm tra hồ sơ hoạt động, revision, trạng thái bộ mẫu và quyền quản trị/CSRF.
- UI lịch sử có nút **Hoàn tất bộ 5 mẫu** cho bộ đủ mẫu chưa hoàn tất/hủy. Không bắt chụp lại vì thời gian dành cho xem hướng dẫn hoặc kiểm thử ứng dụng.
- Đã kiểm thử từ chối ảnh sau hết hạn, hoàn tất giữ đúng 5 mẫu và không tạo thêm vector. Bao phủ cả SQLite và SQL Server trong bộ kiểm thử cuối phiên.
- Chưa tự bấm hoàn tất hoặc xóa bộ thật của người dùng trong quá trình kiểm tra này.
