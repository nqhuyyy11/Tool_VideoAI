"""Kiểm tra người dùng đã đăng nhập hay chưa.

Trình duyệt gửi kèm mỗi yêu cầu một token (do Supabase Auth cấp khi đăng nhập).
Backend hỏi lại Supabase xem token đó có thật không và thuộc về ai.
"""
import time

import requests
from fastapi import Header, HTTPException

from . import settings

_CACHE_SECONDS = 60
_cache: dict[str, tuple[float, dict]] = {}  # token -> (hết hạn lúc, user)


def current_user(authorization: str | None = Header(default=None)) -> dict:
    """Trả về {"id": ..., "email": ...} của người đang đăng nhập, không thì báo lỗi 401."""
    missing = settings.missing()
    if missing:
        raise HTTPException(500, f"Thiếu cấu hình trong file .env: {', '.join(missing)}")

    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Bạn chưa đăng nhập.")
    token = authorization[7:].strip()

    now = time.time()
    cached = _cache.get(token)
    if cached and cached[0] > now:
        return cached[1]

    try:
        r = requests.get(
            f"{settings.SUPABASE_URL}/auth/v1/user",
            headers={"apikey": settings.SUPABASE_ANON_KEY,
                     "Authorization": f"Bearer {token}"},
            timeout=15,
        )
    except requests.RequestException:
        raise HTTPException(503, "Không kết nối được tới Supabase để kiểm tra đăng nhập.")
    if r.status_code != 200:
        raise HTTPException(401, "Phiên đăng nhập đã hết hạn, hãy đăng nhập lại.")

    data = r.json()
    user = {"id": data["id"], "email": data.get("email", "")}

    if len(_cache) > 500:  # dọn các token cũ
        for key in [k for k, v in _cache.items() if v[0] <= now]:
            del _cache[key]
    _cache[token] = (now + _CACHE_SECONDS, user)
    return user
