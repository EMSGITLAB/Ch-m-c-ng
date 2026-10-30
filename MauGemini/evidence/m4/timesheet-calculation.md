# T25 — Bộ tính và bảng công xem trước — 28/10/2026

## Đã triển khai

- Bộ tính `paired-shift-v1` ghép lượt vào/ra theo người, lịch ca và phiên bản quy tắc. Dữ liệu gốc được giữ nguyên; bản xem trước có thời điểm tính và digest đầu vào.
- Sự kiện vào thuộc cửa sổ `[bắt đầu - trước ca, kết thúc)`; sự kiện ra thuộc `(bắt đầu, kết thúc + sau ca]`. Hướng quét giúp phân biệt đúng ranh giới hai ca liền nhau. Nếu còn nhiều ca phù hợp, gắn mơ hồ và không tự chọn.
- Đọc thêm lịch hai ngày trước/sau kỳ để không bỏ sót ca đêm hoặc cửa sổ dài ở biên tháng/năm. Chỉ trả các ca thuộc khoảng ngày bắt đầu được yêu cầu; không đếm lại ca đêm sang ngày ra.
- Ghép lần lượt theo thời gian UTC. Thiếu vào/ra, vào lặp chưa ra, vào/ra cùng thời điểm hoặc ca mơ hồ không được tự tính đủ công. Vẫn hiển thị phần ghép được để xem xét.
- Ca chưa bắt đầu/đang diễn ra/đang chờ lượt được phân biệt với ca đã ghép đủ và ca cần xem lại. Không tự đánh dấu vắng mặt hoặc cấp đủ phút khi chưa có dữ liệu.
- Tính trong phạm vi ca; thời gian trước/sau ca báo riêng, chưa tự trả tăng ca. Dung sai chỉ phân loại muộn/sớm, không cộng bù phút thực.
- Nghỉ không công chỉ trừ phần giao với thời gian đã có mặt, tránh trừ hai lần khi đã quét ra/vào đúng giờ nghỉ. Nghỉ có công có thể bù khoảng ra/vào nằm trong giờ nghỉ nếu chuỗi lượt đầy đủ, không bù ngoài khoảng đã chứng minh bằng lượt đầu/cuối.
- Dùng microsecond để cộng/trừ, không làm tròn từng đoạn. API giữ phần giây; UI chỉ rút gọn cách hiển thị phút.
- API preview giới hạn 31 ngày, phân trang, tối đa 100.000 lượt nguồn/50.000 lịch và hai lượt tính đồng thời. Tổng hợp trên toàn bộ kỳ, không chỉ trang hiện tại. Danh sách ngoại lệ hiển thị có giới hạn và báo rõ nếu cần thu hẹp lọc.
- Đọc dữ liệu với khóa nhân viên dùng chung với các mutator để tránh trộn lịch/sự kiện đang sửa. Không đổi hồ sơ, sự kiện, audit hoặc thời điểm cập nhật; khóa được giải phóng khi kết thúc lượt đọc.
- UI **Quản trị → Bảng công**: lọc ngày/nhân viên, tổng hợp, bảng theo ca, chi tiết từng lượt/cách tính, danh sách lượt chưa có ca và ca mơ hồ. Có cả hồ sơ ngừng hoạt động khi tra lịch sử.

## Kiểm chứng

- Toàn bộ backend: **154 passed, 4 skipped**. Bốn ca cạnh tranh chỉ dành cho SQL Server đã được chạy riêng.
- Bộ kiểm thử SQL Server thử riêng: **91 passed**, gồm report API, đọc không thay đổi dữ liệu, lọc hồ sơ đã ngừng, phân trang/tổng toàn kỳ, quy tắc ca cũ và ngữ cảnh ca dài cách hai ngày.
- Node frontend: **5 passed** (crop camera và ngày địa phương tại biên ngày/năm); TypeScript/Vite build và Ruff đạt.
- Các ví dụ đã đạt: 08:00–17:00 nghỉ không công 12:00–13:00 = **480 phút**; vào 08:07 = **473 phút**; vào 08:07:30 = **472,5 phút**; ca 22:00–06:00 cuối năm = **480 phút**.
- Đã kiểm tra nghỉ có công/không công, quét ra/vào lúc nghỉ, không suy đủ công khi thiếu lượt, giờ ngoài ca báo riêng, dung sai không bù phút và xung đột giờ địa phương khi DST lặp lại.
- Lỗi DB trả 503 không có bảng công một phần, và trả lại đủ capacity xử lý cho lượt sau. Thiếu quyền, khoảng ngày sai và quá tải bị từ chối.
- `timesheet-preview-state.json` là kết quả đọc tổng hợp trên database thật: chưa có lịch/sự kiện, chưa chốt kỳ, không xuất hồ sơ hoặc lượt riêng lẻ. Dữ liệu kiểm thử thời gian chỉ nằm ở DB thử riêng.
- UI laptop thật đã tải báo cáo tháng hiện tại, đủ bộ lọc ngày/nhân viên, thẻ tổng hợp, phân trang và trạng thái chưa có lịch; đã kiểm tra bố cục bằng ảnh màn hình. Không thêm lịch hoặc sự kiện giả vào database thật để làm đẹp màn hình.

## Còn lại

T25 giữ chưa hoàn tất vì còn phụ thuộc T23 — luồng nhận diện/kiosk đến sự kiện thật chưa nghiệm thu. KT14 còn kiểm tra sai giờ tablet trên thiết bị; KT15/KT16/KT17 mới có bằng chứng math/API, chưa đánh dấu nghiệm thu toàn hệ thống.

T26 tiếp tục điều chỉnh có lý do và snapshot kỳ công. Kiểm tra/khóa kỳ phải phối hợp cùng khóa nhân viên trước mọi thay đổi lịch hoặc sự kiện, gồm ảnh hưởng cửa sổ ca lân cận. T27 còn xuất báo cáo và T28 còn kiểm thử toàn bộ sau điều chỉnh/khóa kỳ. Không xem bản preview là kỳ công đã chốt.
