"""Studio: dự án nhiều cảnh (ảnh/clip do AI tạo hoặc tải lên) -> ghép thành 1 video.

Gồm 4 phần:
- Dự án: lưu trong bảng "studio_projects" (cột data là JSON gồm các cảnh).
- Tệp (ảnh/clip/nhạc): chuẩn hoá bằng FFmpeg rồi lưu trong bucket, thư mục <user_id>/studio/.
- Tạo bằng AI: ảnh (Gemini/Imagen) và clip (Veo), chạy nền vì Veo mất 1-3 phút.
- Ghép video: đọc thuyết minh từng cảnh, zoom/pan cho ảnh, chuyển cảnh, phụ đề, nhạc nền.
"""
import copy
import json
import shutil
import subprocess
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import requests

from . import settings, storage
from .errors import UserError, friendly

TABLE = "studio_projects"
MAX_SCENES = 60
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff", ".heic"}
VIDEO_EXT = {".mp4", ".mov", ".webm", ".mkv", ".m4v", ".avi"}
AUDIO_EXT = {".mp3", ".m4a", ".wav", ".aac", ".ogg", ".flac"}
CONTENT_TYPE = {"image": "image/jpeg", "video": "video/mp4", "audio": "audio/mpeg"}
EXT = {"image": "jpg", "video": "mp4", "audio": "mp3"}


def _ffmpeg(cmd: list, cwd=None):
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if p.returncode != 0:
        raise RuntimeError("FFmpeg lỗi:\n" + p.stderr[-1500:])


def _need_ffmpeg():
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise UserError("Máy chủ chưa cài FFmpeg nên chưa xử lý được ảnh/video.")


# =============================================================================
# Dự án
# =============================================================================
def default_data() -> dict:
    return {"format": "vertical", "voice": "vi-VN-HoaiMyNeural", "rate": "+10%",
            "transition": "fade", "music": None, "music_name": "", "scenes": []}


def _asset_prefix(user_id: str) -> str:
    return f"{user_id}/studio/"


def _own_asset(user_id: str, path: str | None) -> str | None:
    """Chỉ nhận đường dẫn nằm trong thư mục Studio của chính người dùng."""
    if not path:
        return None
    if not path.startswith(_asset_prefix(user_id)) or ".." in path:
        raise UserError("Đường dẫn tệp không hợp lệ.")
    return path


def _asset_paths(data: dict) -> list[str]:
    scenes = data.get("scenes", [])
    paths = [s.get("asset") for s in scenes] + [s.get("voice") for s in scenes] + [data.get("music")]
    return [p for p in paths if p]


def _url() -> str:
    return storage.table_url(TABLE)


def _project_filter(user_id: str, pid: str) -> dict:
    return {"id": f"eq.{pid}", "user_id": f"eq.{user_id}"}


def list_projects(user_id: str) -> list[dict]:
    r = requests.get(_url(), headers=storage.headers(), timeout=30,
                     params={"select": "id,name,updated_at", "user_id": f"eq.{user_id}",
                             "order": "updated_at.desc"})
    storage.check(r, "đọc danh sách dự án")
    return r.json()


def create_project(user_id: str, name: str) -> dict:
    r = requests.post(_url(), headers=storage.headers({"Prefer": "return=representation"}),
                      json={"user_id": user_id, "name": name, "data": default_data()}, timeout=30)
    storage.check(r, "tạo dự án")
    return _with_urls(r.json()[0])


def _fetch_row(user_id: str, pid: str) -> dict | None:
    r = requests.get(_url(), headers=storage.headers(), timeout=30,
                     params={"select": "*", **_project_filter(user_id, pid)})
    storage.check(r, "đọc dự án")
    rows = r.json()
    return rows[0] if rows else None


def _with_urls(row: dict) -> dict:
    """Thêm link xem tạm cho từng ảnh/clip/nhạc để trình duyệt hiển thị."""
    data = {**default_data(), **(row.get("data") or {})}
    links = storage.sign_paths(_asset_paths(data))
    for s in data["scenes"]:
        s["url"] = links.get(s.get("asset")) if s.get("asset") else None
        s["voice_url"] = links.get(s.get("voice")) if s.get("voice") else None
    data["music_url"] = links.get(data.get("music")) if data.get("music") else None
    return {"id": row["id"], "name": row["name"], "updated_at": row.get("updated_at"), "data": data}


