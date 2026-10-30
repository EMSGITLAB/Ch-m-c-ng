# Luồng chức năng một người — 28/10/2026

Phạm vi mới do người dùng yêu cầu: hoàn thiện chức năng với một người, chuyển đo nhóm sang thử sau.

## Kết quả thực tế

- Một mẫu tham chiếu của hồ sơ được chỉ định; 11 ảnh camera khác lần chụp, không nhân bản ảnh. Cosine thấp nhất 0,699044; ngưỡng tạm 0,505943 sau đối chiếu các mẫu khác hiện có. Đây không phải ngưỡng đã nghiệm thu cho một nhóm.
- Đã sao lưu database, kiểm tra checksum rồi áp dụng migration `20261028_functional_trial`.
- Chế độ riêng `functional_trial`, PAD vẫn `false`. Cấu hình máy chủ chọn đúng policy; template được ghim theo hash, model, hồ sơ và revision. Xóa mẫu, đổi mẫu/revision, vô hiệu người hoặc tắt cấu hình sẽ chặn ghi mới.
- Kiosk tự dò toàn cảnh, thu chuỗi ba ảnh ổn định, tự commit không cần quản trị đối chiếu. Oval chỉ dùng thu mẫu.
- Người dùng đã thử trực tiếp và xác nhận: **“Đúng tên, có đọc Hợp lệ”**.
- Kiểm tra database sau thử: 1 sự kiện Vào, 2 biên nhận đã dùng cùng phạm vi; lượt lặp không nhân đôi sự kiện. Không gán kết quả người thật cho dữ liệu giả.
- Sự kiện thật đã xuất hiện trong báo cáo và xuất CSV/XLSX local. Hiện chưa phân ca cho ngày thử nên hiển thị đúng ở “Lượt chưa gắn ca”, không tự suy ra đủ ngày công.

## Kiểm thử phần mềm

- Backend toàn bộ sau tích hợp: **229 passed, 6 native-only skipped**; SQL Server riêng: **156 passed**. Tập thử một người có 12 ca, gồm Vào/Ra tới báo cáo và kiểm tra phạm vi tại commit.
- Luồng Vào/Ra → báo cáo → CSV/XLSX, cùng request gửi lại, cooldown, người không khớp, thu hồi và phạm vi commit đều có kiểm thử tự động. Kiểm thử dùng engine giả được ghi rõ, không thay thế thử camera thật ở trên.
- 26 Node tests, frontend build và Ruff đạt. Log tại `.runtime`; bằng chứng SQL Server tại `evidence/m2/admin-sqlserver-check.json`.
- `single-person-trial-activation.json`, `single-person-live-flow.json` và `recognition-runtime-state.json` chỉ chứa số liệu tổng hợp, không ảnh/vector/danh tính.

## Thực hiện sau

Đo nhận đúng/nhận nhầm theo nhóm, người ngoài, PAD, tablet và tải 100 người. Các phép đo này không chặn hoàn thiện chức năng một người. Giữ riêng chúng trong mục 18 của kế hoạch.
