# Công cụ so khớp và hiệu chỉnh local — 28/10/2026

**Cập nhật:** theo điều chỉnh T07, quy tắc hiện tại là `mean-top3-available-per-person-v2`: hỗ trợ 1 ảnh tham chiếu/người, lấy trung bình tối đa 3 điểm đang có. Hiệu chỉnh vẫn cần probe độc lập/người ngoài; không bật policy. Chi tiết `initial-dataset-scope.md`. Những yêu cầu 3/5 ảnh đăng ký bên dưới mô tả bản cũ.

## Đã triển khai

- `backend/app/matching.py`: cosine trên vector chuẩn hóa; lấy trung bình 3 điểm cao nhất của mỗi người, rồi lấy 2 người khác nhau. Phiên bản quy tắc: `mean-top3-per-person-v1`.
- Từ chối gallery rỗng, chỉ một người, vector hỏng, sai kích thước/model; điểm bằng ngưỡng hoặc khoảng cách bằng giới hạn vẫn bị từ chối. Chưa nối quyết định này vào ghi công.
- `backend/app/calibration.py`: chỉ đọc bộ đăng ký và hiệu chỉnh đã hoàn tất của hồ sơ hoạt động, cùng model. Không đọc vector tập đánh giá cuối. Phát hiện khung ảnh trùng và phiên bị gắn lẫn người/mục đích.
- Công cụ ban đầu yêu cầu ít nhất 10 người đăng ký, mỗi người 5 mẫu đăng ký và 5 mẫu hiệu chỉnh khác phiên; tối thiểu 2 người ngoài bộ đăng ký với 5 mẫu/người. Hai người ngoài chỉ là mức khởi đầu M1, chưa đáp ứng nghiệm thu M6 (≥20 người ngoài, ≥300 phiên).
- Duyệt lưới điểm 0..1, khoảng cách 0..2, bước 0,01. Chọn cặp không nhận nhầm/người lạ trên tập hiệu chỉnh và nhận đúng ít nhất 98% mẫu đã đăng ký; ưu tiên số mẫu đúng cao hơn, sau đó ngưỡng điểm cao hơn, rồi khoảng cách lớn hơn. Nếu không có, báo chưa có ứng viên.
- Báo cáo gắn digest bộ dữ liệu/model/quy tắc; chỉ có số lượng tổng hợp và ngưỡng đề xuất. Không xuất danh tính, ảnh hoặc vector.
- Báo cáo luôn có `operational_enabled=false`; chưa lưu/bật cấu hình vận hành. Cần khóa cấu hình và kiểm chứng tập cuối độc lập ở bước kế tiếp.
- CLI: `.venv/Scripts/python.exe scripts/calibrate_local.py`, lưu local `.runtime/calibration/report.json`.
- API quản trị có kiểm tra phiên/CSRF/Origin, chỉ cho một lượt đánh giá đồng thời; UI **Quản trị → Kiểm chứng AI** hiển thị dữ liệu thiếu và kết quả.

## Kết quả thực tế

`calibration-coverage.json` sau lần chụp tiếp theo: 1 người, 10 mẫu đăng ký và 10 mẫu hiệu chỉnh hoàn tất; 0 mẫu người ngoài. Trạng thái **insufficient_data**, chưa có ngưỡng đề xuất. Các phiên đang mở không được tính.

## Kiểm thử

- Toàn bộ backend: **74 passed**, 1 cảnh báo deprecation TestClient.
- Quản trị/thiết bị/thu mẫu/hiệu chỉnh trên SQL Server thử riêng: **27 passed**; `evidence/m2/admin-sqlserver-tests.log` và `admin-sqlserver-check.json`.
- Ruff và TypeScript/Vite build: đạt.
- UI thật sau khi restart backend: **Quản trị → Kiểm chứng AI → Kiểm tra và đề xuất ngưỡng** trả đúng 1 người/10 mẫu đăng ký, 0 bộ hiệu chỉnh hoàn tất và ba lý do còn thiếu. Không có ngưỡng được chọn hoặc ghi công phát sinh.
- Kiểm tra lỗi SQL Server phát hiện `IS 1` không hợp lệ; đã chuyển lọc boolean sang so sánh `= 1`, CLI thật và test database native đều đạt.
- Test số học gồm hai ứng viên khác người, mẫu ngoại lệ không lấn át 3 mẫu nhất quán, bất biến thứ tự, ngưỡng bằng biên, sai model/vector, dữ liệu trùng, rò tập cuối, thiếu dữ liệu và người không phân biệt được. Dữ liệu giả chỉ kiểm tra thuật toán, **không chứng minh độ chính xác nhận diện người thật**.

Chưa hoàn tất T07/T09/T10/T11. Tập hiệu chỉnh nhỏ có thể quá khớp; chỉ số từng ảnh không thay thế phiên chấm công, kiểm thử người lạ, PAD, tải và thiết bị theo kế hoạch.
