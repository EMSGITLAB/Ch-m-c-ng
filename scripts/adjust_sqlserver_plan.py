"""Record the user's database choice without rewriting the historical journal."""
from pathlib import Path

root=Path(__file__).resolve().parents[1]
file=root/'KE_HOACH_TRIEN_KHAI.md'
s=file.read_text(encoding='utf-8')
body,journal=s.split('## 17 Nhật ký triển khai',1)
body=body.replace('**Phiên bản:** 1.1','**Phiên bản:** 1.2')
body=body.replace('PostgreSQL','SQL Server')
body=body.replace('- Các trạng thái, checklist và bằng chứng được cập nhật trực tiếp trong file Markdown này.', '- Database hiện tại dùng SQL Server có sẵn trên laptop. PostgreSQL để sau, không nằm trong luồng khởi động.\n- Các trạng thái, checklist và bằng chứng được cập nhật trực tiếp trong file Markdown này.')
body=body.replace('| Dữ liệu | SQL Server; truy vấn vector trực tiếp trong bộ nhớ đủ cho quy mô ban đầu, cập nhật cache khi hồ sơ đổi. |','| Dữ liệu | SQL Server qua SQLAlchemy/pyodbc, ODBC Driver 18; laptop dùng Windows Authentication. Vector được so khớp trong bộ nhớ và cập nhật cache khi hồ sơ đổi. |')
body=body.replace('Chạy SQL Server native riêng cho dự án, chỉ bind loopback; tạo database và tài khoản ứng dụng riêng.', 'Dùng instance SQL Server có sẵn, tạo database ChamCongFaceLocal riêng có dấu nhận diện dự án; không sửa database khác. Laptop phát triển dùng Windows Authentication.')
body=body.replace('SQL Server dùng cổng `55432` để không ảnh hưởng các database khác. Do SQL Server Windows xử lý kém đường dẫn Unicode trong lúc khởi tạo, laptop dùng junction `D:\\ChamCongLocal` trỏ tới workspace; dữ liệu không bị di chuyển. Đường này là cấu hình riêng của máy, không dùng khi chuyển VM Linux.', 'SQL Server trên laptop là instance mặc định localhost, đã có ODBC Driver 18. Developer Edition hiện có chỉ dùng phát triển/kiểm thử; khi vận hành miễn phí dùng Express hoặc hạ tầng đã có giấy phép. Kết nối của bản vận hành phải có quyền tối thiểu theo database. PostgreSQL portable đã dừng; junction cũ chỉ phục vụ bản thử PostgreSQL trước đó, ứng dụng hiện tại không cần dùng.')
body=body.replace('Dùng Ubuntu Server LTS còn được hỗ trợ, Python venv, SQL Server native và systemd cho backend.', 'Nếu VM dùng Linux, chọn OS được SQL Server hỗ trợ hoặc kết nối tới SQL Server riêng; backend dùng Python venv, ODBC phù hợp và systemd.')
body=body.replace('sao lưu DB mỗi ngày','sao lưu DB mỗi ngày')
body=body.replace('`pg_dump`','SQL Server BACKUP DATABASE')
body=body.replace('Phương án ghi tạm','Phương án ghi tạm')
body=body.replace('  - Minh chứng: backend/migrations/versions; evidence/m0/database-check.json','  - Minh chứng: backend/migrations/versions; evidence/m0/sqlserver-check.json')
body=body.replace('| Bước tiếp theo | T06 nạp model, sau đó T08 kiểm tra chất lượng; T07 cần các phiên ảnh thực tế |','| Bước tiếp theo | T08 kiểm tra chất lượng ảnh, T07 thu các phiên ảnh thực tế; tiếp tục chức năng quản trị khi đủ nền tảng |')
body=body.replace('| Đầu việc đang làm | T06 tải và kiểm tra model YuNet/SFace |','| Đầu việc đang làm | Chuyển kết nối runtime sang SQL Server; T08 kiểm tra chất lượng ảnh |')
extra='''
### Edition SQL Server và phạm vi miễn phí

Laptop có SQL Server 2025 Enterprise Developer 17.0.1000.7 và ODBC Driver 18. Dùng edition này để xây dựng/kiểm thử; không coi đó là giấy phép vận hành thực tế. SQL Server Express là lựa chọn miễn phí khi đưa hệ thống vào sử dụng, hoặc dùng máy chủ đã có giấy phép hợp lệ. Không sử dụng tính năng chỉ có ở Enterprise cho nghiệp vụ ứng dụng. Nguồn: [Microsoft SQL Server editions](https://learn.microsoft.com/en-us/sql/sql-server/editions-and-components-of-sql-server-2025?view=sql-server-ver17).

'''
body=body.replace('## 03 Chức năng của webapp',extra+'## 03 Chức năng của webapp')
row='| 28/10/2026 | T03 và T05 | Theo yêu cầu người dùng, chuyển từ PostgreSQL sang SQL Server có sẵn; database riêng ChamCongFaceLocal. Migration, Unicode, backup/restore SQL Server đạt; PostgreSQL dự án đã dừng. | evidence/m0/sqlserver-environment.json; evidence/m0/sqlserver-check.json | Chạy lại backend bằng SQL Server rồi tiếp tục M1. |'
journal=journal.replace('\n\n### Mẫu ghi sau mỗi phiên','\n'+row+'\n\n### Mẫu ghi sau mỗi phiên')
s=body+'## 17 Nhật ký triển khai'+journal
file.write_text(s,encoding='utf-8')
print('Plan now uses SQL Server; prior PostgreSQL evidence preserved as history')