def get_project(user_id: str, pid: str) -> dict | None:
    row = _fetch_row(user_id, pid)
    return _with_urls(row) if row else None


def save_project(user_id: str, pid: str, payload: dict) -> dict | None:
    row = _fetch_row(user_id, pid)
    if not row:
        return None
    name = payload.pop("name")
    scenes = []
    for s in payload["scenes"]:
        s = dict(s)
        s["asset"] = _own_asset(user_id, s.get("asset"))
        s["voice"] = _own_asset(user_id, s.get("voice"))
        if not s["asset"]:
            s["kind"] = None
        scenes.append(s)
    data = {**payload, "scenes": scenes, "music": _own_asset(user_id, payload.get("music"))}

    old = set(_asset_paths(row.get("data") or {}))
    r = requests.patch(_url(), headers=storage.headers({"Prefer": "return=representation"}),
                       params=_project_filter(user_id, pid), timeout=30,
                       json={"name": name, "data": data,
                             "updated_at": datetime.now(timezone.utc).isoformat()})
    storage.check(r, "lưu dự án")
    gone = old - set(_asset_paths(data))      # cảnh đã xoá thì xoá luôn tệp của nó
    if gone:
        try:
            storage.remove_paths(sorted(gone))
        except Exception as e:
            print(f"   ! Không xoá được tệp cũ: {e}")
    return _with_urls(r.json()[0])


def delete_project(user_id: str, pid: str) -> bool:
    row = _fetch_row(user_id, pid)
    if not row:
        return False
    r = requests.delete(_url(), headers=storage.headers(), params=_project_filter(user_id, pid), timeout=30)
    storage.check(r, "xoá dự án")
    try:
        storage.remove_paths(_asset_paths(row.get("data") or {}))
    except Exception as e:
        print(f"   ! Không xoá được tệp của dự án: {e}")
    return True


# =============================================================================
# Tệp tải lên / tạo ra
# =============================================================================
def _normalize(kind: str, src: Path, dest: Path):
    """Đưa mọi tệp về 1 định dạng chắc chắn phát được: jpg / mp4 (không tiếng) / mp3."""
    if kind == "image":
        _ffmpeg(["ffmpeg", "-y", "-i", str(src), "-frames:v", "1",
                 "-vf", "scale='min(2160,iw)':-2", "-q:v", "3", str(dest)])
    elif kind == "video":
        _ffmpeg(["ffmpeg", "-y", "-i", str(src), "-t", "60", "-an",
                 "-vf", "scale='min(1920,iw)':-2,fps=30,format=yuv420p",
                 "-c:v", "libx264", "-preset", "veryfast", "-crf", "24",
                 "-movflags", "+faststart", str(dest)])
    else:
        _ffmpeg(["ffmpeg", "-y", "-i", str(src), "-vn", "-c:a", "libmp3lame",
                 "-b:a", "160k", str(dest)])


def _store(user_id: str, kind: str, src: Path, tmp: Path) -> dict:
    out = tmp / f"out.{EXT[kind]}"
    _normalize(kind, src, out)
    if out.stat().st_size > settings.MAX_UPLOAD_MB * 1024 * 1024:
        raise UserError(f"Tệp sau khi xử lý vẫn nặng hơn {settings.MAX_UPLOAD_MB:.0f} MB. "
                        "Hãy dùng tệp ngắn/nhẹ hơn.")
    path = f"{_asset_prefix(user_id)}{uuid.uuid4()}.{EXT[kind]}"
    storage.put_file(path, out, CONTENT_TYPE[kind])
    return {"path": path, "kind": kind, "url": storage.sign_paths([path]).get(path)}


