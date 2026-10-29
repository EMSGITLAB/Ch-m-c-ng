# T09 — Phần mềm hiệu chỉnh và phép thử ảnh camera mới

Ngày 28/10/2026. **Đã triển khai mã và thử dữ liệu thật; chưa nghiệm thu ngưỡng vận hành cho toàn nhóm.** T09 không phụ thuộc model PAD/T11.

## Thay đổi

- Bổ sung API quản trị `GET /api/admin/recognition/calibration/coverage`: số ảnh đăng ký, ảnh/phiên hiệu chỉnh, số khung còn thiếu theo từng hồ sơ; phân trang tối đa 100. Chỉ tính mẫu hoàn tất, người hoạt động, model/dimensions/revision hiện hành; không truy vấn tập đánh giá cuối. Metadata có tên/mã chỉ hiển thị cho quản trị, không xuất vào bằng chứng tổng hợp.
- Màn hình **Kiểm chứng AI** tách ba nội dung: **Nhận diện & ngưỡng — T09**, **Chống giả mạo — T11**, **Đối chiếu tại kiosk**. T09 hiển thị hồ sơ thiếu mẫu và mở ngay thu mẫu với mục đích **hiệu chỉnh**, không yêu cầu đăng ký lại ảnh tham chiếu.
- Hiệu chỉnh vẫn chạy so sánh giới hạn 1/3/5 ảnh trên dữ liệu hiện có ngay cả khi chưa đủ độ phủ để chọn ngưỡng. Giữ nguyên danh sách người và ảnh probe; giới hạn số tham chiếu hiện có, không loại người chỉ có một ảnh hoặc nhân bản vector. Chọn tham chiếu bằng thứ tự fingerprint cố định, không chọn theo điểm của probe.
- Báo số ảnh thử/số người thật sự có probe, số ảnh xếp đúng người ở hạng đầu, phân bố cosine và margin. Đây là thống kê xếp hạng trên dữ liệu hiện có, không phải nhận diện được xác nhận hoặc tỷ lệ toàn nhóm. `candidate` vẫn rỗng khi thiếu dữ liệu; không bật policy.
- Thêm script `test_fresh_calibration_sample.py --employee-code ... --since ...` để đọc một mẫu camera mới sau thời điểm yêu cầu thử, kể cả bộ hiệu chỉnh đang mở chưa đủ 5 mẫu. So riêng với **bộ đăng ký hoàn tất**, không trộn mẫu hiệu chỉnh vào gallery. Từ chối dùng tệp tham chiếu làm probe, sai model/revision/chất lượng hoặc mẫu cũ hơn mốc thử.

## Dữ liệu và thử nghiệm thật

Trước phép thử mới, bộ hoàn tất có **16 người/25 ảnh đăng ký, 10 ảnh hiệu chỉnh của 1 người và 0 người ngoài**. Với giới hạn 1/3/5 ảnh, cả 10 probe hiện có đều xếp đúng người ở hạng đầu, nhưng chỉ thuộc một người. Trong cấu hình 3/5, 15 người vẫn chỉ có một ảnh tham chiếu; không gọi đây là phép đo 3/5 ảnh đầy đủ cho cả nhóm. Chi tiết `t09-reference-experiments.json`.

Theo yêu cầu người dùng, đã lấy một ảnh camera mới của hồ sơ được chỉ định. Người dùng tự mở phiên/cho phép camera vì kết nối điều khiển trình duyệt đang lỗi, rồi xác nhận có mẫu mới. Mẫu lưu lúc **15:58:46 UTC / 22:58:46 giờ Việt Nam**, sau mốc yêu cầu thử **15:51:19 UTC**. Bộ ảnh hiệu chỉnh mới vẫn đang mở; mẫu được so riêng, không âm thầm tính thành bộ hoàn tất hoặc dữ liệu hiệu chỉnh toàn nhóm.

| Giới hạn tham chiếu/người | Điểm hồ sơ kỳ vọng | Điểm ứng viên thứ hai | Margin | Đúng hồ sơ ở hạng đầu |
| --- | --- | --- | --- | --- |
| 1 | 0,707823 | 0,183249 | 0,524574 | Có |
| 3 | 0,668957 | 0,183249 | 0,485707 | Có |
| 5 | 0,707180 | 0,183249 | 0,523930 | Có |
| 10 | 0,712702 | 0,183249 | 0,529452 | Có |

Gallery giữ **16 người** trong cả bốn phép so sánh. Không suy ra điểm 0,708 là 70,8% chính xác. Đây là một probe mới của một người, chưa chứng minh cả nhóm/người lạ/PAD. Mã hồ sơ chỉ nằm trong báo cáo riêng `.runtime/calibration/fresh-probe.json`; bằng chứng `t09-fresh-camera-probe.json` đã bỏ mã và danh tính.

## Kiểm tra

- **215 test backend đạt**, 6 native-only skip; **144 test SQL Server đạt** trên DB riêng. Thêm kiểm tra so sánh cap khi chưa đủ bộ thử, giữ người có một ảnh/không nhân bản, không bịa số liệu khi thiếu probe, lặp lại theo thứ tự, coverage loại tập cuối/sai model/revision/hồ sơ dừng/bộ chưa hoàn tất, quyền và phân trang. API T09 vẫn chạy khi PAD vắng.
- **26 test Node và build frontend đạt**, Ruff đạt. Không tuyên bố tự kiểm tra browser UI do công cụ hiện báo `browser.user is unavailable`; thao tác thu camera do người dùng thực hiện và dữ liệu mới đã kiểm tra từ SQL Server.
- Kiểm tra script với mốc tương lai 2099 trả `waiting_for_new_camera_sample`, không tái sử dụng mẫu cũ. Script/báo cáo không tạo template, policy, phiên ghi công hoặc sự kiện. Mẫu mới do người dùng chủ động thu trong ứng dụng chỉ lưu vector theo luồng thu mẫu hiện có.

## Chưa đủ để nghiệm thu ngưỡng

- 15 người đã có ảnh đăng ký nhưng chưa có bộ hiệu chỉnh hoàn tất ở phiên khác; chưa có mẫu người ngoài bộ đăng ký.
- Cần dữ liệu đó để chọn/kiểm chứng ngưỡng và margin cho nhóm. Một ảnh/người đủ làm tham chiếu và thử tích hợp; không cần chờ dữ liệu này để lập trình các chức năng độc lập.
- Tiến độ tổng vẫn **13/42**, **5/32 ca nghiệm thu**; T09 giữ chưa hoàn tất phần kiểm chứng ngưỡng, không đồng nghĩa chưa triển khai mã.
