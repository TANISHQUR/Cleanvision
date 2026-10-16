"""
Runs the detector for uploaded videos, one at a time (a 4 GB GPU can't run
several YOLO processes at once). Each job is a separate Python process, so a
crash in the detector never takes the web server down.
"""
from __future__ import annotations

import asyncio
import logging
import os
import subprocess

from .db import utcnow
from .settings import PROJECT_ROOT, settings

log = logging.getLogger(__name__)
TERMINAL = {"completed", "failed", "cancelled"}


class JobRunner:
    def __init__(self) -> None:
        self.proc: subprocess.Popen | None = None
        self.job_id: str | None = None
        self.lock = asyncio.Lock()

    async def kick(self, db) -> None:
        async with self.lock:
            if self.proc is not None:
                code = self.proc.poll()
                if code is None:
                    return
                job = await db.jobs.find_one({"_id": self.job_id})
                if job and job.get("status") not in TERMINAL:
                    await db.jobs.update_one({"_id": self.job_id}, {"$set": {
                        "status": "failed",
                        "error": f"Detector stopped with exit code {code}. Check {job.get('log_path')}",
                        "finished_at": utcnow(),
                    }})
                self.proc, self.job_id = None, None

            queued = await db.jobs.find({"status": "queued"}).sort("created_at", 1).limit(1).to_list(1)
            if not queued:
                return
            job = queued[0]
            log_path = settings.uploads_dir / job["_id"] / "detector.log"
            cmd = [
                settings.python_exe, "-m", "detector.run",
                "--source", job["video_path"],
                "--config", settings.detector_config,
                "--api-url", settings.public_api_url,
                "--job-id", job["_id"],
                "--camera-id", job["camera_id"],
                "--location", job["location"],
                "--video-name", job["video_name"],
            ]
            env = {**os.environ, "CLEANVISION_API_TOKEN": settings.detector_token, "PYTHONUNBUFFERED": "1"}
            try:
                log_file = open(log_path, "ab")
                self.proc = subprocess.Popen(cmd, cwd=str(PROJECT_ROOT), stdout=log_file,
                                             stderr=subprocess.STDOUT, env=env)
                log_file.close()   # the child keeps its own handle
                self.job_id = job["_id"]
                await db.jobs.update_one({"_id": job["_id"]}, {"$set": {
                    "status": "starting", "started_at": utcnow(), "log_path": str(log_path)}})
                log.info("Started detector for job %s (pid %s)", job["_id"], self.proc.pid)
            except OSError as exc:
                await db.jobs.update_one({"_id": job["_id"]}, {"$set": {
                    "status": "failed", "error": f"Could not start detector: {exc}", "finished_at": utcnow()}})

    async def loop(self, get_db, every: float = 3.0) -> None:
        while True:
            try:
                await self.kick(get_db())
            except Exception:  # keep the loop alive no matter what
                log.exception("Job runner error")
            await asyncio.sleep(every)


runner = JobRunner()