def ingest_upload(user_id: str, raw: bytes, filename: str) -> dict:
    _need_ffmpeg()
    suffix = Path(filename).suffix.lower()
    kind = ("image" if suffix in IMAGE_EXT else "video" if suffix in VIDEO_EXT
            else "audio" if suffix in AUDIO_EXT else None)
    if not kind:
        raise UserError("Chỉ nhận ảnh (jpg, png, webp...), clip (mp4, mov, webm...) và nhạc (mp3, m4a, wav...).")
    tmp = settings.WORK_DIR / ("up_" + uuid.uuid4().hex)
    tmp.mkdir(parents=True, exist_ok=True)
    try:
        src = tmp / f"in{suffix}"
        src.write_bytes(raw)
        try:
            return _store(user_id, kind, src, tmp)
        except RuntimeError:
            raise UserError("Không đọc được tệp này, có thể tệp bị hỏng hoặc không đúng định dạng.")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# =============================================================================
# Tạo ảnh / clip bằng AI (chạy nền)
# =============================================================================
_gens: dict[str, dict] = {}
_gen_lock = threading.Lock()
_gen_slots = threading.Semaphore(2)     # tối đa 2 yêu cầu gọi Gemini cùng lúc
MAX_GEN_PER_USER = 4
ASPECT = {"vertical": "9:16", "horizontal": "16:9", "square": "1:1"}


def start_generation(user_id: str, kind: str, prompt: str, fmt: str,
                     from_asset: str | None = None) -> dict:
    from_asset = _own_asset(user_id, from_asset)
    with _gen_lock:
        now = time.time()
        for gid, g in list(_gens.items()):
            if g["finished"] and now - g["finished"] > 3600:
                del _gens[gid]
        if sum(1 for g in _gens.values() if g["user_id"] == user_id and not g["finished"]) >= MAX_GEN_PER_USER:
            raise UserError("Bạn đang có quá nhiều yêu cầu đang tạo. Hãy chờ vài cái xong đã.")
        g = {"id": uuid.uuid4().hex, "user_id": user_id, "kind": kind, "prompt": prompt,
             "format": fmt, "from_asset": from_asset, "status": "running",
             "error": None, "asset": None, "finished": None}
        _gens[g["id"]] = g
    threading.Thread(target=_gen_worker, args=(g,), daemon=True, name="studio-gen").start()
    return public_generation(g)


def get_generation(gid: str, user_id: str) -> dict | None:
    g = _gens.get(gid)
    return public_generation(g) if g and g["user_id"] == user_id else None


def public_generation(g: dict) -> dict:
    return {"id": g["id"], "kind": g["kind"], "status": g["status"],
            "error": g["error"], "asset": g["asset"]}


def _gen_worker(g: dict):
    with _gen_slots:
        tmp = settings.WORK_DIR / ("gen_" + g["id"])
        tmp.mkdir(parents=True, exist_ok=True)
        try:
            _need_ffmpeg()
            src = tmp / ("raw.mp4" if g["kind"] == "video" else "raw.img")
            if g["kind"] == "video":
                image = None
                if g["from_asset"]:
                    img = tmp / "from.jpg"
                    storage.download(g["from_asset"], img)
                    image = img.read_bytes()
                src.write_bytes(_gen_video(g["prompt"], g["format"], image))
            else:
                src.write_bytes(_gen_image(g["prompt"], g["format"]))
            g["asset"] = _store(g["user_id"], g["kind"], src, tmp)
            g["status"] = "done"
        except Exception as e:
            import traceback
            traceback.print_exc()
            g["status"] = "failed"
            code = getattr(e, "code", None)
            if code in (400, 403, 404) and not isinstance(e, UserError):
                g["error"] = ("Gemini không cho tạo " + ("clip" if g["kind"] == "video" else "ảnh")
                              + ". Kiểm tra key đã bật thanh toán, và tên model trong .env "
                              "(GEMINI_IMAGE_MODEL / GEMINI_VIDEO_MODEL). Chi tiết: " + str(e)[:300])
            else:
                g["error"] = friendly(e)
        finally:
            g["finished"] = time.time()
            shutil.rmtree(tmp, ignore_errors=True)


