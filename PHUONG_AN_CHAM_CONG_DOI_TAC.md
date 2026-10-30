# OnTime — Đề xuất phân hệ Chấm công đối tác

Ngày lập: 30/10/2026. Trạng thái: **đã hoàn thành triển khai chức năng P0–P5 và thử một người trên laptop; đo theo nhóm/PAD/thiết bị/tải thực tế được tách riêng**.

Cập nhật theo xác nhận của người dùng: **đối soát từng lao động bằng mã tạm OnTime tự cấp; không phụ thuộc mã từ đối tác. Giữ riêng chiều Vào/Ra; nhận lại người đã có mã trong cùng ca để dùng đúng mã, không cấp lại.**

Bổ sung đã yêu cầu: **ở lần tiếp nhận mới, cấp/giữ mã tạm và yêu cầu đọc họ tên qua micro thiết bị; chuyển thành chữ bằng xử lý local. Có nhập/sửa tay nếu micro hoặc nhận giọng nói không đáp ứng. Xác nhận tên trước khi hoàn tất lượt Vào.**

**Yêu cầu mới nhất đã chốt ngày 30/10/2026: tiếp nhận hoàn toàn tự động sau khi xác nhận họ tên và kiểm tra lại đúng mặt. Bỏ bước quản trị duyệt từng người. Yêu cầu này thay thế lựa chọn tiếp nhận có kiểm soát trong các nhật ký cũ bên dưới.**

## 1. Cách hiểu yêu cầu

Lao động thời vụ do đối tác cung cấp, số lượng và người tham gia thay đổi theo ngày/ca. Công ty muốn kiểm soát người đã đến, giờ Vào/Ra và đối soát số lao động/giờ công, nhưng không khai báo và duy trì hồ sơ nhân viên như người của công ty.

Giả định để lập phương án: **không cần đăng ký trước hồ sơ hoặc ảnh; được phép giữ mẫu mặt tạm trong thời gian phục vụ ca và đối soát**. Đây là hai việc khác nhau:

- Không khai báo hồ sơ thường trực: khả thi.
- Không lưu bất kỳ ảnh/mẫu mặt nào từ lúc Vào đến lúc Ra: không có dữ liệu tham chiếu để đối chiếu bằng khuôn mặt. Khi đó phải dùng một dấu liên kết khác hoặc kiểm tra thủ công.

Một khuôn mặt mới không tự chứng minh tên, đơn vị cung cấp hay quyền được làm việc. Nếu không có danh sách từ đối tác, OnTime chỉ có thể chứng minh tương đối rằng người quét Ra khớp với người đã được tiếp nhận lúc Vào, trong giới hạn chất lượng nhận diện.

## 2. Phương án đề xuất

**Tiếp nhận tại lần Vào đầu tiên → giữ mã tạm và mẫu mặt trong phiên tiếp nhận → đọc họ tên hoặc nhập tay → xác nhận tên và ghi Vào → nhận diện khi Ra → giữ bảng công, hết hạn thì xóa mẫu mặt.**

Không tạo tài khoản đăng nhập cho người lao động; không thêm vào danh sách nhân viên công ty. Không yêu cầu CCCD, điện thoại, địa chỉ hoặc thông tin hồ sơ thường trực cho luồng này.

| Cách tổ chức | Dữ liệu tối thiểu | Khả năng đối soát | Đề xuất |
|---|---|---|---|
| Mã tạm theo ca, không cần danh sách trước | Đối tác, ca, mã OnTime tự cấp, họ tên tự khai qua micro/nhập tay đã xác nhận, Vào/Ra | Đối soát từng lao động theo mã + họ tên; tổng hợp số lao động/ca và thời gian | **Đã chọn làm luồng chính** |
| Mã lao động của đối tác | Các trường trên + mã đối tác cung cấp | Gửi bảng công về đối tác và theo dõi lại cùng mã qua nhiều ngày | Chỉ bổ sung nếu sau này có mã, không phải điều kiện đầu vào |
| Danh sách ngắn gửi theo ngày | Mã và tên trong danh sách ngày, không tạo hồ sơ công ty | Dễ kiểm tra đích danh khi đối soát | Tùy chọn, không bắt buộc để vận hành |

Ví dụ mã hiển thị: `DT01-20261030-CA02-00017`. Khóa dữ liệu thực tế là UUID, không dùng số thứ tự hiển thị làm mã xác thực. Mã không được cấp lại cho người khác khi hủy lượt hoặc xóa mẫu.

### Chống cấp trùng theo hai lớp

1. **Không trùng mã:** mã tạm có ràng buộc duy nhất trong database; số thứ tự cấp qua bộ đếm giao dịch có khóa, không dựa vào số dòng đang hiển thị hoặc cách đọc `max + 1` không khóa. Thử lại cùng request phải trả cùng mã/biên nhận.
2. **Không cấp thêm mã cho người đã có trong ca:** lấy đặc trưng mặt, so với toàn bộ người đã tiếp nhận trong ca, bao gồm cả người đã ghi Ra. Khớp rõ thì lấy lại mã đã cấp và kiểm tra trạng thái; không mở lượt lao động mới. Không chỉ tìm trong nhóm đang chờ Ra, vì như vậy có thể bỏ sót người đã hoàn tất.
3. **Hai kiosk cùng tiếp nhận:** sau khi lấy đặc trưng phải khóa phạm vi tiếp nhận, đọc lại kho mẫu/hạn mức mới nhất rồi mới cấp mã. Không để cả hai cùng quyết định người mới trên dữ liệu cũ.
4. **Ảnh mờ/không rõ hoặc kết quả gần giống:** yêu cầu thử lại/kiểm tra; không tự cấp mã vì nhận diện hụt. Ràng buộc database bảo đảm mã không trùng; việc biết hai ảnh là cùng người vẫn phụ thuộc chất lượng nhận diện, không được cam kết tuyệt đối chỉ bằng khuôn mặt.
5. **Hết giờ tiếp nhận/đã đóng ca:** từ chối cấp mã mới kể cả mẫu cũ đã hết hạn hoặc đã xóa; không mở lại ca chỉ vì không còn mẫu để so. Chỉ tiếp nhận vào ca mới được cho phép, với một mã/phiên mới theo phạm vi ca đó.
6. **Đang đọc/nhập họ tên:** mã đã giữ chỗ vẫn thuộc cùng phiên tiếp nhận. Lần quét lại, tải lại trang hoặc chuyển từ đọc tên sang nhập tay phải tiếp tục dùng mã đó. Hai kiosk gặp cùng người đang tiếp nhận không được giữ chỗ thêm mã cho người đó; kiểm tra cả phiên tiếp nhận chưa hoàn tất.

Không có mã người ổn định thì báo cáo tháng chỉ kết luận được **lượt lao động/ca**, không kết luận số người duy nhất của cả tháng. Ví dụ 20 người hôm nay và 20 người ngày mai tạo 40 lượt lao động/ngày; chưa thể nói đó là 40 người khác nhau.

## 3. Luồng vận hành hằng ngày

### 3.1. Mở đợt tiếp nhận

Trong Chấm công đối tác, tạo đợt gồm:

- Đối tác cung cấp; vị trí/sàn khai thác.
- Ngày công, giờ bắt đầu/kết thúc, khoảng cho phép Vào/Ra; hỗ trợ ca qua đêm.
- Số lao động yêu cầu và số được phép tiếp nhận.
- Quy tắc nghỉ giữa ca và cách tính thời gian đối soát.
- Chế độ tiếp nhận và thiết bị sử dụng.

