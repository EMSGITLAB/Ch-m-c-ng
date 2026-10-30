# OnTime — Hướng dẫn Chấm công đối tác

Phạm vi: lao động thời vụ theo đợt/ca, không tạo hồ sơ Nhân viên công ty.
Camera, vector, so khớp và giọng nói đều xử lý local; không Docker/API cloud.

## Chuẩn bị đợt

1. Vào **Quản trị → Chấm công đối tác**. Đối tác thử đã có mã `D23`, tên **Đối tác sàn D23**.
2. Tạo đợt nháp: tên, sàn, ngày bắt đầu, giờ bắt đầu/kết thúc, số lao động yêu cầu và hạn mức được tiếp nhận. Giờ kết thúc nhỏ hơn giờ bắt đầu là ca qua đêm, dùng ngày bắt đầu làm ngày công.
3. Có thể khai báo khoảng nghỉ giữa ca, chọn có tính công hay không. Cấu hình ca/nghỉ được giữ cùng đợt; không tự lấy ca nhân viên công ty.
4. Điền lý do thao tác, chọn **Mở tiếp nhận**. Hệ thống ghim cấu hình nhận diện đang hợp lệ; không tự đổi model/ngưỡng. Nếu cấu hình đang chạy thử, báo cáo và CSV ghi rõ không dùng làm chứng từ thanh toán.
5. Tạo/ghép một điểm kiosk tại **Thiết bị Kiosk**, rồi gán điểm đó cho đợt đối tác. Điểm đã gán đợt đối tác không ghi công vào phân hệ nhân viên công ty. Mã ghép dùng một lần; không gửi mã hoặc mật khẩu qua chat.
6. Mở **Chấm công đối tác** ở thanh điều hướng hoặc `#partner`. Màn hình hiện đối tác, ca và chiều Vào/Ra của đúng điểm quét. Camera bật tự động khi cấu hình sẵn sàng; mở **Tùy chọn** để bật/tắt camera, ghép thiết bị hoặc thử giọng đọc.

Trên laptop dùng localhost. iPad/tablet truy cập qua mạng cần HTTPS tin cậy để trình duyệt mở camera/micro; chuẩn bị chứng chỉ khi triển khai máy chủ. Không cần Docker/Caddy cho luồng thử laptop.

## Người mới quét Vào

1. Giữ một người trước camera. Camera lấy toàn cảnh, tự tìm mặt và lấy chuỗi ảnh ngắn; không bấm chụp hoặc lấy đủ năm hướng.
2. Nếu chưa có trong đợt, popup Họ và tên tự hiện giữa màn hình; camera tạm dừng xử lý người khác và giữ mã tạm, ví dụ `D23-20261030-C0001-00001`. **Chưa ghi Vào hoặc phát “Hợp lệ”** ở bước giữ mã.
3. Trong popup chọn **Đọc họ tên** hoặc **Nhập bằng tay**. Bấm micro và đọc đầy đủ họ tên; có thể bấm micro lần nữa để gửi ngay. Khi phát hiện đã nói và có khoảng lặng khoảng 1 giây, bộ thu tự kết thúc; giới hạn vẫn là 8 giây khi quá ồn, âm lượng thấp hoặc thiết bị không hỗ trợ theo dõi mức âm. Kiểm tra chữ/dấu và sửa kết quả. Hoặc nhập trực tiếp trong ô Họ và tên. Micro lỗi, bị từ chối hoặc nhận tên chậm không khóa ô nhập tay.
4. Bấm **Xác nhận họ tên**. Họ tên tự khai dùng để đối soát; không phải chứng minh danh tính bằng giọng nói. Đổi giữa micro/nhập tay không tạo mã khác. Kết quả micro tới muộn không ghi đè tên đã nhập/xác nhận.
5. Tiếp tục giữ mặt trước camera. Hệ thống kiểm tra lại đúng người và **tự động ghi Vào**, hiện mã/tên/giờ, đóng popup và phát tệp “Hợp lệ” đã chọn của OnTime. **Không có bước chờ quản trị cho phép tiếp nhận.**
6. Quản trị chỉ theo dõi kết quả tại **Theo dõi tiếp nhận tự động**, không phải duyệt từng người. Người đã Vào không phải đọc tên lần nữa.

