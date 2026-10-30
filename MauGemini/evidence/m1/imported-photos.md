# Bộ ảnh nhân viên do người dùng cung cấp — 28/10/2026

## Dữ liệu đã lưu thật

- Đọc manifest local; dùng đúng mã, tên và đơn vị trong manifest. Không suy đoán danh tính từ ảnh và không truy cập trường URL bên ngoài.
- Tạo **20 hồ sơ nhân viên**, giữ nguyên hồ sơ đã có. Tổng hiện tại **21 hồ sơ**.
- Lưu **20 ảnh gốc** trong bảng `imported_face_photos` của SQL Server local, chỉ quản trị đăng nhập được đọc ảnh.
- **15 ảnh đạt** bộ lọc chất lượng hiện tại: mỗi người có một bộ đăng ký thử hoàn tất gồm **1 vector 128 chiều**. Nguồn bộ mẫu là `imported-photo-v1`, phân biệt với camera hướng dẫn nhiều tư thế.
- **5 ảnh chưa đạt** vì vùng khuôn mặt nhỏ hơn 96 px. Vẫn lưu ảnh để xem lại; không tạo vector và không giả lập thêm mẫu. Danh sách hồ sơ hiển thị “Ảnh nhập chưa đạt”.
- Không tạo template vận hành, không thay ngưỡng/model và không bật ghi công. `lastScan` trong nguồn không được nhập thành sự kiện chấm công.
- Nhập lại cùng ảnh/hồ sơ không tạo bản sao; xung đột hồ sơ hoặc ảnh liên kết người khác sẽ rollback cả đợt. Không ghi đè hồ sơ có trước.
- Xóa dữ liệu mặt của một hồ sơ xóa cả ảnh nhập và vector liên quan trong cùng giao dịch. Bản sao lưu có vòng đời riêng; bảo vệ phục hồi dấu xóa vẫn thuộc T32.

## Cách thử trên webapp

1. Vào **Quản trị → Nhân viên → Dữ liệu mặt** của một hồ sơ.
2. Xem ảnh gốc và lý do Đạt/Chưa đạt.
3. Trong **Thử so khớp với bộ ảnh nhập**, chọn ảnh JPG/PNG/WebP. Ứng dụng xử lý trên máy local, liệt kê ba mẫu gần nhất trong bộ ảnh nhập đang hợp lệ.
4. Điểm hiển thị là cosine, không phải phần trăm chính xác. Ảnh trùng chính tệp đăng ký có ghi chú riêng. Luồng thử không ghi công.

## Bằng chứng và giới hạn

- `imported-photos-check.json`: đọc lại database thật, phân tích lại 15 ảnh và đối chiếu vector lưu; 15 lần truy hồi chính tệp đều về đúng hồ sơ. Đây là kiểm tra luồng dữ liệu, **không phải phép đo độ chính xác nhận lại người ở phiên khác**.
- 105 cặp khác người trong 15 mẫu hợp lệ; điểm cosine lớn nhất 0,344612. Chỉ mô tả bộ hiện tại, không dùng để tự chọn ngưỡng vận hành.
- Đã kiểm tra giao diện thật: 21 hồ sơ, ảnh nhập/mẫu 1 ảnh, tải ảnh thử và bảng thứ hạng. Chưa đo camera thật của 20 nhân viên.
- Kiểm thử: 174 backend đạt, 5 ca đồng thời chỉ chạy SQL Server được kiểm tra riêng; 112 test SQL Server native đạt; 5 test Node, frontend build và Ruff đạt. Các kiểm tra migration/backup/restore Unicode native cũng đạt.
- Ảnh, vector, danh tính và bản sao lưu không được chép vào thư mục bằng chứng/Git. Bảng tổng hợp chỉ chứa số đếm và chỉ số vô danh.
- T07/T09 giữ chưa hoàn tất: còn thiếu ảnh hiệu chỉnh/đánh giá độc lập và người ngoài danh sách. Sẽ so sánh số mẫu đăng ký 1/3/5 trên cùng bộ thử riêng khi có đủ dữ liệu; không bắt mọi nhân viên thực hiện toàn bộ quá trình phát triển.

## Công cụ

```powershell
.venv/Scripts/python.exe scripts/import_employee_photos.py "<thư mục nguồn>/manifest.json"
.venv/Scripts/python.exe scripts/import_employee_photos.py "<thư mục nguồn>/manifest.json" --apply
.venv/Scripts/python.exe scripts/check_imported_photos.py
```

Không dùng ảnh đăng ký làm ảnh kiểm thử độc lập; không nhân bản/biến đổi cùng một ảnh để tuyên bố đủ nhiều phiên chụp.
