"""Nén video, tạo ảnh thumbnail và lưu lên Supabase (Storage + bảng "videos").

Mọi thao tác ở đây dùng service_role key nên chỉ được chạy ở backend.
File trong bucket được đặt theo dạng:  <user_id>/<video_id>.mp4
"""
import re
import subprocess
import unicodedata
import uuid
from pathlib import Path
from urllib.parse import quote

import requests

from . import settings
from .errors import UserError

TABLE = "videos"


# ---------- FFmpeg ----------
def _ffmpeg(cmd: list):
    p = subprocess.run(cmd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if p.returncode != 0:
        raise RuntimeError("FFmpeg lỗi:\n" + p.stderr[-1500:])


def compress(source: Path, out: Path, landscape: bool):
    """Nén về 720p, H.264 + AAC để file nhẹ, phát được ngay trên web."""
    scale = "scale=-2:720" if landscape else "scale=720:-2"
    _ffmpeg(["ffmpeg", "-y", "-i", str(source), "-vf", scale,
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "26",
             "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
             "-movflags", "+faststart", str(out)])


def make_thumbnail(video: Path, out: Path):
    """Lấy 1 khung hình ở giây thứ 1 làm ảnh đại diện."""
    _ffmpeg(["ffmpeg", "-y", "-ss", "1", "-i", str(video), "-frames:v", "1",
             "-vf", "scale=360:-2", "-q:v", "4", str(out)])


# ---------- Gọi Supabase ----------
def _headers(extra: dict | None = None) -> dict:
    key = settings.SUPABASE_SERVICE_ROLE_KEY
    headers = {"apikey": key, "Authorization": f"Bearer {key}"}
    headers.update(extra or {})
    return headers


def _check(r: requests.Response, action: str):
    """Báo lỗi dễ hiểu nếu Supabase từ chối."""
    if r.status_code < 400:
        return
    text = r.text[:300]
    hint = ""
    if "Bucket not found" in text:
        hint = f" Chưa có bucket \"{settings.SUPABASE_BUCKET}\": xem lại bước tạo bucket trong README."
    elif "PGRST205" in text or "Could not find the table" in text:
        hint = " Chưa có bảng \"videos\": hãy chạy file supabase/schema.sql trong SQL Editor."
    elif r.status_code in (401, 403):
        hint = " Kiểm tra lại SUPABASE_SERVICE_ROLE_KEY trong file .env."
    elif r.status_code == 413:
        hint = " File vượt giới hạn dung lượng của bucket."
    raise UserError(f"Supabase báo lỗi khi {action} (mã {r.status_code}).{hint} Chi tiết: {text}")


def _storage_url(path: str = "") -> str:
    base = f"{settings.SUPABASE_URL}/storage/v1/object"
    return f"{base}/{path}" if path else base


def _upload(path: str, file: Path, content_type: str):
    with open(file, "rb") as f:
        r = requests.post(
            _storage_url(f"{settings.SUPABASE_BUCKET}/{path}"),
            headers=_headers({"Content-Type": content_type, "x-upsert": "true",
                              "Cache-Control": "max-age=3600"}),
            data=f, timeout=600,
        )
    _check(r, "upload file")


def _remove(paths: list[str]):
    paths = [p for p in paths if p]
    if not paths:
        return
    r = requests.delete(_storage_url(settings.SUPABASE_BUCKET), headers=_headers(),
                        json={"prefixes": paths}, timeout=60)
    _check(r, "xoá file")


def _sign(paths: list[str]) -> dict[str, str]:
    """Tạo link tạm (có hạn) cho các file trong bucket riêng tư."""
    paths = [p for p in paths if p]
    if not paths:
        return {}
    r = requests.post(
        _storage_url(f"sign/{settings.SUPABASE_BUCKET}"), headers=_headers(),
        json={"expiresIn": settings.SIGNED_URL_TTL, "paths": paths}, timeout=30,
    )
    _check(r, "tạo link xem video")
    links = {}
    for item in r.json():
        if item.get("signedURL"):
            links[item["path"]] = f"{settings.SUPABASE_URL}/storage/v1{item['signedURL']}"
    return links


def _table_url() -> str:
    return f"{settings.SUPABASE_URL}/rest/v1/{TABLE}"


# ---------- Dữ liệu trả về cho web ----------
def _file_name(title: str) -> str:
    text = title.replace("đ", "d").replace("Đ", "D")
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return (text[:60] or "video") + ".mp4"


def _with_links(rows: list[dict]) -> list[dict]:
    """Đổi đường dẫn trong bucket thành link xem được trên trình duyệt."""
    paths = [r["file_url"] for r in rows] + [r.get("thumbnail_url") for r in rows]
    links = _sign(paths)
    out = []
    for r in rows:
        video_url = links.get(r["file_url"])
        out.append({
            "id": r["id"],
            "title": r["title"],
            "prompt": r["prompt"],
            "caption": r.get("caption") or "",
            "created_at": r["created_at"],
            "video_url": video_url,
            "thumbnail_url": links.get(r.get("thumbnail_url")),
            # thêm ?download=... thì Supabase trả file dạng tải về thay vì phát
            "download_url": (f"{video_url}&download={quote(_file_name(r['title']))}"
                             if video_url else None),
        })
    return out


# ---------- Hàm dùng bởi các phần khác ----------
def save_video(user_id: str, title: str, prompt: str, caption: str,
               source: Path, work: Path, landscape: bool) -> dict:
    """Nén -> kiểm tra dung lượng -> upload -> ghi bảng. Trả về thông tin video."""
    small = work / "upload.mp4"
    compress(source, small, landscape)

    size_mb = small.stat().st_size / (1024 * 1024)
    if size_mb > settings.MAX_UPLOAD_MB:
        raise UserError(
            f"Video sau khi nén vẫn nặng {size_mb:.0f} MB, vượt giới hạn "
            f"{settings.MAX_UPLOAD_MB:.0f} MB mỗi file của Supabase. "
            "Hãy thử chủ đề ngắn hơn để video ngắn lại.")

    video_id = str(uuid.uuid4())
    video_path = f"{user_id}/{video_id}.mp4"
    thumb_path = None

    _upload(video_path, small, "video/mp4")
    try:
        thumb = work / "thumb.jpg"
        make_thumbnail(small, thumb)
        thumb_path = f"{user_id}/{video_id}.jpg"
        _upload(thumb_path, thumb, "image/jpeg")
    except Exception as e:  # thiếu thumbnail không đáng để hỏng cả video
        print(f"   ! Không tạo được thumbnail: {e}")
        thumb_path = None

    try:
        r = requests.post(
            _table_url(), headers=_headers({"Prefer": "return=representation"}),
            json={"id": video_id, "user_id": user_id, "title": title, "prompt": prompt,
                  "caption": caption, "file_url": video_path, "thumbnail_url": thumb_path},
            timeout=30,
        )
        _check(r, "ghi vào bảng videos")
    except Exception:
        _remove([video_path, thumb_path])  # không để file mồ côi trong bucket
        raise
    return _with_links(r.json())[0]


def list_videos(user_id: str) -> list[dict]:
    r = requests.get(
        _table_url(), headers=_headers(),
        params={"select": "*", "user_id": f"eq.{user_id}", "order": "created_at.desc"},
        timeout=30,
    )
    _check(r, "đọc danh sách video")
    return _with_links(r.json())


def delete_video(user_id: str, video_id: str) -> bool:
    """Xoá file trong bucket và dòng trong bảng. Trả về False nếu không tìm thấy."""
    match = {"id": f"eq.{video_id}", "user_id": f"eq.{user_id}"}
    r = requests.get(_table_url(), headers=_headers(),
                     params={"select": "file_url,thumbnail_url", **match}, timeout=30)
    _check(r, "tìm video")
    rows = r.json()
    if not rows:
        return False
    _remove([rows[0]["file_url"], rows[0].get("thumbnail_url")])
    r = requests.delete(_table_url(), headers=_headers(), params=match, timeout=30)
    _check(r, "xoá video")
    return True
