# OnTime — Chấm công khuôn mặt

Webapp nhận diện khuôn mặt và chấm công nội bộ. Toàn bộ ảnh và vector xử lý trên máy chủ, không Docker.

Tiến độ và tiêu chí kiểm tra: [KE_HOACH_TRIEN_KHAI.md](KE_HOACH_TRIEN_KHAI.md).

## Chạy bản thiết lập trên laptop

1. Kết nối SQL Server có sẵn và chuẩn bị database riêng: `.venv/Scripts/python.exe scripts/start_sqlserver.py`.
2. Nâng cấp schema: `.venv/Scripts/python.exe -m alembic -c backend/alembic.ini upgrade head`.
3. Build giao diện: `npm.cmd run build` trong `frontend`.
4. Chạy backend: `scripts/start_backend.ps1`.
5. Truy cập `http://localhost:5173`; camera được hỗ trợ trên HTTP localhost. Có thể chạy cả backend và frontend bằng `scripts/start_local.ps1`.

HTTPS và reverse proxy sẽ cấu hình ở máy chủ ảo sau. Không cần Caddy để chạy bản laptop.

Hiện là bản thiết lập; không ghi chấm công thật trước khi tính năng nhận diện và lưu sự kiện được kiểm thử.

Kiosk tự mở camera khi thiết bị đã ghép và trình duyệt cho phép; nếu trình duyệt chặn, chỉ cần bấm **Bật camera** một lần. Camera gửi toàn cảnh để tự dò vị trí mặt và hiện khung bám theo mặt, không có nút chụp từng người. Dò mặt hoạt động cả khi đang thử và chưa bật ghi công; dò được mặt không đồng nghĩa đã xác minh danh tính hoặc ghi công. Tên và giọng **“Hợp lệ”** chỉ xuất hiện sau biên nhận đã ghi từ máy chủ.

## Dữ liệu và cấu hình

- `.env` chứa bí mật riêng của máy, không commit.
- `config/business.json` chứa cấu hình nghiệp vụ có thể đổi; ca mẫu chưa dùng cho bảng công thật.
- `.runtime` chứa công cụ portable và cấu hình native riêng của máy.
- Database hiện tại là `localhost / ChamCongFaceLocal`, dùng Windows Authentication và ODBC Driver 18. Không ghi mật khẩu SQL vào mã nguồn.
- Máy hiện có SQL Server 2025 Developer: chỉ dùng phát triển/kiểm thử. Bản vận hành miễn phí dùng Express phù hợp hoặc hạ tầng SQL Server đã có giấy phép.
- PostgreSQL đã dừng và để sau; các script PostgreSQL cũ không nằm trong luồng khởi động.
- Chỉ có máy chủ bind loopback trong M0; chưa mở firewall hoặc truy cập từ mạng ngoài.

## Kiểm tra

Mở thư mục gốc bằng VS Code. **Ctrl+Shift+B** build frontend; **F5** chọn `Chấm công: Build & Debug` để build, nhường cổng 8000 từ dịch vụ nền rồi chạy/debug FastAPI. **Ctrl+F5** dùng cùng cấu hình để chạy không debug. Khi kết thúc phiên, task bật lại dịch vụ nền. Muốn chạy nền trực tiếp: **Ctrl+Shift+P → Tasks: Run Task → Chấm công: Build & Run**. Cấu hình ở `.vscode/`, dùng Python trong `.venv`; Python/Debugger đã được cài trên laptop. Những lệnh này dùng database trong `.env` hiện tại; không tạo database khác hoặc dừng SQL Server.

**Phạm vi hiện tại:** đã thử camera trực tiếp một người, tự nhận đúng tên, ghi sự kiện và đọc **Hợp lệ**. `functional_trial` hiện hỗ trợ danh sách nhiều hồ sơ với các mẫu được ghim theo phiên bản; quản trị có thể đưa/cập nhật/loại bộ mẫu khỏi chấm công, không cần sửa code hoặc khởi động lại. Luồng 100 danh tính → chuỗi ảnh → 100 sự kiện đã được kiểm thử bằng vector giả lập trong database cô lập; đây là bằng chứng chức năng, không phải độ chính xác nhận diện. Dữ liệu đang bật trên laptop vẫn là người đã thử thực tế. Đo chất lượng theo nhóm/PAD/100 người thật thuộc mục 18 trong kế hoạch, không chặn triển khai chức năng. Báo cáo ghi nhãn các lượt chấm công thử.

Hướng dẫn sử dụng và chuyển máy: [HUONG_DAN_VAN_HANH.md](HUONG_DAN_VAN_HANH.md). Bản frontend đã build cũng được phục vụ tại `http://localhost:8000` sau khi khởi động backend mới; không cần Vite cho bản đóng gói.

Quản trị → **Kiểm chứng AI** cho biết độ phủ bộ đăng ký/hiệu chỉnh và đề xuất ngưỡng khi đủ dữ liệu. Bộ đánh giá cuối được giữ riêng. Công cụ chưa tự bật nhận diện ghi công.

