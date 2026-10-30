# T18 — Tự dò và bám vị trí mặt, không bấm chụp

Ngày 28/10/2026. Sửa theo phản hồi kiosk có nút chụp và không thấy bám mặt.

## Thay đổi

- Kiosk tự thử mở camera khi thiết bị đã ghép, còn quyền và model sẵn sàng. Nếu trình duyệt không cho tự mở, nút **Bật camera** là thao tác mở/cấp quyền một lần; không có nút chụp cho từng người. Dừng khi ẩn trang/rời kiosk/đổi thiết bị. Xử lý cả vòng setup/cleanup bổ sung của React StrictMode.
- Cứ mỗi nhịp điều khiển 500 ms, khi không có yêu cầu đang xử lý, gửi toàn ảnh tới preview local. Có tối đa một thao tác đang gửi; thời gian thực tế tùy mạng/CPU. Giữ timeout, backoff và kiểm tra quyền. Không phải tracker 30/60 FPS hoặc xác minh người thật/PAD.
- `/api/kiosk/recognition/preview` chỉ kiểm tra có mặt/chất lượng/vị trí, không trích danh tính, không lưu ảnh/vector/sự kiện. Được dùng khi chưa bật policy nhưng vẫn yêu cầu quyền kiosk, same-origin và header intent. Tạo phiên/nhận diện/ghi công tiếp tục kiểm tra policy riêng; không bật ghi công bằng kết quả tìm thấy mặt.
- Vị trí lấy từ detector trong toàn ảnh, chuẩn hóa 0..1, chuyển sang tọa độ gương đúng như video. Hiển thị khung chữ nhật bám theo mặt, nhãn **Đã thấy khuôn mặt**; không có oval cố định. Mất mặt/lỗi hoặc kết quả quá cũ thì bỏ khung; timeout khung 1,8 giây khi chưa có cập nhật mới.
- Tìm và sửa việc `recognition_api`/`recognition_sequence` dùng nhầm `check_frame` của thu mẫu. Kiosk nay dùng `check_scene`, chấp nhận mặt đạt chất lượng tại vị trí bất kỳ và tỷ lệ camera ngang/dọc; thu mẫu vẫn giữ oval 4:3. Không bỏ bộ lọc mặt nhỏ/mờ/tối/nhiều mặt hoặc thay ngưỡng nhận diện.
- Tên/biên nhận và câu **Hợp lệ** vẫn chỉ dùng sau xác nhận đã ghi công. Trong chế độ thử, thông báo rõ **chưa ghi công**, không đưa tên phỏng đoán hoặc phát âm xác nhận.

## Kiểm chứng

- **202 test backend đạt, 6 native-only skip**; các test native đã chạy trong **131 test SQL Server đạt** trên database riêng. Có hồi quy preview không cần policy vẫn tìm mặt ngoài giữa khung 16:9, đồng thời tạo phiên ghi công bị từ chối; preview không tạo frame/session/event.
- Kiểm tra riêng `check_scene`: mặt ở cạnh ảnh ngang/dọc được chấp nhận trong khi bộ kiểm tra oval thu mẫu tiếp tục từ chối; lỗi chất lượng vẫn có vị trí để hướng dẫn, dữ liệu box sai không vẽ.
- **22 test Node đạt**, gồm camera toàn cảnh, tọa độ gương và ảnh lỗi, dò mặt liên tiếp khi ghi công tắt mà không tạo UUID/commit/receipt; dừng lúc ảnh đang encode không được gửi ảnh muộn. Các kịch bản phục hồi/idempotency trước đó vẫn đạt. Build và Ruff đạt.
- **Camera laptop thật đã chạy tự động** sau khi người dùng đăng nhập: video 1280×720, không nút chụp, không oval, DOM có khung vị trí mặt và phản hồi **Đã tìm thấy khuôn mặt… Đang kiểm tra tự động, chưa ghi công**. Chỉ đọc trạng thái UI, không lưu ảnh camera vào bằng chứng.
- Hai lần quan sát camera thật có khung mặt; vị trí CSS thay đổi theo kết quả detector giữa hai lần. Không tuyên bố đã nghiệm thu chuyển động nhanh, mọi góc mặt hoặc độ chính xác danh tính chỉ từ quan sát này.
- Kiểm tra runtime vẫn 0 policy bật, 0 template vận hành, 0 phiên/khung hình/sự kiện công; model local sẵn sàng. Không dùng dò mặt này để tuyên bố nhận diện danh tính/PAD đạt. KT03 iPad/Android và T23 vẫn chờ thử thực tế theo phạm vi toàn hệ thống.

T07 đã được tách đúng phạm vi bộ tham chiếu khởi đầu: **15 người × 1 ảnh hợp lệ**, đáp ứng tối thiểu 10×1. Chi tiết `evidence/m1/initial-dataset-scope.md`; việc bổ sung ảnh thử độc lập/người ngoài thuộc T09/T10/T39.
