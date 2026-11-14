# AutoVideo Web

Trang web để dùng tool AutoVideo bằng giao diện: nhập chủ đề, bấm "Tạo video", theo dõi tiến độ, xem và tải video. Video được lưu trên Supabase, mỗi người đăng nhập chỉ thấy video của mình.

Làm lần lượt từ Bước 1 đến Bước 7 là mở được web trên máy mình.

## Cấu trúc thư mục

```
Tool_VideoAI/
  autovideo/              tool gốc (script_gen, tts, footage, render)
  Web/
    backend/
      app.py              các API + phục vụ giao diện
      auth.py             kiểm tra đăng nhập
      jobs.py             hàng đợi: mỗi video là 1 job chạy nền, lần lượt từng cái
      pipeline.py         gọi tool gốc theo 5 bước, báo tiến độ, giữ kết quả từng cảnh
      storage.py          nén 720p, tạo thumbnail, upload Supabase, ghi bảng videos
      errors.py           đổi lỗi kỹ thuật thành câu tiếng Việt
      settings.py         đọc file .env
    frontend/
      login.html          đăng nhập / đăng ký
      index.html          trang "Tạo video"
      library.html        trang "Thư viện"
      css/style.css
      js/common.js, login.js, create.js, library.js
    supabase/schema.sql   bảng + bucket + policy (dán vào SQL Editor)
    .env.example          mẫu file cấu hình
    requirements.txt
    Dockerfile            dùng khi đưa lên host
```

Cách hoạt động: trình duyệt đăng nhập qua Supabase Auth, rồi gửi chủ đề lên backend. Backend dựng video bằng tool gốc, nén về 720p, upload lên bucket `videos`, ghi một dòng vào bảng `videos` và trả link cho web phát.

---

## Bước 1: Kiểm tra Python và FFmpeg

Mở PowerShell, gõ:

```powershell
python --version
ffmpeg -version
```

Cần Python 3.10 trở lên và FFmpeg. Nếu thiếu FFmpeg: `winget install ffmpeg`, rồi đóng và mở lại PowerShell.

## Bước 2: Tạo project Supabase

1. Vào https://supabase.com, bấm **Start your project**, đăng nhập bằng GitHub hoặc email.
2. Bấm **New project**.
3. Điền:
   - **Name**: `autovideo` (tuỳ ý).
   - **Database Password**: bấm **Generate a password** rồi lưu lại ở nơi an toàn.
   - **Region**: chọn **Southeast Asia (Singapore)** cho gần Việt Nam.
   - **Plan**: Free.
4. Bấm **Create new project** và chờ 1-2 phút tới khi project sẵn sàng.

## Bước 3: Tạo bảng, bucket và policy

Cách nhanh nhất là chạy file SQL có sẵn, nó tạo đủ cả ba thứ.

1. Trong project, mở **SQL Editor** ở thanh bên trái.
2. Bấm **New query**.
3. Mở file `supabase/schema.sql` trong thư mục này, copy toàn bộ, dán vào ô soạn thảo.
4. Bấm **Run**. Thấy dòng `Success. No rows returned` là xong.

Kiểm tra lại trên dashboard:

| Xem ở đâu | Phải thấy gì |
|---|---|
| **Table Editor** → bảng `videos` | Các cột `id, user_id, title, prompt, caption, file_url, thumbnail_url, created_at` |
| **Authentication** → **Policies** → bảng `videos` | RLS đang bật, có 1 policy "Xem video cua minh" |
| **Storage** → bucket `videos` | Bucket **không** có nhãn Public, giới hạn 50 MB |
| **Storage** → **Policies** | Có policy "Doc file video cua minh" |

File SQL làm những việc sau:

- **Bảng `videos`**: mỗi dòng là một video. Cột `file_url` và `thumbnail_url` lưu đường dẫn file trong bucket (dạng `<user_id>/<video_id>.mp4`), không phải link đầy đủ. Lý do: bucket để riêng tư nên không có link cố định; backend tạo link tạm có hạn 1 giờ mỗi khi web cần phát.
- **Row Level Security (RLS)**: sau khi bật, mặc định không ai đọc hay ghi được. Policy duy nhất cho phép người đã đăng nhập đọc các dòng có `user_id` trùng với mình. Không có policy ghi, nên trình duyệt không tự thêm hay xoá dòng được; việc đó chỉ backend làm.
- **Bucket `videos`**: riêng tư, tối đa 50 MB mỗi file, chỉ nhận mp4 và jpg.
- **Policy của bucket**: người đã đăng nhập chỉ đọc được file nằm trong thư mục mang `user_id` của mình.

Nếu muốn tạo bucket bằng tay thay vì SQL: **Storage** → **New bucket** → tên `videos` → để tắt **Public bucket** → bật **Restrict file upload size** và nhập `50 MB` → **Save**. Sau đó vẫn chạy file SQL để có bảng và policy.

## Bước 4: Cài đặt đăng nhập bằng email

