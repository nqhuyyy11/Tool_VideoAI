"""Bước 3: tìm và tải video nền miễn phí bản quyền.

Dùng Pexels nếu có PEXELS_API_KEY, nếu không thì dùng Pixabay (PIXABAY_API_KEY).
Video khác khổ cũng được: render.py tự crop về khổ đã chọn.
"""
import time

import requests

import config

PEXELS_API = "https://api.pexels.com/videos/search"
PIXABAY_API = "https://pixabay.com/api/videos/"

# Clip dạng green screen / chữ "COMMENT", "SUBSCRIBE"... không dùng làm video nền được
_OVERLAY_WORDS = ("green screen", "greenscreen", "chroma key", "overlay",
                  "subscribe", "comment", "like button", "lower third")


def _is_overlay(text: str) -> bool:
    text = (text or "").lower().replace("-", " ")
    return any(w in text for w in _OVERLAY_WORDS)


# ---------- Pexels ----------
def _pexels_pick(video: dict) -> str | None:
    fits = {
        "portrait": lambda f: f["height"] >= f["width"],
        "landscape": lambda f: f["width"] >= f["height"],
        "square": lambda f: True,
    }[config.ORIENTATION]
    files = [
        f for f in video.get("video_files", [])
        if f.get("width") and f.get("height") and fits(f)
    ]
    if not files:
        return None
    files.sort(key=lambda f: abs(max(f["width"], f["height"]) - max(config.WIDTH, config.HEIGHT)))
    return files[0]["link"]


def _pexels_search(query: str) -> list[tuple[str, str]]:
    r = requests.get(
        PEXELS_API,
        headers={"Authorization": config.PEXELS_API_KEY},
        params={"query": query, "orientation": config.ORIENTATION, "per_page": 10},
        timeout=30,
    )
    r.raise_for_status()
    out = []
    for v in r.json().get("videos", []):
        if _is_overlay(v.get("url", "")):  # url của Pexels chứa tên clip
            continue
        link = _pexels_pick(v)
        if link:
            out.append((f"pexels-{v['id']}", link))
    return out


# ---------- Pixabay ----------
def _pixabay_pick(hit: dict) -> str | None:
    vids = hit.get("videos", {})
    # ưu tiên bản 1080p (large), rồi 720p (medium)
    for size in ("large", "medium", "small"):
        v = vids.get(size) or {}
        if v.get("url"):
            return v["url"]
    return None


def _pixabay_search(query: str) -> list[tuple[str, str]]:
    r = requests.get(
        PIXABAY_API,
        params={
            "key": config.PIXABAY_API_KEY,
            "q": query[:100],
            "video_type": "film",
            "safesearch": "true",
            "per_page": 10,
        },
        timeout=30,
    )
    r.raise_for_status()
    out = []
    for hit in r.json().get("hits", []):
        if _is_overlay(hit.get("tags", "")):
            continue
        link = _pixabay_pick(hit)
        if link:
            out.append((f"pixabay-{hit['id']}", link))
    return out


# ---------- Chung ----------
def _search(query: str) -> list[tuple[str, str]]:
    if config.PEXELS_API_KEY:
        return _pexels_search(query)
    return _pixabay_search(query)


def fetch_clip(keywords: str, dest, used_ids: set) -> bool:
    """Tải 1 video khớp keywords vào dest. Trả về False nếu không tìm được."""
    if not (config.PEXELS_API_KEY or config.PIXABAY_API_KEY):
        return False
    source = "Pexels" if config.PEXELS_API_KEY else "Pixabay"
    queries = [keywords, keywords.split()[0], "abstract background"]
    for q in queries:
        results = None
        for attempt in range(4):  # bị giới hạn tốc độ (429) thì chờ rồi thử lại
            try:
                results = _search(q)
                break
            except requests.RequestException as e:
                status = getattr(e.response, "status_code", None)
                if status == 429 and attempt < 3:
                    wait = 15 * (attempt + 1)
                    print(f"   ! {source} giới hạn tốc độ, chờ {wait}s rồi thử lại...")
                    time.sleep(wait)
                    continue
                print(f"   ! Lỗi {source}: {status or type(e).__name__}")
                return False
        for vid, link in results:
            if vid in used_ids:
                continue
            with requests.get(link, stream=True, timeout=120) as resp:
                resp.raise_for_status()
                with open(dest, "wb") as f:
                    for part in resp.iter_content(1 << 20):
                        f.write(part)
            used_ids.add(vid)
            return True
    return False
