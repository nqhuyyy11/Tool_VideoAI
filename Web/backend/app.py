"""Các API của bản web + phục vụ giao diện (thư mục frontend).

Chạy:  python -m uvicorn backend.app:app --port 8000   (đứng trong thư mục Web)
"""
import shutil
import uuid
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from . import jobs, script_md, settings, storage
from .auth import current_user
from .errors import UserError


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Job nằm trong bộ nhớ nên sau khi khởi động lại, file tạm cũ không còn dùng được
    shutil.rmtree(settings.WORK_DIR, ignore_errors=True)
    if settings.missing():
        print(f"!! Thiếu cấu hình trong .env: {', '.join(settings.missing())}")
    if not shutil.which("ffmpeg"):
        print("!! Chưa tìm thấy FFmpeg trên máy, sẽ không dựng được video.")
    jobs.start_worker()
    yield


app = FastAPI(title="AutoVideo Web", lifespan=lifespan)


@app.exception_handler(RequestValidationError)
async def invalid_input(request, exc):
    return JSONResponse(status_code=422, content={
        "detail": "Dữ liệu gửi lên không hợp lệ. Chủ đề cần dài từ 3 đến 300 ký tự."})


@app.exception_handler(UserError)
async def supabase_problem(request, exc):
    return JSONResponse(status_code=502, content={"detail": str(exc)})


@app.middleware("http")
async def no_stale_frontend(request, call_next):
    # Trình duyệt luôn hỏi lại server, tránh dùng bản JS/CSS cũ sau khi sửa giao diện
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-cache"
    return response


# ---------- Cấu hình cho trình duyệt ----------
@app.get("/api/config")
def get_config():
    """Chỉ trả về URL và anon key (được phép công khai). Không bao giờ trả service_role key."""
    missing = settings.missing()
    if missing:
        raise HTTPException(500, f"Thiếu cấu hình trong file .env: {', '.join(missing)}")
    return {"supabase_url": settings.SUPABASE_URL,
            "supabase_anon_key": settings.SUPABASE_ANON_KEY}


# ---------- Job tạo video ----------
class JobInput(BaseModel):
    topic: str = Field(default="", max_length=300)  # có thể trống nếu đính kèm kịch bản
    format: Literal["vertical", "horizontal", "square"] = "vertical"
    voice: Literal["vi-VN-HoaiMyNeural", "vi-VN-NamMinhNeural"] = "vi-VN-HoaiMyNeural"
    rate: str = Field(default="+10%", pattern=r"^[+-]\d{1,2}%$")
    script_md: str | None = Field(default=None, max_length=50000)  # nội dung file .md đính kèm

    @field_validator("topic", mode="before")
    @classmethod
    def strip_topic(cls, value):
        return value.strip() if isinstance(value, str) else value


def _job_or_404(job_id: str, user: dict) -> jobs.Job:
    job = jobs.get(job_id, user["id"])
    if job is None:
        raise HTTPException(404, "Không tìm thấy video đang tạo (có thể server vừa khởi động lại).")
    return job


@app.post("/api/jobs")
def create_job(data: JobInput, user: dict = Depends(current_user)):
    script = None
    if data.script_md and data.script_md.strip():
        try:
            script = script_md.parse(data.script_md)
        except UserError as e:
            raise HTTPException(422, str(e))
    topic = data.topic or (str(script.get("title") or "") if script else "")
    if script and not topic:
        topic = "Kịch bản đính kèm"
    if not script and len(topic) < 3:
        raise HTTPException(422, "Chủ đề cần dài từ 3 đến 300 ký tự, hoặc hãy đính kèm file kịch bản.")
    try:
        job = jobs.create(user["id"], topic,data.format, data.voice, data.rate, script)
    except jobs.Busy:
        raise HTTPException(409, "Bạn đang có một video chưa tạo xong. Hãy chờ video đó xong đã.")
    return jobs.public(job)


@app.get("/api/jobs/current")
def current_job(user: dict = Depends(current_user)):
    job = jobs.current(user["id"])
    return {"job": jobs.public(job) if job else None}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str, user: dict = Depends(current_user)):
    return jobs.public(_job_or_404(job_id, user))


@app.post("/api/jobs/{job_id}/retry")
def retry_job(job_id: str, user: dict = Depends(current_user)):
    job = _job_or_404(job_id, user)
    if not jobs.retry(job):
        raise HTTPException(409, "Chỉ thử lại được video đang bị lỗi.")
    return jobs.public(job)


@app.delete("/api/jobs/{job_id}")
def discard_job(job_id: str, user: dict = Depends(current_user)):
    job = _job_or_404(job_id, user)
    if not jobs.discard(job):
        raise HTTPException(409, "Video đang được tạo, chưa bỏ được.")
    return {"ok": True}


# ---------- Thư viện ----------
@app.get("/api/videos")
def list_videos(user: dict = Depends(current_user)):
    return {"videos": storage.list_videos(user["id"])}


@app.delete("/api/videos/{video_id}")
def delete_video(video_id: uuid.UUID, user: dict = Depends(current_user)):
    if not storage.delete_video(user["id"], str(video_id)):
        raise HTTPException(404, "Không tìm thấy video này.")
    return {"ok": True}


# ---------- Giao diện ----------
# Đặt cuối cùng để các đường dẫn /api/... ở trên được ưu tiên.
app.mount("/", StaticFiles(directory=settings.FRONTEND_DIR, html=True), name="frontend")