def _client():
    from . import pipeline  # nạp tool gốc để lấy GEMINI_API_KEY
    key = pipeline.config.GEMINI_API_KEY
    if not key:
        raise UserError("Chưa có GEMINI_API_KEY nên chưa tạo được ảnh/clip bằng AI.")
    from google import genai
    return genai.Client(api_key=key)


def _gen_image(prompt: str, fmt: str) -> bytes:
    import os
    from google.genai import types
    client = _client()
    model = os.getenv("GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image")
    ratio = ASPECT[fmt]
    if model.startswith("imagen"):
        resp = client.models.generate_images(
            model=model, prompt=prompt,
            config=types.GenerateImagesConfig(number_of_images=1, aspect_ratio=ratio))
        if not resp.generated_images:
            raise UserError("AI không trả về ảnh (prompt có thể bị chặn). Hãy thử mô tả khác.")
        return resp.generated_images[0].image.image_bytes

    try:
        cfg = types.GenerateContentConfig(response_modalities=["TEXT", "IMAGE"],
                                          image_config=types.ImageConfig(aspect_ratio=ratio))
    except (AttributeError, TypeError):  # bản SDK cũ: bỏ tỉ lệ, lúc ghép video sẽ tự cắt cho vừa
        cfg = types.GenerateContentConfig(response_modalities=["TEXT", "IMAGE"])
    resp = client.models.generate_content(model=model, contents=prompt, config=cfg)
    for cand in resp.candidates or []:
        for part in (cand.content.parts if cand.content else None) or []:
            if getattr(part, "inline_data", None) and part.inline_data.data:
                return part.inline_data.data
    raise UserError("AI không trả về ảnh (prompt có thể bị chặn). Hãy thử mô tả khác.")


def _gen_video(prompt: str, fmt: str, image: bytes | None) -> bytes:
    import os
    from google.genai import types
    client = _client()
    model = os.getenv("GEMINI_VIDEO_MODEL", "veo-3.0-fast-generate-001")
    ratio = "9:16" if fmt == "vertical" else "16:9"   # Veo không có khổ vuông, lúc ghép sẽ cắt giữa
    kwargs = {"model": model, "prompt": prompt,
              "config": types.GenerateVideosConfig(aspect_ratio=ratio, number_of_videos=1)}
    if image:
        kwargs["image"] = types.Image(image_bytes=image, mime_type="image/jpeg")
    op = client.models.generate_videos(**kwargs)
    deadline = time.time() + 10 * 60
    while not op.done:
        if time.time() > deadline:
            raise UserError("Veo tạo clip quá lâu (hơn 10 phút). Hãy thử lại.")
        time.sleep(8)
        op = client.operations.get(op)
    if getattr(op, "error", None):
        raise UserError(f"Veo báo lỗi: {op.error}")
    videos = getattr(op.response, "generated_videos", None) if op.response else None
    if not videos:
        raise UserError("Veo không trả về clip (prompt có thể bị chặn). Hãy thử mô tả khác.")
    client.files.download(file=videos[0].video)
    return videos[0].video.video_bytes


# =============================================================================
# Ghép thành video hoàn chỉnh
# =============================================================================
def _even(n: float) -> int:
    return int(n) // 2 * 2


