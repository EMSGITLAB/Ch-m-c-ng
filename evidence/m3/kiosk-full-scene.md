# T18 — Toàn cảnh chấm công và giọng “Hợp lệ”

Ngày: 28/10/2026. Điều chỉnh theo yêu cầu người dùng; tổng tiến độ vẫn **12/42 đầu việc, 5/32 kiểm thử nghiệm thu**.

- Kiosk không render `CameraFaceFrame`, oval hoặc hình đầu/vai mẫu. Tỷ lệ khung lấy từ metadata camera và cập nhật khi video đổi kích thước; `object-fit: contain` không cắt mất hai bên hoặc đầu/cuối hình. Xem trước vẫn dạng gương, ảnh cho engine giữ hướng camera gốc.
- `fullFramePhoto` đọc toàn bộ source camera, giữ tỷ lệ, không phóng lớn ảnh nhỏ; chỉ thu nhỏ cạnh dài tối đa 1600 px. Cả chuỗi tự động và chụp thử kiosk dùng hàm này. `FaceCollectionPanel` vẫn dùng `cameraPhoto` cắt giữa 4:3 cùng oval/hướng dẫn tư thế thu mẫu, không thay đổi.
- Engine local tiếp tục tìm mặt trong ảnh đầy đủ và áp dụng bộ lọc chất lượng. Một người trong tầm nhìn; nhiều mặt hoặc mặt quá nhỏ vẫn phải điều chỉnh, không bỏ bộ lọc để nhận bừa.
- Tên/mã/chiều/giờ từ receipt máy chủ chỉ hiện khi receipt đã kiểm tra hợp lệ. Âm đọc **“Hợp lệ”** chỉ cho `recorded`; `duplicate`, chờ đối chiếu, lỗi hoặc chụp thử không tự phát. Nhớ tối đa 100 event ID theo thiết bị trong sessionStorage để chống đọc lặp khi tải lại/khôi phục; không lưu ảnh hoặc tên vào lịch sử âm thanh.
- Âm thanh là WAV 42.780 byte, PCM mono 22.050 Hz, 0,969 giây, được tạo offline bằng eSpeak NG. Không có dịch vụ TTS hoặc giọng đám mây lúc vận hành; không yêu cầu tablet cài giọng tiếng Việt. Nguồn/checksum/tham số ở `frontend/public/audio/README.md`. Có nút thử loa riêng và thông báo nếu trình duyệt chặn phát.

## Kiểm tra

- **18 test Node đạt**: giữ nguyên 9 kịch bản điều khiển kiosk; thêm kiểm tra không crop cảnh ngang/dọc, encoder đọc toàn source, đọc một lần/sự kiện kể cả tải lại/cạnh tranh, không đọc khi duplicate hoặc phát lỗi.
- `npm run build` đạt; script tạo âm thanh tái tạo đúng checksum, Ruff đạt. Bản build chứa WAV local.
- Trình duyệt thật: kiosk `ovalCount=0`, video `object-fit=contain`, khung mặc định 16:9; nút thử loa phát thành công ở mức API media (không có media error). Đây chưa phải đánh giá người nghe/chất lượng loa trên tablet.
- Render chính app trong viewport desktop 768/390/1024: bề rộng nội dung và scrollWidth lần lượt cùng là 768/375/1009 px, không tràn ngang; kích thước camera lần lượt 334,94×188,40 / 309,60×174,15 / 413,55×232,61 px, đều 16:9 ở trạng thái chưa mở camera và không có oval. Tỷ lệ camera thật sẽ theo metadata, không cố định 16:9.
- Không mở camera, không tạo ảnh, template, policy hoặc sự kiện chấm công thật trong bước này. Không đổi backend/schema/ngưỡng. Các test backend/native trước đó giữ giá trị lịch sử, không tuyên bố đã chạy lại.

KT03 trên iPad/Android, phát âm thanh sau khoảng chờ dài trên thiết bị thật và luồng camera→nhận diện/PAD→ghi công T23 vẫn chưa nghiệm thu. Runtime ghi công thật tiếp tục tắt.
