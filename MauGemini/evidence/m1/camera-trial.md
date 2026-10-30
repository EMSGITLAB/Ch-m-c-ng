# Thử ảnh từ camera laptop ngày 28/10/2026

- Người dùng trực tiếp cấp quyền camera và bấm Chụp thử trong webapp `http://localhost:5173`.
- Người dùng xác nhận kết quả hiển thị: **Ảnh đạt bộ lọc ban đầu**.
- Bản ứng dụng 0.2.0 xử lý ảnh bằng YuNet/SFace trên CPU local; endpoint trả kết quả bộ lọc và không ghi công.
- Luồng thử không lưu ảnh hoặc vector vào database. Không đưa ảnh cá nhân vào bằng chứng hoặc repo.
- Bộ kiểm thử kỹ thuật bổ sung: `backend/tests/test_quality.py`, `backend/tests/test_face_input.py`, `evidence/m1/quality-pipeline.json`.
- Kết quả này chỉ xác nhận một lượt thử camera laptop. Chưa đo độ chính xác danh tính, ngưỡng so khớp, người ngoài danh sách, PAD hoặc iPad/Android.

T08 có chức năng lọc ảnh và căn chỉnh được kiểm tra. Ngưỡng chất lượng hiện là giá trị khởi điểm; tiếp tục hiệu chỉnh bằng dữ liệu thực tế ở T07/T09.