Tab **Nhận diện & ngưỡng — T09** hiển thị từng hồ sơ có bao nhiêu ảnh đăng ký/hiệu chỉnh và còn thiếu gì; nút **Thu ảnh hiệu chỉnh mới** mở đúng mục đích chụp, không cần đăng ký lại ảnh nhân sự đã nhập. Báo cáo so sánh giới hạn 1/3/5 tham chiếu chạy trên cùng danh sách người/probe hiện có kể cả khi chưa đủ dữ liệu chọn ngưỡng. Ảnh đăng ký là ảnh đã lưu làm tham chiếu; ảnh thử độc lập là ảnh mới của cùng người ở phiên khác, không phải dùng lại chính tệp ảnh đó.

Tab **Chống giả mạo — T11** có **Kiểm chứng chống ảnh giả**: chọn đúng tình huống thực tế, mở camera và đo tự động 5 khung. Có thể tải báo cáo JSON chứa điểm/model/thời gian, không chứa ảnh/vector; phần điều kiện thử là nội dung tự nhập, không điền tên người. 5 khung là một phiên có tương quan, không phải 5 phép thử độc lập. Chưa có ngưỡng PAD đã kiểm chứng hoặc quyền bật ghi công từ công cụ này. Model/giấy phép được ghim trong `models/pad`; tải bằng `scripts/download_pad_models.py`, thử CPU bằng `scripts/check_pad_cpu.py`.

T07 đã đáp ứng bộ khởi đầu ban đầu. Theo phạm vi mới, một ảnh tham chiếu cùng ảnh camera mới của một người đủ triển khai và nghiệm thu luồng chức năng. Bộ hiệu chỉnh nhóm/người ngoài và tập cuối được giữ riêng cho đợt đo mở rộng sau.

Một người có bộ đăng ký và bộ hiệu chỉnh ở hai phiên riêng vẫn xem được điểm so khớp thử cùng người. Điểm cosine không phải phần trăm độ chính xác; kiểm chứng nhận nhầm/người lạ cần bổ sung người thật theo kế hoạch.

Trong **Thu mẫu**, phiên hết hạn sẽ dừng nhận ảnh mới. Bộ đã có ít nhất 5 mẫu hợp lệ vẫn có thể hoàn tất từ nút ở lịch sử phiên.

Quản trị → **Ca & lịch** để tạo ca ngày/qua đêm, cấu hình khoảng nghỉ và phân lịch hàng loạt. Sửa ca tạo phiên bản mới, giữ nguyên quy tắc của lịch cũ; hủy lịch giữ lý do và lịch sử. Phút công hiển thị ở đây là dự kiến theo ca, chưa phải bảng công từ sự kiện thực tế.

Quản trị → **Bảng công** có **Xem trước**, **Điều chỉnh công**, **Chốt kỳ & bản lưu**. Bổ sung/loại/thu hồi cần lý do và giữ lượt gốc; khóa kỳ tạo bản lưu theo phiên bản, mở lại vẫn giữ bản cũ. Lượt thiếu/mơ hồ chưa cộng đủ công; phút ngoài ca tách riêng, chưa tự tính tăng ca. Có thể xuất CSV/XLSX theo bộ lọc hoặc đúng phiên bản bản chốt; số liệu đổi sau khi xem sẽ yêu cầu tải lại trước khi xuất.

Chạy từ dòng lệnh: `.venv/Scripts/python.exe scripts/calibrate_local.py`. Báo cáo tổng hợp nằm trong `.runtime/calibration/report.json`, không xuất danh tính hoặc vector.

```text
.venv/Scripts/python.exe -m pytest backend/tests -q
.venv/Scripts/python.exe -m ruff check backend scripts
.venv/Scripts/python.exe scripts/check_sqlserver.py
```

Kiểm tra frontend từ thư mục gốc dự án (Node.js 24):

```text
npm.cmd --prefix frontend test
npm.cmd --prefix frontend run build
```

Giấy phép bên thứ ba: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Ảnh nhân viên nhập để thử

Vào **Quản trị → Nhân viên → Dữ liệu mặt** để xem ảnh đã nhập, trạng thái chất lượng và chọn ảnh khác thử so khớp với toàn bộ bộ ảnh nhập. Ảnh và vector xử lý/lưu trong SQL Server local, không gọi URL trong manifest. Mỗi ảnh đạt tạo một bộ mẫu thử 1 ảnh; chưa dùng ghi công.

Ảnh chưa đạt vẫn được giữ để xem lý do, chưa có vector. Xóa dữ liệu mặt trong hồ sơ xóa cả ảnh nhập của người đó. Ảnh dùng lại chính tệp đăng ký được đánh dấu để tránh coi kết quả đó là độ chính xác thực tế.

Hướng dẫn và kết quả vô danh: [evidence/m1/imported-photos.md](evidence/m1/imported-photos.md). Dùng `scripts/migrate_local.py` để sao lưu database có dấu nhận diện dự án, kiểm checksum và nâng cấp schema trước phiên bản mới.

Kiosk đã nối giao diện với preview, phiên/chuỗi ảnh, chờ đối chiếu, commit và phục hồi receipt khi mất mạng/tải lại trang. Máy chủ phải báo cấu hình và gallery hợp lệ trước khi camera tự quét. Quản trị đối chiếu tại **Kiểm chứng AI → Đối chiếu tại kiosk**. Hiện dữ liệu thật vẫn chưa bật ghi công; luồng điều khiển và API đã kiểm thử bằng transport/engine và database giả, còn camera/model/thiết bị thật. Xem [evidence/m3/kiosk-ui.md](evidence/m3/kiosk-ui.md) và [evidence/m3/recognition-sequence.md](evidence/m3/recognition-sequence.md).
