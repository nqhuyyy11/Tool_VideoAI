# AutoVideo - Tài liệu mô tả tool (dùng làm prompt để dựng bản web)

> Cách dùng: đưa file này cho AI (Claude, v.v.) kèm câu: "Dựa vào tài liệu này, hãy xây dựng bản web của tool". Phần **"Prompt mẫu"** ở cuối có thể copy dán thẳng.

---

## 1. Tool này làm gì

AutoVideo là tool tạo **video ngắn tự động bằng AI**. Người dùng nhập một chủ đề, tool tự:

1. Nhờ AI viết kịch bản (chia thành các cảnh).
2. Đọc kịch bản thành giọng nói tiếng Việt.
3. Tải video nền miễn phí bản quyền khớp với từng cảnh.
4. Ghép video + giọng đọc + phụ đề chạy theo lời + nhạc nền.
5. Xuất file MP4 và một file caption (tiêu đề, mô tả, hashtag) để đăng bài.

Hiện tại tool chạy bằng dòng lệnh Python trên máy cá nhân (Windows). Mục tiêu: **đưa lên web** để người dùng thao tác bằng giao diện thay vì gõ lệnh.

## 2. Luồng xử lý hiện tại (pipeline)

| Bước | File | Việc | Công nghệ / Model |
|---|---|---|---|
| 1 | `script_gen.py` | AI viết kịch bản JSON từ chủ đề | Gemini `gemini-2.5-flash` (dự phòng: `gemini-2.5-flash-lite`, `gemini-2.0-flash`) |
| 2 | `tts.py` | Tạo giọng đọc mp3 + mốc thời gian từng từ | edge-tts, giọng `vi-VN-HoaiMyNeural` (nữ) / `vi-VN-NamMinhNeural` (nam) |
| 3 | `footage.py` | Tìm và tải video nền theo keywords | Pexels API (chính), Pixabay API (dự phòng) |
| 4 | `render.py` | Crop/lặp clip, nối cảnh, phụ đề, trộn nhạc, xuất MP4 | FFmpeg + ffprobe (libx264, aac, phụ đề ASS) |
| 5 | `main.py` | Điều phối, gom caption, lưu `caption.txt`, `script.json` | Python 3.10+ |

`config.py` đọc cấu hình từ file `.env`.

## 3. Đầu vào của người dùng (những gì giao diện web cần cho nhập)

| Trường | Mô tả | Giá trị / Mặc định |
|---|---|---|
| Chủ đề | Câu mô tả nội dung video (bắt buộc nếu không tự đưa kịch bản) | Văn bản tự do, tiếng Việt |
| Chế độ kịch bản | AI viết từ chủ đề **hoặc** người dùng tự nhập/sửa kịch bản | AI (mặc định) / Tự viết |
| Khổ video | Kích thước khung hình | `vertical` 1080x1920 (9:16, mặc định) / `horizontal` 1920x1080 (16:9) / `square` 1080x1080 (1:1) |
| Giọng đọc | Giọng edge-tts | `vi-VN-HoaiMyNeural` (nữ, mặc định) / `vi-VN-NamMinhNeural` (nam) |
| Tốc độ đọc | Tốc độ giọng | `+10%` mặc định (ví dụ `+0%`, `+15%`) |
| Phong cách kênh | Mô tả kênh để AI viết đúng giọng | Mặc định: "Kênh 'Sự thật thú vị' cho người Việt 18-30 tuổi, giọng kể gần gũi, hấp dẫn, có chút hài hước, thông tin chính xác." |
| Số từ mỗi dòng phụ đề | Gom từ thành cụm | `4` mặc định |
| Nhạc nền | Chọn bài trong thư viện hoặc không dùng | Tuỳ chọn; âm lượng `0.12` (0.0 - 1.0) |
| Chạy hàng loạt | Nhiều chủ đề, mỗi dòng 1 chủ đề (dòng bắt đầu bằng `#` bị bỏ qua) | Tuỳ chọn |

## 4. Định dạng kịch bản (JSON)

```json
{
  "title": "Tiêu đề video, dưới 80 ký tự",
  "scenes": [
    {"text": "Câu thoại cảnh 1 (sẽ được đọc và hiện phụ đề).", "keywords": "octopus underwater"},
    {"text": "Câu thoại cảnh 2.", "keywords": "ocean deep blue"}
  ],
  "caption": "Mô tả đăng kèm video, 1-2 câu",
  "hashtags": ["#fyp", "#kienthuc", "#suthatthuvi"]
}
```

