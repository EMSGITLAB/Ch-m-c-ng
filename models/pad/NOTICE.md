# MiniFASNet — model kiểm chứng chống giả mạo

Hai model gốc thuộc dự án [Minivision Silent-Face-Anti-Spoofing](https://github.com/minivision-ai/Silent-Face-Anti-Spoofing), Apache-2.0. Bản ONNX và tham chiếu tiền xử lý lấy từ [yakhyo/face-anti-spoofing](https://github.com/yakhyo/face-anti-spoofing), Apache-2.0. Giữ cả hai tệp LICENSE kèm theo và thông báo nguồn khi đóng gói.

Manifest lưu commit nguồn, URL, kích thước và SHA256. Release tag `weights` có thể thay đổi; checksum cố định kiểm soát nội dung thực tế. Không dùng model/code từ các gói thương mại hoặc nguồn chưa rõ giấy phép. Upstream chưa công bố dữ liệu huấn luyện đầy đủ tại các nguồn đã kiểm tra; giấy phép phần mềm/model không phải chứng nhận nguồn dữ liệu hay chất lượng PAD.

`pad_engine.py` điều chỉnh tiền xử lý từ `onnx_inference.py` của yakhyo tại commit đã ghi: ảnh BGR raw 0..255, crop clip theo cạnh, NCHW float32 80×80, softmax output 3 lớp, lớp 1 là score người thật. Đây là giao thức khác cách dịch crop giữ nguyên diện tích ở một số code gốc Minivision; không trộn hai phép crop hoặc dùng ngưỡng của giao thức khác. Báo `context_clipped` khi vùng mở rộng chạm biên; cần đo riêng tình huống này.

Trạng thái **experimental_not_validated**. Chưa có ngưỡng đã hiệu chỉnh, kết quả ảnh in/màn hình/video hoặc chứng nhận PAD cho thiết bị này. Điểm softmax không phải xác suất bảo đảm người trước camera là người thật. Tải và chạy model không bật ghi công tự động. Cần T11/KT09 trước khi quyết định vận hành.
