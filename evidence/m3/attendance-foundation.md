# Giao dịch ghi công, chống trùng và truy vấn kết quả — 28/10/2026

## Phạm vi đã viết và kiểm thử

- `RecognitionPolicy` gắn model, quy tắc điểm, ngưỡng và trạng thái kiểm chứng. Cấu hình tự động yêu cầu dấu PAD đã kiểm chứng; cấu hình có giám sát yêu cầu xác nhận riêng trên từng phiên trước ghi.
- `RecognitionSession` giữ request ID, kiosk, chiều vào/ra, policy, danh tính/revision do máy chủ xác định, thời hạn và biên nhận. API commit không nhận mã nhân viên, điểm tin cậy hoặc giờ từ tablet.
- Lưu sự kiện, đánh dấu phiên đã dùng, lưu biên nhận và audit trong cùng giao dịch. Chỉ trả thành công sau commit. Biên nhận giữ tên/mã tại thời điểm ghi và có thể truy vấn lại khi mất phản hồi.
- Khóa theo thứ tự policy → nhân viên → kiosk → phiên nhận diện; kiểm tra lại active/revision/token/model/policy/chiều/thời hạn dưới khóa. Không nhận quyết định dựa trên đối tượng ORM đã cũ.
- Chống trùng theo cùng người + cùng chiều trong cooldown server (mặc định 60 giây). Hai kiosk đồng thời dùng chung một sự kiện; request ID khác vẫn có biên nhận riêng trỏ đến sự kiện gốc. Đúng mốc 60 giây có thể ghi lượt mới; vào/ra được xét riêng.
- Kiosk chỉ đọc biên nhận thuộc chính thiết bị đó. Phiên chờ/trượt/hết hạn không được báo đã ghi. Kiosk bị thu hồi hoặc đổi token bị chặn.
- Tối đa 4 giao dịch commit đồng thời ở API, vượt trả 429 kèm Retry-After. Lỗi kết nối DB trả kết quả chưa xác nhận và hướng dẫn tra cùng request ID.
- `attendance_events` thêm chỉ mục người/chiều/giờ; schema hiện có 15 bảng tính cả alembic_version. Migration upgrade/downgrade/native backup/restore đã kiểm tra trên database thử riêng.

## Kết quả kiểm thử

- Toàn bộ backend: **112 passed, 2 skipped**. Hai ca cạnh tranh bỏ qua trên SQLite được thực thi riêng trên SQL Server thật.
- SQL Server thử riêng: **67 passed**, gồm hai request đồng thời từ hai kiosk và hai retry đồng thời của cùng request ID.
- Mô phỏng mất phản hồi sau commit: API trả 503, truy vấn request ID vẫn nhận biên nhận recorded và không sinh sự kiện thứ hai.
- Mô phỏng audit hỏng: sự kiện, biên nhận và trạng thái phiên đều rollback.
- Bao phủ vô hiệu nhân viên, revision cũ, model cũ, hết phiên, thu hồi/đổi token, đổi chiều, policy tắt, yêu cầu chưa verified, yêu cầu giám sát chưa xác nhận, đồng hồ máy chủ lùi và policy cache cũ.
- Ruff và TypeScript/Vite build: đạt.

## Trạng thái triển khai thật

Đã migrate schema và restart bản local. `runtime-state.json` xác nhận 0 policy, 0 phiên nhận diện và 0 sự kiện chấm công trong database thật; `/api/system/status` vẫn báo `attendance_enabled=false`. Runtime không tự chọn policy. Các policy/phiên verified trong test là dữ liệu giả nằm ở database thử riêng, **không phải bằng chứng độ chính xác/PAD**.

T20/T21/T22 giữ chưa hoàn tất do T19 và luồng kiosk đầu-cuối chưa được nối/kiểm chứng. Cần hoàn tất hiệu chỉnh, chọn policy có bằng chứng, xử lý chuỗi ảnh/PAD và UI tra kết quả khi mất mạng trước vận hành.
