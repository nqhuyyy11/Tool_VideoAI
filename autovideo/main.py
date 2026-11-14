"""
Tạo video ngắn tự động: chủ đề -> kịch bản -> giọng đọc -> video nền -> phụ đề -> MP4.

Cách dùng:
  python main.py "Vì sao bầu trời có màu xanh"
  python main.py --file topics.txt          # mỗi dòng 1 chủ đề, tạo hàng loạt
  python main.py --script my_script.json    # tự viết kịch bản, không cần Gemini
"""
import argparse
import json
import random
import re
import shutil
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

import config
import footage
import render
import script_gen
import tts

PUNCT_END = (",", ".", "!", "?", ":", ";", "…")


def slugify(text: str, maxlen=40) -> str:
    text = text.replace("đ", "d").replace("Đ", "D")
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text[:maxlen] or "video"


def build_captions(words, text, duration, offset):
    """Gom từ thành cụm ngắn (mặc định 4 từ), ngắt ở dấu câu."""
    n = config.WORDS_PER_CAPTION
    if not words:  # không có mốc thời gian -> chia đều
        tokens = text.split()
        step = duration / max(len(tokens), 1)
        words = [(i * step, step, t) for i, t in enumerate(tokens)]

    groups, cur = [], []
    for w in words:
        cur.append(w)
        if len(cur) >= n or w[2].endswith(PUNCT_END):
            groups.append(cur)
            cur = []
    if cur:
        groups.append(cur)

    caps = []
    for i, g in enumerate(groups):
        start = offset + g[0][0]
        if i + 1 < len(groups):
            end = offset + groups[i + 1][0][0]
        else:
            end = offset + min(duration, g[-1][0] + g[-1][1] + 0.3)
        txt = " ".join(w[2] for w in g).strip(" ,.;:")
        caps.append((start, max(end, start + 0.2), txt))
    return caps


def make_video(topic: str | None = None, script: dict | None = None) -> Path:
    if script is None:
        print(f"\n[1/5] AI viết kịch bản: {topic}")
        script = script_gen.generate_script(topic)
    script = script_gen.validate(script)
    print(f"   -> {script['title']} ({len(script['scenes'])} cảnh)")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    job = config.OUTPUT_DIR / f"{stamp}_{slugify(script['title'])}"
    work = job / "work"
    work.mkdir(parents=True, exist_ok=True)
    (job / "script.json").write_text(
        json.dumps(script, ensure_ascii=False, indent=2), encoding="utf-8")

    print("[2/5] Tạo giọng đọc + [3/5] tải video nền")
    used, audios, clips, captions, t = set(), [], [], [], 0.0
    for i, sc in enumerate(script["scenes"], 1):
        a = work / f"voice_{i:02d}.mp3"
        words = tts.synthesize(sc["text"], a)
        dur = render.probe_duration(a)

        src = work / f"src_{i:02d}.mp4"
        ok = footage.fetch_clip(sc["keywords"], src, used)
        print(f"   cảnh {i}: {dur:.1f}s | '{sc['keywords']}' "
              f"{'✓' if ok else '(không có video, dùng nền màu)'}")

        clip = work / f"clip_{i:02d}.mp4"
        render.make_scene_clip(src if ok else None, dur, clip)

        captions += build_captions(words, sc["text"], dur, t)
        audios.append(a)
        clips.append(clip)
        t += dur

    print("[4/5] Ghép video + phụ đề")
    render.concat_videos(clips, work / "video.mp4", work)
    render.concat_audios(audios, work / "voice.m4a", work)
    render.write_ass(captions, work / "subs.ass")

    music_files = list(config.MUSIC_DIR.glob("*.mp3")) if config.MUSIC_DIR.exists() else []
    music = random.choice(music_files) if music_files else None
    render.final_render(work, work / "video.mp4", work / "voice.m4a",
                        work / "subs.ass", music, work / "final.mp4")

    final = job / "final.mp4"
    shutil.move(str(work / "final.mp4"), final)

    print("[5/5] Lưu caption để đăng bài")
    post = f"{script['title']}\n\n{script['caption']}\n\n{' '.join(script['hashtags'])}"
    (job / "caption.txt").write_text(post, encoding="utf-8")

    shutil.rmtree(work, ignore_errors=True)  # xóa file tạm; comment dòng này nếu muốn giữ
    print(f"✅ Xong: {final}  ({t:.0f}s)")
    return final


def main():
    ap = argparse.ArgumentParser(description="Tạo video ngắn bằng AI")
    ap.add_argument("topic", nargs="?", help="chủ đề video")
    ap.add_argument("--file", help="file .txt, mỗi dòng một chủ đề")
    ap.add_argument("--script", help="file kịch bản JSON tự viết")
    ap.add_argument("--format", choices=list(config.FORMATS), default=None,
                    help="khổ video: vertical 9:16 (mặc định) | horizontal 16:9 | square 1:1")
    args = ap.parse_args()
    if args.format:
        config.set_format(args.format)

    if not shutil.which("ffmpeg"):
        sys.exit("Chưa cài FFmpeg. Windows: chạy 'winget install ffmpeg' rồi mở lại terminal.")

    if args.script:
        make_video(script=json.loads(Path(args.script).read_text(encoding="utf-8")))
    elif args.file:
        topics = [l.strip() for l in Path(args.file).read_text(encoding="utf-8").splitlines()
                  if l.strip() and not l.startswith("#")]
        for i, tp in enumerate(topics, 1):
            print(f"\n===== Video {i}/{len(topics)} =====")
            try:
                make_video(topic=tp)
            except Exception as e:  # 1 video lỗi không làm dừng cả lô
                print(f"❌ Lỗi với '{tp}': {e}")
    elif args.topic:
        make_video(topic=args.topic)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
