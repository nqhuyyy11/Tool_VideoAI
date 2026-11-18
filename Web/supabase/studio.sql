-- AutoVideo Studio: bảng "studio_projects" + cho bucket "videos" nhận thêm file nhạc (mp3).
-- Cách dùng: Supabase Dashboard -> SQL Editor -> New query -> dán toàn bộ file này -> Run.
-- Chạy lại nhiều lần cũng không sao. Cần chạy file schema.sql trước.

create table if not exists public.studio_projects (
  id         uuid primary key default gen_random_uuid(),
  user_id    uuid not null references auth.users (id) on delete cascade,
  name       text not null default 'Dự án mới',
  data       jsonb not null default '{}'::jsonb,   -- khổ video, giọng đọc, danh sách cảnh...
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists studio_projects_user_idx
  on public.studio_projects (user_id, updated_at desc);

alter table public.studio_projects enable row level security;

drop policy if exists "Xem du an cua minh" on public.studio_projects;
create policy "Xem du an cua minh"
  on public.studio_projects for select
  to authenticated
  using ((select auth.uid()) = user_id);
-- Không có policy ghi: backend ghi bằng service_role key.

-- Bucket nhận thêm mp3 (nhạc nền). Ảnh/clip Studio đều được đổi về jpg/mp4 trước khi lưu.
update storage.buckets
   set allowed_mime_types = array['video/mp4', 'image/jpeg', 'audio/mpeg']
 where id = 'videos';
