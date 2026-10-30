# OnTime — nhận diện thương hiệu

Người dùng duyệt tên OnTime và logo phương án 02 ngày 30/10/2026. Bản phác thảo được lưu tại ontime-approved-concepts.png; triển khai lại thành vector từ hình học, không cắt ảnh bảng so sánh làm logo.

- Biểu tượng: bốn góc khung quét bo tròn, dấu xác nhận ở giữa.
- Màu biểu tượng: cobalt #2563EB, navy #0F172A; dấu xác nhận chuyển trắng trên nền tối.
- Tên hiển thị: OnTime. Mô tả: Chấm công khuôn mặt.
- Không đổi bảng màu nghiệp vụ của giao diện Gemini đã duyệt.
- Tệp sử dụng: frontend/public/brand/ontime-mark-dark.svg ở header; bản sáng ontime-mark.svg; logo ngang ontime-logo-light.svg và ontime-logo-dark.svg.
- Favicon SVG/PNG 32, Apple touch icon 180, icon 192/512 và manifest.webmanifest dùng cùng biểu tượng. Manifest chỉ cung cấp thông tin/biểu tượng mở trang, không thêm service worker hoặc chế độ ghi công offline.
- Xuất lại bằng `.venv/Scripts/python.exe scripts/build_ontime_brand.py`. Pillow chỉ dùng lúc phát triển. Các SVG không tải font hoặc tài nguyên ngoài; logo ngang dùng font hệ thống, header dùng font sẵn của ứng dụng.
- Không đổi tên database, cookie, biến môi trường hoặc khóa dữ liệu chỉ vì thay tên hiển thị.