Đợt có trạng thái: Nháp → Đang tiếp nhận → Đang thực hiện → Chờ đối soát → Đã chốt. Đóng tiếp nhận không được làm mất quyền quét Ra của người đã vào.

### 3.2. Lần Vào đầu tiên — kết hợp tiếp nhận và lấy mẫu

1. Kiosk đang ở phân hệ Đối tác, hiển thị rõ đối tác/ca đã được cấu hình. Người lao động không tự chọn tùy ý đối tác để ghi công.
2. Camera tự tìm mặt, kiểm tra một người, độ rõ và độ sáng; dùng một chuỗi ngắn để chọn mẫu đủ chất lượng. Không bắt chụp thủ công đủ 5 hướng.
3. Đối chiếu với toàn bộ lượt đã tiếp nhận trong phạm vi ca, kể cả người đã Ra, để tìm người đã có mã hoặc trường hợp gần giống cần kiểm tra.
4. Nếu là người chưa có, tự tiếp nhận trong đúng đợt/ca đang mở và còn hạn mức; không cần quản trị duyệt từng người.
5. Giữ một mã tạm duy nhất và mẫu mặt trong **phiên tiếp nhận đang chờ họ tên**. Hiện mã cùng yêu cầu “Vui lòng đọc đầy đủ họ và tên”. Chưa tính người đã Vào và chưa phát “Hợp lệ” ở bước này.
6. Người lao động đọc họ tên hoặc chọn Nhập tay theo luồng bên dưới. Hiển thị kết quả để kiểm tra, sửa khi cần và bấm “Xác nhận họ tên và vào ca”.
7. Kiểm tra phiên chưa hết hạn, vẫn đúng người đang trước camera và quyền/hạn mức tiếp nhận; lưu họ tên đã xác nhận, mẫu tham chiếu và lượt Vào. Chỉ hoàn tất sau khi lưu thành công; thử lại vẫn trả cùng mã/biên nhận.
8. Hiện mã tạm + họ tên, đối tác/ca và giờ Vào; đọc âm “Hợp lệ” đang dùng của OnTime. Nếu sau này có mã do đối tác cung cấp thì chỉ là thông tin bổ sung.

### 3.2.a. Thu họ tên bằng micro và nhập tay dự phòng

**Mục đích là chuyển lời nói thành văn bản họ tên, không phải nhận diện người bằng giọng nói.** Họ tên tự khai không thay thế mẫu mặt, mã tạm hoặc quyền được tiếp nhận; hai người trùng tên vẫn có mã riêng.

Giao diện cho người mới:

- Mã tạm vừa giữ chỗ; trạng thái “Chờ xác nhận họ tên”.
- Hướng dẫn “Nhìn vào camera và đọc đầy đủ họ tên”, trạng thái micro/đang nghe/đang chuyển thành chữ.
- Ô “Họ và tên” hiển thị nội dung nhận được, luôn cho sửa chữ và dấu.
- Các nút “Đọc lại”, “Nhập tay” và “Xác nhận họ tên và vào ca”. Không dùng khoảng im lặng hoặc điểm tin cậy của model để tự xác nhận tên.
- Nhập tay sử dụng ngay được, kể cả khi chưa cấp quyền micro. Micro lỗi không làm mất hình camera hoặc mã đang tiếp nhận.

Luồng giọng nói dự kiến:

1. Bật micro theo quyền trình duyệt. Sau khi thiết bị đã được cho phép, chỉ mở cửa sổ thu ngắn khi có người mới đang tiếp nhận; không nghe liên tục ngoài luồng.
2. Thu câu họ tên ngắn, đề xuất giới hạn tối đa 8 giây; hiển thị rõ đang thu và có Dừng. Không phát âm “Hợp lệ” trong lúc thu để tránh tự thu tiếng loa.
3. Gửi đoạn âm thanh tới **máy chủ local của OnTime**, chuyển thành chữ tiếng Việt và điền ô họ tên. Không gửi ra nhà cung cấp bên ngoài.
4. Người nhập/người tiếp nhận kiểm tra và xác nhận. Nhận sai thì đọc lại hoặc sửa tay; không tự đoán họ tên từ một danh sách hoặc coi câu model sinh ra là đã đúng.
5. Chỉ lưu tên đã xác nhận. Nếu chưa có tên hợp lệ thì giữ trạng thái chưa hoàn tất, không có lượt Vào thành công.

| Tình huống | Xử lý |
|---|---|
| Micro hoạt động, tên nhận đúng | Kiểm tra → xác nhận tên → hoàn tất Vào |
| Nhận sai chữ/dấu hoặc tên gần giống | Sửa ngay trong ô tên hoặc Đọc lại; giữ nguyên mã tạm |
| Sàn quá ồn, im lặng, nhiều người nói hoặc kết quả không rõ | Báo chưa nhận rõ, cho nhập tay; không tự chấp nhận một tên phỏng đoán |
| Thiếu micro, bị từ chối quyền hoặc trình duyệt không ghi được | Mở Nhập tay; camera tiếp tục hoạt động |
| Máy chủ chuyển giọng nói bị lỗi, chậm quá hạn hoặc chưa có model | Thông báo và nhập tay; không tự chuyển sang dịch vụ cloud |
| Đổi người trước camera trong lúc nhập | Không ghép tên của người sau vào mẫu người trước; yêu cầu tiếp nhận lại/khôi phục đúng phiên |
| Đã có mã/đã Vào hoặc đang quét Ra | Nhận mặt để lấy đúng mã và tên đã lưu; không yêu cầu đọc lại họ tên |

Tên được chuẩn hóa Unicode, bỏ khoảng trắng thừa/ký tự điều khiển và kiểm tra độ dài. Không dùng họ tên làm khóa chống trùng. Sửa tên sau khi đã ghi Vào cần lịch sử chỉnh sửa và quyền phù hợp; giữ nguyên mã, mặt tham chiếu và giờ đã ghi.

Phiên chờ họ tên có hạn dùng 5 phút. Hủy/hết hạn thì xóa dữ liệu thu tạm và giải phóng chỗ tiếp nhận, không tạo lượt công; mã đã giữ chỗ không tái cấp cho người khác. Trong thời gian phiên còn hợp lệ, thử lại hoặc đổi sang nhập tay không cấp thêm mã.

Một mẫu tham chiếu đạt chất lượng là điểm khởi đầu. Có thể chọn mẫu tốt từ nhiều khung camera tự động mà không tăng số lần thao tác của người chấm. Không mặc định một ảnh sẽ đáp ứng mọi ánh sáng/góc nhìn.

### 3.3. Quét Vào lại

Nếu đã ghi Vào cho cùng ca/chiều, chỉ hiện **“Đã quét vào ca”**, không đọc âm thanh, không thêm lượt, không thay giờ ban đầu và không tăng số lao động.

Vẫn dùng lại mã đã cấp. Không tự chuyển lần quét Vào tiếp theo thành Ra. Nếu người đó đã ghi cả Ra trong ca, hiển thị đã hoàn tất ca và giữ nguyên mã/lượt, không tiếp nhận lại thành người mới.

Nếu không nhận diện được, hiển thị cần nhìn thẳng/thử lại hoặc kiểm tra. **Không tự coi việc nhận diện hụt là một lao động mới.**

### 3.4. Quét Ra

