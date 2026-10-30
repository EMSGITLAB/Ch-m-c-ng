# Sao lưu và khôi phục local — checkpoint 29/10/2026

- Đã tạo gói `.ccbackup` khoảng 60 MB bằng Fernet (`cryptography` 50.0.2, Apache-2.0 OR BSD-3-Clause). Xác thực ciphertext và SHA256 từng tệp trước khi báo thành công. Giới hạn plaintext 256 MiB được kiểm tra rõ.
- Gói gồm SQL native backup có checksum, model, backend/migration, frontend build, cấu hình riêng và sổ dấu xóa. Bản hiện tại còn đưa nguồn frontend/các helper cần thiết vào snapshot nếu có trong thư mục chạy.
- Khóa ở thư mục riêng được giới hạn ACL. SQL chỉ có quyền cần thiết tại staging riêng; file staging của đường xử lý mới được xóa sau khi dùng. Không mở quyền rộng trên thư mục SQL Server mặc định.
- Sổ dấu xóa có mã hóa/xác thực, nằm ngoài database. Purge phải ghi được dấu xóa trước khi xác nhận; lỗi ghi sổ rollback thao tác SQL. Lỗi commit sau khi ghi sổ để lại ý định xóa bảo thủ cho khôi phục, không hồi sinh mẫu. Dấu xóa cũ từ audit đã được đồng bộ.
- Khôi phục chỉ tạo database/thư mục mới, từ chối tên production hoặc đích đã tồn tại. DB nguồn không bị thay đổi. Hợp nhất sổ dấu xóa hiện tại và sổ trong backup, bảo toàn sự kiện công; thu hồi phiên/quyền kiosk cũ, tắt policy và đổi bí mật phiên.
- Đã khôi phục gói thật vào database tách biệt, chạy lại app/model/config bằng đường dẫn mới, đối chiếu số đếm nguồn và bản khôi phục. Phép thử local mất **7,91 giây**; không phải thời gian phục hồi lên VM sau sự cố vật lý.
- Lượt backup tự động 03:00 ngày 29/10 đã trả kết quả 0, marker xác thực/mã hóa thành công. Có phát hiện CPU tăng kéo dài trong lượt kiểm tra thủ công trước đó; chưa xác định nguyên nhân gốc. Lượt chạy lịch sau đó hoàn tất; tiếp tục theo dõi ở phép đo tải T34, không coi đó là lỗi đã được tái hiện và sửa xong.

Bằng chứng: `backup-restore-check.json`, `native-service-state.json`, `backend/tests/test_recovery_privacy.py`, `backend/tests/test_native_backup.py` và SQL Server tests. Evidence không chứa dữ liệu cá nhân, ảnh, vector hoặc khóa.

## Phần còn lại

C: và D: cùng Disk 0. Chưa có đường dẫn USB/NAS từ người dùng, nên **chưa xác nhận lưu trên thiết bị khác**. Chưa có phép thử VM hoặc reboot thật. Đã hỏi người dùng vị trí lưu ngoài; các việc phần mềm khác tiếp tục trong lúc chờ. Cần bảo quản riêng khóa và sổ dấu xóa mới nhất khi chuyển máy; backup cũ một mình không biết yêu cầu xóa mới hơn.

## Cập nhật sau khi người dùng cung cấp đường dẫn

Đã nhận `E:\Database\ChamCong`, kiểm tra ghi và xác nhận E: là USB Disk 1, khác Disk 0 chứa nguồn/database/khóa. Cấu hình `CHAMCONG_BACKUP_DIRECTORY` đã lưu trong `.env`; các lần backup theo lịch dùng đường dẫn đó. Gói 60.541.452 byte/143 tệp đã xác thực, và phép khôi phục từ chính USB hoàn tất trong 27,25 giây vào database tách biệt. Số đếm nguồn không đổi; policy/quyền cũ trong bản khôi phục vẫn tắt. Xem `external-backup-check.json` và bản cập nhật `backup-restore-check.json`.

Phần chờ đường dẫn đã được giải quyết. Việc bảo quản khóa giải mã độc lập vẫn cần hoàn thiện: không sao chép khóa plaintext cùng archive trên USB, và không coi việc chỉ giữ khóa tại C/D là đủ bảo vệ trước khi ổ máy nguồn hỏng. Chưa thử VM/reboot thật.

## Chốt bảo quản khóa và snapshot — 29/10/2026

Người dùng đã tự nhập mật khẩu trên form local và lưu `.cckey` thành công trên USB E:. Đã kiểm tra checksum của tệp, dấu khớp khóa hiện tại và sổ dấu xóa ngoài DB; không đọc/lưu mật khẩu hoặc chép khóa plaintext. Xem `protected-recovery-key-check.json`. Sổ dấu xóa bên cạnh archive được bắt buộc cho gói format 2, cập nhật trước khi xác nhận purge; thiếu USB thì purge không được xác nhận.

Gói mới 60.567.588 byte/145 tệp đã được khôi phục vào database/thư mục mới trong 14,71 giây. App/model/config/frontend chạy lại đạt, dữ liệu nguồn không đổi và quyền cũ tắt. Đã bổ sung số đếm snapshot có xác thực trong manifest để so sánh với đúng thời điểm backup: lượt trước chênh một sự kiện do có chấm công phát sinh sau backup, không phải mất sự kiện trong archive. Bản khôi phục đối chiếu số đếm trước khi áp sổ xóa, sau đó kiểm tra lịch sử công giữ nguyên.

T32 đạt cho laptop + USB hiện tại. Chưa có thử khôi phục trên VM/ổ máy nguồn hỏng hay reboot thật; không có chứng thư HTTPS ở localhost để sao lưu. Bộ khôi phục cần đủ archive + `.cckey` + mật khẩu người dùng giữ + sổ dấu xóa mới nhất; không tách một backup cũ khỏi sổ dấu xóa.
