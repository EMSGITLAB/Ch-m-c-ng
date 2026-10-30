# Vận hành OnTime — Chấm công khuôn mặt

## Bản hiện tại

Toàn bộ ảnh, vector, model và database xử lý local. Không Docker hoặc API nhận diện ngoài. Dữ liệu đang bật trên laptop hiện có một người đã thử camera thật. Phần mềm có danh sách nhận diện nhiều người và chức năng đưa mẫu vào chấm công từ quản trị; luồng 100 hồ sơ được kiểm thử bằng vector giả lập trong database cô lập. Đo độ chính xác/PAD trên nhóm người thật được ghi riêng trong kế hoạch để làm sau; không coi kiểm thử giả lập là nghiệm thu chất lượng nhận diện.

## Mở ứng dụng

- Laptop phát triển: chạy `scripts/start_local.ps1`, mở `http://localhost:5173`.
- Bản đã đóng gói: chạy `scripts/start_backend.ps1`, mở `http://localhost:8000`. Backend phục vụ cả web và API; không cần Node/Vite khi sử dụng.
- Camera localhost dùng HTTP được. Khi chuyển lên VM để tablet truy cập qua LAN, cấu hình HTTPS tin cậy và địa chỉ cho phép trước; không cần Caddy nếu hạ tầng đã có SSL/reverse proxy.

## Chấm công

1. Đăng nhập Quản trị, cấp mã ghép một lần cho thiết bị ở mục Thiết bị. Chọn chiều Vào hoặc Ra.
2. Mở Chấm công, ghép kiosk nếu chưa ghép. Cho phép camera; một số trình duyệt cần bấm Bật camera lần đầu hoặc Thử giọng đọc để mở quyền âm thanh.
3. Đứng trong tầm nhìn camera, nhìn thẳng và giữ yên. Camera tự tìm mặt trong toàn cảnh, không có oval hoặc nút chụp mỗi người.
4. Chỉ khi máy chủ đã lưu biên nhận mới hiện tên và đọc **Hợp lệ**. Lượt lặp trong khoảng chống trùng trả biên nhận cũ.
5. Khi mất phản hồi, giữ nguyên trang để ứng dụng truy vấn lại cùng mã yêu cầu; không tự ghi công khi offline.

Màn hình chấm công bố trí như thiết bị chuyên dụng: đồng hồ/lời chào ở trái, camera toàn cảnh ở giữa, **Vừa ghi nhận** bên phải và kết quả ở dưới. Cột bên phải chỉ hiển thị tối đa 4 biên nhận đã được máy chủ xác nhận trong phiên mở trang này, dùng tên viết tắt làm ảnh đại diện; không phải danh sách chấm công toàn cơ quan. Danh sách chỉ giữ trong bộ nhớ trình duyệt và xóa khi tải lại/đổi thiết bị. Xem lịch sử đầy đủ tại Quản trị. **⚙ Tùy chọn** chứa Bật/Tắt camera, đổi camera, Ghép thiết bị và Thử giọng đọc, không cần mở để chấm công tự động. Màn hình hẹp chuyển cột lượt gần đây xuống dưới camera.

### Build và chạy từ VS Code

Mở **File → Open Folder → thư mục mã nguồn**, ví dụ `D:\Chấm công` trên laptop. Đã cấu hình interpreter `.venv/Scripts/python.exe`, task và launch; Python/Debugger đã được cài trên máy hiện tại.

- **Ctrl+Shift+B:** build TypeScript/React vào `frontend/dist`.
- **F5**, chọn **Chấm công: Build & Debug:** build frontend trước, dừng bộ giám sát đang giữ cổng 8000, chạy Python/FastAPI dưới debugger và mở `http://localhost:8000` sau khi server báo sẵn sàng. Đặt breakpoint trong `backend/app` để kiểm tra xử lý.
- **Ctrl+F5:** chạy cùng cấu hình mà không dừng tại breakpoint.
- **Ctrl+Shift+P → Tasks: Run Task → Chấm công: Build & Run:** build rồi chạy lại bằng dịch vụ nền; không cần mở phiên debugger.
- Kết thúc debug sẽ chạy task **Restore background service**. Nếu đóng VS Code đột ngột trước khi task chạy, dùng `scripts/start_service.ps1` hoặc task đó để bật lại.