1. Camera đối chiếu với toàn bộ mã tạm đã tiếp nhận trong đợt/ca của thiết bị, gồm cả người đã Ra; sau khi xác định mã mới kiểm tra điều kiện được ghi Ra.
2. Khớp rõ, có Vào hợp lệ và chưa có Ra: ghi giờ Ra; hiện mã người và đọc “Hợp lệ”.
3. Đã có Ra: chỉ hiện **“Đã quét ra ca”**, không đọc, không ghi thêm hoặc đổi giờ.
4. Không khớp/không có Vào: chưa ghi Ra, không cấp mã mới ở chiều Ra; chuyển trường hợp cần đối chiếu. Không tự ghép sang người có điểm gần nhất nếu chưa đủ điều kiện.

Ca 22:00–06:00 được gắn với ngày bắt đầu ca; không chia thành hai người hoặc hai lượt chỉ vì qua nửa đêm.

### 3.5. Đối soát và chốt

Ví dụ đợt yêu cầu 30 lao động, có 27 mã đã Vào; 24 mã đủ Vào/Ra và 3 mã chưa Ra. Báo cáo phải thể hiện đúng các nhóm này, không tự gán giờ kết thúc ca cho 3 mã thiếu Ra.

Cho phép bổ sung/điều chỉnh có lý do và lịch sử thao tác; giữ nguyên dấu vết lượt gốc. Không tự tạo lượt camera để lấp dữ liệu thiếu.

## 4. Tiếp nhận người mới tự động

Thiết bị đã ghép được quản trị gán đúng đối tác và ca. Trong khoảng tiếp nhận còn hiệu lực, hệ thống tự tìm mặt, đối chiếu người đã có mã trong ca; người mới đạt chất lượng được giữ mã tạm và mở popup đọc/nhập tên. Sau khi người lao động xác nhận tên, kiểm tra lại đúng mặt và tự ghi Vào, không chờ quản trị hoặc phiếu/QR tiếp nhận.

Tên là thông tin tự khai; các trường hợp không rõ chất lượng/khớp gần nhau vẫn phải thử lại, không tự ghép sang người gần nhất. Hạn mức, chiều Vào/Ra, thời gian đợt, quyền thiết bị và tình trạng mẫu vẫn được máy chủ kiểm tra. Tăng hạn mức cần thao tác quản trị và ghi lý do. Hai kiosk cùng tiếp nhận khóa hạn mức và kiểm tra trùng phía máy chủ để không vượt số lượng do chạy đồng thời.

Nếu có mã lao động từ đối tác, một mã chỉ gắn với một lượt lao động trong cùng ca; đổi người thay thế phải thu hồi lượt chưa thực hiện hoặc ghi nhận thay thế rõ ràng, không ghi đè mặt của người đã chấm.

## 5. Quy tắc Vào/Ra và ra vào nhiều lần

**Đã chốt cho bản đầu: một mã tạm, một cặp Vào/Ra trong ca; giữ riêng chiều Vào/Ra của kiosk.** Không dùng quy tắc lần quét thứ hai tự thành Ra.

| Trạng thái của người trong ca | Chiều đang quét | Xử lý |
|---|---|---|
| Chưa có mã | Vào | Tiếp nhận hợp lệ → giữ mã tạm duy nhất → đọc/nhập và xác nhận họ tên → ghi Vào |
| Đang chờ họ tên | Vào | Dùng phiên/mã đang giữ chỗ, tiếp tục bổ sung tên; chưa tính đã Vào |
| Đang chờ họ tên | Ra | Báo chưa hoàn tất lượt Vào; không ghi Ra và không cấp mã khác |
| Đã Vào, chưa Ra | Vào | Hiện mã cũ và “Đã quét vào ca”; không âm thanh, không cấp mã/ghi thêm |
| Đã Vào, chưa Ra | Ra | Dùng mã cũ, ghi Ra; đọc “Hợp lệ” |
| Đã ghi Ra | Ra | Hiện mã cũ và “Đã quét ra ca”; không âm thanh, không ghi thêm |
| Đã ghi Ra | Vào | Hiện mã cũ và “Đã hoàn tất ca”; không cấp lại mã hoặc tạo lượt mới |
| Chưa có mã | Ra | Báo chưa có lượt Vào; không cấp mã, không tự tạo cặp |

Chế độ nhiều lượt dưới đây chỉ là hướng mở rộng sau, không thuộc quy tắc vừa chốt. Nếu sau này lao động được ra ngoài nghỉ rồi quay lại trong cùng ca và cần ghi từng đoạn, có thể bổ sung **Theo dõi nhiều lượt ra/vào** riêng cho đối tác:

- Cho phép Vào → Ra → Vào → Ra thành nhiều đoạn thời gian hợp lệ.
- Quét liên tiếp cùng chiều vẫn chỉ thông báo, không ghi thêm/không phát âm thanh.
- Tổng thời gian là các đoạn được ghép đúng; xử lý khoảng nghỉ để không trừ hai lần.
- Không tự sửa quy tắc đang dùng cho nhân viên công ty.

Không được dùng số mã “đã Vào nhưng chưa Ra” như cam kết số người thực tế trên sàn nếu người lao động có thể ra ngoài không quét. Màn hình nên ghi **“Chưa ghi lượt Ra”** thay cho khẳng định hiện diện tuyệt đối.

## 6. Chức năng và màn hình dự kiến

Thêm lối vào rõ ràng **Chấm công đối tác** trong OnTime; quyền và phạm vi của thiết bị được máy chủ kiểm tra, không chỉ đổi nhãn trên giao diện.

| Màn hình | Chức năng chính |
|---|---|
| Đối tác | Mã/tên đối tác, trạng thái sử dụng; chưa cần tài khoản đăng nhập riêng cho đối tác |
| Đợt/ca tăng cường | Ngày công, sàn, giờ ca/nghỉ, số yêu cầu/hạn mức, mở/đóng tiếp nhận, chọn thiết bị |
| Tiếp nhận lao động | Tự bắt mặt, mã tạm, cho phép tiếp nhận, đọc họ tên qua micro, nhập/sửa tay và xác nhận; xử lý trùng/nghi ngờ; số còn được nhận |
| Kiosk Đối tác | Camera toàn cảnh, chiều Vào/Ra, đối tác/ca đang dùng, mã + họ tên khi có kết quả, âm báo đúng quy tắc |
| Theo dõi và đối soát | Đã Vào, đã Ra, thiếu cặp, giờ đầu/cuối, thời gian đủ điều kiện, điều chỉnh có lý do, chốt đợt, xuất CSV |

Bộ lọc báo cáo: khoảng ngày, đối tác, sàn, ca, trạng thái đủ/thiếu lượt. Báo cáo được giữ sau khi mẫu mặt đã xóa.

Giờ giữa Vào và Ra là thời gian ghi nhận tại điểm quét; giờ công để đối soát còn phụ thuộc nghỉ giữa ca và quy tắc đã thống nhất. Chưa tự tính đơn giá, tiền thanh toán hoặc hệ số ngoài giờ khi chưa có quy tắc từ công ty.

## 7. Dữ liệu tạm và vòng đời

