"""Cấu hình của bản web. Giá trị lấy từ file Web/.env, không sửa trực tiếp ở đây."""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

WEB_DIR = Path(__file__).resolve().parent.parent
load_dotenv(WEB_DIR / ".env")

# Tool gốc in tiếng Việt ra màn hình. Nếu cửa sổ lệnh không hiển thị được ký tự
# nào đó thì thay bằng dấu "?" chứ không để cả job bị lỗi.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(errors="replace")
    except Exception:
        pass

# --- Thư mục ---
FRONTEND_DIR = WEB_DIR / "frontend"
WORK_DIR = WEB_DIR / "work"  # file tạm của từng job, tự xoá khi xong

AUTOVIDEO_DIR = Path(os.getenv("AUTOVIDEO_DIR", "../autovideo"))
if not AUTOVIDEO_DIR.is_absolute():
    AUTOVIDEO_DIR = (WEB_DIR / AUTOVIDEO_DIR).resolve()

# --- Supabase ---
SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "").strip()
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
SUPABASE_BUCKET = os.getenv("SUPABASE_BUCKET", "videos").strip()

# Gói Free của Supabase: mỗi file tối đa 50 MB
MAX_UPLOAD_MB = float(os.getenv("MAX_UPLOAD_MB", "50"))
# Link xem video chỉ có hiệu lực trong thời gian này (giây)
SIGNED_URL_TTL = 3600


def missing() -> list[str]:
    """Tên các biến Supabase còn thiếu trong .env."""
    required = {
        "SUPABASE_URL": SUPABASE_URL,
        "SUPABASE_ANON_KEY": SUPABASE_ANON_KEY,
        "SUPABASE_SERVICE_ROLE_KEY": SUPABASE_SERVICE_ROLE_KEY,
    }
    return [name for name, value in required.items() if not value]
