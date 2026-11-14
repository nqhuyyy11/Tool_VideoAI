"""Bước 2: chuyển câu thoại thành giọng đọc + lấy mốc thời gian từng từ."""
import asyncio
import time

import edge_tts

import config


async def _synth(text: str, out_path: str) -> list[tuple[float, float, str]]:
    try:  # edge-tts >= 7 cần bật WordBoundary
        comm = edge_tts.Communicate(
            text, config.TTS_VOICE, rate=config.TTS_RATE, boundary="WordBoundary"
        )
    except TypeError:  # bản cũ mặc định đã có WordBoundary
        comm = edge_tts.Communicate(text, config.TTS_VOICE, rate=config.TTS_RATE)

    words = []
    with open(out_path, "wb") as f:
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                # offset/duration tính bằng đơn vị 100 nano giây
                words.append(
                    (chunk["offset"] / 1e7, chunk["duration"] / 1e7, chunk["text"])
                )
    return words


def synthesize(text: str, out_path, retries: int = 7) -> list[tuple[float, float, str]]:
    """Trả về danh sách (start, duration, word), tính theo giây."""
    # Server edge-tts hay chập chờn: cùng 1 câu lúc lỗi NoAudioReceived, lúc chạy được
    for attempt in range(1, retries + 1):
        try:
            return asyncio.run(_synth(text, str(out_path)))
        except edge_tts.exceptions.NoAudioReceived:
            if attempt == retries:
                raise
            print(f"   (TTS không trả audio, thử lại {attempt}/{retries - 1}...)")
            time.sleep(3 * attempt)  # lỗi theo đợt ~15-20s nên chờ tăng dần