1. Mở **Authentication** → **Sign In / Providers** → **Email**. Mặc định đã bật.
2. Khi chạy thử trên máy, nên tắt **Confirm email** rồi bấm **Save**. Đăng ký xong sẽ vào được ngay, không phải chờ email xác nhận (gói Free chỉ gửi được vài email mỗi giờ).
3. Khi đưa web lên mạng cho người khác dùng thì bật lại **Confirm email**.

## Bước 5: Lấy URL và key, điền vào file `.env`

1. Trong thư mục `Web`, tạo file `.env` từ file mẫu:

   ```powershell
   cd e:\MyTool\Tool_VideoAI\Web
   copy .env.example .env
   ```

2. Trên Supabase, mở **Project Settings** (biểu tượng bánh răng) rồi lấy 3 giá trị:

   | Dòng trong `.env` | Lấy ở đâu |
   |---|---|
   | `SUPABASE_URL` | **Data API** → **Project URL**, dạng `https://abcdefgh.supabase.co` |
   | `SUPABASE_ANON_KEY` | **API Keys** → **Publishable key**, hoặc key `anon` `public` ở tab Legacy |
   | `SUPABASE_SERVICE_ROLE_KEY` | **API Keys** → **Secret key**, hoặc key `service_role` ở tab Legacy |

3. Mở file `.env` bằng VS Code, dán từng giá trị vào sau dấu `=`, không thêm dấu cách hay dấu nháy. Lưu file.

Về hai loại key:

- **Key công khai** (`anon` / publishable) được phép nằm trong trình duyệt. Nó chỉ làm được những gì policy cho phép.
- **Key bí mật** (`service_role` / secret) bỏ qua mọi policy, có toàn quyền với dữ liệu. Chỉ để trong `.env` của backend. Không dán vào file nào trong thư mục `frontend`, không gửi cho ai, không đưa lên GitHub.

Key Gemini và Pixabay không cần điền lại: web tự đọc từ thư mục `autovideo`.

## Bước 6: Cài thư viện Python

Trên máy này mình đã tạo sẵn thư mục `.venv` và cài đủ thư viện, bạn bỏ qua bước này. Trên máy khác thì chạy:

```powershell
cd e:\MyTool\Tool_VideoAI\Web
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Bước 7: Chạy web

```powershell
cd e:\MyTool\Tool_VideoAI\Web
.\.venv\Scripts\python.exe -m uvicorn backend.app:app --port 8000
```

Thấy dòng `Uvicorn running on http://127.0.0.1:8000` thì mở trình duyệt vào http://localhost:8000.

1. Bấm tab **Đăng ký**, nhập email và mật khẩu (từ 6 ký tự).
2. Ở trang **Tạo video**, nhập chủ đề, chọn khổ video, giọng đọc, bấm **Tạo video**.
3. Chờ 5 bước chạy xong (thường 1-3 phút). Video hiện ngay trên trang, có nút **Tải MP4** và **Copy caption**.
4. Vào **Thư viện** để xem lại, tải về hoặc xoá video cũ.

Dừng server: bấm `Ctrl + C` trong cửa sổ PowerShell.

Muốn mở bằng điện thoại cùng mạng wifi: chạy thêm `--host 0.0.0.0`, rồi trên điện thoại vào `http://<IP của máy tính>:8000` (xem IP bằng lệnh `ipconfig`, dòng IPv4 Address).

---

## Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách sửa |
|---|---|---|
| Trang báo "Thiếu cấu hình trong file .env: ..." | Chưa tạo `.env` hoặc còn dòng để trống | Làm lại Bước 5, rồi tắt và chạy lại server |
| "Không kết nối được tới Supabase để kiểm tra đăng nhập" | `SUPABASE_URL` sai, hoặc mất mạng | Copy lại Project URL, không có dấu `/` hay khoảng trắng thừa |
| Đăng nhập báo "Email chưa được xác nhận" | Supabase đang bật Confirm email | Bấm link trong email, hoặc tắt Confirm email (Bước 4) rồi đăng ký lại |
| Đăng ký báo "Gửi quá nhiều yêu cầu" | Gói Free giới hạn số email mỗi giờ | Tắt Confirm email (Bước 4), hoặc chờ 1 giờ |
| Lỗi có chữ "Chưa có bucket" hoặc "Chưa có bảng" | Chưa chạy `schema.sql` | Làm lại Bước 3 rồi bấm **Thử lại** |
| Lỗi "Supabase báo lỗi ... (mã 401)" hoặc 403 | `SUPABASE_SERVICE_ROLE_KEY` sai hoặc dán nhầm key công khai | Copy lại key bí mật, chạy lại server |
| "Dịch vụ giọng đọc (edge-tts) tạm thời không trả về âm thanh" | Server edge-tts chập chờn | Chờ 1 phút rồi bấm **Thử lại**; cảnh đã xong không phải làm lại |
| "Gemini đã hết hạn mức" | Hết lượt miễn phí trong ngày/phút | Chờ vài phút rồi bấm **Thử lại** |
| Video chỉ có nền màu tối, không có cảnh quay | Pixabay hoặc Pexels từ chối (lỗi 429), hoặc không có key | Chờ rồi tạo lại; nên lấy thêm key Pexels miễn phí tại https://www.pexels.com/api/ và thêm dòng `PEXELS_API_KEY=...` vào `.env` |
| "Video sau khi nén vẫn nặng ... MB" | File vượt 50 MB của gói Free | Dùng chủ đề ngắn hơn. Video 1 phút thường chỉ 5-15 MB nên hiếm gặp |
| "Bạn đang có một video chưa tạo xong" | Mỗi người chỉ tạo 1 video một lúc | Chờ video đang chạy xong |
| "Không tìm thấy video đang tạo (có thể server vừa khởi động lại)" | Tắt server khi video đang dựng | Tạo lại video. Video đã xong thì không mất |
| "Máy chủ chưa cài FFmpeg" | Chưa cài hoặc chưa mở lại PowerShell sau khi cài | `winget install ffmpeg`, mở lại PowerShell, chạy lại server |
| `Không tìm thấy tool gốc tại ...` khi tạo video | Thư mục `autovideo` nằm chỗ khác | Sửa `AUTOVIDEO_DIR` trong `.env` |
| Cổng 8000 đang bị dùng | Chương trình khác chiếm cổng | Đổi sang `--port 8001` và mở http://localhost:8001 |