Phiên giữ mã chờ xác nhận tên tối đa 5 phút. Khi xác nhận tên hoặc ghi Vào, camera chỉ đối chiếu lại với đúng người đang giữ mã; mặt khác không được cấp thêm mã trong bước này. Tải lại trang khôi phục cùng phiên nhập tên. Hết phiên hiển thị Quét lại, không tự cấp mã ở phía sau popup. Hủy/hết phiên chưa ghi công; số đã cấp không được tái sử dụng. Người ở điểm khác đang tiếp nhận được báo rõ, không giữ thêm mã. Nếu đổi người trước camera, không gắn tên của người cũ cho mặt mới.

Máy chủ nạp sẵn model giọng nói trong nền khi khởi động, không thu micro hoặc lưu audio trong bước nạp. Có thể tắt bằng `CHAMCONG_SPEECH_PREWARM_ENABLED=false` nếu máy cần tiết kiệm RAM; khi đó lượt đọc đầu phải chờ tải model. Model và thuật toán giải mã giữ nguyên; không dùng API/cloud để tăng tốc.

Âm Hợp lệ sử dụng tệp đã cung cấp, mở quyền phát bằng thao tác bấm trên trình duyệt. Nếu bị chặn, màn hình có nút **Bật âm thanh và nghe thử**; cũng có **Tùy chọn → Thử giọng đọc**. Quét lại một chiều đã ghi công vẫn im lặng; thử âm thanh không tạo thêm lượt công.

## Quét lại và chiều Ra

- Giữ riêng chiều **Vào/Ra**; lần quét tiếp theo không tự đổi thành Ra.
- Đã Vào, quét tiếp chiều Vào: thông báo đã quét vào, không âm thanh, không sửa giờ hoặc thêm lượt.
- Chọn chiều Ra mới ghi Ra, dùng lại mã/tên trong ca và phát “Hợp lệ”. Không cần đọc tên lại.
- Đã Ra, quét tiếp chiều Ra: chỉ hiện đã quét ra; không âm thanh/thêm lượt.
- Đã hoàn tất cặp Vào/Ra, quét lại chiều Vào vẫn giữ mã cũ, không tạo lượt lao động mới.
- Người chưa Vào quét Ra không được cấp mã hoặc tự tạo cặp.
- Sau kết quả, bước ra khỏi khung để hệ thống sẵn sàng cho lượt quét tiếp theo. Mất phản hồi/tải lại trang dùng mã yêu cầu đã giữ để kiểm tra lại biên nhận; không tự ghi lượt mới vì chưa nhận được phản hồi.

## Dừng tiếp nhận, đối soát và chốt

