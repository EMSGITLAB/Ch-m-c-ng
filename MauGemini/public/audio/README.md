# Giọng báo chấm công

## Bản đang dùng — đọc dứt khoát

`hop-le-dut-khoat.wav`: **“Hợp lệ.”**, WAV PCM 16-bit mono 44.100 Hz, dài **0,7763 giây**. Tên tệp mới giúp trình duyệt nạp bản mới khi thay âm báo. Bộ phát trong ứng dụng đặt âm lượng phần tử audio ở 100%; âm lượng loa vật lý do thiết bị điều khiển.

- Tổng hợp offline bằng cùng eSpeak NG bên dưới, giọng `vi`, tốc độ 150, cao độ 42, biên độ 100, khoảng từ 6; câu có dấu chấm để kết thúc dứt khoát. Không dùng bản thu hoặc bắt chước giọng của một người.
- Xử lý offline bằng FFmpeg có sẵn trên máy phát triển: cắt im lặng đầu/cuối, giữ khoảng giữa hai từ, lọc 85–7.000 Hz, tăng độ rõ ở 2.200 Hz, nén động 4:1 và chuẩn hóa loudness mục tiêu −11 LUFS / đỉnh thật tối đa −1 dBTP. Fade ngắn tránh tiếng bật đầu/cuối. Không phân phối FFmpeg cùng ứng dụng.
- Kiểm tra WAV thực tế: peak **−1,00 dBFS**, RMS **−15,52 dBFS**, **0 mẫu clipping**. RMS toàn tệp cao hơn bản cũ khoảng 4,27 dB; số đo này không thay cho nghe thử trên loa thiết bị.
- SHA256: `bf60c7ec93b387d3269f44de5315c1dbc54a6f3db673907d92107444f796756a`.
- Tái tạo: `scripts/generate_kiosk_audio.py --executable <espeak-ng.exe> --data-root <thư mục chứa espeak-ng-data> --style firm --ffmpeg <ffmpeg.exe>`. Script chạy công cụ qua thư mục tạm ASCII để tương thích đường dẫn workspace tiếng Việt trên Windows.

## Bản cũ được giữ để đối chiếu

`hop-le.wav`: câu **“Hợp lệ”**, WAV PCM mono 22.050 Hz.
Được tổng hợp offline, không sử dụng bản thu của một người hoặc dịch vụ TTS bên ngoài.
Ứng dụng phát tệp từ cùng máy chủ local, không cần cài giọng tiếng Việt trên tablet.

- Công cụ tạo: eSpeak NG, release asset **1.51 / espeak-ng-X64.msi**. Bản nhị phân của asset này báo `1.52-dev`.
- Nguồn chính thức: https://github.com/espeak-ng/espeak-ng/releases/tag/1.51
- Công cụ eSpeak NG có giấy phép GPL-3.0-or-later; không phân phối executable, DLL hoặc dữ liệu công cụ cùng frontend.
- Tham số: `-v vi -s 155 -p 50`, văn bản UTF-8 `Hợp lệ`.
- Thời lượng: 0,969 giây; SHA256: `cb3dffe6fcaebb2204fdd627cb0adf9807ee9bd86cfa910740a02836ed3f80df`.
- SHA256 asset MSI dùng tạo: `5368d9dab4e1371f35b2cdc4f4053e28060d450c3328038a783bdb9d2476e3bf`.
- Tái tạo bằng `scripts/generate_kiosk_audio.py --executable <espeak-ng.exe> --data-root <thư mục chứa espeak-ng-data>`. Công cụ chỉ dùng khi phát triển, không cần lúc vận hành.

Chỉ phát tự động sau biên nhận `recorded` hợp lệ. `duplicate`, lỗi, chờ đối chiếu và thử camera không phát “Hợp lệ”. Nhớ event ID gần nhất theo thiết bị trong phiên trình duyệt để không đọc lại khi phục hồi cùng biên nhận. Nút **Thử giọng đọc** trong **Tùy chọn thiết bị** phát riêng để kiểm tra loa, không tạo lượt công. Đây là giọng tổng hợp; cần nghe thử trên iPad/Android thật cùng kiểm tra âm lượng/quyền phát media.
