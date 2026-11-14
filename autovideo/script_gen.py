"""Bước 1: AI viết kịch bản video ngắn."""
import json
import re

import config

PROMPT = """Bạn là biên kịch video ngắn (TikTok/Reels/Shorts) cho kênh sau:
{style}

Viết kịch bản video khoảng 45-60 giây về chủ đề: "{topic}"

Yêu cầu:
- 6 đến 9 cảnh, tổng 120-160 từ tiếng Việt.
- Cảnh 1 là câu mở đầu gây tò mò mạnh (hook) để người xem không lướt qua.
- Cảnh cuối kêu gọi theo dõi kênh / bình luận, ngắn gọn, tự nhiên.
- Câu thoại viết để ĐỌC thành tiếng: câu ngắn, không emoji, không ký hiệu lạ.
- Mỗi cảnh có "keywords": 2-3 từ TIẾNG ANH mô tả hình ảnh cụ thể để tìm video
  stock (vd "ocean waves", "city night traffic"), tránh từ trừu tượng.
- Thông tin phải chính xác, không bịa số liệu.

Chỉ trả về JSON đúng định dạng:
{{
  "title": "tiêu đề video, dưới 80 ký tự",
  "scenes": [{{"text": "câu thoại", "keywords": "english keywords"}}],
  "caption": "mô tả đăng kèm video, 1-2 câu",
  "hashtags": ["#tag1", "#tag2", "#tag3", "#tag4", "#tag5"]
}}"""


def _parse_json(raw: str) -> dict:
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)
    return json.loads(raw)


def validate(script: dict) -> dict:
    scenes = [s for s in script.get("scenes", []) if str(s.get("text", "")).strip()]
    if not scenes:
        raise ValueError("Kịch bản không có cảnh nào.")
    for s in scenes:
        s["text"] = s["text"].strip()
        s["keywords"] = str(s.get("keywords") or "nature landscape").strip()
    script["scenes"] = scenes
    script.setdefault("title", scenes[0]["text"][:80])
    script.setdefault("caption", "")
    script.setdefault("hashtags", [])
    return script


def generate_script(topic: str) -> dict:
    if not config.GEMINI_API_KEY:
        raise RuntimeError(
            "Chưa có GEMINI_API_KEY trong file .env. "
            "Lấy key miễn phí tại https://aistudio.google.com/apikey "
            "hoặc dùng --script để tự đưa kịch bản."
        )
    from google import genai
    from google.genai import errors

    client = genai.Client(api_key=config.GEMINI_API_KEY, http_options={"api_version": "v1beta"})
    models = [config.GEMINI_MODEL] + [m for m in config.GEMINI_FALLBACK_MODELS if m != config.GEMINI_MODEL]
    for i, model in enumerate(models):
        try:
            resp = client.models.generate_content(
                model=model,
                contents=PROMPT.format(style=config.CHANNEL_STYLE, topic=topic),
                config={"response_mime_type": "application/json", "temperature": 0.9},
            )
            break
        except errors.APIError as e:
            # chỉ chuyển model khi quá tải (5xx) hoặc hết hạn mức (429)
            if (e.code != 429 and e.code < 500) or i == len(models) - 1:
                raise
            print(f"      Model {model} lỗi {e.code}, chuyển sang {models[i + 1]}...")
    return validate(_parse_json(resp.text))