Quy tắc:
- `text` bắt buộc; cảnh có `text` rỗng bị bỏ.
- `keywords` là 2-3 từ **tiếng Anh** mô tả hình ảnh cụ thể để tìm video stock (vd "ocean waves", "city night traffic"). Rỗng thì dùng `nature landscape`.
- Nếu thiếu `title` thì lấy 80 ký tự đầu của câu thoại đầu tiên.
- Prompt gửi Gemini yêu cầu: 6-9 cảnh, tổng 120-160 từ (khoảng 45-60 giây); cảnh 1 là câu hook gây tò mò; cảnh cuối kêu gọi theo dõi/bình luận; câu viết để đọc thành tiếng (ngắn, không emoji, không ký hiệu lạ); thông tin chính xác, không bịa số liệu; chỉ trả về JSON.

## 5. Đầu ra

Mỗi lần chạy tạo một thư mục `output/<ngày_giờ>_<tên-không-dấu>/`:
- `final.mp4`: video hoàn chỉnh (H.264 + AAC, 30 fps, tối ưu phát web `faststart`).
- `caption.txt`: tiêu đề + mô tả + hashtag, để copy khi đăng bài.
- `script.json`: kịch bản đã dùng (để sửa rồi chạy lại).

## 6. Quy tắc kỹ thuật quan trọng (bản web phải giữ)

**Phụ đề**
- Chữ Arial 88, in hoa, đậm, trắng, viền đen dày 6, đổ bóng 3, hiệu ứng mờ dần 60 ms.
- Gom 4 từ mỗi cụm, ngắt sớm ở dấu câu (`, . ! ? : ; …`).
- Thời gian từng cụm lấy từ mốc từng từ của TTS (WordBoundary); nếu không có thì chia đều theo thời lượng cảnh.
- Lề dưới tuỳ khổ: dọc 560 px, ngang 130 px, vuông 200 px.

**Video nền**
- Pexels lọc theo hướng: dọc → `portrait`, ngang → `landscape`, vuông → `square`; chọn bản có cạnh dài gần nhất với khung hình.
- Mỗi cảnh thử lần lượt: từ khoá đầy đủ → từ đầu tiên của từ khoá → `abstract background`.
- Không dùng lại cùng một clip trong một video.
- Không tìm được clip (hoặc không có key) thì dùng nền màu tối `#1a1a2e`.
- Clip được scale + crop về đúng khổ, lặp lại nếu ngắn hơn giọng đọc.

**Giọng đọc**
- Thời lượng mỗi cảnh = độ dài file mp3 của cảnh đó.
- edge-tts là dịch vụ không chính thức, **đôi khi không trả audio** (`NoAudioReceived`). Bắt buộc có cơ chế thử lại (hiện tại: tối đa 7 lần, chờ 3s, 6s, 9s...). Đợt lỗi >1 phút vẫn làm hỏng job.

**Gemini**
- Tự chuyển model dự phòng khi lỗi 429 (hết hạn mức) hoặc 5xx (quá tải).

**FFmpeg**
- Là bước nặng nhất (CPU, vài chục giây tới vài phút/video). Phải chạy ở **server/worker nền**, không chạy trong trình duyệt.

## 7. Dịch vụ ngoài và biến cấu hình

| Biến `.env` | Dùng cho | Ghi chú |
|---|---|---|
| `GEMINI_API_KEY` | Viết kịch bản | Bắt buộc nếu dùng chế độ AI |
| `GEMINI_MODEL`, `GEMINI_FALLBACK_MODELS` | Model chính và dự phòng | Mặc định như bảng ở mục 2 |
| `PEXELS_API_KEY` | Video nền (ưu tiên) | Có key này thì dùng Pexels |
| `PIXABAY_API_KEY` | Video nền dự phòng | Không lọc được theo hướng khung |
| `TTS_VOICE`, `TTS_RATE` | Giọng và tốc độ đọc | |
| `CHANNEL_STYLE` | Phong cách kênh trong prompt AI | |
| `VIDEO_FORMAT` | Khổ mặc định | `vertical` / `horizontal` / `square` |
| `WORDS_PER_CAPTION`, `MUSIC_VOLUME`, `OUTPUT_DIR` | Phụ đề, nhạc, thư mục xuất | |

**Các API key phải nằm ở server**, không bao giờ để lộ ra trình duyệt.

## 8. Lỗi và hạn chế đã biết (nên xử lý khi làm bản web)

