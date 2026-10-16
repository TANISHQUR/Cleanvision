from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from ..auth import require_admin, require_detector
from ..db import get_db, new_id, out, utcnow
from ..files import safe_name, save_upload
from ..jobs_runner import TERMINAL, runner
from ..settings import settings

router = APIRouter(prefix="/api/jobs", tags=["jobs"])
VIDEO_EXT = {".mp4", ".avi", ".mov", ".mkv", ".webm", ".m4v"}


@router.post("", status_code=201)
async def create_job(
    video: UploadFile = File(...),
    camera_id: str = Form(default="UPLOAD", max_length=40),
    location: str = Form(default="", max_length=200),
    user: str = Depends(require_admin),
):
    name = safe_name(video.filename or "video.mp4")
    ext = "." + name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in VIDEO_EXT:
        raise HTTPException(422, f"Upload a video file ({', '.join(sorted(VIDEO_EXT))}).")
    job_id = new_id()
    dest = settings.uploads_dir / job_id / name
    size = await save_upload(video, dest)
    doc = {
        "_id": job_id,
        "status": "queued",
        "video_name": video.filename or name,
        "video_path": str(dest),
        "size_bytes": size,
        "camera_id": camera_id.strip() or "UPLOAD",
        "location": location.strip(),
        "progress": 0.0,
        "violations": 0,
        "events": 0,
        "error": None,
        "created_by": user,
        "created_at": utcnow(),
    }
    db = get_db()
    await db.jobs.insert_one(doc)
    await runner.kick(db)
    return out(await db.jobs.find_one({"_id": job_id}))


@router.get("")
async def list_jobs(limit: int = Query(default=30, ge=1, le=100), _: str = Depends(require_admin)):
    db = get_db()
    await runner.kick(db)
    docs = await db.jobs.find({}).sort("created_at", -1).limit(limit).to_list(limit)
    return {"items": [out(d) for d in docs]}


@router.get("/{job_id}")
async def get_job(job_id: str, _: str = Depends(require_admin)):
    doc = await get_db().jobs.find_one({"_id": job_id})
    if not doc:
        raise HTTPException(404, "Job not found.")
    return out(doc)


class JobUpdate(BaseModel):
    status: Literal["running", "completed", "failed"] | None = None
    progress: float | None = Field(default=None, ge=0, le=1)
    events: int | None = Field(default=None, ge=0)
    error: str | None = Field(default=None, max_length=2000)
    run_id: str | None = None


@router.patch("/{job_id}", dependencies=[Depends(require_detector)])
async def update_job(job_id: str, body: JobUpdate):
    db = get_db()
    job = await db.jobs.find_one({"_id": job_id})
    if not job:
        raise HTTPException(404, "Job not found.")
    fields = body.model_dump(exclude_none=True)
    if fields.get("status") in TERMINAL:
        fields["finished_at"] = utcnow()
    if fields:
        await db.jobs.update_one({"_id": job_id}, {"$set": fields})
    return out(await db.jobs.find_one({"_id": job_id}))
