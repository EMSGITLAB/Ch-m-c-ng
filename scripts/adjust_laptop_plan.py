"""Apply the user's staging decision: HTTP localhost now, HTTPS on the VM later."""
from pathlib import Path

root = Path(__file__).resolve().parents[1]
file = root / "KE_HOACH_TRIEN_KHAI.md"
s = file.read_text(encoding="utf-8")
s = s.replace('**Phiên bản:** 1.0', '**Phiên bản:** 1.1')
s = s.replace('**Trạng thái:** Goal đang hoạt động; đang triển khai M0 trên laptop tạm.', '**Trạng thái:** Goal đang hoạt động; M0 hoàn tất trên laptop, tiếp tục M1.')
s = s.replace('| Mốc đang thực hiện | **M0** — nền tảng chạy local trên laptop |', '| Mốc đang thực hiện | **M1** — nhận diện local trên CPU |')
s = s.replace('| Đầu việc đang làm | T04 kiểm tra camera; T06 nạp model nhận diện local |', '| Đầu việc đang làm | T06 tải và kiểm tra model YuNet/SFace |')
s = s.replace('| Bước tiếp theo | Khởi động PostgreSQL, tạo migration và kiểm tra HTTPS/camera laptop |', '| Bước tiếp theo | T06 nạp model, sau đó T08 kiểm tra chất lượng; T07 cần các phiên ảnh thực tế |')
s = s.replace('- Không Docker; triển khai bằng môi trường Python riêng và tiến trình/dịch vụ nền native.', '- Không Docker; triển khai bằng môi trường Python riêng và tiến trình/dịch vụ nền native. Bản laptop dùng HTTP localhost; HTTPS và reverse proxy bổ sung khi lên VM, không bắt buộc Caddy.')
s = s.replace('    T["iPad Safari hoặc Android Chrome"] -->|HTTPS nội bộ| C["Caddy native"]\n    C --> W["Giao diện web local"]\n    C --> A["FastAPI"]', '    T["Camera laptop qua localhost"] --> W["React webapp"]\n    W --> A["FastAPI"]\n    V["Tablet qua HTTPS sau khi lên VM"] -.-> A')
s = s.replace('| HTTPS | Caddy chạy native; CA nội bộ được cài tin cậy trên tablet; chỉ cổng HTTPS mở cho kiosk. |', '| HTTPS | Chưa cần ở laptop localhost. Khi lên VM, dùng SSL/HTTPS của hạ tầng được chọn; reverse proxy không cố định công nghệ. |')
s = s.replace('| Dịch vụ nền | Windows Task Scheduler chạy không cần đăng nhập cho backend/Caddy; PostgreSQL chạy Windows Service. Linux dùng systemd. |', '| Dịch vụ nền | Laptop chạy backend/frontend/PostgreSQL native. Khi lên máy chủ dùng Task Scheduler/Windows Service hoặc systemd tùy OS. |')
s = s.replace('Repo và môi trường chạy, cấu hình nghiệp vụ, schema, HTTPS và camera trên thiết bị thật.', 'Repo và môi trường chạy, cấu hình nghiệp vụ, schema, webapp và camera laptop qua localhost.')
s = s.replace('**T04 — Dựng HTTPS và mở camera thật**', '**T04 — Chạy webapp và kiểm tra camera laptop**')
s = s.replace('Tiêu chí xong: iPad và Android mở camera bằng địa chỉ LAN có chứng thư tin cậy.', 'Tiêu chí xong: Backend, frontend và PostgreSQL chạy local; camera laptop mở được trên http://localhost. HTTPS/tablet chuyển sang M5 và KT02.')
s = s.replace('  - Kiểm thử liên quan: KT02.\n', '')
s = s.replace('Tiêu chí xong: Caddy, PostgreSQL và backend tự chạy sau reboot; backend tự khởi động lại khi lỗi.', 'Tiêu chí xong: PostgreSQL và backend tự chạy sau reboot; backend tự khởi động lại khi lỗi; reverse proxy chỉ cấu hình nếu hạ tầng VM cần.')
s = s.replace('**KT02 — Camera** · Liên quan T04', '**KT02 — Camera** · Liên quan T29')
s = s.replace('### Thông tin cần làm rõ trong M0', '### Thông tin nghiệp vụ có thể điều chỉnh')
s = s.replace('3. Làm đường HTTPS tới camera thật, đồng thời dựng prototype YuNet/SFace local.', '3. Chạy webapp qua HTTP localhost và camera laptop, đồng thời dựng prototype YuNet/SFace local. HTTPS để giai đoạn VM/tablet.')
start=s.index('## 10 Trình tự triển khai trên Windows')
end=s.index('## 12 Kế hoạch kiểm thử nhận diện và hiệu năng')
s=s[:start]+'''## 10 Trình tự triển khai trên Windows

Các bước này do Codex thực hiện. Bản hiện tại chạy trên laptop để xây dựng và thử nghiệm; không cài web server hay SSL chỉ để mở localhost.

1. Khảo sát máy, camera, dung lượng và runtime; ghi môi trường để đối chiếu khi chuyển VM.
2. Tạo `.venv`, cài thư viện Python từ bản khóa; cài dependency frontend bằng lockfile.
3. Chạy PostgreSQL native riêng cho dự án, chỉ bind loopback; tạo database và tài khoản ứng dụng riêng.
4. Chạy migration và kiểm tra sao lưu/khôi phục trên database thử riêng.
5. Chạy FastAPI tại `127.0.0.1:8000` và frontend tại `http://localhost:5173`. Proxy phát triển chuyển `/api` và `/health` tới backend.
6. Cấp quyền camera và kiểm tra hình ảnh trực tiếp trên laptop; không lưu ảnh mặc định.
7. Bổ sung model và nghiệp vụ theo M1–M4. Chưa bật ghi công nếu chưa đạt kiểm thử cần thiết.
8. Đóng gói frontend thành tài nguyên tĩnh cùng backend; không phụ thuộc Vite dev server ở bản vận hành.
9. Khi chuyển VM, cấu hình database, đường dẫn, bí mật và lịch sao lưu theo môi trường đích. Không đưa đường dẫn laptop vào mã ứng dụng.
10. Thiết lập tiến trình/dịch vụ nền, HTTPS và truy cập tablet ở M5; thử reboot, restore và các thiết bị thực tế.

Lệnh khởi động bản laptop:

```powershell
.\\scripts\\start_local.ps1
```

PostgreSQL dùng cổng `55432` để không ảnh hưởng các database khác. Do PostgreSQL Windows xử lý kém đường dẫn Unicode trong lúc khởi tạo, laptop dùng junction `D:\\ChamCongLocal` trỏ tới workspace; dữ liệu không bị di chuyển. Đường này là cấu hình riêng của máy, không dùng khi chuyển VM Linux.

## 11 HTTPS ở giai đoạn máy chủ ảo

### Giai đoạn laptop

Trình duyệt cho mở camera trên `http://localhost`; chưa cần Caddy hoặc chứng thư. PostgreSQL lưu dữ liệu, FastAPI xử lý nghiệp vụ/AI và React cung cấp giao diện. Chúng chạy trực tiếp bằng các tiến trình local.

### Giai đoạn VM và tablet

Khi iPad/Android truy cập địa chỉ máy chủ từ xa hoặc trong LAN, camera web cần secure context. Lúc đó cấu hình tên miền, SSL/TLS và HTTPS tin cậy trên hạ tầng máy chủ. Có thể dùng HTTPS/reverse proxy có sẵn; không bắt buộc Caddy. Nếu chạy mạng cách ly, dùng chứng thư nội bộ và thiết lập tin cậy trên thiết bị. [S04, S06]

Chỉ backend được truy cập database. Chỉ mở các cổng cần cho webapp; giới hạn truy cập theo mạng sử dụng. Kiểm tra camera trên đúng iPad/Android, không chỉ kiểm tra HTTP 200. Địa chỉ truy cập phải khớp chứng thư.

### Khi VM dùng Linux

Dùng Ubuntu Server LTS còn được hỗ trợ, Python venv, PostgreSQL native và systemd cho backend. Giữ cùng mã nguồn, migration và bộ kiểm thử. Cấu hình HTTPS trên hạ tầng đích, chạy backup theo timer và thử phục hồi trước khi chuyển dữ liệu thực tế. [S07–S08]

''' + s[end:]
s=s.replace('- [HTTPS và phương án Linux](#11-https-nội-bộ-và-phương-án-linux)', '- [HTTPS khi lên VM](#11-https-ở-giai-đoạn-máy-chủ-ảo)')
s=s.replace('\n\n| 28/10/2026 | T01–T05', '\n| 28/10/2026 | T01–T05')
row='| 28/10/2026 | T04 và điều chỉnh triển khai | Camera laptop hoạt động sau khi cấp quyền. Theo yêu cầu người dùng, dừng Caddy và chuyển SSL/HTTPS sang VM; bản laptop dùng HTTP localhost. | evidence/m0/browser-check.md; scripts/start_local.ps1 | Hoàn tất M0 theo phạm vi laptop, tiếp tục T06. |'
s=s.replace('\n\n### Mẫu ghi sau mỗi phiên', '\n'+row+'\n\n### Mẫu ghi sau mỗi phiên')
file.write_text(s, encoding="utf-8")
print('Plan adjusted for laptop HTTP and future VM HTTPS')
