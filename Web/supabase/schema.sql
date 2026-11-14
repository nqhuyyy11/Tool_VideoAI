-- AutoVideo Web: bảng "videos", bucket "videos" và các policy bảo mật.
-- Cách dùng: Supabase Dashboard -> SQL Editor -> New query -> dán toàn bộ file này -> Run.
-- Chạy lại nhiều lần cũng không sao.

-- 1) Bảng lưu thông tin video ------------------------------------------------
create table if not exists public.videos (
  id            uuid primary key default gen_random_uuid(),
  user_id       uuid not null references auth.users (id) on delete cascade,
  title         text not null,
  prompt        text not null,              -- chủ đề người dùng đã nhập
  caption       text not null default '',   -- tiêu đề + mô tả + hashtag để đăng bài
  file_url      text not null,              -- đường dẫn file trong bucket: <user_id>/<video_id>.mp4
  thumbnail_url text,                       -- đường dẫn ảnh đại diện trong bucket
  created_at    timestamptz not null default now()
);

create index if not exists videos_user_created_idx
  on public.videos (user_id, created_at desc);

-- 2) Row Level Security cho bảng ---------------------------------------------
-- Bật RLS: mặc định không ai đọc/ghi được, chỉ những gì policy cho phép mới được.
alter table public.videos enable row level security;

-- Người đã đăng nhập chỉ xem được dòng của chính mình.
drop policy if exists "Xem video cua minh" on public.videos;
create policy "Xem video cua minh"
  on public.videos for select
  to authenticated
  using ((select auth.uid()) = user_id);

-- Không có policy insert/update/delete: trình duyệt không tự ghi được vào bảng.
-- Việc ghi và xoá do backend làm bằng service_role key (key này bỏ qua RLS).

-- 3) Bucket chứa file video --------------------------------------------------
-- Bucket riêng tư (public = false), mỗi file tối đa 50 MB, chỉ nhận mp4 và jpg.
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('videos', 'videos', false, 52428800, array['video/mp4', 'image/jpeg'])
on conflict (id) do update
  set public = excluded.public,
      file_size_limit = excluded.file_size_limit,
      allowed_mime_types = excluded.allowed_mime_types;

-- 4) Policy cho bucket -------------------------------------------------------
-- File nằm trong thư mục mang tên user_id. Người đã đăng nhập chỉ đọc được
-- file trong thư mục của chính mình.
drop policy if exists "Doc file video cua minh" on storage.objects;
create policy "Doc file video cua minh"
  on storage.objects for select
  to authenticated
  using (
    bucket_id = 'videos'
    and (storage.foldername(name))[1] = (select auth.uid())::text
  );
