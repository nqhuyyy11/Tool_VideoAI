"""Các API của bản web + phục vụ giao diện (thư mục frontend).

Chạy:  python -m uvicorn backend.app:app --port 8000   (đứng trong thư mục Web)
"""
import shutil
import uuid
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from . import jobs, script_md, settings, storage, studio
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


# ---------- Studio: dự án nhiều cảnh ----------
class SceneIn(BaseModel):
    id: str = Field(max_length=40)
    prompt: str = Field(default="", max_length=1000)
    text: str = Field(default="", max_length=1500)
    kind: Literal["image", "video"] | None = None
    asset: str | None = Field(default=None, max_length=300)
    voice: str | None = Field(default=None, max_length=300)  # giọng người dùng tự thu cho cảnh


class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    format: Literal["vertical", "horizontal", "square"] = "vertical"
    voice: Literal["vi-VN-HoaiMyNeural", "vi-VN-NamMinhNeural"] = "vi-VN-HoaiMyNeural"
    rate: str = Field(default="+10%", pattern=r"^[+-]\d{1,2}%$")
    transition: Literal["fade", "mixed", "none"] = "fade"
    music: str | None = Field(default=None, max_length=300)
    music_name: str = Field(default="", max_length=120)
    scenes: list[SceneIn] = Field(default_factory=list, max_length=studio.MAX_SCENES)


class NewProject(BaseModel):
    name: str = Field(default="Dự án mới", min_length=1, max_length=80)


class GenerateIn(BaseModel):
    kind: Literal["image", "video"]
    prompt: str = Field(min_length=3, max_length=1000)
    format: Literal["vertical", "horizontal", "square"] = "vertical"
    from_asset: str | None = Field(default=None, max_length=300)  # ảnh gốc để biến thành clip


def _bad_input(e: UserError) -> HTTPException:
    return HTTPException(422, str(e))


@app.get("/api/studio/projects")
def studio_list(user: dict = Depends(current_user)):
    return {"projects": studio.list_projects(user["id"])}


@app.post("/api/studio/projects")
def studio_create(data: NewProject, user: dict = Depends(current_user)):
    return studio.create_project(user["id"], data.name.strip() or "Dự án mới")


@app.get("/api/studio/projects/{pid}")
def studio_get(pid: uuid.UUID, user: dict = Depends(current_user)):
    proj = studio.get_project(user["id"], str(pid))
    if not proj:
        raise HTTPException(404, "Không tìm thấy dự án.")
    return proj


@app.put("/api/studio/projects/{pid}")
def studio_save(pid: uuid.UUID, data: ProjectIn, user: dict = Depends(current_user)):
    try:
        proj = studio.save_project(user["id"], str(pid), data.model_dump())
    except UserError as e:
        raise _bad_input(e)
    if not proj:
        raise HTTPException(404, "Không tìm thấy dự án.")
    return proj


@app.delete("/api/studio/projects/{pid}")
def studio_delete(pid: uuid.UUID, user: dict = Depends(current_user)):
    if not studio.delete_project(user["id"], str(pid)):
        raise HTTPException(404, "Không tìm thấy dự án.")
    return {"ok": True}


@app.post("/api/studio/assets")
async def studio_upload(request: Request, name: str = "file", user: dict = Depends(current_user)):
    """Nhận 1 tệp (gửi thẳng nội dung tệp làm body), chuẩn hoá và lưu lại."""
    limit = int(settings.MAX_UPLOAD_MB * 1024 * 1024)
    if int(request.headers.get("content-length") or 0) > limit:
        raise HTTPException(413, f"Tệp quá lớn (tối đa {settings.MAX_UPLOAD_MB:.0f} MB).")
    raw = await request.body()
    if not raw or len(raw) > limit:
        raise HTTPException(413 if raw else 422, "Tệp trống hoặc quá lớn.")
    try:
        return await run_in_threadpool(studio.ingest_upload, user["id"], raw, name)
    except UserError as e:
        raise _bad_input(e)


@app.post("/api/studio/generate")
def studio_generate(data: GenerateIn, user: dict = Depends(current_user)):
    try:
        return studio.start_generation(user["id"], data.kind, data.prompt.strip(),
                                       data.format, data.from_asset)
    except UserError as e:
        raise _bad_input(e)


@app.get("/api/studio/generations/{gid}")
def studio_generation(gid: str, user: dict = Depends(current_user)):
    g = studio.get_generation(gid, user["id"])
    if not g:
        raise HTTPException(404, "Không tìm thấy yêu cầu này (có thể server vừa khởi động lại).")
    return g


@app.post("/api/studio/projects/{pid}/compose")
def studio_compose(pid: uuid.UUID, user: dict = Depends(current_user)):
    """Ghép dự án thành 1 video. Tiến độ theo dõi qua /api/jobs/... như video thường."""
    try:
        snap = studio.snapshot(user["id"], str(pid))
        if not snap["data"]["scenes"]:
            raise UserError("Dự án chưa có cảnh nào để ghép.")
        job = jobs.create(user["id"], snap["name"], snap["data"]["format"],
                          snap["data"]["voice"], snap["data"]["rate"], project=snap)
    except UserError as e:
        raise _bad_input(e)
    except jobs.Busy:
        raise HTTPException(409, "Bạn đang có một video chưa tạo xong. Hãy chờ video đó xong đã.")
    return jobs.public(job)


# ---------- Giao diện ----------
# Đặt cuối cùng để các đường dẫn /api/... ở trên được ưu tiên.
app.mount("/", StaticFiles(directory=settings.FRONTEND_DIR, html=True), name="frontend")
