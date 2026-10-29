# Khung mặt và chụp tự động — 28/10/2026

## Hành vi đã triển khai

- Khung oval nằm trong vùng camera 4:3; SVG định vị tuyệt đối theo kích thước vùng xem, tránh grid làm tăng chiều cao và cắt vòng phía dưới như ảnh người dùng gửi.
- Ảnh gửi lên được crop giữa theo đúng `object-fit: cover` của vùng xem rồi xuất 960×720; không lật ảnh gửi lên. Hình xem trước dạng gương, minh họa trái/phải theo phía của người chụp.
- Có khuôn mặt minh họa chuyển động, xem trước 5 hướng, vòng tiến độ 10 mẫu và vùng hướng cần quay. Hỗ trợ giảm chuyển động theo cài đặt trình duyệt.
- Khi mở phiên, tự rà khoảng 2 lần/giây, từng yêu cầu nối tiếp. Kiểm tra một mặt, chất lượng, vị trí/kích thước so với oval, đúng tư thế và ổn định tối thiểu 3 khung khác nhau qua ≥0,85 giây.
- Preview chỉ phát hiện/đo chất lượng; không tạo hoặc lưu vector, không lưu ảnh. Khi đủ điều kiện, máy chủ phát quyền chụp một lần, hết hạn 3 giây, gắn đúng ảnh/model/phiên/revision/số mẫu.
- Trình duyệt tự gửi đúng ảnh vừa kiểm tra để tạo vector và lưu; không cần bấm chụp từng ảnh. Máy chủ kiểm tra lại chất lượng/tư thế/khung và trạng thái hồ sơ trước ghi. Phiên bản bộ đếm ngăn hai yêu cầu cùng tăng một vị trí.
- Hiển thị hướng dẫn trực tiếp, ba vạch ổn định và Đạt/Chưa đạt sau mỗi ảnh đã thử lưu. Có tạm dừng/bật lại và chụp thủ công dự phòng. Đủ 10 mẫu sẽ dừng tự chụp; người dùng bấm Hoàn tất bộ mẫu.
- Bộ ổn định giữ trạng thái ngắn hạn trong một process, giới hạn 256 phiên; bản triển khai hiện tại chạy một worker. Không phải PAD hoặc xác thực Face ID có cảm biến chiều sâu.

## Bằng chứng

- **91 passed** backend, **44 passed** API/loader trên SQL Server thử riêng, **3 passed** Node test về crop 16:9/portrait/4:3.
- Ruff và TypeScript/Vite build: đạt.
- Model OpenCV thật trên fixture có giấy phép: preview không gọi extract, khung/pose đạt, ổn định `[1,2,3]` và quyền chụp một lần đạt; `auto-capture-pipeline.json`. Không dùng fixture thay dữ liệu người thật.
- Bộ hiệu chỉnh trước khi thêm tự chụp đã hoàn tất trên camera laptop: 10 mẫu, mỗi hướng 2 mẫu; `guided-camera-capture.json`. Đây là kiểm chứng luồng hướng dẫn/chụp thủ công, chưa chứng minh độ chính xác nhận diện/PAD.
- Đã restart backend với tính năng tự chụp. UI thật: vòng oval nằm trọn trong vùng camera, rà soát và tự chuyển hướng sau khi nhận mẫu, có thông báo Đạt sau lưu.
- SQL Server tại checkpoint xác nhận **3 mẫu có `quality.capture_mode=auto`**; xem `camera-auto-trial.json` và `guided-camera-capture.json`. Phiên tự chụp vẫn đang mở tại checkpoint, chưa ghi nhận hoàn tất toàn bộ bộ mẫu. Tablet/độ chính xác/PAD chưa nghiệm thu; KT02/KT03/T09/T14 vẫn chưa hoàn tất.
