# Chấm Công Local AI (Tablet & Kiosk Edition)

Ứng dụng web chấm công và nhận diện khuôn mặt nội bộ chuyên dụng cho Tablet (iPad / Android Tablet) và Kiosk lễ tân / cửa ra vào. Toàn bộ quy trình xử lý dữ liệu sinh trắc học, nhận diện và lưu trữ bảng công hoạt động 100% cục bộ (Local / Offline), đảm bảo quyền riêng tư và tốc độ phản hồi tức thì.

---

## Điểm Nổi Bật Về Giao Diện & Trải Nghiệm (UI/UX)

1. **Tối ưu hóa chuyên sâu cho Tablet & iPad (Landscape & Portrait):**
   - **Kiosk Viewfinder HUD**: Khung ngắm camera sinh trắc học với 4 góc định vị phát sáng, tia quét laser động và viền nhận diện khuôn mặt tức thời.
   - **Chạm chuyển ca 1-chạm (Vào ca ↔ Ra ca)**: Nhân viên hoặc quản lý chạm trực tiếp nút chuyển đổi trên tablet mà không cần cấu hình phức tạp.
   - **Chế độ Toàn màn hình (Fullscreen)**: Nút bật/tắt toàn màn hình trên thanh điều hướng giúp ẩn thanh trình duyệt Safari / Chrome khi đặt máy trên đế bàn hoặc gắn tường.
   - **Nút "Thử nhận diện ngay (1-chạm)"**: Cho phép chạy mô phỏng quy trình chấm công với bất kỳ nhân sự nào để kiểm tra luồng, âm thanh và bảng công ngay cả khi chưa cấp quyền webcam.
   - **Đổi Camera trước/sau**: Dễ dàng đổi giữa camera selfie và camera sau của máy tính bảng.
   - **Phản hồi âm thanh & rung (Haptic feedback)**: Phát âm thanh chuông thành công kết hợp giọng đọc AI chào tên nhân viên bằng tiếng Việt.

2. **Bảng điều khiển Quản trị (Admin Dashboard) hiện đại:**
   - **📊 Tổng quan (Overview)**: Thẻ số liệu KPI thời gian thực (Tổng nhân sự, Đang làm việc, Lượt điểm danh hôm nay, Trạng thái Kiosk) và dòng sự kiện điểm danh trực tiếp.
   - **👥 Quản lý nhân viên**: Tìm kiếm, lọc theo phòng ban, thêm/sửa nhân sự, thu thập bộ mẫu khuôn mặt đa góc độ và tải ảnh chân dung.
   - **⏱️ Ca làm việc & Phân ca**: Cấu hình ca hành chính, ca sáng, ca tối, giờ nghỉ và phân ca hàng loạt cho nhân viên.
   - **📋 Bảng công & Điểm danh**: Xem trước bảng công theo khoảng ngày, tính toán giờ làm, đi muộn, về sớm; chức năng điều chỉnh công có lưu vết lý do; chốt kỳ công và xuất file báo cáo Excel / CSV.
   - **📱 Quản lý thiết bị Kiosk**: Tạo thiết bị, sinh mã ghép 8 chữ số và quản lý quyền của từng máy tính bảng.
   - **🎯 Kiểm chứng AI & Chống ảnh giả (PAD)**: Phân tích độ tương đồng cosine, đề xuất ngưỡng nhận diện và thử nghiệm chống tấn công ảnh in / màn hình.
   - **⚙️ Giám sát vận hành**: Kiểm tra dung lượng ổ đĩa, tình trạng sao lưu mã hóa và xuất khóa khôi phục an toàn.

---

## Hướng Dẫn Khởi Chạy

```bash
# Cài đặt thư viện
npm install

# Khởi chạy máy chủ phát triển (Port 3000)
npm run dev

# Kiểm tra bản đóng gói sản phẩm
npm run build
```

---

## Tài Khoản Đăng Nhập Quản Trị

- **Tên đăng nhập:** `admin`
- **Mật khẩu:** Bất kỳ mật khẩu nào (mặc định: `admin123`)
