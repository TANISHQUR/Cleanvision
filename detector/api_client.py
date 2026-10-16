"""Small HTTP client the detector uses to send violations and job progress to the backend."""
from __future__ import annotations

import json
import logging
from contextlib import ExitStack
from pathlib import Path

import requests

log = logging.getLogger(__name__)


class ApiClient:
    def __init__(self, base_url: str, token: str, timeout: float = 30):
        self.base = base_url.rstrip("/")
        self.headers = {"X-Detector-Token": token}
        self.timeout = timeout

    def post_violation(self, meta: dict, clip: Path | None, contact: Path, scene: Path) -> dict | None:
        with ExitStack() as stack:
            files = {
                "contact": ("contact.jpg", stack.enter_context(open(contact, "rb")), "image/jpeg"),
                "scene": ("scene.jpg", stack.enter_context(open(scene, "rb")), "image/jpeg"),
            }
            if clip and Path(clip).exists():
                files["clip"] = ("clip.mp4", stack.enter_context(open(clip, "rb")), "video/mp4")
            try:
                r = requests.post(f"{self.base}/api/violations", data={"meta": json.dumps(meta)},
                                  files=files, headers=self.headers, timeout=self.timeout)
                r.raise_for_status()
                return r.json()
            except requests.RequestException as exc:
                log.error("Could not upload violation %s: %s", meta.get("event_id"), exc)
                return None

    def update_job(self, job_id: str, **fields) -> None:
        try:
            r = requests.patch(f"{self.base}/api/jobs/{job_id}", json=fields,
                               headers=self.headers, timeout=self.timeout)
            r.raise_for_status()
        except requests.RequestException as exc:
            log.warning("Could not update job %s: %s", job_id, exc)
