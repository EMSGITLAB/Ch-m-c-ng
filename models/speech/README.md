# Nhận họ tên bằng giọng nói — local

Thiết lập một lần bằng `.venv/Scripts/python.exe scripts/prepare_partner_speech.py`.
Script tải đúng `Systran/faster-whisper-small`, revision
`536b0662742c02347bc0e980a01041f333bce120`, xác minh kích thước/SHA-256,
và tạo manifest cạnh model. Không dùng tài khoản/token trả phí.

Ứng dụng chỉ đọc thư mục local `faster-whisper-small/`, không tự tải model.
Chạy CPU INT8, hai luồng trong tiến trình riêng; toàn bộ kết nối mạng từ
tiến trình giọng nói bị chặn. ONNX Runtime telemetry bị tắt.
Tệp `model.bin` khoảng 484 MB; model được đưa vào bộ cài offline khi có đủ
manifest và checksum hợp lệ. Không đưa trọng số có thể cài lại vào bản sao lưu
dữ liệu nghiệp vụ có giới hạn 256 MiB. Sau khôi phục cần có model trong bộ cài;
nếu thiếu, nhập họ tên bằng tay vẫn sử dụng được.

Audio tối đa 8 giây, 2 MB, chỉ xử lý trong bộ nhớ. Kết quả là họ tên nháp,
luôn cần người dùng kiểm tra và xác nhận. Không nhận diện danh tính bằng giọng.
Chưa nghiệm thu chất lượng đọc tên tiếng Việt trên thiết bị/người thật.

Nguồn: [faster-whisper](https://github.com/SYSTRAN/faster-whisper),
[model](https://huggingface.co/Systran/faster-whisper-small) — MIT.
Giữ nguyên LICENSE/NOTICE của các wheel và thư viện phụ thuộc khi phân phối.
