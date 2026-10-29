# T19/T20 — Nền tảng API chuỗi ảnh local

Trạng thái: **backend và UI kiosk đã nối với nhau**, kiểm thử giao dịch/HTTP và điều khiển trình duyệt đã có; chưa hoàn tất PAD T11 hay luồng camera/model thật T23. Database thật chưa bật chính sách nhận diện ghi công.

## Đã triển khai

- Phiên có UUID yêu cầu, một phiên còn hiệu lực cho mỗi kiosk, thời hạn 20 giây. Gắn với kiosk, chiều vào/ra, phiên bản quyền thiết bị, cấu hình/model và thử thách HMAC do máy chủ cấp.
- Ảnh gửi theo vị trí 1–12; từ chối sai thứ tự, vị trí đã dùng cho ảnh khác, thiếu thử thách, sai kiosk, quyền đã đổi/hết hạn hoặc phiên đã hết hạn.
- Tối thiểu ba khung hình phù hợp cùng người, có thời gian máy chủ cách nhau và kéo dài ít nhất 0,85 giây. Ảnh lặp lại không tăng chuỗi; đổi người giữa phiên hủy phiên. Chất lượng/khuôn mặt/vị trí khung được phân tích bởi model local.
- Đây là **khung hình khi quét**, không phải số ảnh cần đăng ký hồ sơ. Không nhân bản ảnh đăng ký để tạo bộ đánh giá độc lập.
- Ảnh quét và vector truy vấn không được lưu vào bảng chuỗi ảnh. Chỉ lưu hash ảnh, thứ tự, thời điểm, tham chiếu hồ sơ/revision và phản hồi để khôi phục gửi lại.
- Kiểm tra gallery mới nhất trong giao dịch được điều phối cùng việc vô hiệu/xóa dữ liệu nhân viên. Nạp lại trạng thái phiên sau khi chờ khóa, tránh dùng số thứ tự đã đọc trước khi suy luận ảnh.
- Chạy chế độ có đối chiếu: chuỗi đạt vẫn chưa ghi công. Quản trị phải đối chiếu đúng mã nhân viên và ghi lý do; chỉ sau đó API commit nguyên tử mới ghi sự kiện/biên nhận. Phiên tự hết hạn, xác nhận không gia hạn phiên.
- Nhánh tự động chưa có PAD được kiểm chứng nên API từ chối, kể cả chỉ đặt cờ `pad_verified=true` trong cấu hình. Không coi kiểm tra ổn định/ba khung hình là chống ảnh giả.
- Hàng đợi suy luận hữu hạn hai lượt; trả 429 khi quá tải, ảnh tối đa theo cấu hình và thời gian truyền tối đa 10 giây. SQL lỗi trả trạng thái chưa xác nhận; tra cứu lại cùng UUID trước khi gửi tiếp.

## Các API đang dùng trong UI

| API | Mục đích |
|---|---|
| `POST /api/kiosk/recognition/preview` | Kiểm tra chất lượng/vị trí trước khi tạo phiên; không tạo bản ghi ảnh |
| `POST /api/kiosk/recognition/sessions` | Tạo/thử lại cùng UUID; chỉ máy chủ chọn cấu hình và chiều kiosk |
| `GET /api/kiosk/recognition/sessions/{id}` | Khôi phục trạng thái, vị trí ảnh tiếp theo, yêu cầu đối chiếu hoặc receipt đã lưu |
| `POST /api/kiosk/recognition/sessions/{id}/frames/{index}` | Ảnh nhị phân có nonce phiên và intent kiosk; không nhận vector hoặc danh tính từ client |
| `GET /api/admin/recognition/pending` | Danh sách phiên đã đạt, còn hạn, chờ quản trị đối chiếu |
| `POST /api/admin/recognition/sessions/{id}/confirm` | Đối chiếu mã đúng hồ sơ máy chủ đã chọn, lý do và CSRF; chưa tự ghi công |
| `POST /api/kiosk/attendance/{id}/commit` | Ghi sự kiện/receipt nguyên tử, chống trùng; kiểm tra lại hồ sơ, quyền và cấu hình |

## Bằng chứng kiểm thử

`backend/tests/test_recognition_sequence.py` dùng engine/vector và hồ sơ **giả trong database thử tách biệt**, không phải phép đo chất lượng nhận diện thật:

1. Ba ảnh → verified → chưa ghi khi chưa đối chiếu → quản trị xác nhận → ghi đúng một sự kiện; retry nhận cùng receipt.
2. Người lạ, không thấy mặt, ảnh lặp, thứ tự sai và ảnh khác cho cùng vị trí không làm tăng chuỗi sai.
3. Đổi người hủy phiên; hồ sơ bị vô hiệu không tiếp tục được chuỗi cũ.
4. Kiosk khác, nonce khác, hết hạn, chưa đăng nhập và cấu hình tự động chưa có PAD đều bị từ chối.
5. Mất phản hồi **sau khi lưu ảnh**: trả 503, GET khôi phục chỉ số đã lưu, gửi lại không nhân đôi bản ghi.
6. Cache phiên từ bước trước suy luận được nạp lại sau khi ảnh trước đã commit ở giao dịch khác.
7. Hai giao dịch SQL Server gửi cùng khung hình đồng thời chỉ ghi một khung hình và nhận cùng phản hồi.

Migration `20261028_recognition_frames` đã kiểm tra trên SQL Server tách biệt: upgrade, dữ liệu ca cũ, rollback guard có lịch sử, backup/checksum/restore Unicode. Schema gồm 21 bảng kể cả `alembic_version`.

Kết quả mới nhất: **190 test backend đạt**, 6 kiểm thử native-only chạy trong bộ **129 test SQL Server đạt**; 14 Node, build và Ruff đạt. Log tại `evidence/m2/admin-sqlserver-tests.log` và `.runtime/backend-check.log`.

Đã sao lưu/checksum database thật trước migration và cập nhật backend. `recognition-runtime-state.json` xác nhận schema mới, model sẵn sàng, yêu cầu tạo phiên không đăng nhập bị từ chối 401; **0 policy bật, 0 template vận hành, 0 phiên/khung hình và 0 sự kiện công**. Không tự bật cấu hình hoặc dùng bộ thử làm bằng chứng để ghi công thật.

## Còn làm để hoàn tất M3

- T18 đã nối UI/điều khiển, kiểm tra dọc/ngang và phục hồi request/receipt; còn kiểm tra quyền/camera/cookie trên iPad/Android thật KT03 và toàn luồng T23. Xem `kiosk-ui.md`.
- T09/T10/T11/T14: dữ liệu kiểm chứng độc lập, quyết định ngưỡng/chống giả mạo và đưa mẫu vào gallery vận hành qua luồng quản trị có kiểm chứng. Các ảnh nhập hiện vẫn là bộ thử.
- T19/T23: kiểm thử camera/model thật tới sự kiện, người lạ/nhiều mặt/giả mạo trên thiết bị thực tế. Không đánh dấu hoàn tất từ engine giả.
- T33: vòng đời metadata phiên/chuỗi ảnh, giữ receipt/audit theo chính sách; hết hạn phiên không đồng nghĩa xóa ngay biên nhận đã ghi.