F5 dùng database/cấu hình `.env` hiện tại. Không chạy `start_backend.ps1` thêm khi F5 đã giữ cổng 8000. Cổng 5173 dành cho Vite khi phát triển; gói deploy phục vụ frontend đã build từ backend 8000 và không cần Node.js trên VM. Cấu hình VS Code dành cho bộ mã nguồn đầy đủ, không phải thư mục triển khai chỉ chứa frontend đã build. JSON/task links, regex mở web, interpreter, lệnh build và đường chạy nền PowerShell 5.1 đã kiểm tra; chưa giả định đã bấm F5 trong giao diện editor.

## Hồ sơ và mẫu

Quản trị → Hồ sơ để tạo/sửa/nhập nhân viên. Mã nhân viên phải duy nhất. Thu mẫu dùng oval, hướng dẫn tư thế và tự chụp khi đạt; ảnh không đạt phải được hướng dẫn chụp lại. Ảnh tham chiếu có thể là một ảnh; nhiều mẫu không bắt buộc cho thử chức năng hiện tại.

Nhập roster/ảnh local số lượng lớn bằng `scripts/import_employee_dataset.py <manifest.json> --apply`; bỏ `--apply` để kiểm tra trước. Công cụ hỗ trợ tối đa 1.000 dòng, giữ số 0 đầu mã, không tải `imageUrl`, lưu ảnh bị bộ lọc từ chối để xem lại và không tự thay danh sách chấm công. Hồ sơ không có tệp ảnh local vẫn được tạo; metadata mâu thuẫn về tên/ảnh bị chặn. Trùng cùng mã/tên/tệp nhưng khác phòng ban được để trống phòng ban, lưu dấu đối chiếu trong audit và `.runtime/photo-import/`.

Cấu hình thử một người được thiết lập bằng `scripts/enable_functional_trial.py --employee-code <mã>` sau khi đã có ảnh tham chiếu và ảnh camera mới. Script ghi audit, không gửi ảnh ra ngoài. Không chạy lại khi đã có policy bật. Xóa/vô hiệu/đổi mẫu của hồ sơ sẽ dừng nhận diện mới; giữ lịch sử chấm công.

Sau khi cấu hình đầu tiên đã có ngưỡng được thử, thêm người theo luồng sau:

1. Vào **Quản trị → Hồ sơ**, tạo hoặc nhập hồ sơ với mã duy nhất.
2. Thu bộ mẫu tham chiếu bằng camera rồi hoàn tất, hoặc nhập ảnh tham chiếu đạt chất lượng bằng công cụ nhập local. Một ảnh nhập hợp lệ có thể làm bộ tham chiếu; không dùng ảnh hiệu chỉnh/đánh giá làm mẫu vận hành. Camera có hướng dẫn oval và tự chụp theo tư thế.
3. Mở **Dữ liệu mặt → Đưa mẫu vào chấm công thử**. Nút dùng bộ tham chiếu hoàn tất mới nhất của đúng hồ sơ. Máy chủ không đổi model/ngưỡng, kiểm tra lại các ảnh hiệu chỉnh đã có và từ chối đổi cấu hình nếu chúng không còn nhận đúng hoặc mẫu các hồ sơ bị trùng/không phân biệt được.
4. Sau thông báo đã cập nhật, kiểm tra số hồ sơ trong danh sách. Kiosk lấy cấu hình mới mà không khởi động lại; phiên nhận diện chưa ghi công thuộc cấu hình cũ bị hủy. Lượt đã ghi vẫn tra cứu/gửi lại được, không nhân đôi sự kiện.
5. Để thay ảnh, hoàn tất bộ tham chiếu mới rồi chọn **Cập nhật bộ mẫu vào chấm công thử**. Để ngừng nhận diện riêng người đó, chọn **Loại khỏi danh sách nhận diện** hoặc ngừng hoạt động hồ sơ. Những người còn lại tiếp tục dùng; mẫu/lịch sử công chưa bị xóa bởi thao tác loại khỏi danh sách.