def _scene_clip(kind, src, duration: float, idx: int, out: Path, cfg, render):
    """1 cảnh -> 1 clip đúng khổ và đúng độ dài. Ảnh được zoom/pan nhẹ."""
    W, H, FPS = cfg.WIDTH, cfg.HEIGHT, cfg.FPS
    if kind == "image" and src:
        frames = max(2, int(round(duration * FPS)))
        pw, ph = _even(W * 1.4), _even(H * 1.4)
        z = (f"1+0.14*on/{frames}" if idx % 2 == 0 else f"1.14-0.14*on/{frames}")
        vf = (f"scale={pw}:{ph}:force_original_aspect_ratio=increase,crop={pw}:{ph},"
              f"zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={W}x{H}:fps={FPS},"
              f"setsar=1,format=yuv420p")
        render.run(["ffmpeg", "-y", "-i", str(src), "-vf", vf, "-frames:v", str(frames),
                    "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                    "-pix_fmt", "yuv420p", str(out)])
    else:
        render.make_scene_clip(src if kind == "video" else None, duration, out)


TRANSITIONS = ["fade", "slideleft", "fade", "circleopen", "fade", "slideright", "wipeleft", "fade"]


def _join_clips(clips: list[Path], durations: list[float], t: float, mode: str,
                out: Path, work: Path, render):
    if t <= 0 or len(clips) == 1:
        render.concat_videos(clips, out, work)
        return
    cmd = ["ffmpeg", "-y"]
    for c in clips:
        cmd += ["-i", c.name]
    parts = [f"[{i}:v]settb=AVTB,fps=30,setpts=PTS-STARTPTS,format=yuv420p[v{i}]" for i in range(len(clips))]
    last, elapsed = "v0", durations[0]
    for i in range(1, len(clips)):
        name = TRANSITIONS[(i - 1) % len(TRANSITIONS)] if mode == "mixed" else "fade"
        parts.append(f"[{last}][v{i}]xfade=transition={name}:duration={t}:offset={elapsed - t:.3f}[x{i}]")
        last = f"x{i}"
        elapsed += durations[i] - t
    cmd += ["-filter_complex", ";".join(parts), "-map", f"[{last}]", "-c:v", "libx264",
            "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", out.name]
    render.run(cmd, cwd=work)


def _mix_voices(entries: list[tuple[Path, float]], total: float, out: Path, work: Path, render):
    """Đặt từng đoạn giọng đọc đúng thời điểm của cảnh trên một đường tiếng dài bằng cả video."""
    if not entries:
        render.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                    "-t", f"{total:.3f}", "-c:a", "aac", "-b:a", "128k", out.name], cwd=work)
        return
    cmd = ["ffmpeg", "-y"]
    parts = []
    for i, (path, start) in enumerate(entries):
        cmd += ["-i", path.name]
        ms = int(start * 1000)
        parts.append(f"[{i}:a]aformat=sample_rates=44100:channel_layouts=stereo,adelay={ms}|{ms}[a{i}]")
    labels = "".join(f"[a{i}]" for i in range(len(entries)))
    parts.append(f"{labels}amix=inputs={len(entries)}:normalize=0:dropout_transition=0:duration=longest,"
                 f"apad=whole_dur={total:.3f}[a]")
    cmd += ["-filter_complex", ";".join(parts), "-map", "[a]", "-t", f"{total:.3f}",
            "-c:a", "aac", "-b:a", "192k", out.name]
    render.run(cmd, cwd=work)


