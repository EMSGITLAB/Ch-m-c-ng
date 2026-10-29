# Cấu hình nghiệp vụ ban đầu

Nguồn: `config/business.json`. Mọi giá trị đều có thể thay đổi khi có quy định thực tế.

- Múi giờ Việt Nam; cooldown 60 giây cùng người/cùng chiều.
- Kiosk mặc định Vào ca; sẽ có cấu hình Ra ca riêng, không tự đảo trạng thái mỗi lần quét.
- Không lưu ảnh quét và ảnh đăng ký theo mặc định. Vector sinh trắc sẽ chỉ lưu ở local khi xây chức năng đăng ký.
- Chưa đặt thời hạn xóa sự kiện chấm công vì chưa có quy định thực tế. Chưa bật tác vụ xóa.
- Ca 08:00–17:00 nghỉ 12:00–13:00 chỉ là cấu hình mẫu cho kiểm thử. `approved_for_real_timesheets=false`; không sử dụng để kết luận công thực tế.
- Cấu hình ứng dụng tách biệt máy; laptop là máy chủ tạm, có thể chuyển lên VM.

Không cần thủ tục duyệt. Khi đến phần bảng công, Codex sẽ hỏi quy tắc ca thật nếu người dùng chưa cung cấp.