Khi cần xem lỗi chi tiết, nhìn cửa sổ PowerShell đang chạy server: mọi lỗi đều in ra ở đó.

## Giới hạn của gói Free

- Tổng dung lượng lưu trữ 1 GB. Mỗi video khoảng 5-15 MB, nên chứa được khoảng 70-200 video. Xoá video cũ trong Thư viện khi gần đầy.
- Project Free bị tạm dừng nếu không có ai dùng trong 1 tuần. Vào dashboard bấm **Restore** để mở lại.

---

## Đưa lên host

Làm phần này sau khi web đã chạy ổn trên máy.

Web cần một host chạy được FFmpeg trong nhiều phút, nên các host chỉ chạy hàm ngắn (Vercel, Netlify) không dùng được. Dưới đây là cách làm với Render bằng Docker; Railway hay một VPS cũng làm tương tự.

### 1. Giấu key trước khi đưa code lên GitHub

File `autovideo/.env.example` đang chứa key Gemini và Pixabay thật. Đổi tên nó thành `.env` để Git bỏ qua:

```powershell
cd e:\MyTool\Tool_VideoAI\autovideo
ren .env.example .env
```

Tool gốc vẫn chạy như cũ vì nó ưu tiên đọc `.env`.

Tạo file `.gitignore` trong thư mục `Tool_VideoAI` với nội dung:

```
.env
.venv/
__pycache__/
autovideo/output/
Web/work/
```

### 2. Đưa code lên GitHub

Tạo một repository **Private** trên GitHub, rồi:

```powershell
cd e:\MyTool\Tool_VideoAI
git init
git add .
git status
```

Đọc kỹ danh sách file ở `git status`: không được có file `.env` nào. Sau đó:

```powershell
git commit -m "AutoVideo web"
git branch -M main
git remote add origin https://github.com/<tên-bạn>/<tên-repo>.git
git push -u origin main
```

### 3. Tạo dịch vụ trên Render

1. Vào https://render.com, đăng nhập bằng GitHub.
2. **New** → **Web Service** → chọn repository vừa tạo.
3. Điền:
   - **Language**: Docker
   - **Dockerfile Path**: `Web/Dockerfile`
   - **Docker Build Context Directory**: `.`
4. Ở phần **Environment Variables**, thêm:
   - `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`
   - `GEMINI_API_KEY`
   - `PEXELS_API_KEY` hoặc `PIXABAY_API_KEY`
5. Bấm **Deploy**. Xong sẽ có địa chỉ dạng `https://ten-cua-ban.onrender.com`.

### 4. Cập nhật Supabase

1. **Authentication** → **URL Configuration** → **Site URL**: dán địa chỉ web trên Render. Link trong email xác nhận sẽ dẫn về đây.
2. **Authentication** → **Sign In / Providers** → **Email**: bật lại **Confirm email**.
3. Nếu chỉ muốn mình bạn dùng: sau khi đã có tài khoản, tắt **Allow new users to sign up**. Nếu để mở, ai có link cũng đăng ký được và dùng hạn mức Gemini của bạn.

### Lưu ý khi chạy trên host

- Gói miễn phí của Render có ít RAM và CPU, dựng video 1080p có thể rất chậm hoặc bị dừng giữa chừng. Nếu gặp, cần gói trả phí hoặc VPS có từ 2 GB RAM.
- Gói miễn phí tự ngủ sau 15 phút không ai truy cập; lần mở đầu tiên sau đó sẽ chậm.
- Chỉ chạy 1 bản (1 instance). Trạng thái job nằm trong bộ nhớ, chạy nhiều bản sẽ làm web không tìm thấy job.

## Những thứ chưa có trong bản này

Đúng theo phạm vi bản gọn: chưa có bước duyệt/sửa kịch bản trước khi dựng, nhạc nền, chạy hàng loạt, đăng bài tự động.
