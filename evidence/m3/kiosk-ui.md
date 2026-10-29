# T18 — Giao diện kiosk và phục hồi yêu cầu

**Cập nhật mới nhất:** kiosk tự dò/bám vị trí mặt bằng camera thật, bỏ nút chụp từng người và bỏ ràng buộc vị trí oval 4:3 tại backend; dùng toàn cảnh, giọng **“Hợp lệ”** sau receipt ghi công. Bản hiện tại có 22 test Node đạt; chi tiết ở [kiosk-auto-tracking.md](kiosk-auto-tracking.md). [kiosk-full-scene.md](kiosk-full-scene.md) và phần mô tả oval/4:3/14 test bên dưới là bằng chứng các phiên triển khai trước.

## Đã triển khai

- `KioskCapture.tsx` quản lý camera, khung oval và trạng thái căn mặt, xử lý, chờ đối chiếu, đang ghi, kiểm tra lại, thành công, thử lại, mất mạng và hết quyền.
- Camera dùng cùng phép cắt giữa khung 4:3 như ảnh gửi lên server; không co méo ảnh. Nút **Chụp thử** vẫn có trong chế độ chưa bật ghi công, trả Đạt/Chưa đạt và hướng điều chỉnh.
- Khi kiosk đã ghép và máy chủ báo cấu hình/bộ mẫu hợp lệ, tự preview → tạo phiên → chụp chuỗi → đợi đối chiếu → commit → đọc biên nhận. Không cần bấm chụp từng khung hình.
- Chỉ lưu UUID yêu cầu trong `sessionStorage`, theo định danh kiosk. Ảnh chỉ nằm trong bộ nhớ của lần gửi, không lưu vào browser storage. UUID được lưu trước yêu cầu ghi đầu tiên.
- Mất phản hồi/tải lại trang phải GET trạng thái UUID cũ trước khi gửi ảnh hoặc ghi công tiếp. Nếu server đã ghi, dùng receipt đã lưu; không tạo yêu cầu mới thay cho yêu cầu chưa rõ kết quả.
- Chỉ hiện thành công khi receipt có mã yêu cầu khớp, event ID, danh tính, chiều và giờ hợp lệ. Phản hồi không hợp lệ hoặc chưa xác nhận chỉ hiện kiểm tra lại.
- Một thao tác đang gửi tại một thời điểm; backoff khi quá tải, timeout hữu hạn. Đổi/hết quyền dừng luồng đến khi người dùng ghép/kiểm tra và bật lại camera.
- Hiện biên nhận trong thời gian ngắn, rồi yêu cầu người trước rời khung trước khi bắt đầu người kế tiếp. Tắt camera/ẩn trang/rời màn hình sẽ dừng luồng và bỏ hiển thị danh tính.
- Đồng hồ hiển thị đồng bộ theo `server_time` và múi giờ nghiệp vụ, tăng thời gian bằng đồng hồ đơn điệu; lịch quét/backoff không phụ thuộc việc đổi giờ hệ thống của tablet.
- **Quản trị → Kiểm chứng AI → Đối chiếu tại kiosk**: danh sách phiên còn hạn, chọn hồ sơ máy chủ gợi ý, ghi lý do và xác nhận. Thao tác không đổi danh tính đã nhận diện và không báo đã ghi công thay kiosk.
- `/api/system/status` phản ánh policy/giao thức/mode/gallery phía server; không bật bằng cờ phía trình duyệt. Nhánh tự động chưa có PAD vẫn bị từ chối.

## Kiểm chứng

**14 test Node đạt**, gồm các phép cắt camera/ngày Việt Nam và 9 kịch bản điều khiển kiosk:

- Không có mặt/chưa bật: không tạo yêu cầu công.
- Chuỗi → chờ đối chiếu → biên nhận thực mới báo thành công.
- Mất phản hồi sau commit, tải lại và dừng policy: khôi phục đúng receipt, không commit lần hai.
- Mất phản hồi khung hình: đọc chỉ số server trước ảnh kế tiếp.
- Receipt sai UUID/không hợp lệ không được coi là thành công.
- Một thao tác đang gửi; dừng giữa chừng ngăn gửi ảnh muộn.
- Phiên hết hạn, quá tải/backoff và đổi quyền cần khởi động lại rõ ràng.
- Ẩn danh tính sau thông báo và chờ rời mặt trước phiên mới.

**190 test backend đạt**, 6 kiểm thử native-only được chạy trong **129 test SQL Server đạt**. Kiểm thử readiness chứng minh cờ policy không đủ để bật khi mode/PAD chưa được hỗ trợ. Build frontend và Ruff đạt.

Trên webapp đang chạy đã kiểm tra khung camera và trạng thái mặc định. Dùng iframe viewport để render chính app tại **768×1024**, **1024×768** và **390×1024**; không tràn ngang, tỷ lệ camera 4:3 đúng. Windows có scrollbar nên bề rộng nội dung đo ở viewport 1024 và 390 lần lượt là 1009 và 375 px. Số đo ở `kiosk-layout-check.json`.

## Giới hạn còn lại

- T18 là phần giao diện/điều khiển; **KT03 trên iPad/Android thật chưa chạy**. Kiểm tra viewport desktop không thay cho quyền camera, cookie, nền ứng dụng và hiệu năng thiết bị thật.
- Kịch bản điều khiển dùng transport giả; backend dùng engine/vector giả ở database thử. Chưa phải xác nhận độ chính xác/PAD hoặc nghiệm thu đầu-cuối camera thật T23.
- Cấu hình/gallery vận hành thật vẫn chưa bật. Các ảnh đăng ký/nhập để thử không tự trở thành template vận hành. Tiếp tục T09–T11/T14 và nghiệm thu thực tế trước khi ghi công thật.