1. Đôi khi video nền là clip **green screen có chữ "COMMENT"/overlay** (từ Pixabay hoặc từ khoá dự phòng `abstract background`). Cần lọc bỏ.
2. Nếu TTS lỗi kéo dài, cả job dừng và phải làm lại từ đầu → nên **lưu kết quả từng cảnh** (mp3, clip) để chạy lại không mất công.
3. Pixabay không lọc được hướng khung, video ngang bị crop nhiều khi làm khổ dọc.
4. Chưa có test tự động.
5. Nhạc nền chưa được kiểm thử (thư mục `music/` đang trống).
6. Chạy hàng loạt (`--file`) chưa được kiểm thử.

## 9. Gợi ý kiến trúc bản web

**Giao diện (frontend)**
1. Màn hình tạo video: ô chủ đề, chọn khổ video (3 thẻ có hình minh hoạ tỷ lệ), chọn giọng, tốc độ, nhạc nền; nút "Tạo video".
2. Bước duyệt kịch bản (tuỳ chọn): hiện danh sách cảnh để người dùng sửa câu thoại và keywords trước khi dựng.
3. Màn hình tiến độ: 5 bước (kịch bản → giọng → video nền → ghép → hoàn tất), thanh tiến độ, báo lỗi rõ ràng và nút "Thử lại".
4. Màn hình kết quả: phát video, nút tải MP4, khu vực copy caption + hashtag, nút "Tạo lại với khổ khác".
5. Lịch sử: danh sách video đã tạo, mở lại kịch bản để chỉnh và dựng lại.

**Máy chủ (backend)**
- Mỗi video là một **job** chạy nền (hàng đợi), vì FFmpeg và TTS mất thời gian.
- Trạng thái job: `queued` → `scripting` → `voicing` → `fetching_footage` → `rendering` → `done` / `failed`.
- API gợi ý:
  - `POST /api/jobs` — tạo job (chủ đề hoặc kịch bản + các tuỳ chọn ở mục 3)
  - `GET /api/jobs/{id}` — trạng thái, tiến độ, lỗi
  - `GET /api/jobs/{id}/video` — tải/phát `final.mp4`
  - `GET /api/jobs/{id}/caption` — nội dung caption
  - `POST /api/script` — chỉ sinh kịch bản (để người dùng duyệt trước)
  - `GET /api/jobs` — lịch sử
- Cập nhật tiến độ bằng polling hoặc SSE/WebSocket.
- Backend cần: Python 3.10+, FFmpeg cài trên server, lưu file video (đĩa hoặc object storage), giới hạn số job chạy đồng thời và tần suất gọi API theo người dùng.
- **Cách đơn giản nhất để giữ nguyên logic**: giữ nguyên các module Python hiện có (`script_gen`, `tts`, `footage`, `render`) và bọc bằng FastAPI + hàng đợi (RQ/Celery hoặc `BackgroundTasks` cho bản đầu).

## 10. Phạm vi bản đầu (MVP) đề xuất

- Có: nhập chủ đề, chọn khổ video + giọng, theo dõi tiến độ, xem/tải video, copy caption.
- Chưa cần: tài khoản, thanh toán, đăng bài tự động, chỉnh sửa timeline, nhạc nền, chạy hàng loạt.

---

## Prompt mẫu (copy dán cho AI)

```
Hãy xây dựng bản WEB cho tool "AutoVideo" mô tả trong tài liệu dưới đây.

Yêu cầu:
- Giữ nguyên logic của các module Python hiện có (script_gen, tts, footage, render); bọc chúng bằng backend FastAPI, mỗi video là 1 job chạy nền với trạng thái queued/scripting/voicing/fetching_footage/rendering/done/failed.
- Frontend (React hoặc Next.js): form nhập chủ đề, chọn khổ video (vertical/horizontal/square), chọn giọng (nữ/nam), tốc độ đọc; màn hình tiến độ 5 bước; màn hình kết quả có trình phát video, nút tải MP4 và khu vực copy caption + hashtag; trang lịch sử.
- Có bước duyệt/sửa kịch bản trước khi dựng (tuỳ chọn người dùng bật).
- API key (Gemini, Pexels, Pixabay) chỉ ở server qua biến môi trường.
- Xử lý các lỗi đã biết ở mục 8: thử lại TTS, lưu kết quả từng cảnh để chạy lại, lọc clip green screen/overlay.
- Giao diện tiếng Việt, hiển thị tốt trên điện thoại.
- Trước khi code: nêu giả định, đề xuất cấu trúc thư mục và kế hoạch từng bước, rồi mới bắt đầu.

[Dán toàn bộ nội dung file AutoVideo_WebTool_Spec.md vào đây]
```
