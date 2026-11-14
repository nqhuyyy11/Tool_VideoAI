"""Hàng đợi job: mỗi video là một job, chạy nền, lần lượt từng cái một.

Trạng thái job chỉ nằm trong bộ nhớ. Nếu tắt server thì job đang chạy sẽ mất
(video đã xong thì vẫn còn trong Supabase).
"""
import queue
import shutil
import threading
import time
import traceback
import uuid
from dataclasses import dataclass, field

from . import settings
from .errors import friendly

RUNNING = ("queued", "scripting", "voicing", "fetching_footage", "rendering", "uploading")
KEEP_SECONDS = 6 * 3600  # job đã xong/lỗi được giữ trong bộ nhớ bao lâu


class Busy(Exception):
    """Người dùng đang có một video chưa làm xong."""


@dataclass
class Job:
    id: str
    user_id: str
    topic: str
    video_format: str
    voice: str
    rate: str
    status: str = "queued"
    step: str = "queued"  # bước gần nhất đã chạy tới (để biết lỗi ở bước nào)
    percent: int = 0
    message: str = "Đang chờ tới lượt…"
    error: str | None = None
    video: dict | None = None
    created_at: float = field(default_factory=time.time)
    finished_at: float | None = None

    def report(self, status: str, percent: int, message: str):
        self.status = self.step = status
        self.percent = int(percent)
        self.message = message


_jobs: dict[str, Job] = {}
_lock = threading.Lock()
_queue: "queue.Queue[str]" = queue.Queue()
_worker_started = False


def _remove_work(job_id: str):
    shutil.rmtree(settings.WORK_DIR / job_id, ignore_errors=True)


def _prune():
    """Dọn job cũ. Gọi khi đang giữ _lock."""
    now = time.time()
    for job in list(_jobs.values()):
        if job.finished_at and now - job.finished_at > KEEP_SECONDS:
            del _jobs[job.id]
            _remove_work(job.id)


def create(user_id: str, topic: str, video_format: str, voice: str, rate: str) -> Job:
    with _lock:
        _prune()
        for job in list(_jobs.values()):
            if job.user_id != user_id:
                continue
            if job.status in RUNNING:
                raise Busy()
            if job.status == "failed":  # tạo video mới thì bỏ job lỗi cũ
                del _jobs[job.id]
                _remove_work(job.id)
        job = Job(id=uuid.uuid4().hex, user_id=user_id, topic=topic,
                  video_format=video_format, voice=voice, rate=rate)
        _jobs[job.id] = job
    _queue.put(job.id)
    return job


def get(job_id: str, user_id: str) -> Job | None:
    job = _jobs.get(job_id)
    return job if job and job.user_id == user_id else None


def current(user_id: str) -> Job | None:
    """Job đang chạy hoặc vừa lỗi của người dùng (để mở lại trang vẫn thấy tiến độ)."""
    mine = [j for j in list(_jobs.values())
            if j.user_id == user_id and (j.status in RUNNING or j.status == "failed")]
    return max(mine, key=lambda j: j.created_at) if mine else None


def retry(job: Job) -> bool:
    with _lock:
        if job.status != "failed":
            return False
        job.status = "queued"
        job.error = None
        job.finished_at = None
        job.message = "Đang chờ tới lượt…"
    _queue.put(job.id)
    return True


def discard(job: Job) -> bool:
    with _lock:
        if job.status in RUNNING:
            return False
        _jobs.pop(job.id, None)
    _remove_work(job.id)
    return True


def public(job: Job) -> dict:
    """Thông tin job gửi về cho web."""
    ahead = 0
    if job.status == "queued":
        ahead = sum(1 for j in list(_jobs.values())
                    if j.id != job.id and j.status in RUNNING and j.created_at < job.created_at)
    return {
        "id": job.id,
        "topic": job.topic,
        "status": job.status,
        "step": job.step,
        "percent": job.percent,
        "message": job.message,
        "error": job.error,
        "video": job.video,
        "ahead": ahead,
    }


def _work_loop():
    while True:
        job = _jobs.get(_queue.get())
        if job is None or job.status != "queued":
            continue
        try:
            # Nạp tool gốc ở đây: nếu sai AUTOVIDEO_DIR thì lỗi hiện lên web
            # thay vì làm dừng cả hàng đợi.
            from . import pipeline
            job.video = pipeline.run(job, job.report)
            job.status = "done"
            job.percent = 100
            job.message = "Hoàn tất"
        except Exception as e:
            traceback.print_exc()
            job.status = "failed"
            job.error = friendly(e)
        job.finished_at = time.time()


def start_worker():
    global _worker_started
    if _worker_started:
        return
    _worker_started = True
    threading.Thread(target=_work_loop, name="video-worker", daemon=True).start()
