# T24 — Ca làm và lịch phân ca — 28/10/2026

## Chức năng đã triển khai

- Quản trị → **Ca & lịch** gồm định nghĩa ca và lịch theo ngày. Tạo ca ngày/qua đêm, tối đa 8 khoảng nghỉ có hoặc không tính công, dung sai muộn/sớm và cửa sổ tìm sự kiện trước/sau ca.
- Mỗi ca giữ múi giờ, thời gian và quy tắc riêng. Sửa tạo ID/phiên bản mới, ngừng dùng phiên bản cũ cho phân ca mới; lịch đã phân vẫn trỏ đến quy tắc cũ. Không cập nhật sự kiện chấm công gốc.
- Phân hàng loạt tối đa 100 hồ sơ đang hoạt động trong 31 ngày, chọn các thứ trong tuần. Kiểm tra trùng/chồng ca cả ngày trước/sau để bắt ca qua đêm; ca liền giờ được phép.
- Toàn bộ lượt phân là một giao dịch. Chỉ một xung đột hoặc hồ sơ vô hiệu làm từ chối cả lượt, không phân dở một phần.
- Khóa nhân viên theo thứ tự ID rồi khóa ca đang dùng; các yêu cầu phân ca đồng thời không vượt qua kiểm tra chồng lịch. Hai yêu cầu sửa cùng một phiên bản chỉ tạo một bản kế tiếp.
- Hủy lịch hoặc ngừng dùng ca có lý do và audit; không xóa lịch sử. Có thể phân lại sau hủy, với bản ghi mới. Chỉ mục unique có điều kiện chặn hai lịch active trùng đúng người/ca/ngày.
- Tra lịch theo khoảng ngày (tối đa 93 ngày), nhân viên, trạng thái hủy và phân trang. UI tìm/chọn hồ sơ, chọn ngày/thứ, xem phiên bản ca và lịch hủy.

## Kiểm chứng

- Backend toàn bộ: **127 passed, 4 skipped**; 4 ca cạnh tranh được chạy riêng trên SQL Server.
- SQL Server thử riêng: **84 passed**, gồm cạnh tranh phân ca/sửa ca và các ca commit nhận diện trước đó. Không có ca cạnh tranh bị bỏ qua trong lượt SQL Server.
- Ruff và TypeScript/Vite build đạt.
- Ví dụ ca 08:00–17:00 nghỉ không công 12:00–13:00: 480 phút dự kiến; đổi giờ vào 09:00 tạo phiên bản 420 phút, lịch cũ vẫn 480.
- Ví dụ ca 22:00–06:00, nghỉ có công 23:45–00:15 và không công 02:00–02:30: 480 phút ca, 450 phút công dự kiến.
- Kiểm tra năm mới, chuyển giờ UTC/Vietnam, khoảng nghỉ chồng/ngoài ca, giờ không hợp lệ/giờ DST không duy nhất, phân theo thứ, nguyên tử khi có hồ sơ vô hiệu và hủy/phân lại.
- Migration trên SQL Server: nâng từ schema có ca/lịch cũ giữ đúng dữ liệu, native backup/restore Unicode, downgrade/upgrade đều đạt. Khi đã có phiên bản/hủy, downgrade bị từ chối trước khi mất lịch sử.
- Lỗi downgrade ban đầu do yêu cầu bỏ default constraint ở cột không có default; đã sửa chỉ bỏ default ở cột thực sự có. Harness lưu đủ stderr UTF-8 để chẩn đoán.
- UI laptop thật: đã kiểm tra tab Ca & lịch, biểu mẫu ngày/giờ/nghỉ/dung sai, thêm/bỏ khoảng nghỉ, đóng bản nháp, lịch theo ngày/thứ và tải hồ sơ. Chưa nhập ca/lịch thật; `schedule-state.json` ghi 0 ca/0 lịch. Các dữ liệu mẫu chỉ ở DB thử riêng.

## Phạm vi tiếp theo

T24 hoàn tất. Đây là quy tắc và lịch dự kiến, chưa phải bảng công thực tế. T25/T26 phải tính từ sự kiện, điều chỉnh có audit và bảo vệ kỳ đã khóa; T28 kiểm thử trọn bộ nghiệp vụ. Kiểm thử tablet, PAD và độ chính xác vẫn chưa hoàn tất.
