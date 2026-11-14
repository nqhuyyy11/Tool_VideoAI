# AutoVideo - tạo video ngắn bằng AI

Nhập chủ đề, tool tự viết kịch bản, đọc giọng tiếng Việt, tải video nền, chèn phụ đề và xuất MP4 (dọc 9:16, ngang 16:9 hoặc vuông 1:1, chọn bằng `--format`).

## Cài đặt (làm 1 lần)

1. Cài Python 3.10 trở lên: https://www.python.org/downloads/
2. Cài FFmpeg. Windows: mở terminal, chạy `winget install ffmpeg`, rồi mở lại terminal.
3. Trong thư mục này chạy:
   ```
   pip install -r requirements.txt
   ```
4. Đổi tên `.env.example` thành `.env`, điền 2 key miễn phí:
   - Gemini: https://aistudio.google.com/apikey
   - Pexels: https://www.pexels.com/api/
5. Sửa dòng `CHANNEL_STYLE` trong `.env` theo kênh của bạn.

## Chạy

```
python main.py "Vì sao bầu trời có màu xanh"     # 1 video
python main.py --file topics.txt                  # hàng loạt, mỗi dòng 1 chủ đề
python main.py --script example_script.json       # dùng kịch bản tự viết, không cần Gemini
```

Kết quả nằm trong `output/<ngày giờ>_<tên>/`:
- `final.mp4`: video hoàn chỉnh
- `caption.txt`: tiêu đề, mô tả, hashtag để đăng kèm
- `script.json`: kịch bản, sửa rồi chạy lại bằng `--script` nếu muốn

## Tùy chỉnh

- Nhạc nền: bỏ file `.mp3` vào thư mục `music/`, tool chọn ngẫu nhiên một bài.
- Giọng đọc, tốc độ, số từ mỗi dòng phụ đề, âm lượng nhạc: sửa trong `.env`.
- Kiểu chữ phụ đề: sửa dòng `Style:` trong `render.py`.
- Cách viết kịch bản: sửa `PROMPT` trong `script_gen.py`.

## Cấu trúc

| File | Việc |
|---|---|
| `main.py` | Điều phối cả luồng |
| `script_gen.py` | AI viết kịch bản (Gemini) |
| `tts.py` | Giọng đọc (edge-tts) |
| `footage.py` | Tải video nền (Pexels) |
| `render.py` | Ghép video, phụ đề, nhạc (FFmpeg) |
| `config.py` | Đọc cấu hình từ `.env` |