Danh sách thử có thể mở rộng mà không cần đổi code hoặc tự nhân bản ảnh. Hồ sơ chưa có ảnh kiểm tra độc lập vẫn được ghi rõ là chưa đo chất lượng; ngưỡng thử không phải cam kết độ chính xác của toàn nhóm và không phải kiểm chứng PAD. Khi số hồ sơ cuối cùng bị loại, ghi công dừng; có thể đưa bộ mẫu hợp lệ vào lại từ cùng màn hình. Xóa dữ liệu sinh trắc học là thao tác riêng ở phần dưới và cần ghi được sổ dấu xóa trên USB đã cấu hình.

## Ca và bảng công

- Tạo ca ngày/đêm và phân lịch ở Ca & lịch. Ca mẫu là cấu hình thử; sửa ca tạo phiên bản mới.
- Vào Bảng công, chọn ngày và nhân viên rồi Tính lại. Lượt chưa phân ca hiển thị ở ngoại lệ. Thiếu Vào/Ra không được tự cộng đủ công.
- Điều chỉnh công phải có lý do; sự kiện gốc vẫn giữ. Chốt kỳ lưu một phiên bản; mở lại kỳ không xóa bản cũ.
- Xuất CSV/XLSX theo bộ lọc hoặc bản chốt. Báo cáo ghi số lượt thuộc chế độ thử chức năng. File xuất chứa thông tin cá nhân, chỉ lưu trong nơi nội bộ được bảo vệ.

## Dừng và chuyển máy

### Mạng và báo cáo sử dụng của SQL Server

