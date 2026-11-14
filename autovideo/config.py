"""Cấu hình chung. Sửa trong file .env, không cần sửa file này."""
import os
from pathlib import Path

from dotenv import load_dotenv

_BASE = Path(__file__).parent
# Ưu tiên file .env; nếu chưa có thì đọc .env.example
load_dotenv(_BASE / ".env") or load_dotenv(_BASE / ".env.example")

# --- API keys ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
# Model dự phòng khi model chính quá tải (503) hoặc hết hạn mức (429), cách nhau bằng dấu phẩy
GEMINI_FALLBACK_MODELS = [
    m.strip()
    for m in os.getenv("GEMINI_FALLBACK_MODELS", "gemini-2.5-flash-lite,gemini-2.0-flash").split(",")
    if m.strip()
]
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")
PIXABAY_API_KEY = os.getenv("PIXABAY_API_KEY", "")  # dùng khi không có key Pexels

# --- Giọng đọc (edge-tts, miễn phí) ---
# Giọng nữ: vi-VN-HoaiMyNeural | Giọng nam: vi-VN-NamMinhNeural
TTS_VOICE = os.getenv("TTS_VOICE", "vi-VN-HoaiMyNeural")
TTS_RATE = os.getenv("TTS_RATE", "+10%")  # tốc độ đọc, vd "+0%", "+15%"

# --- Phong cách kênh: AI sẽ viết kịch bản theo mô tả này ---
CHANNEL_STYLE = os.getenv(
    "CHANNEL_STYLE",
    "Kênh 'Sự thật thú vị' cho người Việt 18-30 tuổi, giọng kể gần gũi, "
    "hấp dẫn, có chút hài hước, thông tin chính xác.",
)

# --- Video ---
FPS = 30
# Khổ video: tên -> (rộng, cao, hướng tìm video nền, lề dưới của phụ đề)
FORMATS = {
    "vertical": (1080, 1920, "portrait", 560),    # 9:16  TikTok / Reels / Shorts
    "horizontal": (1920, 1080, "landscape", 130),  # 16:9  YouTube
    "square": (1080, 1080, "square", 200),         # 1:1   Facebook / Instagram feed
}
WIDTH = HEIGHT = ORIENTATION = SUB_MARGIN_V = None


def set_format(name: str):
    """Chọn khổ video; gọi trước khi tải video nền / render."""
    global WIDTH, HEIGHT, ORIENTATION, SUB_MARGIN_V
    if name not in FORMATS:
        raise ValueError(f"Khổ video '{name}' không hợp lệ, chọn: {', '.join(FORMATS)}")
    WIDTH, HEIGHT, ORIENTATION, SUB_MARGIN_V = FORMATS[name]


set_format(os.getenv("VIDEO_FORMAT", "vertical"))  # mặc định giữ nguyên như cũ
WORDS_PER_CAPTION = int(os.getenv("WORDS_PER_CAPTION", "4"))
MUSIC_VOLUME = float(os.getenv("MUSIC_VOLUME", "0.12"))  # 0.0 - 1.0

BASE_DIR = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / os.getenv("OUTPUT_DIR", "output")
MUSIC_DIR = BASE_DIR / "music"  # bỏ file .mp3 nhạc nền vào đây (tùy chọn)
