# Thành phần bên thứ ba

Ứng dụng chạy local. Không có thuê bao bắt buộc hoặc API nhận diện bên ngoài.

| Thành phần chính | Giấy phép được công bố | Bản đang dùng |
|---|---|---|
| Python | Python Software Foundation License | Python 3.12.10 trên máy hiện tại |
| FastAPI | MIT | `backend/requirements.lock` |
| Uvicorn | BSD 3 Clause | `backend/requirements.lock` |
| SQLAlchemy và Alembic | MIT | `backend/requirements.lock` |
| pyodbc | MIT | `backend/requirements.lock` |
| SQL Server | Giấy phép Microsoft theo edition | Developer có sẵn cho phát triển; Express miễn phí khi vận hành |
| OpenCV 4 | Apache 2.0 | `backend/requirements.lock` |
| NumPy | BSD 3 Clause | `backend/requirements.lock` |
| openpyxl | MIT | `backend/requirements.lock` — xuất XLSX local |
| React | MIT | `frontend/package-lock.json` |
| TypeScript | Apache 2.0 | `frontend/package-lock.json` |
| Vite và plugin React | MIT | `frontend/package-lock.json` |

Âm báo `frontend/public/audio/hop-le.wav` và bản dứt khoát cũ `hop-le-dut-khoat.wav` được tổng hợp offline bằng eSpeak NG từ câu “Hợp lệ”. Công cụ eSpeak NG (GPL-3.0-or-later, [nguồn chính thức](https://github.com/espeak-ng/espeak-ng)) chỉ dùng lúc phát triển; không có executable/DLL/data eSpeak trong frontend phân phối. Bản dứt khoát được cân chỉnh âm lượng bằng FFmpeg có sẵn trên máy phát triển, không phân phối FFmpeg trong ứng dụng. Nguồn, tham số và checksum ở `frontend/public/audio/README.md`; thiết bị chỉ phát tệp local, không gọi dịch vụ giọng đọc.

Danh mục đầy đủ theo metadata của các gói đã cài nằm trong `evidence/m0/python-licenses.json` và `evidence/m0/frontend-licenses.json`. Metadata không thay thế các tệp LICENSE/NOTICE trong thư viện; khi đóng gói phân phối cần giữ các thông báo đó.

Model YuNet/SFace đã được tải và xác minh theo Git LFS SHA256. Nguồn, commit và checksum nằm trong `models/manifest.json`; giấy phép đúng phiên bản được lưu tại `models/LICENSE_face_detection_yunet.txt` (MIT) và `models/LICENSE_face_recognition_sface.txt` (Apache 2.0). Không dùng model chỉ dành cho nghiên cứu phi thương mại.

Model PAD thử nghiệm MiniFASNetV2/MiniFASNetV1SE có nguồn Minivision Silent-Face-Anti-Spoofing và bản ONNX từ yakhyo/face-anti-spoofing, được công bố theo Apache-2.0. Giữ `models/pad/LICENSE_minivision.txt`, `LICENSE_onnx_exporter.txt` và `NOTICE.md`. Commit, hợp đồng tiền xử lý và checksum ở `models/pad/manifest.json`. Hai mạng chạy bằng OpenCV DNN CPU hiện có, không thêm API hoặc thuê bao. Chưa công bố bộ dữ liệu huấn luyện đầy đủ ở nguồn đã kiểm tra; giấy phép không chứng minh độ chính xác PAD tại điểm chấm công.

Nguồn: https://opencv.org/license/ ; https://learn.microsoft.com/en-us/sql/sql-server/editions-and-components-of-sql-server-2025 ; các tệp LICENSE và metadata của từng gói trong môi trường đã khóa.

Sao lưu và sổ dấu xóa sử dụng `cryptography` 50.0.2, giấy phép `Apache-2.0 OR BSD-3-Clause` theo metadata wheel chính thức. Dùng Fernet để mã hóa có xác thực, chạy hoàn toàn local; không có API hoặc dịch vụ lưu trữ bên ngoài. Giữ LICENSE/NOTICE trong wheel khi phân phối. [Mã nguồn](https://github.com/pyca/cryptography), [tài liệu Fernet](https://cryptography.io/en/stable/fernet/). Công cụ giới hạn gói plaintext 256 MiB vì Fernet cần xử lý trọn dữ liệu trong bộ nhớ.


## MediaPipe — khung bám mặt trong trình duyệt

`@mediapipe/tasks-vision` 1.2.0 và BlazeFace short-range float16 phiên bản 1, Apache-2.0. Chỉ tạo vị trí khung mặt trực quan; không quyết định danh tính/ghi công. JS, WASM và model được phục vụ từ `frontend/public/vision`, không CDN/API bên ngoài. Giấy phép, model card và SHA-256 từng tệp trong cùng thư mục. Nguồn model: https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/1/blaze_face_short_range.tflite . Mô hình nhận diện YuNet/SFace và ngưỡng trên máy chủ giữ nguyên.

Âm báo đang dùng `hop-le-user-fast-135.wav` được chuyển từ HopLe.mp3 do người dùng cung cấp, tăng tốc 1,35 lần giữ cao độ bằng FFmpeg local. Không dùng eSpeak hoặc dịch vụ TTS để thay giọng nguồn. FFmpeg chỉ dùng lúc phát triển; ứng dụng phát WAV local. Thông số/checksum ở frontend/public/audio/README.md.

## Nhận họ tên qua micro local

`faster-whisper` 1.2.1 và model đa ngôn ngữ `Systran/faster-whisper-small` (MIT), revision `536b0662742c02347bc0e980a01041f333bce120`. CTranslate2 chạy CPU INT8; ONNX Runtime dùng VAD với telemetry tắt. PyAV giải mã audio trong bộ nhớ bằng thư viện FFmpeg đi kèm wheel. Giữ LICENSE/NOTICE của các wheel và thư viện phụ thuộc, gồm cả FFmpeg trong PyAV, khi đóng gói; không loại bỏ giấy phép khỏi bộ cài offline.

Nguồn: [faster-whisper](https://github.com/SYSTRAN/faster-whisper), [model](https://huggingface.co/Systran/faster-whisper-small), [CTranslate2](https://github.com/OpenNMT/CTranslate2), [PyAV](https://github.com/PyAV-Org/PyAV). Phiên bản phụ thuộc khóa tại `backend/requirements.lock`; checksum được xác minh trong `models/speech/faster-whisper-small/manifest.json`. Runtime chỉ dùng model local, không tự tải hoặc gọi API. Audio không ghi ra đĩa, kết quả chỉ là tên nháp cần xác nhận; chưa nghiệm thu độ chính xác họ tên với người thật.
