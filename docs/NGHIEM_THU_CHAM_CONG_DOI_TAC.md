# OnTime — kiểm tra hoàn thành phân hệ đối tác

Ngày: 30/10/2026. Phạm vi: triển khai P0–P5 và một phiên người thật trên laptop hiện có. Yêu cầu mới nhất là **tiếp nhận tự động**, thay lựa chọn duyệt quản trị ban đầu. Không kết luận đạt độ chính xác theo nhóm, PAD hoặc tải thực tế.

## Bằng chứng bản hiện hành

- Backend: 381 passed, 10 native-only skipped; nhóm speech 8 passed trên SQL Server cô lập, 0 lần thử mạng ngoài. Các ca SQL đối tác sau đổi luồng: 56 passed và 19 ca chấm công sau chỉnh cuối. P4 đã thử khôi phục SQL thật trên database cô lập.
- Frontend: 63 passed, build đạt; sau đổi nhãn Chấm công nội bộ, build lại đạt. Ruff đạt.
- Bộ cài `partner-candidate-20261030-v6`: 217 tệp, xác minh checksum, cài wheels offline trong venv mới, model/giọng nói/âm thanh/web tại đường dẫn chuyển chỗ; không mở database thật, không kèm dữ liệu riêng. Xem `evidence/m5/native-release-check.json`.
- Người dùng xác nhận camera/popup, tự ghi Vào, nghe thử âm thanh, quét Ra và không đọc lặp. SQL thật có đúng 1 Vào + 1 Ra, cùng một worker, thời gian có thứ tự; có biên nhận duplicate ở cả hai chiều mà số sự kiện vẫn là 2. Tên có nguồn voice; không coi đó là xác minh tên pháp lý.
- UI báo cáo: 1 người đã Vào, 1 cặp đủ, 0 thiếu cặp, 0 đang tiếp nhận. CSV tải qua quản trị khớp cặp thật, dùng giây nguyên nhất quán, các phiên bỏ dở không có giờ công; có nhãn chạy thử không dùng thanh toán. CSV chứa tên giữ tại `.runtime/partner-trial-evidence`, không đưa vào Git/bộ cài.
- Lượt Vào trước bản sửa chưa phát âm báo. Sau sửa, người dùng xác nhận nghe thử và nghe lượt Ra, quét lặp im lặng; cùng bộ phát dùng cho cả hai chiều. Không ghi rằng đã thử lại một lượt Vào mới sau sửa âm thanh.

## Đối chiếu tiêu chí trong kế hoạch

| Yêu cầu | Bằng chứng đã kiểm tra |
|---|---|
| Không cần hồ sơ nhân viên công ty | Các bảng Partner riêng; `test_vendor_code_is_normalized_unique_and_never_creates_an_employee`; số Employee thật vẫn 374 |
| Đúng đối tác/ca/thiết bị, hạn mức, tạo/đóng đợt | `test_partner_admin.py`, `test_native_close_and_correction_serialize_against_same_source`; gán D23 và cấu hình đợt đã thấy trên UI |
| Giữ mã, popup tên, chưa có công trước xác nhận | `test_name_and_same_face_automatically_admit_worker_without_admin_approval`, kiểm tra popup, phiên người thật |
| Đọc tiếng Việt, sửa/nhập tay, lỗi micro/STT | `test_partner_speech.py`, `partner-flow.test.mjs`, thao tác voice thật; nhập tay và lỗi/timeout được kiểm tra chức năng, không gán thử vật lý mọi thiết bị |
| Không hỏi lại tên/cấp mã khi đã có người trong ca | `test_same_person_keeps_code_on_both_devices_before_and_after_checkout`, khôi phục popup/request; cùng worker cho cặp thật |
| Không tự coi văn bản ASR là danh tính | `decode_bounded`, `clean_draft`, `test_voice_returns_draft_only_and_requires_intent_owner_and_current_revision`; tên luôn cần xác nhận |
| Hủy/hết hạn/đổi người/ASR muộn | Các ca expiry, cancellation, pinned same-worker proof và late voice/manual revision trong hai bộ test trên |
| Audio trong RAM, không cloud/backup | Worker chặn mạng; decode/timeout/cleanup tests; bộ cài chuyển chỗ chạy STT offline bằng âm thanh công khai; không lưu audio/transcript cá nhân trong bằng chứng |
| Mã duy nhất, hai kiosk, request thử lại | `test_native_concurrent_final_frames_never_overallocate_or_duplicate_the_person`, final-frame retry, capacity/cancellation không tái dùng số |
| Không cấp thêm mã trong vùng kết quả mơ hồ | Phân loại/margin và pinned-proof reject; không tuyên bố hết false-negative bằng kiểm thử vector giả; đo chất lượng theo nhóm tách riêng |
| Nhận lại cả người đã Ra | Same-person before/after checkout test, biên nhận duplicate thật sau cặp hoàn tất |
| Vào/Ra riêng; Ra không tiếp nhận người mới | `test_unknown_out_never_reserves_a_code_and_wrong_direction_cannot_commit`, phiên Vào/Ra thật |
| Ra phải khớp mẫu và có Vào trước | Các kiểm tra proof/model/scope/expiry trong `partner_attendance.py` và `test_partner_attendance.py`; cặp thật cùng worker |
| Trùng chỉ hiện chữ, không âm/giờ/lượt mới | `kiosk-announcement.test.mjs`, lost-receipt/flow tests; người dùng xác nhận Ra không đọc lặp; SQL có duplicate hai chiều nhưng chỉ hai sự kiện |
| Ca đêm, nhiều đợt, đồng thời, hết hạn | Overnight, binding/scope, concurrency và expiring-store tests; không gọi đây là thử tải thiết bị thật |
| Thiếu Ra không tự đủ công, sửa có lịch sử | `test_partner_reports.py`: missing-out, append-only correction, stale-source rejection, immutable snapshot/CSV |
| Xóa mẫu 48h, restart/restore không hồi sinh | Expiry đúng hạn, read fail khi hết hạn, sweep startup/30s, backup allowlist và native SQL restore tests; kho hỏng có cảnh báo vận hành, không tự tái tạo mẫu |
| Luồng nội bộ/tài khoản/dữ liệu giữ nghiệp vụ | Hồi quy backend toàn bộ, số Employee thật không đổi; chỉ đổi nhãn điều hướng, giữ route/quyền |

## Công việc đã tách riêng theo phạm vi người dùng chốt

Đo FAR/FRR theo nhiều người, PAD bằng ảnh/video đa dạng, iPad/tablet Android thực tế, lưu lượng giờ cao điểm/nhiều kiosk, độ trễ và độ đúng họ tên dưới nhiều mức ồn. Các nội dung này chưa đạt và không được dùng để tuyên bố vận hành đại trà/chứng nhận chống giả. Điểm lưu backup ngoài máy E: cần kết nối lại theo ghi chú vận hành trước đây; bản mã hóa local và kiểm tra khôi phục SQL đã có.

Đợt thử vẫn để mở để người dùng tiếp tục kiểm tra; không chỉnh sửa giờ gốc, không chốt thanh toán hoặc tự thêm người/lượt công. Chức năng đóng/chốt đã được kiểm tra trên SQL cô lập, không cần đóng đợt thật để đổi nhãn giao diện.
