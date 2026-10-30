# T11 — Chống giả mạo local: model, công cụ thử và kết quả ban đầu

Ngày 28/10/2026. **Đang thực hiện, chưa nghiệm thu T11/KT09; không bật ghi công.**

## Đã triển khai

- Hai model MiniFASNetV2 (crop 2,7) và MiniFASNetV1SE (crop 4,0), khoảng 1,74 MB/tệp, chạy bằng OpenCV DNN CPU hiện có; không Docker, thêm runtime AI, API tính phí hoặc Internet khi suy luận.
- Nguồn Minivision và bản ONNX từ yakhyo đều công bố Apache-2.0. Manifest ghim commit, byte count, SHA256, input BGR float32 0..255/NCHW 80×80, output logits ba lớp/softmax lớp 1. Hai bản LICENSE và NOTICE được lưu trong `models/pad`. Không thay YuNet/SFace hoặc ngưỡng danh tính.
- Crop bám đúng code của nhà xuất bản ONNX, clip theo cạnh ảnh; báo `context_clipped` khi vùng mở rộng bị giới hạn. Không trộn phép crop này với cách dịch vùng giữ kích thước của code Minivision khác phiên bản.
- Model kiểm checksum trước khi nạp, chỉ dùng OpenCV CPU; warmup/kiểm đầu ra hữu hạn. Đầu ra là điểm thử nghiệm và `decision=not_evaluated`, `validated_for_attendance=false`; không có ngưỡng mặc định hoặc quyền bật policy từ điểm đó.
- **Quản trị → Kiểm chứng AI → Kiểm chứng chống ảnh giả**: khai báo tình huống, mở camera, tự lấy 5 khung theo thứ tự; ảnh lỗi giữ rõ lý do, không gán điểm 0 hoặc 1 giả. Một phiên có tương quan, không tính thành 5 thử độc lập. Có báo cáo JSON không chứa ảnh/vector; ghi chú do người dùng nhập cần tránh tên/dữ liệu cá nhân.
- API quản trị/CSRF/same-origin/intent; upload giới hạn 2 MB/10 giây, một phép xử lý đồng thời, trả 429 khi bận. Ảnh/vector chỉ trong bộ nhớ; không tạo hồ sơ/template/sự kiện hoặc lưu dữ liệu camera vào DB. Model PAD vắng/hỏng không làm ứng dụng tự nhận đã kiểm chứng.
- Camera và yêu cầu dừng khi rời/ẩn trang hoặc bấm dừng. Kiểm tra trạng thái sau từng await để không gửi ảnh muộn; không xuất một phiên hoàn tất nếu dừng giữa chừng hoặc model đổi trong lúc đo.

## Bằng chứng kỹ thuật

- `scripts/download_pad_models.py` kiểm lại hai checksum đúng manifest; binary được Git ignore, giấy phép/manifest/NOTICE là tài liệu nguồn.
- `scripts/check_pad_cpu.py`: chạy hai mạng thật 20 lần trên ảnh demo OpenCV Zoo công khai, không gán nhãn PAD; kết quả lặp lại nhất quán. **Trung vị 10,01 ms, P95 11,05 ms**, chỉ gồm tiền xử lý/hai mạng PAD; không phải độ trễ camera→ghi công hoặc độ chính xác. Chi tiết `pad-cpu-smoke.json`.
- **212 test backend đạt**, 6 native-only skip và đã được chạy trong **141 test SQL Server đạt** trên DB riêng. Có kiểm tra BGR/không chia 255, hình dạng tensor, crop biên, output sai/non-finite, trung bình đúng hai mạng, checksum/path, quyền/CSRF, 429 và không ghi DB/bật policy.
- **26 test frontend đạt**, gồm phiên 5 khung, dữ liệu không đạt, hủy giữa encode/nghỉ, model đổi/điểm không hữu hạn/tuyên bố đã xác minh bị từ chối. Build frontend và Ruff đạt.
- Công cụ điều khiển trình duyệt mất kết nối (`browser.user is unavailable`) trong phiên này; không tuyên bố đã tự kiểm thử giao diện/download bằng browser. Người dùng đã thực hiện đo thật và gửi kết quả hiển thị dưới đây; nguồn báo cáo được ghi rõ.

## Hai phiên do người dùng thực hiện

| Tình huống được người dùng xác nhận | Phiên độc lập | Khung đạt | Ngữ cảnh bị cắt | Điểm thấp nhất / trung bình / cao nhất |
| --- | --- | --- | --- | --- |
| Người thật trực tiếp | 1 | 5/5 | 5/5 | 0,999 / 1,000 / 1,000 |
| Ảnh chân dung trên điện thoại | 1 | 5/5 | 5/5 | 0,620 / 0,749 / 0,929 |

- Nguồn: `pad-user-live-trial-01.json`, `pad-user-screen-trial-01.json`. Đây là số làm tròn do người dùng sao chép, không có score gốc/model ID trong phần gửi; manifest ghi model dự kiến của bản ứng dụng. Không suy ra mức tin cậy thống kê hoặc tỷ lệ lỗi từ hai phiên.
- Nhãn UI lúc chụp lần lượt là **Chưa gán nhãn** và **Người thật trực tiếp**; người dùng xác nhận lại trong chat rằng thực tế lần lượt là người thật và ảnh điện thoại. Giữ cả nhãn ban đầu/lời xác nhận, không âm thầm sửa lịch sử hoặc gán nhãn theo score model.
- **Ảnh điện thoại vẫn nhận điểm lớp người thật cao**: chưa đủ căn cứ bật tự động hoặc chọn ngưỡng từ một cặp thử. Chưa có ảnh in/video, điều kiện không cắt vùng ngữ cảnh hoặc đủ cỡ mẫu KT09 (ít nhất 30 phiên mỗi loại trên nhiều người). Hai trường hợp có vùng ngữ cảnh bị cắt cần được thử đối chiếu khi chừa đủ khoảng quanh mặt; không mặc định đây là nguyên nhân duy nhất.

## Tiếp theo

1. Thu thêm cặp người thật/ảnh màn hình cùng điều kiện, cố gắng đủ ngữ cảnh quanh mặt; xem riêng score từng mạng từ JSON, không chỉ trung bình.
2. Thử ảnh in và video phát lại, nhiều ánh sáng/khoảng cách/thiết bị/người; chia dữ liệu hiệu chỉnh và giữ tập thử cuối độc lập.
3. Chỉ chọn ngưỡng/chính sách kết hợp khi đủ dữ liệu; giữ các mẫu thất bại làm hồi quy. Không tự tăng ngưỡng để vừa khớp hai phiên đầu hoặc coi không ghi công khi policy tắt là chứng minh PAD từ chối tấn công.
4. Sau khi đạt T11 mới gắn kết quả PAD từng phiên vào chuỗi ghi công tự động và kiểm tra đầu cuối. Nếu chưa đạt, tiếp tục cải thiện phương án miễn phí/local; chưa đề xuất API trả phí chỉ từ hai phiên này.

Nguồn chính: [Minivision](https://github.com/minivision-ai/Silent-Face-Anti-Spoofing), [bản ONNX và code tiền xử lý](https://github.com/yakhyo/face-anti-spoofing/blob/01a38903f4f2680bb59d32a994a6c7b5ae56f49b/onnx_inference.py). Giấy phép không thay thế kiểm chứng chất lượng ở camera thật.
