"""Bước 4: ghép video, giọng đọc, phụ đề, nhạc nền bằng FFmpeg."""
import subprocess
from pathlib import Path

import config

FPS = config.FPS


def run(cmd: list, cwd=None):
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if p.returncode != 0:
        raise RuntimeError("FFmpeg lỗi:\n" + p.stderr[-2000:])


def probe_duration(path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True,
    ).stdout.strip()
    return float(out)


def make_scene_clip(src: Path | None, duration: float, out: Path):
    """Cắt/lặp video nguồn đúng độ dài cảnh, crop về khổ đã chọn. Không có nguồn thì nền tối."""
    W, H = config.WIDTH, config.HEIGHT
    vf = (f"scale={W}:{H}:force_original_aspect_ratio=increase,"
          f"crop={W}:{H},fps={FPS},setsar=1")
    if src and src.exists():
        inp = ["-stream_loop", "-1", "-i", str(src)]
    else:
        inp = ["-f", "lavfi", "-i", f"color=c=0x1a1a2e:s={W}x{H}:r={FPS}"]
    run(["ffmpeg", "-y", *inp, "-t", f"{duration:.3f}", "-vf", vf, "-an",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
         "-pix_fmt", "yuv420p", str(out)])


def _concat(files: list[Path], out: Path, codec: list, job_dir: Path):
    lst = job_dir / f"{out.stem}_list.txt"
    lst.write_text("".join(f"file '{f.name}'\n" for f in files), encoding="utf-8")
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst.name, *codec,
         out.name], cwd=job_dir)


def concat_videos(files, out, job_dir):
    _concat(files, out, ["-c", "copy"], job_dir)


def concat_audios(files, out, job_dir):
    _concat(files, out, ["-c:a", "aac", "-b:a", "192k"], job_dir)


def _ass_time(t: float) -> str:
    cs = int(round(t * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def write_ass(captions: list[tuple[float, float, str]], out: Path):
    """Phụ đề kiểu TikTok: chữ to, đậm, viền đen, nằm giữa-dưới màn hình."""
    W, H = config.WIDTH, config.HEIGHT
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,88,&H00FFFFFF,&H0000FFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,6,3,2,80,80,{config.SUB_MARGIN_V},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    for start, end, text in captions:
        text = text.replace("\\", "").replace("{", "(").replace("}", ")")
        lines.append(f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Default,,0,0,0,,"
                     f"{{\\fad(60,0)}}{text.upper()}")
    out.write_text(header + "\n".join(lines) + "\n", encoding="utf-8")


def final_render(job_dir: Path, video: Path, voice: Path, ass: Path,
                 music: Path | None, out: Path):
    # chạy trong job_dir và dùng tên file tương đối để tránh lỗi đường dẫn "C:\" trên Windows
    cmd = ["ffmpeg", "-y", "-i", video.name, "-i", voice.name]
    if music:
        cmd += ["-stream_loop", "-1", "-i", str(music.resolve())]
        fc = (f"[0:v]subtitles={ass.name}[v];"
              f"[2:a]volume={config.MUSIC_VOLUME}[m];"
              f"[1:a][m]amix=inputs=2:duration=first:dropout_transition=0,volume=2[a]")
    else:
        fc = f"[0:v]subtitles={ass.name}[v];[1:a]anull[a]"
    cmd += ["-filter_complex", fc, "-map", "[v]", "-map", "[a]",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
            "-shortest", "-movflags", "+faststart", out.name]
    run(cmd, cwd=job_dir)
