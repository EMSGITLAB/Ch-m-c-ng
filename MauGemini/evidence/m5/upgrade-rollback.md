# T36 / KT30 — Nâng ứng dụng và phục hồi tương thích, 29/10/2026

`scripts/check_upgrade.py --release upgrade-candidate-20261029-a` đã chạy trên backup thực từ USB, với database khôi phục riêng. Không chuyển hoặc sửa database/dịch vụ đang dùng.

- Snapshot ứng dụng trước và ứng viên đều cài dependency trong venv mới bằng wheels offline, khởi động model và phục vụ frontend; cấu hình nghiệp vụ giữ nguyên.
- Nâng ứng dụng ở schema hiện tại, chạy Alembic head và smoke test trên database mới đạt. Đây là nâng bản ứng dụng cùng schema, không phải bằng chứng nâng giữa hai revision schema khác nhau.
- Gây lỗi sau khi **commit** tạo bảng và ghi dữ liệu thử trong database ứng viên. Công cụ đã khôi phục một database mới khác và ứng dụng tương thích từ archive gốc, cài offline/chạy app/model đạt; bảng của bước nâng lỗi không có trong bản quay lui.
- Số bản ghi nguồn và checksum archive giữ nguyên. Phiên đăng nhập, quyền kiosk, policy của các bản phục hồi đều tắt. Không dùng ứng dụng cũ với database đã bị DDL sửa dở.
- Toàn bộ phép thử mất 985,24 giây, bao gồm nhiều lần cài venv, model warmup và khôi phục. Đây không phải thời gian dừng dịch vụ nguồn; nguồn vẫn hoạt động riêng.
- Bộ ứng viên thiếu hợp đồng `authenticated-v2-external-deletion-ledger`, sai checksum, có đường dẫn thoát/thành phần riêng tư hoặc thiếu wheels bị từ chối trước khi copy/chạy. `test_upgrade.py` kiểm tra các lỗi này; fixture của verifier không được coi là bộ cài thực.

Kết quả: `upgrade-rollback-check.json`. Công cụ vận hành: `backend/app/upgrade.py`, `scripts/stage_upgrade.py`. Hướng dẫn chuyển thật, sao lưu sau khi dừng nhận công và giới hạn quay lui sau phát sinh công mới nằm trong `HUONG_DAN_VAN_HANH.md`.

T36 đạt cho bản nâng ứng dụng hiện tại và tình huống migration lỗi có DDL dở. Khi một bản sau thay revision schema, cần thêm phép nâng từ revision trước với dữ liệu tương thích; chưa có bằng chứng đó hôm nay. Chưa kiểm thử VM hoặc chuyển traffic thật.
