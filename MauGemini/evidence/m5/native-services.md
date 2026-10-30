# Giám sát tiến trình và khởi động trên laptop — 29/10/2026

- `scripts/run_service.py`/`backend/app/runtime_supervisor.py` chạy backend native, bind loopback, có khóa độc quyền, định danh phiên dừng và chờ tăng dần khi lỗi. Không tin PID cũ để giết tiến trình khác.
- Thử trên cổng riêng: tiến trình backend bị kết thúc cưỡng bức thì tự chạy lại; bản giám sát thứ hai không tạo thêm server; dừng thường hoặc kết thúc cưỡng bức bộ giám sát đều giải phóng cây tiến trình và cổng. Windows Job Object dùng `KILL_ON_JOB_CLOSE`.
- Tác vụ Windows của dự án đã đăng ký cho tài khoản hiện tại khi đăng nhập, không lưu mật khẩu. Đã chạy chính action đã đăng ký để đưa backend thật lên; readiness trả 200. SQL Server là Automatic. **Chưa reboot máy thật; chưa chứng minh chạy trước đăng nhập trên VM.**
- Tác vụ backup hằng ngày lúc 03:00 đã có lượt tự chạy ngày 29/10, kết quả 0 và có marker bản mã hóa mới. Bản trên cùng ổ vẫn chưa phải bản bảo vệ khỏi hỏng thiết bị.
- Log giám sát xoay vòng 2 MB × 3 bản, chỉ ghi sự kiện tiến trình/mã thoát. Backend không ghi access log/query và không đưa tham số SQL vào exception trả về.
- `start_local.ps1` dùng Node được tìm trên máy thay cho đường dẫn cố định và giữ kết nối SQL trong `.env` đã cấu hình.

Bằng chứng: `supervisor-check.json`, `native-service-state.json`; unit `backend/tests/test_runtime_supervisor.py`. Quy tắc Windows dựa trên [Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects) và [Scheduled Task Principal](https://learn.microsoft.com/en-us/powershell/module/scheduledtasks/new-scheduledtaskprincipal).