Ứng dụng/model không tích hợp telemetry hoặc API ngoài. Trên laptop phát hiện dịch vụ hệ thống `SQLTELEMETRY` đang chạy; cần chặn đường gửi ra riêng của dịch vụ này để đáp ứng yêu cầu local. Microsoft chỉ hỗ trợ tùy chọn opt-out CEIP ở bản trả phí và không hỗ trợ vô hiệu hóa dịch vụ CEIP: [tài liệu CEIP](https://learn.microsoft.com/en-us/sql/sql-server/usage-and-diagnostic-data-configuration-for-sql-server?view=sql-server-ver17).

Từ PowerShell chạy bằng **Administrator**, áp dụng quy tắc đã chuẩn bị:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "<thư mục ứng dụng>\scripts\configure_sql_telemetry_egress.ps1" -Apply
```

Script xác định `sqlceip.exe` từ dịch vụ được cài trên máy, chỉ chặn outbound của đúng chương trình/dịch vụ CEIP trên mọi profile. Không dừng SQL Server hoặc tắt firewall chung. Nếu dùng instance có tên, truyền đúng tên dịch vụ qua `-ServiceName`, ví dụ chuỗi literal `'SQLTELEMETRY$SQLEXPRESS'`. Không truyền tên dịch vụ database.

Chạy script không có `-Apply` để đọc trạng thái. Chỉ khi `effective_outbound_block=true` mới coi quy tắc đang có hiệu lực; báo cáo ở `.runtime/network/sql-telemetry-egress.json`. `-Remove` gỡ riêng quy tắc do script tạo và cũng cần quyền Administrator. Script không tự bật firewall profile đang tắt và không đổi mạng của chương trình khác. Cần áp dụng/kiểm tra lại trên VM mới; đây là cấu hình của Windows, không được tự khôi phục bằng việc chép database. Quy tắc chặn gửi không đồng nghĩa tắt thu thập cục bộ của SQL Server.

Kiểm thử ngắt WAN trong trình duyệt thật vẫn là bước riêng. Trên laptop dùng `http://localhost:8000`; không dùng chế độ DevTools Offline để mô phỏng vì nó có thể chặn cả localhost. Kiosk tablet cần LAN tới server và HTTPS tin cậy khi triển khai; Internet không phải nơi xử lý ảnh.

### Độ phân giải và tài nguyên CPU

Kiosk gửi toàn bộ cảnh với cạnh dài mặc định 1280 pixel, giữ tỷ lệ, không cắt giữa ảnh; thu mẫu ban đầu giữ luồng oval riêng. `CHAMCONG_CAPTURE_MAX_EDGE` cho phép 640–1600 và `CHAMCONG_OPENCV_THREADS` cho phép 1–32 (mặc định 4). Chỉ tăng độ phân giải/luồng sau khi đo lại trên máy chủ tương ứng; không suy diễn rằng thêm luồng luôn nhanh hơn. Đổi cấu hình máy chủ cần khởi động lại backend. Không thay model hoặc ngưỡng bằng các thiết lập này.

### Kiểm tra bản nâng cấp trước khi chuyển dịch vụ

#### Tạo và chuyển bộ triển khai

Từ thư mục mã nguồn đầy đủ, build frontend trước rồi tạo thư mục phát hành mới. Dùng wheelhouse đã có để đóng gói offline:

```powershell
.venv/Scripts/python.exe scripts/build_release.py --name "<tên bản mới>" --wheelhouse "<thư mục wheels local>"
.venv/Scripts/python.exe scripts/verify_release.py --name "<tên bản mới>"
.venv/Scripts/python.exe scripts/archive_release.py --name "<tên bản mới>"
```

Chỉ chuyển bản khi cả ba lệnh thành công. ZIP nằm cạnh thư mục tương ứng trong `.runtime/releases`; checksum ở `evidence/m5/release-archive-check.json`. Công cụ ZIP chỉ lấy các tệp trong manifest đã xác thực, kiểm tra lại từng tệp sau khi nén và không ghi đè ZIP cũ. Các thư mục venv/runtime phát sinh khi kiểm thử không được đưa vào ZIP. Log cài/kiểm tra riêng ở `.runtime/release-verification/<tên bản>-<mã kiểm tra>/`.

Giải nén ZIP vào thư mục mới trên máy chủ Windows x64 có Python 3.12, SQL Server và ODBC Driver 18. Khôi phục dữ liệu bằng gói `.ccbackup` mã hóa và khóa được bảo quản riêng; ZIP ứng dụng không chứa hồ sơ, ảnh, vector, mật khẩu hoặc khóa. Khi cài mới không có dữ liệu cũ, tạo `.env` riêng theo `config/server.env.example` rồi chạy `scripts/setup_release.ps1`. Khi nâng bản đang dùng, làm theo quy trình thử và chuyển dưới đây; không chép đè thư mục đang ghi công. Triển khai tablet qua LAN cần HTTPS tin cậy, cấu hình lại tác vụ Windows và kiểm tra camera trên thiết bị đích.

#### Thử ứng viên và quay lui

Giữ bộ phát hành/wheels cũ và một backup đã xác thực. Chạy từ thư mục ứng dụng hiện tại:

```powershell
.venv/Scripts/python.exe scripts/stage_upgrade.py --archive "<gói .ccbackup>" --release "<thư mục bộ phát hành mới>" --key-file "<khóa .cckey>"
```

Mật khẩu khóa được nhập kín tại terminal local, không truyền qua tham số hoặc chat. Có thể bỏ `--key-file` khi máy nguồn còn khóa được bảo vệ. Nếu dependency bản cũ khác bản mới, thêm `--rollback-wheels "<wheels của bản cũ>"`. Công cụ kiểm tra manifest/checksum, hợp đồng phục hồi và bộ wheels offline trước khi dùng; các bộ phát hành cũ thiếu hợp đồng sổ dấu xóa ngoài DB bị từ chối làm ứng viên nâng cấp.

Công cụ khôi phục vào database/thư mục **mới**, cài môi trường riêng hoàn toàn offline, chạy thử ứng dụng cũ, cài ứng viên, chạy migration và kiểm tra app/model/DB. Lỗi migration sẽ khôi phục lại một database mới khác kèm ứng dụng tương thích, thay vì mở ứng dụng cũ với database đã bị sửa dở. Database và dịch vụ nguồn không bị chuyển hoặc sửa bởi phép kiểm tra. Cấu hình nghiệp vụ được giữ, các phiên/quyền kiosk và policy cũ trong bản phục hồi đều tắt. Kết quả chi tiết nằm ở `.runtime/upgrade-result.json` của thư mục khôi phục; log riêng ở `.runtime/upgrade/`.

Đây là bước kiểm tra, chưa chuyển nơi ghi công. Khi chuyển bản thật, thực hiện trong khoảng dừng chấm công:

1. Dừng bộ giám sát cũ và gỡ tác vụ khởi động/backup cũ bằng script của đúng thư mục đó; không dừng SQL Server dùng chung. Tạo backup mới sau khi ngừng nhận chấm công.
2. Chạy lại kiểm tra nâng cấp từ chính backup mới, không lấy bản thử cũ đã lệch dữ liệu. Nếu thất bại, dùng lại dịch vụ nguồn còn nguyên hoặc bản quay lui tương thích mà công cụ vừa tạo.
3. Khi ứng viên đạt, dùng `candidate_app_root` được báo trong kết quả làm thư mục ứng dụng mới. Kiểm tra `.env`, đường dẫn backup và kết nối SQL đúng database mới. Khởi động bằng script tại thư mục đó, đăng ký tác vụ Windows mới và kiểm tra readiness; chỉ một thư mục được phục vụ cổng 8000.
4. Đăng nhập quản trị, ghép kiosk lại và đưa bộ mẫu hợp lệ vào chấm công thử từ **Dữ liệu mặt**. Policy tắt sau khôi phục là trạng thái có chủ đích. Kiểm tra tên, biên nhận, bảng công và âm thanh trước khi mở cho người dùng.
5. Lưu bản cũ/backup để đối chiếu. Sau khi bản mới đã nhận công, không quay thẳng về database cũ vì sẽ bỏ các lượt phát sinh mới. Cần sao lưu trạng thái mới và kiểm tra khả năng tương thích dữ liệu trước khi quay lui; không tự hạ migration hoặc ghi đè dữ liệu.

Đã thử nâng ứng dụng giữa hai snapshot cùng schema và gây lỗi DDL đã commit trên database riêng, rồi khôi phục ứng dụng/database tương thích. Chưa thử nâng giữa các phiên bản schema khác nhau; mỗi bản phát hành có migration mới phải được thử thêm tình huống đó trước khi chuyển. Chưa chuyển traffic thật hoặc thử VM trong phép kiểm tra này.

Backend trên laptop hiện chạy bằng bộ giám sát native. `scripts/start_service.ps1` mở nền; `.venv/Scripts/python.exe scripts/run_service.py --status` kiểm tra và `--stop` dừng đúng tiến trình của dự án. Backend lỗi sẽ được khởi động lại với thời gian chờ tăng dần; không giết tiến trình theo PID cũ trong file.

`scripts/install_autostart.ps1 -WithDailyBackup` đăng ký tác vụ của tài khoản Windows hiện tại: mở backend khi đăng nhập và sao lưu lúc 03:00. Không lưu mật khẩu Windows; backup chạy khi người dùng đã đăng nhập và có chế độ chạy bù khi có thể. SQL Server đang để Automatic. Chưa thử reboot thực tế; dịch vụ chạy trước đăng nhập trên VM cần cấu hình tài khoản dịch vụ phù hợp khi chuyển máy. Gỡ tác vụ bằng `scripts/install_autostart.ps1 -Remove`, không tác động SQL Server của ứng dụng khác.

Quản trị → **Vận hành** hiển thị DB/model, tiến trình giám sát, dung lượng và bản sao lưu gần nhất; tự cập nhật khi mở trang. Thông báo camera/âm thanh nằm tại từng kiosk. Log giám sát có xoay vòng, chỉ chứa sự kiện tiến trình, không ảnh/vector hoặc tham số SQL.

- Dừng backend bằng Ctrl+C nếu chạy trực tiếp. Không dừng SQL Server của ứng dụng khác.
- Không chép nguyên `.venv` sang máy khác; dùng bộ cài/wheels và tạo venv mới với Python 3.12 x64, ODBC Driver 18 và SQL Server local.
- Bộ phát hành không chứa database, `.env`, ảnh, vector hoặc tài khoản. Chuyển dữ liệu qua quy trình backup/restore riêng. Sao lưu khóa/bí mật an toàn, không commit.
- Khi nâng cấp database đang có dữ liệu, dùng `scripts/migrate_local.py`: kiểm tra database thuộc dự án, backup/checksum rồi mới migrate. Không downgrade lịch sử đang có dữ liệu để cố chạy bản cũ.

## Kiểm tra và xử lý lỗi

- `/health/live`: tiến trình còn chạy. `/health/ready`: DB/model/cấu hình chấm công sẵn sàng.
- Không thấy camera: kiểm tra quyền, camera có bị ứng dụng khác giữ và trang có dùng localhost/HTTPS tin cậy.
- Có tên nhưng không có tiếng: kiểm tra âm lượng rồi bấm Thử giọng đọc một lần.
- Chưa nhận diện: kiểm tra hồ sơ còn hoạt động, mẫu/model/revision đúng; chỉnh sáng, khoảng cách và nhìn thẳng.
- Không thấy bảng công: kiểm tra bộ lọc, lịch ca và các lượt ngoại lệ trước khi điều chỉnh.
- Không chép `.env`, ảnh, vector hoặc file backup vào báo lỗi. Chỉ dùng số đếm, mã lỗi và thời điểm.

## Sao lưu mã hóa và khôi phục thử

Tạo bản mã hóa bằng `.venv/Scripts/python.exe scripts/backup_local.py create`. Mặc định lưu trong `.runtime/backups`; có thể cấu hình `CHAMCONG_BACKUP_DIRECTORY` hoặc truyền `--destination` tới thư mục nội bộ khác. Chỉ chọn đường dẫn ổ ngoài/ổ mạng khi thiết bị đó thực sự có sẵn. Không tự xóa các bản cũ theo tuổi khi chưa có chính sách lưu giữ.

Gói `.ccbackup` chứa SQL native backup có checksum, model, mã backend/migration, frontend đã build, cấu hình riêng và bản chụp sổ dấu xóa. Gói được mã hóa có xác thực; dữ liệu bị sửa hoặc dùng sai khóa sẽ bị từ chối. Giới hạn 256 MiB plaintext, phù hợp bộ hiện tại; vượt giới hạn sẽ báo lỗi để xử lý thay vì cố nạp không giới hạn vào RAM.

Khóa giải mã nằm tại `.runtime/keys/backup.key`, được giới hạn quyền trên Windows. Cần bảo quản khóa riêng trong nơi an toàn; không gửi lên chat, không commit và không lưu khóa plaintext cùng gói mã hóa trên USB công khai. Mất khóa sẽ không giải mã được. Đã cấu hình archive tại `E:\Database\ChamCong` trên ổ USB riêng; C/D vẫn cùng một ổ vật lý. Người dùng đã lưu khóa `.cckey` có mật khẩu trên USB; checksum và dấu khớp khóa hiện tại đã được kiểm chứng. Mật khẩu không được đọc hoặc lưu bởi ứng dụng/agent; cần tự giữ mật khẩu ở nơi an toàn.

Để bảo quản khóa độc lập, vào **Quản trị → Vận hành → Bảo quản khóa khôi phục**, tự chọn và nhập lại mật khẩu riêng từ 12 ký tự, rồi bấm **Lưu khóa khôi phục có mật khẩu**. Không gửi mật khẩu qua chat. Máy chủ lưu tệp `.cckey` đã bảo vệ vào thư mục backup; mật khẩu không được lưu. Khóa gốc không thay đổi. Cần nhớ/bảo quản mật khẩu để đọc khóa khi đổi máy; nếu quên khi máy nguồn vẫn còn hoạt động, có thể xuất thêm một bản với mật khẩu mới.

Khi chuyển máy, giữ cùng bộ: gói `.ccbackup`, tệp khóa `.cckey` đã bảo vệ và **sổ dấu xóa mới nhất** `chamcong_revocations.fernet` trong thư mục backup. Sổ ngoài được cập nhật khi xóa mẫu và khi backup; nếu ổ backup mất kết nối, yêu cầu xóa mẫu không được báo thành công khi chưa lưu được dấu xóa ngoài. Gói định dạng 2 từ chối khôi phục nếu thiếu sổ ngoài, thay vì phục hồi nhầm mẫu đã bị xóa sau ngày tạo backup.

Khôi phục thử bằng `.venv/Scripts/python.exe scripts/backup_local.py restore-new "<đường-dẫn-gói.ccbackup>" --key-file "<đường-dẫn-khóa>"`. Công cụ chỉ tạo database mới có tên `ChamCong_RecoveryNew_...`, không ghi đè database đang chạy. Thư mục ứng dụng khôi phục nằm trong `.runtime/recoveries`; thông tin vị trí được lưu riêng tại `.runtime/backups/last-restore.json`.

Với tệp `.cckey`, chạy lệnh trên trong terminal tương tác local; công cụ hỏi mật khẩu theo chế độ ẩn. Không đưa mật khẩu vào tham số lệnh hoặc lịch sử shell. Khóa có mật khẩu được kiểm tra trước khi tạo database. Sai mật khẩu, tệp bị thay đổi hoặc thiếu sổ dấu xóa bắt buộc đều dừng khôi phục.

Sau khôi phục, phiên đăng nhập và quyền kiosk cũ bị thu hồi, policy ghi công tắt, bí mật phiên được thay mới. Đăng nhập và ghép kiosk lại trước khi dùng. Dấu xóa hiện tại được hợp nhất với bản trong backup để không làm sống lại mẫu đã xóa. Khi chuyển máy cần mang theo **sổ dấu xóa mới nhất** `.runtime/privacy/revocations.fernet` và khóa được bảo quản an toàn; một backup cũ đơn lẻ không biết các yêu cầu xóa phát sinh sau ngày tạo nó.

Phép thử đã chạy trên một database riêng trong cùng laptop và đối chiếu số liệu nguồn không đổi; chưa thay thế kiểm tra phục hồi trên VM hoặc từ ổ vật lý khác. Không trỏ ứng dụng thật vào database thử hoặc bật ghi công chỉ vì đã giải mã được archive.


## Ảnh hồ sơ dùng ngay để nhận diện

Vào Quản trị → Nhân viên → Thêm nhân viên hoặc Sửa hồ sơ. Chọn đơn vị từ danh sách, hoặc chọn “Thêm đơn vị mới”. Tải ảnh JPEG/PNG/WebP tối đa 2 MB (tối đa 4 triệu pixel) hoặc bấm Mở camera → Chụp ảnh hồ sơ → Lưu hồ sơ. Sau khi lưu, thông báo cho biết ảnh đã dùng để nhận diện hay lý do chưa đưa vào nhận diện. Một ảnh rõ một người là đủ, Thu thêm mẫu là tùy chọn.

Ảnh tham chiếu yêu cầu vùng mặt tối thiểu 64 px từ ảnh gốc; ảnh camera chấm công vẫn tối thiểu 96 px. Ảnh nhiều mặt/mờ/tối/cắt mặt không tự trở thành mẫu. Ảnh vẫn hiển thị trong hồ sơ để thay lại khi cần. Cấu hình nhận diện đã kiểm tra phải đang bật; tải ảnh không tự bật lại cấu hình đã dừng. Ảnh trùng/khó phân biệt giữa hai hồ sơ không tự thay cấu hình đang dùng. Dữ liệu đã xóa/thu hồi không được tự lấy lại từ phiên ảnh cũ.

Với dữ liệu ảnh đã nhập trước đây, chạy `scripts/prepare_profile_references.py` bằng Python trong venv để xem trước; thêm `--apply` để tạo mẫu và công bố một phiên danh sách mới. Công cụ giữ mẫu đang hoạt động, kiểm tra ảnh và ảnh hiệu chỉnh sẵn có, giữ model/ngưỡng nhận diện. Nên có backup mã hóa trước khi cập nhật hàng loạt. Nhật ký loại ảnh lưu trong database; không xuất ảnh/vector ra ngoài.

Màn hình chấm công dùng bộ dò vị trí khuôn mặt chạy bằng worker trên trình duyệt (JS/WASM/model local), tối đa 10 khung/giây; máy chủ vẫn kiểm tra danh tính và ghi công từ ảnh toàn cảnh. Khi trình duyệt không hỗ trợ bộ dò nhanh, khung vị trí dùng phản hồi máy chủ. Khung bám mặt chưa phải thông báo chấm công hợp lệ; chỉ biên nhận máy chủ mới hiện tên và phát âm báo.


## Giao diện theo mẫu Gemini

Ứng dụng có các màn hình Chấm công nội bộ, Chấm công đối tác và Quản trị (Admin), cùng nút toàn màn hình. Trên di động, thanh điều hướng nằm dưới. Quản trị mở trang Tổng quan với tổng nhân sự/nhân sự hoạt động, lượt chấm trong ngày theo múi giờ cấu hình và số điểm đang liên lạc; số liệu đọc từ SQL Server local.

Ghép trình duyệt tại Quản trị → Thiết bị Kiosk: tạo thiết bị/lấy mã một lần, nhập mã vào thẻ “Cấu hình điểm chấm công cho thiết bị”. Trên kiosk đã ghép, chọn Vào ca hoặc Ra ca để thay chiều ghi công. Máy chủ xác nhận chiều mới trước khi cập nhật màn hình; các phiên nhận diện dở theo chiều cũ bị hủy, biên nhận đã ghi vẫn tra cứu được.

Nút “⚙ Tùy chọn” luôn hiện trên đầu vùng chấm công; bấm để hiện Bật/Tắt camera, đổi camera, Ghép thiết bị và Thử giọng đọc. Các nút điều khiển được ẩn mặc định. Nhận diện thử dùng camera trực tiếp và ghi công theo kết quả thật của máy chủ. Thử giọng đọc chỉ phát âm thanh và không ghi lượt. Giao diện không có API giả hoặc chức năng chọn tên người để tự tạo biên nhận.

Khung trang trí trên kiosk lấy từ mẫu Gemini. Video và khung bám mặt vẫn hiển thị toàn cảnh, căn theo đúng tỷ lệ camera; không áp oval thu mẫu vào việc chấm công. Các ảnh khuôn mặt, vector và âm báo đều phục vụ local.


### Nếu chỉ thấy khung định vị mà không chấm công

Nhìn vùng trạng thái/hướng dẫn phía dưới ảnh camera. “Chưa ghép quyền chấm công” nghĩa là trình duyệt chưa có cookie kiosk hợp lệ; khung định vị vẫn có thể chạy local nhưng không ghi công. Bấm “⚙ Tùy chọn” ở đầu vùng chấm công, chọn “Ghép thiết bị” để nhập mã 8 số. Liên kết “Lấy mã ghép 8 số trong Quản trị → Thiết bị Kiosk” mở đúng trang cấu hình; bấm “Tạo lại mã ghép” của kiosk cần dùng (hoặc tạo thiết bị mới nếu thật sự là điểm mới). Mã chỉ hiện khi được cấp, có hạn và dùng một lần; sau khi ghép xong không có mã cố định để xem lại. Không cần cấp lại mã khi thiết bị vẫn đang hoạt động bình thường.

Nếu ghi công bị tạm dừng hoặc bộ nhận diện chưa sẵn sàng, màn hình báo riêng. Đăng nhập quản trị và ghép kiosk là hai quyền khác nhau; chỉ đăng nhập chưa tự cấp quyền ghi công cho trình duyệt. Dòng hướng dẫn chất lượng/nhận diện chỉ nằm ở phần trạng thái phía dưới ảnh, không đè lên video. Thanh cảnh báo phía trên ảnh đã bỏ theo yêu cầu. Khi camera đang chờ quyền mở, nút “Hủy mở camera” có thể hủy lần mở đó.

### Xóa nhân viên và quét lại cùng ca

Nhân viên → Xóa → xác nhận Xóa nhân viên: hồ sơ ngừng nhận diện và được đưa vào bộ lọc Đã xóa — tra cứu lịch sử. Lượt công, lịch ca và thông tin đối chiếu vẫn còn để tra cứu/xuất báo cáo; mã nhân viên không cấp lại cho người khác. Đây là xóa mềm; xóa dữ liệu sinh trắc học dùng chức năng riêng.

Mỗi nhân viên chỉ ghi một lượt Vào và một lượt Ra cho từng ca đã phân. Camera quét lại cùng chiều chỉ hiện Đã quét vào ca/Đã quét ra ca, giữ nguyên giờ lần đầu và không phát âm báo. Ca qua đêm dùng ngày bắt đầu ca. Nếu chưa phân ca, mỗi chiều ghi một lần trong ngày theo múi giờ nghiệp vụ; cần phân lịch để dùng nhiều ca/ngày. Khoảng nhận ca giao thoa cần sửa ở Ca/Lịch trước khi chấm công, hệ thống không tự đoán ca. Chiều kiosk vẫn do cấu hình Vào/Ra quyết định.


## Chấm công đối tác

Hướng dẫn thao tác và vòng đời riêng: [docs/CHAM_CONG_DOI_TAC.md](docs/CHAM_CONG_DOI_TAC.md). Kiosk đối tác ở `#partner`; cấu hình, tiếp nhận và đối soát trong Quản trị → Chấm công đối tác. Không tạo người thời vụ trong Nhân viên công ty. Kho mặt tạm không thuộc backup; bản chốt/điều chỉnh vẫn thuộc SQL. Bộ cài mới có model giọng nói local; nếu thiếu model, nhập tay vẫn dùng được. Sau khôi phục cần ghép/gán lại thiết bị và kích hoạt chính sách có kiểm soát.
