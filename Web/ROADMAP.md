# AutoVideo - Tính năng sẽ phát triển thêm

Bản hiện tại là bản gọn: đăng nhập, tạo video bằng AI, thư viện video.
Danh sách dưới đây xếp theo thứ tự nên làm.

## 1. Chất lượng video (làm trước)

- [ ] **Video nền ổn định hơn.** Thêm key Pexels làm nguồn chính, Pixabay làm dự phòng.
  Nếu cảnh nào không tải được video nền thì báo cho người dùng, không lặng lẽ dùng nền màu trơn.
  (Lý do: Pixabay hay báo lỗi 429 khi gọi nhiều.)
- [ ] **Nhạc nền.** Thư mục `autovideo/music/` đang trống. Thêm nhạc nhỏ phía sau giọng đọc.
- [ ] **Xem và sửa kịch bản trước khi dựng.** Cho sửa chữ và từ khoá từng cảnh để khỏi phải làm lại cả video.

## 2. Dùng được với nhiều người

- [ ] **Hàng đợi và giới hạn.** Hiện mỗi lúc chỉ chạy 1 job. Giới hạn số video mỗi người mỗi ngày để khỏi tốn tiền API.
- [ ] **Đặt lại mật khẩu** (quên mật khẩu) và **đăng nhập bằng Google**.
- [ ] **Xoá video trong Thư viện** (kiểm tra xem đã có chưa, chưa thì thêm).

## 3. Trải nghiệm

- [ ] Tạo video hàng loạt từ danh sách chủ đề (tool gốc đã có `--file`, cần kiểm thử).
- [ ] Chọn thêm giọng đọc, kiểu phụ đề, thêm logo hoặc watermark.
- [ ] Thông báo (email hoặc trình duyệt) khi video xong, vì mỗi video mất 1 đến 3 phút.

## 4. Đưa lên mạng

- [ ] Deploy lên host (đã có `Dockerfile`), nhớ cài FFmpeg trên máy chủ.
- [ ] Test tự động và ghi log lỗi.
- [ ] Gói dùng và thanh toán (nếu muốn thu tiền).

## Đã làm

- [x] Giao diện mới: nền gradient, thẻ kính mờ, nút gradient.
- [x] Trang đăng ký có ô nhập lại mật khẩu.
- [x] Tự thử lại khi Pixabay báo giới hạn tốc độ (429).
