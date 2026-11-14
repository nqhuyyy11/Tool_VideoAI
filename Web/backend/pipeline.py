"""Chạy 5 bước tạo video bằng các module của tool gốc (thư mục autovideo).

Khác với main.py của tool gốc ở 2 điểm:
- Báo tiến độ ra ngoài sau mỗi bước để web hiển thị.
- Giữ lại kết quả từng cảnh (giọng đọc, clip). Nếu job lỗi giữa chừng rồi bấm
  "Thử lại" thì chỉ làm tiếp phần còn thiếu.
"""
import json
import shutil
import sys

from . import settings, storage
from .errors import UserError

if not (settings.AUTOVIDEO_DIR / "render.py").exists():
    raise RuntimeError(
        f"Không tìm thấy tool gốc tại {settings.AUTOVIDEO_DIR}. "
        "Hãy sửa AUTOVIDEO_DIR trong file .env cho đúng thư mục chứa render.py.")
sys.path.insert(0, str(settings.AUTOVIDEO_DIR))

import config  # noqa: E402  (các module dưới đây thuộc tool gốc)
import footage  # noqa: E402
import main as autovideo_main  # noqa: E402
import render  # noqa: E402
import script_gen  # noqa: E402
import tts  # noqa: E402


def _read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def run(job, report) -> dict:
    """Tạo video cho `job`. `report(status, percent, message)` dùng để báo tiến độ.

    Trả về thông tin video đã lưu trên Supabase.
    """
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise UserError("Máy chủ chưa cài FFmpeg. Windows: chạy 'winget install ffmpeg' "
                        "rồi mở lại cửa sổ lệnh và khởi động lại server.")

    work = settings.WORK_DIR / job.id
    work.mkdir(parents=True, exist_ok=True)

    # Tool gốc đọc các lựa chọn này từ biến toàn cục, nên mỗi lúc chỉ chạy 1 job.
    config.set_format(job.video_format)
    config.TTS_VOICE = job.voice
    config.TTS_RATE = job.rate

    # ----- Bước 1: kịch bản -----
    report("scripting", 2, "AI đang viết kịch bản…")
    script_file = work / "script.json"
    if script_file.exists():
        script = _read_json(script_file)
    else:
        script = script_gen.generate_script(job.topic)
        _write_json(script_file, script)
    scenes = script["scenes"]
    n = len(scenes)

    # ----- Bước 2: giọng đọc -----
    voices = []  # mỗi cảnh: {"words": [...], "duration": giây}
    for i, sc in enumerate(scenes, 1):
        report("voicing", 8 + 32 * (i - 1) // n, f"Đang tạo giọng đọc cảnh {i}/{n}…")
        mp3 = work / f"voice_{i:02d}.mp3"
        info_file = work / f"voice_{i:02d}.json"  # có file này nghĩa là cảnh đã xong
        if mp3.exists() and info_file.exists():
            info = _read_json(info_file)
        else:
            words = tts.synthesize(sc["text"], mp3)
            info = {"words": words or [], "duration": render.probe_duration(mp3)}
            _write_json(info_file, info)
        voices.append(info)

    # ----- Bước 3: video nền -----
    used_file = work / "used_clips.json"
    used = set(_read_json(used_file)) if used_file.exists() else set()
    for i, sc in enumerate(scenes, 1):
        report("fetching_footage", 40 + 35 * (i - 1) // n, f"Đang tải video nền cảnh {i}/{n}…")
        clip = work / f"clip_{i:02d}.mp4"
        if clip.exists():
            continue
        duration = voices[i - 1]["duration"]
        src = work / f"src_{i:02d}.mp4"
        try:
            found = footage.fetch_clip(sc["keywords"], src, used)
        except Exception as e:  # lỗi tải clip thì dùng nền màu, không dừng job
            print(f"   ! Không tải được video nền cảnh {i}: {e}")
            found = False

        part = work / f"clip_{i:02d}.part.mp4"
        try:
            render.make_scene_clip(src if found else None, duration, part)
        except RuntimeError:
            if not found:
                raise
            render.make_scene_clip(None, duration, part)  # clip tải về bị hỏng
        part.replace(clip)
        _write_json(used_file, sorted(used))
        src.unlink(missing_ok=True)

    # ----- Bước 4: ghép video + phụ đề -----
    report("rendering", 75, "Đang ghép video và phụ đề…")
    final = work / "final.mp4"
    if not final.exists():
        captions, t = [], 0.0
        for sc, info in zip(scenes, voices):
            captions += autovideo_main.build_captions(
                info["words"], sc["text"], info["duration"], t)
            t += info["duration"]
        clips = [work / f"clip_{i:02d}.mp4" for i in range(1, n + 1)]
        audios = [work / f"voice_{i:02d}.mp3" for i in range(1, n + 1)]
        render.concat_videos(clips, work / "video.mp4", work)
        render.concat_audios(audios, work / "voice.m4a", work)
        render.write_ass(captions, work / "subs.ass")
        part = work / "final.part.mp4"
        render.final_render(work, work / "video.mp4", work / "voice.m4a",
                            work / "subs.ass", None, part)
        part.replace(final)

    # ----- Bước 5: nén + lưu lên Supabase -----
    report("uploading", 90, "Đang nén và lưu video…")
    title = str(script.get("title") or job.topic)[:200]
    hashtags = " ".join(str(h) for h in script.get("hashtags") or [])
    caption = "\n\n".join(p for p in (title, str(script.get("caption") or ""), hashtags) if p)
    video = storage.save_video(
        user_id=job.user_id, title=title, prompt=job.topic, caption=caption,
        source=final, work=work, landscape=config.WIDTH > config.HEIGHT)

    shutil.rmtree(work, ignore_errors=True)
    return video