1. **Dừng nhận người mới** chuyển đợt sang Đang thực hiện; người đã Vào vẫn được quét Ra.
2. Khi kết thúc ghi nhận, chọn **Chuyển đối soát**. Bước này dừng ghi Vào/Ra để kiểm tra và chỉnh công.
3. Tại **Theo dõi và đối soát**, lọc khoảng ngày (tối đa 93 ngày), đối tác, sàn và chọn đợt. Lọc dòng đủ cặp/thiếu cặp/chưa tiếp nhận; có phân trang.
4. Kiểm tra số yêu cầu/hạn mức, đã Vào, đủ/thiếu cặp và tổng giờ đủ điều kiện. “Chưa ghi lượt Ra” không khẳng định người còn hiện diện. Thiếu Ra không tự lấy giờ cuối ca hoặc tính đủ công.
5. Giờ công của cặp đầy đủ là thời gian nằm trong ca sau trừ phần nghỉ không tính công thực sự chồng lên cặp Vào/Ra. Không trừ nghỉ hai lần; thời gian ngoài ca được thể hiện riêng, chưa tính tiền/hệ số ngoài giờ.
6. **Gốc & lịch sử** xem lượt camera và toàn bộ điều chỉnh. **Điều chỉnh** chỉ có khi đợt Chờ đối soát và người đã Vào. Nhập/sửa tên hoặc giờ theo múi giờ của ca, bắt buộc có lý do. Chỉ trường thay đổi mới được lưu; lượt gốc, mã và mẫu mặt không bị ghi đè. Bảng đã thay đổi sẽ yêu cầu tải lại thay vì sửa trên nguồn cũ.
7. **Xuất CSV bản đang xem** dùng đúng bộ lọc trạng thái và mã nguồn dữ liệu của báo cáo đã xem. Nếu nguồn thay đổi, tải lại trước khi xuất. CSV UTF-8 có giờ địa phương, giờ gốc/đối soát và dấu điều chỉnh/chạy thử; tên có ký tự công thức Excel được vô hiệu hóa khi xuất.
8. Nhập ghi chú và **Chốt bản đối soát này**. Nếu còn thiếu cặp phải xác nhận rõ, các dòng thiếu vẫn thiếu và không tự có giờ công. Phiên chưa tiếp nhận khi chốt không trở thành người đã Vào.
9. Bản chốt lưu riêng dữ liệu, quy tắc, tổng hợp, nguồn, người chốt, thời điểm/lý do và checksum. Không sửa trực tiếp hoặc mở lại đợt đã chốt. Chưa có bản chốt hoặc checksum sai thì hệ thống báo lỗi, không tự dựng lại chứng từ.

## Mẫu tạm, giọng nói và khôi phục

- Không lưu ảnh camera gốc. Vector tạm mã hóa trong `.runtime/partner-biometrics`, có khóa riêng và giới hạn phạm vi đợt/model. Không đưa kho/khóa này vào backup nghiệp vụ.
- Vector hết hạn 48 giờ sau kết thúc ca; từ thời điểm hết hạn không dùng để nhận diện. Dọn file khi khởi động và mỗi 30 giây. Lỗi dọn được báo trong Vận hành; không tự tạo lại kho đang có dữ liệu hỏng/mất khóa.
- Audio tối đa 8 giây/2 MB, chỉ xử lý trong bộ nhớ; không lưu audio vào SQL/file/log/backup. Kết quả nhận tên luôn là nháp cần xác nhận.
- Model giọng nói khoảng 484 MB thuộc bộ cài offline; không đưa trọng số có thể cài lại vào backup dữ liệu giới hạn 256 MiB. Thiếu model thì nhập tay vẫn hoạt động; ứng dụng không tự tải model qua Internet.
- Backup SQL giữ bảng công, sự kiện, điều chỉnh và bản chốt. Khôi phục vào database/thư mục mới, kiểm checksum và số bản ghi. Kho mặt tạm không được phục hồi, kể cả khi tạo backup trước lúc xóa mẫu.
- Sau khôi phục, phiên quản trị/quyền kiosk cũ bị thu hồi, gán thiết bị đối tác bị tắt và chính sách nhận diện bị dừng. Phải cấu hình lại có kiểm soát; không coi mẫu bị mất là một người mới để tự cấp thêm mã.
- Bảng công và CSV đã chốt vẫn xem được khi mẫu hết hạn/mất kho hoặc đối tác đổi tên.

## Giới hạn nghiệm thu

Kiểm thử giao dịch/giả lập không chứng minh độ chính xác nhận diện hoặc chống ảnh giả. Bản đầu hoàn tất luồng bằng một người thật sẵn có; đo nhiều lao động, thiết bị, ánh sáng/sàn và PAD là đợt thử riêng trong kế hoạch. Chưa tự tính tiền thanh toán đối tác hoặc cam kết phát hiện ảnh giả.

Máy laptop hiện dùng SQL Server Developer cho phát triển/kiểm thử. Khi vận hành miễn phí trên VM dùng SQL Server Express phù hợp; có thể dùng SQL Server đã có giấy phép. Bộ cài Windows không cần Node hoặc Docker để phục vụ frontend đã build, nhưng máy đích cần Python/SQL Server/ODBC và cấu hình TLS/quyền truy cập theo hướng dẫn vận hành chính.