| Dữ liệu | Cách xử lý đề xuất |
|---|---|
| Đối tác và định nghĩa đợt/ca | Giữ trong SQL Server để quản lý và đối soát |
| Mã lao động tạm và họ tên đã xác nhận | Giữ cùng chứng từ công để đối soát từng người; họ tên được thu ngay khi tiếp nhận, không trở thành hồ sơ nhân viên công ty |
| Nguồn nhập tên và thời điểm xác nhận | Lưu đọc giọng nói / nhập tay / đọc rồi sửa tay; hỗ trợ đối soát và lịch sử chỉnh sửa |
| Bản ghi giọng nói gốc | Chỉ xử lý tạm để lấy chữ; mặc định xóa sau xử lý hoặc khi hủy/lỗi/hết hạn. Không lưu để nhận diện giọng nói, không đưa vào backup/log |
| Ảnh camera gốc | Mặc định không lưu lâu dài; chỉ xử lý để lấy mẫu/so khớp |
| Vector khuôn mặt tạm | Có phạm vi đối tác/ca, phiên bản model, trạng thái, hạn dùng; đề xuất hết hạn 48 giờ sau kết thúc ca |
| Lượt Vào/Ra, biên nhận, điều chỉnh, chốt | Giữ theo chính sách bảng công do công ty duyệt |
| Nhật ký kỹ thuật | Không ghi ảnh/vector/token vào log |

Mốc 48 giờ là **đề xuất vận hành để duyệt**, không phải thời hạn pháp luật được suy ra. Xóa theo thời điểm kết thúc ca thực tế đã cấu hình, không xóa hàng loạt lúc 00:00 gây hỏng ca đêm. Thiếu Ra phải cảnh báo trước khi hết hạn; không tự giữ sinh trắc học vô thời hạn.

Sau khi mẫu đã xóa, OnTime vẫn xem/xuất được mã và bảng công; không còn tự nhận lại khuôn mặt cũ chỉ từ báo cáo. Người đến ca/ngày mới có thể được tiếp nhận thành phiên mới. Không âm thầm tạo hồ sơ mặt thường trực từ các phiên tạm.

**Lưu ý bản sao lưu:** xóa ở database đang chạy không đồng nghĩa mẫu đã biến mất khỏi bản sao lưu cũ. Full backup SQL Server hiện có không loại trừ riêng một bảng sinh trắc học. Hướng thiết kế đề xuất là giữ dữ liệu bảng công trong SQL Server, tách kho mẫu mặt tạm local có mã hóa khỏi phạm vi backup bảng công. Kho này tồn tại qua lần khởi động lại bình thường nhưng không được phục hồi từ backup dài hạn. Nếu kho tạm bị mất, giữ bảng công và xử lý đối chiếu/tiếp nhận lại có kiểm soát, không giả vờ đã nhận diện được.

Cần rà soát cả danh sách tệp backup và quy trình khôi phục để mẫu hết hạn không bị sống lại. Thời hạn giữ chứng từ công, mẫu mặt và backup là ba cấu hình khác nhau. Giao diện cần thông báo mục đích và thời hạn giữ mẫu cho người được tiếp nhận; vector vẫn là dữ liệu sinh trắc học, không coi là vô danh chỉ vì không lưu ảnh.

## 8. Khả năng công nghệ và cách mở rộng OnTime