def compose(job, report) -> dict:
    """Ghép dự án thành video. Giữ lại kết quả từng bước để "Thử lại" chỉ làm phần còn thiếu."""
    from . import pipeline
    _need_ffmpeg()
    cfg, render, tts, main = pipeline.config, pipeline.render, pipeline.tts, pipeline.autovideo_main
    proj = job.project
    data = proj["data"]
    scenes = data["scenes"]
    if not scenes:
        raise UserError("Dự án chưa có cảnh nào.")
    mode = data.get("transition", "fade")
    t = 0.0 if mode == "none" else 0.4
    n = len(scenes)

    work = settings.WORK_DIR / job.id
    work.mkdir(parents=True, exist_ok=True)
    cfg.set_format(data["format"])
    cfg.TTS_VOICE = data["voice"]
    cfg.TTS_RATE = data["rate"]

    def read(p):
        return json.loads(p.read_text(encoding="utf-8"))

    # ----- 1. Giọng đọc từng cảnh -----
    voices = []
    for i, sc in enumerate(scenes):
        report("voicing", 3 + 27 * i // n, f"Đang tạo giọng đọc cảnh {i + 1}/{n}…")
        text = (sc.get("text") or "").strip()
        if not text and not sc.get("voice"):
            voices.append(None)
            continue
        mp3, info_file = work / f"voice_{i:02d}.mp3", work / f"voice_{i:02d}.json"
        if not (mp3.exists() and info_file.exists()):
            if sc.get("voice"):  # giọng người dùng tự thu: dùng nguyên, chữ phụ đề chia đều theo độ dài
                storage.download(sc["voice"], mp3)
                dur = render.probe_duration(mp3)
                w = text.split()
                words = [(k * dur / len(w), dur / len(w), x) for k, x in enumerate(w)]
            else:
                words = tts.synthesize(text, mp3)
            info_file.write_text(json.dumps({"words": words or [], "duration": render.probe_duration(mp3)}),
                                 encoding="utf-8")
        voices.append(read(info_file))

    # ----- 2. Tải ảnh/clip của dự án về máy chủ -----
    sources = []
    for i, sc in enumerate(scenes):
        report("fetching_footage", 30 + 20 * i // n, f"Đang lấy ảnh/clip cảnh {i + 1}/{n}…")
        if not sc.get("asset"):
            sources.append(None)
            continue
        dest = work / f"asset_{i:02d}.{EXT[sc['kind']]}"
        if not dest.exists():
            storage.download(sc["asset"], dest)
        sources.append(dest)
    music = None
    if data.get("music"):
        music = work / "music.mp3"
        if not music.exists():
            storage.download(data["music"], music)

    # ----- 3. Độ dài từng cảnh + dựng clip -----
    durations = []
    for i, sc in enumerate(scenes):
        v = voices[i]["duration"] if voices[i] else 0.0
        if voices[i]:
            d = v + (2 * t + 0.15 if t else 0.3)
        elif sc.get("kind") == "video" and sources[i]:
            d = min(max(render.probe_duration(sources[i]), 2.0), 12.0)
        else:
            d = 3.0
        durations.append(max(d, 1.5))

    clips = []
    for i, sc in enumerate(scenes):
        report("rendering", 50 + 20 * i // n, f"Đang dựng cảnh {i + 1}/{n}…")
        clip = work / f"clip_{i:02d}.mp4"
        if not clip.exists():
            part = work / f"clip_{i:02d}.part.mp4"
            _scene_clip(sc.get("kind"), sources[i], durations[i], i, part, cfg, render)
            part.replace(clip)
        clips.append(clip)

    # ----- 4. Ghép: chuyển cảnh + giọng đọc + phụ đề + nhạc -----
    report("rendering", 72, "Đang ghép các cảnh, giọng đọc và phụ đề…")
    final = work / "final.mp4"
    if not final.exists():
        total = sum(durations) - (n - 1) * t
        starts, acc = [], 0.0
        for d in durations:
            starts.append(acc)
            acc += d - t
        voice_at = [s + max(t, 0.1) for s in starts]

        captions, entries = [], []
        for i, info in enumerate(voices):
            if not info:
                continue
            entries.append((work / f"voice_{i:02d}.mp3", voice_at[i]))
            if (scenes[i].get("text") or "").strip():
                captions += main.build_captions(info["words"], scenes[i]["text"], info["duration"], voice_at[i])

        _join_clips(clips, durations, t, mode, work / "video.mp4", work, render)
        _mix_voices(entries, total, work / "voice.m4a", work, render)
        render.write_ass(captions, work / "subs.ass")
        part = work / "final.part.mp4"
        render.final_render(work, work / "video.mp4", work / "voice.m4a", work / "subs.ass", music, part)
        part.replace(final)

    # ----- 5. Nén + lưu vào Thư viện -----
    report("uploading", 90, "Đang nén và lưu video…")
    title = proj["name"][:200]
    video = storage.save_video(user_id=job.user_id, title=title, prompt=title, caption=title,
                               source=final, work=work, landscape=data["format"] == "horizontal")
    shutil.rmtree(work, ignore_errors=True)
    return video


def snapshot(user_id: str, pid: str) -> dict:
    """Bản chụp dự án tại lúc bấm "Ghép", để người dùng sửa tiếp mà không ảnh hưởng job đang chạy."""
    proj = get_project(user_id, pid)
    if not proj:
        raise UserError("Không tìm thấy dự án.")
    snap = copy.deepcopy({"name": proj["name"], "data": proj["data"]})
    for s in snap["data"]["scenes"]:
        s.pop("url", None)
        s.pop("voice_url", None)
    snap["data"].pop("music_url", None)
    return snap