Khả thi với mô hình local hiện tại. OpenCV cung cấp các bước phát hiện mặt, trích đặc trưng và so khớp đặc trưng; việc lấy một mẫu tạm lúc Vào để so với lúc Ra không cần huấn luyện lại model cho từng người. Tài liệu này là cơ sở kỹ thuật, không phải bảo đảm độ chính xác của môi trường sàn thực tế. [Tài liệu OpenCV](https://docs.opencv.org/4.12.0/d0/dd4/tutorial_dnn_face.html).

Đối chiếu mã nguồn OnTime hiện tại:

- Hồ sơ mặt và lượt công đang gắn với `employees`; phiên nhận diện cũng ràng buộc `employee_id`. Vì vậy không thể chỉ thêm một nút hoặc ẩn vài trường nhập để có đúng luồng mới.
- Có thể dùng lại camera toàn cảnh, bộ trích đặc trưng local, kiểm tra chất lượng, kiểu giao diện, âm báo, quyền kiosk và cơ chế thử lại không ghi hai lần.
- Cần bổ sung miền dữ liệu riêng: đối tác, đợt/ca, lượt lao động tạm, mẫu tạm/hạn dùng, phiên nhận diện đối tác, sự kiện Vào/Ra và biên nhận riêng.
- Tách phạm vi dữ liệu và kiểm tra quyền phía server. Không đưa kho mẫu thời vụ vào danh sách nhận diện nhân viên công ty; không dùng “không khớp nhân viên” làm điều kiện tự đăng ký lao động đối tác.
- Cần xử lý lưu mẫu và ghi Vào an toàn: giao dịch lỗi không để lại người đã đếm nhưng chưa có mẫu, hoặc phát “Hợp lệ” khi lượt Vào chưa lưu. Sau restart phải xử lý được phiên dở và tệp tạm.
- Chuẩn bị thay đổi bằng migration có backup/rollback, dùng database thử cô lập và kiểm thử cạnh tranh trên SQL Server. Giữ đường dẫn/cấu hình độc lập laptop để chuyển VM.

Giữ công nghệ miễn phí, local, không Docker, không CDN và không gọi API nhận diện trả phí. Dung lượng và tải chủ yếu tùy số lượt/đợt đang mở, số máy quét đồng thời và lưu lượng lúc đầu ca; chưa có số đo thì chưa cam kết thời gian xử lý hoặc khả năng thông qua cụ thể.

### Phương án kỹ thuật nhận họ tên qua micro

- **Thu âm trên thiết bị, chuyển thành chữ trên máy chủ local.** Đề xuất thử `faster-whisper` với model Whisper đa ngôn ngữ hỗ trợ tiếng Việt; khởi đầu đánh giá bản `small` chạy CPU INT8. Đây là lựa chọn để đo thử, chưa cài đặt/chưa cam kết độ trễ hoặc độ đúng tên riêng trên sàn. Runtime hỗ trợ CPU INT8 và model trong thư mục local: [tài liệu faster-whisper](https://github.com/SYSTRAN/faster-whisper). Tiếng Việt có mã `vi` trong [Whisper tokenizer](https://github.com/openai/whisper/blob/main/whisper/tokenizer.py).
- Thư viện faster-whisper có [giấy phép MIT](https://github.com/SYSTRAN/faster-whisper/blob/master/LICENSE); việc đóng gói vẫn cần giữ notice và kiểm tra giấy phép các thành phần/model đi kèm. Không có phí theo lượt chuyển giọng nói. Model và dependency chuẩn bị một lần khi cài đặt; vận hành chỉ nạp bộ tệp local đầy đủ, kiểm checksum, không tự tải model/tokenizer hoặc gọi API khi có người đọc tên.
- Không dùng nhận giọng nói mặc định của trình duyệt làm phương án bảo đảm local. MDN nêu một số trình duyệt dùng dịch vụ máy chủ và gửi âm thanh ra web service; khả năng offline không đồng nhất: [SpeechRecognition](https://developer.mozilla.org/en-US/docs/Web/API/SpeechRecognition).
- Thu qua `getUserMedia`/`MediaRecorder`, kiểm tra định dạng được hỗ trợ tại thiết bị bằng `isTypeSupported`; máy chủ giải mã định dạng được phép. Không mặc định mọi iPad/Android cùng ghi WebM. Tham khảo [MediaRecorder.isTypeSupported](https://developer.mozilla.org/en-US/docs/Web/API/MediaRecorder/isTypeSupported_static).
- Micro cần người dùng cho phép và ngữ cảnh an toàn: localhost trên laptop hoặc HTTPS tin cậy khi tablet truy cập qua LAN. HTTP qua địa chỉ IP LAN không được xem là localhost của tablet. Không cần cài Caddy cho bước lập phương án này: [getUserMedia](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia).
- Chuyển giọng nói chạy ở worker/hàng đợi local có giới hạn CPU, số yêu cầu và thời gian chờ; không chặn luồng nhận diện mặt. Tắt dịch vụ giọng nói vẫn dùng được nhập tay. Cần đo trên laptop/VM thực tế trước khi quyết định model và mức tải.
- Mỗi đoạn thu gắn với phiên tiếp nhận/mã đang giữ chỗ và kiosk hợp lệ; giới hạn dung lượng/thời lượng, dọn tệp tạm khi lỗi hoặc restart. Phản hồi giọng nói đến muộn sau khi đã nhập tay/hủy/đổi người không được ghi đè tên hoặc hoàn tất nhầm phiên.
- Chỉ xử lý chuỗi họ tên như dữ liệu văn bản. Không dùng giọng nói làm mật khẩu, bằng chứng tên thật hoặc mẫu sinh trắc học bổ sung. Xử lý giọng nói không thay thế việc được phép tiếp nhận người mới.

Nhận diện đúng người và chống dùng ảnh/video để quét hộ là hai vấn đề khác nhau. OnTime hiện chưa nghiệm thu PAD trên nhóm người thật; không coi phân hệ mới tự giải quyết được hạn chế đó. Bản hiện hành tiếp nhận tự động theo yêu cầu người dùng, báo trường hợp không rõ và giữ lịch sử để đối soát. Tham khảo khái niệm [Presentation Attack Detection của NIST](https://csrc.nist.gov/glossary/term/Presentation_Attack_Detection); không coi đây là chứng nhận cho OnTime.

## 9. Các bước triển khai sau khi được duyệt

| Bước | Kết quả cần có để kiểm tra tiến độ |
|---|---|
| P0 — Chốt nghiệp vụ | Mức định danh cần lưu, quyền tiếp nhận, số lượt trong ca, thời hạn mẫu và quy tắc đối soát |
| P1 — Đối tác/đợt/ca | Tạo đối tác, mở đợt, hạn mức, cấu hình thiết bị; dữ liệu tách khỏi nhân viên công ty |
| P2 — Tiếp nhận và Vào | Một người thật được bắt mặt, giữ mã tạm, đọc họ tên hoặc nhập tay, xác nhận tên và ghi Vào; không cần hồ sơ/ảnh có sẵn |
| P3 — Ra và chống trùng | Nhận lại người đã Vào; quét trùng chỉ hiện chữ; thử mất phản hồi, đổi người, hai kiosk và ca đêm |
| P4 — Đối soát/vòng đời | Báo cáo đủ/thiếu, điều chỉnh/chốt, xuất CSV; xóa mẫu đúng hạn; restart/khôi phục không làm mất bảng công hoặc sống lại mẫu hết hạn |
| P5 — Chạy thử và mở sử dụng | Hoàn tất luồng với số người thực tế sẵn có; đo lưu lượng và chất lượng với nhiều lao động/thiết bị thành hạng mục riêng |

Codex thực hiện phần phát triển và kiểm thử phần mềm. Chỉ cần người dùng cung cấp quy tắc thực tế và thao tác người thật/thiết bị khi không thể tự thực hiện. Không bắt buộc huy động một nhóm đông người trước khi hoàn thành luồng đầu-cuối; không dùng kiểm thử giả lập để kết luận độ chính xác thực tế.

## 10. Tiêu chí kiểm tra bản đầu

- Không cần thêm người thời vụ vào Nhân viên công ty.
- Tạo/đóng đợt đúng đối tác, ca và hạn mức; thiết bị không ghi nhầm sang đợt khác.
- Lần Vào đầu tiên kết hợp lấy mẫu, giữ mã tạm, thu/xác nhận họ tên và lưu giờ Vào thành công. Chờ tên không được tính là đã Vào/phát “Hợp lệ”.
- Tên đọc tiếng Việt có thể sửa dấu/chữ; nhập tay hoạt động khi từ chối quyền micro, không có micro, mất dịch vụ STT hoặc sàn nhiều tiếng ồn.
- Không đòi đọc tên lại khi đã có mã hoặc khi quét Ra; đổi cách nhập/đọc lại/tải lại không sinh mã mới.
- Không có nhận dạng đáng tin từ im lặng/tiếng loa; không tự xác nhận một tên chỉ vì model trả văn bản. Có bước kiểm tra tên.
- Hủy/hết hạn/đổi người hoặc phản hồi STT đến muộn không làm ghép sai tên–mặt hay ghi đè tên nhập tay.
- Âm thanh gốc được dọn sau xử lý/hủy/lỗi và không vào backup/log; chạy thử cắt mạng ngoài vẫn đọc tên bằng model local hoặc chuyển nhập tay rõ ràng.
- Mã tạm không trùng kể cả hai kiosk đồng thời; thử lại cùng request không sinh mã mới; hủy lượt không tái sử dụng mã cho người khác.
- Người đã Vào không bị tạo thành người mới khi nhận diện hụt; không tăng số lượng do quét lại hoặc thử lại request.
- Nhận lại người đã ghi Ra cũng giữ mã cũ; không cấp thêm mã cho cùng người trong chính ca đó.
- Giữ đúng chiều kiosk; quét lại chiều Vào không tự ghi Ra, chiều Ra không được tiếp nhận/cấp mã mới.
- Người quét Ra được so với mẫu đã tiếp nhận; người chưa có Vào không được tự tạo cặp.
- Quét lại cùng chiều chỉ hiện chữ; không âm thanh, không sửa giờ, không thêm lượt.
- Ca qua đêm, nhiều đợt gần nhau, hai kiosk đồng thời và hết hạn mẫu không làm ghép sai lượt.
- Thiếu Ra được báo riêng; không tự tính đủ công. Sửa công phải có lý do và lịch sử.
- Hết hạn mẫu vẫn xem/xuất bảng công; backup/khôi phục không tái kích hoạt mẫu hết hạn.
- Luồng nhân viên công ty, tài khoản và dữ liệu hiện có không bị đổi nghiệp vụ.

## 11. Nội dung đã chốt và các điểm còn cần duyệt

Đã chốt:

1. Đối soát theo từng lao động bằng mã tạm do OnTime cấp; không yêu cầu có mã đối tác trước.
2. Nhận lại khuôn mặt đã tiếp nhận trong ca để lấy đúng mã cũ; không cấp thêm mã dù người đó đã quét Ra.
3. Giữ riêng chiều Vào/Ra: quét lại Vào chỉ thông báo đã vào, quét chiều Ra mới được ghi Ra; một cặp trong ca.
4. Thu họ tên tại lần tiếp nhận mới bằng micro thiết bị; có nhập/sửa tay khi micro hoặc nhận giọng nói không đáp ứng. Họ tên đã xác nhận gắn với đúng mã tạm và mẫu mặt của phiên, không đòi hồ sơ từ trước.

Lựa chọn cho bản đầu theo yêu cầu bắt đầu triển khai kế hoạch:

1. Tiếp nhận tự động tại kiosk đã ghép và gán đúng ca, sau xác nhận tên và kiểm tra đúng mặt; không có bước quản trị duyệt từng người hoặc phiếu một lần. Khuôn mặt và họ tên tự khai không chứng minh danh tính pháp lý.
2. Mẫu tạm hết hạn 48 giờ sau kết thúc ca; bảng công giữ riêng. Không giữ kho mặt thời vụ thường trực.

Thông tin cần bổ sung trước khi đo tải/mở sử dụng: số lao động tối đa trong một ca, khung giờ dồn người đến và số điểm quét đồng thời. Những thông tin này chưa cản trở việc duyệt kiến trúc và hoàn thành một luồng thử ban đầu.


## 12. Tiến độ triển khai theo Goal

Goal mới đã tạo ngày 30/10/2026, trạng thái active. Không thay thế hoặc đánh dấu hoàn thành các phần kiểm định còn lại của Goal nhân viên công ty trước đây.

- [x] P0: chốt phạm vi bản đầu — tiếp nhận tự động sau xác nhận tên/đúng mặt (thay lựa chọn duyệt thủ công theo yêu cầu mới nhất), một cặp Vào/Ra, mã tạm, micro local/nhập tay, mẫu hết hạn 48 giờ sau ca.
- [x] P1: dữ liệu/API và UI đối tác, đợt/ca, hạn mức, gán thiết bị; kiểm thử và migration SQL Server.
- [x] P2: triển khai và kiểm thử kỹ thuật kho mẫu tạm, cấp mã không trùng, mặt + họ tên + nhập tay/STT local, tự động tiếp nhận và ghi Vào; thử người thật nằm ở P5.
- [x] P3: triển khai và kiểm thử kỹ thuật nhận lại đúng mã, ghi Ra, quét trùng im lặng, mất phản hồi/thử lại/hai kiosk/ca đêm; nghiệm thu thiết bị/người thật nằm ở P5.
- [x] P4: bảng công, điều chỉnh/chốt, CSV, hết hạn mẫu, restart/backup/khôi phục không hồi sinh mẫu; đã kiểm thử kỹ thuật và cập nhật bản chạy.
- [x] P5: đã thử một người thật trên laptop, giọng nói/xác nhận tên, tự Vào, Ra, âm báo và quét trùng; đối chiếu SQL/bảng công/CSV, cập nhật bản chạy/bộ cài. Đo theo nhóm/PAD/thiết bị/tải và độ trễ tên thực tế ghi riêng, chưa gán đạt.

### Kết quả P2/P3 — 30/10/2026

- Bản chạy đã nâng cấp tới migration `20261030_partner_admission`, sau backup SQL/checksum; nhận diện và chấm công nhân viên vẫn bật. Dữ liệu thật hiện chỉ có đối tác D23, chưa có ca/lao động/lượt công đối tác giả.
- Camera đối tác nằm ở `#partner`, toàn cảnh và quét tự động, có bám khung mặt trực quan, Vào/Ra riêng, Tùy chọn bật/tắt camera/ghép thiết bị/thử giọng. Thiết bị gán đợt đối tác bị chặn ghi công vào phân hệ nhân viên.
- Mã duy nhất dạng `D23-20261030-C0001-00001`; UUID và ràng buộc SQL bảo vệ giao dịch. Khớp cả người chờ tên, đã Vào và đã Ra trong ca. Mất phản hồi tra cứu lại cùng yêu cầu; quét trùng giữ giờ và sự kiện cũ, không đọc Hợp lệ.
- Tên được nhập tay hoặc đọc qua MediaRecorder; faster-whisper-small tiếng Việt, CPU INT8 local, 2 luồng, tiến trình riêng bị chặn mạng, ONNX telemetry tắt. Audio tối đa 8 giây/2 MB trong RAM, không lưu file/log/SQL. Bản nháp luôn cần kiểm tra và xác nhận; kết quả giọng nói tới muộn không ghi đè tên nhập tay.
- Người mới giữ mã trong phiên 120 giây, xác nhận tên, được quản trị cho phép và quét lại đúng mặt trước khi ghi Vào. Hủy/hết phiên không tự ghi công; không tái sử dụng số đã cấp. Chuỗi mặt ngắn không phải bằng chứng PAD.
- Mẫu tạm mã hóa bằng khóa riêng ngoài backup; bị từ chối ngay khi hết hạn và tác vụ khởi động/chu kỳ 30 giây dọn file hết hạn. Kho mất/hỏng không được tự tái tạo danh tính. Trọng số giọng nói khoảng 484 MB thuộc bộ cài offline, không đưa vào backup dữ liệu 256 MiB.
- Kiểm chứng: 355 backend passed/8 native-only skipped; SQL Server cô lập 250 passed, 0 nonlocal network attempts; frontend 45 passed và build/Ruff đạt. Sau bổ sung kiểm tra vòng đời, nhóm đối tác 27 passed/2 native-only skipped; kiểm tra riêng ca đêm/vòng đời 9 passed. Đây là kiểm tra chức năng/giao dịch, không chứng minh độ chính xác nhận diện/PAD hoặc đọc tên thực tế.
- Codex browser đã thấy D23, màn hình tiếp nhận và kiosk; 768/390 không tràn ngang, đã reset viewport. Bằng chứng `evidence/m5/partner-p2-check.json`, `partner-p2-admin.png`, `partner-p2-d23.png`, `partner-speech-pipeline.json`.
- Tiếp theo: P4 báo cáo/điều chỉnh/chốt/CSV và kiểm tra khôi phục; P5 chạy một người thật, thử micro/nhập tay/Vào/Ra/âm báo. Chưa đánh dấu Goal hoàn thành.

Nhật ký ban đầu P1: đã viết migration và 3 bảng riêng partner_vendors/partner_batches/partner_device_bindings; API quản trị có xác thực/CSRF, kiểm trạng thái, snapshot ngưỡng/model đang vận hành khi mở đợt (không nhận ngưỡng do client gửi), hạn mức và audit. Đã có UI cấu hình trong Quản trị → Chấm công đối tác. 13 kiểm thử tập trung đạt trên database cô lập; đang chạy kiểm thử hồi quy và SQL Server. Chưa migration vào database đang chạy hoặc tạo đối tác giả trong dữ liệu thật.

Kết quả P1 (mốc trước P2): 330 kiểm thử hồi quy backend đạt/6 native-only skipped; SQL Server cô lập 229 passed, 0 lần thử mạng ngoài; 13 ca tập trung đối tác đạt, build/Ruff đạt. Migration 20261030_partner_batches đã áp dụng sau backup SQL/checksum và supervisor khởi động lại ready=true. Đã tạo đúng một đơn vị do người dùng yêu cầu: D23 — Đối tác sàn D23; không tạo ca/nhân sự giả trong DB thật. Codex browser thấy phân hệ và D23; viewport 768/390 không tràn và đã reset. Bằng chứng evidence/m5/partner-p1-check.json và partner-p1-setup.png. P2 đã có lớp kho vector tạm mã hóa với khóa riêng, kiểm phạm vi/hạn dùng và không lọt vào backup allowlist; 6 kiểm thử cô lập đạt. Kho này chưa nối vào camera hoặc bật tiếp nhận lao động. Goal tiếp tục active để hoàn thiện P2–P5, không coi P1 là hoàn thành phân hệ.


### Kết quả P4 — 30/10/2026

Đã triển khai và cập nhật bản chạy tới migration `20261030_partner_reports` sau backup SQL/checksum. Có lọc ngày/đối tác/sàn/ca và trạng thái; giờ gốc/đối soát, số yêu cầu riêng hạn mức, nghỉ có/không tính công, thiếu cặp không tự có giờ công; lịch sử điều chỉnh append-only, kiểm nguồn chống sửa đè; chốt bất biến có checksum và xác nhận dòng thiếu; CSV đúng nguồn/bộ lọc và chống công thức. Chạy thử được đánh dấu trong báo cáo/CSV, chưa tính tiền.

Khôi phục SQL đã thử thật trên database cô lập: giữ sự kiện, điều chỉnh/bản chốt và kiểm số bản ghi đối tác, không phục hồi kho mặt/khóa tạm. Thu hồi phiên/quyền kiosk, bỏ gán điểm đối tác và dừng chính sách sau khôi phục. Có cảnh báo dọn kho tạm trong Vận hành.

Kiểm chứng: hồi quy backend 370 passed/10 native-only skipped; SQL Server đầy đủ 273 passed/0 nonlocal attempts, bộ SQL sau sửa 30 passed; nhóm cuối 34 passed/2 native-only skipped; allowlist backup 16 passed; frontend 48 passed, build/Ruff đạt. Codex browser thấy báo cáo đợt thực tế cấu hình với 0 lao động, 768/390 không tràn và đã reset viewport. Bằng chứng `evidence/m5/partner-p4-check.json`, `partner-p4-report-summary.png`; hướng dẫn `docs/CHAM_CONG_DOI_TAC.md`.

### P5 đang thực hiện

Đã tạo đúng một đợt riêng `Thử chức năng D23 — 1 người`, sàn `D23 (thử chức năng)`, ca mẫu 08:00–17:00, nghỉ không tính công 12:00–13:00, yêu cầu/hạn mức 1; cấu hình nhận diện đang là functional_trial và báo cáo không dùng thanh toán. Đã có điểm `Kiosk thử D23 (laptop)` riêng gán đợt. Chưa ghép lại trình duyệt, chưa mở camera hoặc tự tạo lao động/lượt công đối tác; điểm nhân viên cũ không bị đổi gán. Đã hỏi người dùng về việc thử camera/micro bằng người thật và đang chờ sẵn sàng.

Bộ cài candidate v1 có frontend/model giọng nói/wheels offline, đã cài vào venv mới và kiểm tra chuyển thư mục, phục vụ web/audio, pipeline giọng nói local và đường dẫn riêng bị chặn. Candidate v2 bổ sung hướng dẫn và cập nhật UI cuối đang xác minh. Chưa nghiệm thu người thật, độ chính xác theo nhóm hoặc PAD; Goal tiếp tục active.


### Điều chỉnh UI theo người dùng — popup họ tên riêng

Người dùng yêu cầu tách bước bắt mặt và khai tên. Đã thay thẻ nhập tên bên dưới camera bằng popup giữa màn hình: Đọc họ tên/Nhập bằng tay, kiểm tra/sửa, xác nhận; nút xác nhận/hủy luôn ở footer, nội dung cuộn trong popup. Camera tạm dừng xử lý mặt trong lúc nhập/chờ duyệt, giữ mã và khôi phục phiên sau reload. Chỉ khi xác nhận mới lấy chuỗi mặt mới ràng buộc đúng worker_id; người khác không tạo thêm mã phía sau. Phiên nhập tên mới 5 phút (thay lựa chọn 120 giây ban đầu); hết hạn phải bấm Quét lại. Có cơ chế các tab OnTime nhường camera cho nhau.

Kiểm tra: backend toàn bộ 377 passed/10 native-only skipped; SQL cô lập 17 passed, 0 nonlocal attempts; nhóm backend thay đổi 21 passed/2 skipped; frontend 56 passed và build/Ruff đạt. Popup đã kiểm tra hình thức tại 768×1024/390×700, footer nằm trong khung và viewport đã reset. Ảnh partner-name-popup-voice.png/partner-name-popup-manual.png là xem trước UI, không có lượt công hoặc bằng chứng độ chính xác.

Bản chạy đã cập nhật. Thử thật chưa xong: camera báo Could not start video source/NotReadableError; đã yêu cầu người dùng chỉ giữ một tab OnTime, tắt nguồn camera khác và thử lại. Không tự gán đạt P5. Bộ cài candidate v2 trước đó đã cài offline/giọng nói local thành công; chưa phải bộ cài cuối cho popup mới. Ổ E hiện không được nhận; đã tạo bản mã hóa local 123.9 MB/checksum đúng, giữ cấu hình E để bổ sung khi kết nối lại.

Bộ cài `partner-candidate-20261030-v3` đã chứa popup, phối hợp nhường camera giữa các tab và bản frontend mới. Đã xác minh 217 tệp theo checksum, cài wheels hoàn toàn offline vào venv mới, chạy web/audio/model/STT tại thư mục chuyển chỗ với mạng ngoài bị chặn; không mở/sửa database thật, không kèm dữ liệu cá nhân. Bằng chứng `evidence/m5/native-release-check.json`. Frontend cuối chạy lại 56/56 đạt và build thành công. P5 vẫn chờ người thật mở được camera, thử nhập/đọc tên và Vào/Ra/âm báo; không coi ảnh xem trước popup là nghiệm thu luồng thật.

### Điểm chờ P5 — 30/10/2026, 12:50

Kiểm tra chỉ đọc bản chạy: HTTP health 200; 1 đợt đang mở, 2 dòng giữ mã ở trạng thái pending, 0 sự kiện Vào/Ra đối tác. Chưa có kết quả người dùng xác nhận mở lại camera/micro sau lỗi nguồn video gần nhất. Cùng điểm chờ đã lặp qua ba lượt Goal liên tiếp; các công việc phần mềm/bộ cài độc lập đã hoàn tất, không còn bước nghiệm thu thật có thể tự làm thay người đứng trước camera. Goal chuyển blocked, P5 giữ chưa hoàn tất. Không tạo tên/lượt công hoặc gán nhãn người thật để vượt qua bước này.

Để tiếp tục: mở duy nhất tab OnTime dùng để thử, bật camera; khi popup hiện, đọc hoặc nhập họ tên rồi xác nhận và báo kết quả. Codex tiếp tục duyệt tiếp nhận trong đợt thử, kiểm tra Vào, quét trùng im lặng, Ra, quét trùng Ra và âm báo theo kết quả thật. Không thay đổi mục tiêu hoặc bỏ các tiêu chí này.

Cập nhật sau phản hồi: người dùng xác nhận đã thấy hình camera và popup họ tên. Phiên sau đó hết hạn trước khi hoàn tất tiếp nhận; không khôi phục hay ghi Vào từ phiên hết hạn. Đã chuẩn bị sẵn quản trị tiếp nhận đúng đợt thử D23, chờ người dùng bấm Quét lại, xác nhận tên và giữ mặt trước camera để duyệt ngay trong phiên mới. Chưa có bằng chứng Vào/Ra/âm báo đối tác thực tế.

Phiên thử tiếp theo: người dùng báo đã xác nhận tên và đang chờ tiếp nhận. Codex đã duyệt đúng phiên còn hạn qua giao diện quản trị; kiểm tra chỉ đọc SQL xác nhận có thời điểm xác nhận tên và cho phép tiếp nhận, chưa có sự kiện công tại thời điểm kiểm tra. Đã yêu cầu giữ mặt trước camera chiều Vào để xác minh lượt đầu/âm báo và quét lặp im lặng. Ảnh giao diện chứa họ tên được giữ riêng trong .runtime, không đưa vào bộ cài/Git. P5 chưa hoàn tất.

### Điều chỉnh yêu cầu — tự động tiếp nhận

Theo yêu cầu mới nhất của người dùng, đã bỏ chờ duyệt quản trị: bắt mặt → popup đọc/nhập họ tên → xác nhận tên → kiểm tra lại đúng mặt → tự động ghi Vào và phát Hợp lệ. Đã bỏ API/nút duyệt từng người, thay vùng quản trị bằng theo dõi tiếp nhận tự động; context/API/báo cáo cùng thể hiện luồng mới. Lịch sử duyệt trước đây giữ nguyên, không gán hành động cho tài khoản quản trị ở các lượt tự động.

Phiên đã xác nhận tên từ bản cũ còn hạn được tự tiếp tục sau khi có proof mặt mới, không cần nhập lại hoặc duyệt. Phiên hết hạn không hồi sinh và không tự ghi công. Giữ kiểm tra quyền thiết bị, đúng đợt/chiều/thời gian, hạn mức, chống cấp trùng, tên đã xác nhận, proof đúng worker và lượt trùng im lặng. Không đổi model/ngưỡng hoặc nghiệp vụ nhân viên công ty; không sửa tay dữ liệu thật để chứng minh thử thành công.

Kiểm chứng: backend 379 passed/10 native-only skipped; SQL cô lập nhóm đối tác 56 passed/0 mạng ngoài; sau sửa context/nhãn cuối có thêm 32 passed/4 native-only skipped, SQL chấm công 19 passed/0 mạng ngoài; frontend 57 passed, build/Ruff đạt. Đã restart bản chạy, health 200. Codex browser thấy Theo dõi tiếp nhận tự động, không còn nút Cho phép tiếp nhận. Bằng chứng `evidence/m5/partner-auto-admission-check.json`, `partner-auto-admission-ui.png`; hướng dẫn hiện hành đã cập nhật trong `docs/CHAM_CONG_DOI_TAC.md`. P5 còn kiểm tra người thật tự Vào/Ra/âm báo sau thay đổi này; chưa đánh dấu hoàn tất.

### P5 — đã tự ghi Vào, điều chỉnh độ trễ giọng nói và âm báo

Người dùng xác nhận đã tự ghi Vào nhưng chưa nghe âm báo. SQL chỉ đọc xác nhận 1 lượt Vào, 1 lao động active và tên có nguồn voice; không tự tạo lượt để vượt nghiệm thu. Bộ cài v4 cho tiếp nhận tự động đã xác minh offline vào venv mới thành công.

Đã xử lý hai nguồn chờ đọc tên: thu âm tự kết thúc sau khoảng lặng khi đã có tiếng nói đủ mức, vẫn cho bấm micro gửi ngay/nhập tay và giới hạn 8 giây; máy chủ nạp sẵn model/VAD trong nền, không nhận micro ở bước nạp. Phiên đầu chờ dùng chung model đang nạp thay vì lỗi bận. Giữ model small, INT8, 2 luồng và beam 3; thử 4 luồng không nhanh hơn nên không đổi cấu hình. Tệp công khai 0.775 giây cho kết quả khoảng 9 giây lượt lạnh, 2.3–5 giây khi đã nạp tùy phép đo/tải; không suy rộng thành tốc độ hoặc độ chính xác tên người thật.

Âm báo dùng chính tệp Hợp lệ hiện có qua Web Audio mở quyền trong thao tác bấm; có fallback và nút Bật âm thanh khi trình duyệt chặn, không treo âm thầm nếu resume chờ quyền. Lượt trùng vẫn im lặng. Đã restart bản chạy với nạp model trong nền; frontend 63 passed/build đạt, backend 381 passed/10 native-only skipped, 8 ca speech đạt cả SQL cô lập/0 mạng ngoài, Ruff đạt. Bằng chứng `evidence/m5/partner-voice-latency-check.json`. Chờ người dùng thử nghe và Ra/quét trùng Ra; chưa gán đạt nghe trên thiết bị, độ trễ tên thực tế hoặc P5 hoàn tất.

### Hoàn thành P5 và đối chiếu phạm vi

Người dùng xác nhận nghe được âm thử, đã Ra và không đọc lặp. SQL thật xác nhận đúng một cặp Vào/Ra cùng worker, thứ tự thời gian đúng; các biên nhận duplicate ở cả hai chiều không làm tăng số sự kiện. Tên nguồn voice, không thêm Employee. UI báo cáo 1 cặp đủ, 0 thiếu, 0 đang tiếp nhận; CSV tải từ quản trị khớp dữ liệu, phiên bỏ dở không có giờ công và vẫn có nhãn chạy thử không dùng thanh toán. Lượt Vào ban đầu không có âm; sau sửa âm báo đã được kiểm tra qua nghe thử và lượt Ra, không ghi rằng đã thử lại một Vào mới.

Bộ cài cuối `partner-candidate-20261030-v6` gồm cả tối ưu giọng nói, âm báo và nhãn Chấm công nội bộ: 217 tệp đã kiểm checksum, cài offline trong venv mới, chạy web/model/giọng nói/âm thanh sau chuyển thư mục với mạng ngoài bị chặn, không mở/sửa DB thật hoặc kèm dữ liệu riêng. Bằng chứng `evidence/m5/native-release-check.json`, `partner-p5-final-check.json`, `partner-final-trial-summary.png`, `internal-attendance-label.png`. Đối chiếu từng tiêu chí tại `docs/NGHIEM_THU_CHAM_CONG_DOI_TAC.md`.

Đã hoàn tất phạm vi chức năng P0–P5 theo yêu cầu mới nhất tiếp nhận tự động; giữ đợt thử mở để tiếp tục thao tác, không chốt thanh toán hoặc sửa giờ thật. Các nhật ký blocked/chờ duyệt ở trên là lịch sử đã được giải quyết hoặc thay thế. Chưa kết luận độ chính xác theo nhóm, PAD, tablet, tải cao điểm hoặc độ trễ tên người thật sau tối ưu; đây là nhóm thử sau đã tách riêng.

### UI đối tác theo mẫu Gemini cập nhật

Đã mở lại các view mẫu trong Codex Browser và áp dụng vào bản chính: Điều phối Đợt & Thiết bị, Giám sát Tiếp nhận, Đối soát & Xuất công, Danh mục Đối tác; form tạo nhanh, kiosk có cột thông tin/lượt gần đây và popup đọc/nhập tên. Các component/CSS đối tác lấy từ mẫu; entrypoint bỏ toàn bộ mockApi của AI Studio. Mẫu/đối chiếu dùng dữ liệu minh họa ở cổng riêng, không đưa vào SQL hoặc bộ cài.

Hồi quy backend 381 passed/10 native-only skipped, frontend 63 passed/build đạt; 64 file backend và các module core nhận diện/giọng nói/âm báo/nhường camera giữ nguyên. Chọn đúng đợt giữa các tab, bốn view ở 390 px, quản trị/kiosk 768 px và footer popup đã kiểm tra; đây là viewport trình duyệt, không phải nghiệm thu iPad/Android vật lý. D23 thật đã tải overview mới, sau đó phiên admin hết hạn ở bước xem tiếp và cần người dùng đăng nhập lại. Không tự đổi auth/ghép điểm, không tạo lượt công mới. Bộ cài partner-gemini-ui-20261030-v7 đã cài offline/kiểm chuyển đường dẫn thành công. Bằng chứng evidence/m5/gemini-partner-ui-check.json và các ảnh gemini-partner-*.png; ảnh minh họa có ghi rõ, không dùng làm bằng chứng nhận diện.

Người dùng đã đăng nhập lại. Cả bốn view D23 thật đã kiểm tra: đúng đợt giữa Giám sát/Đối soát, báo cáo vẫn một cặp đủ và không thiếu/đang tiếp nhận; danh mục đúng đối tác. Form tạo nhanh mở/hủy được, không gửi dữ liệu. Ảnh gemini-partner-live-d23.png là overview bản chạy chính, không có họ tên/khuôn mặt; điểm chờ đăng nhập đã hết.
