"""Saving uploaded files safely."""
from __future__ import annotations

import re
from pathlib import Path

from fastapi import HTTPException, UploadFile

from .settings import settings

CHUNK = 1024 * 1024


def safe_name(name: str) -> str:
    name = Path(name or "upload").name
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")
    return name[:120] or "upload"


async def save_upload(upload: UploadFile, dest: Path, max_mb: int | None = None) -> int:
    limit = (max_mb or settings.max_upload_mb) * CHUNK
    dest.parent.mkdir(parents=True, exist_ok=True)
    size = 0
    with open(dest, "wb") as fh:
        while chunk := await upload.read(CHUNK):
            size += len(chunk)
            if size > limit:
                fh.close()
                dest.unlink(missing_ok=True)
                raise HTTPException(413, f"File is larger than {limit // CHUNK} MB.")
            fh.write(chunk)
    return size


def resolve_media(rel: str) -> Path:
    """Map a stored relative path to a file inside the storage folder, refusing anything outside it."""
    base = settings.storage_dir
    path = (base / rel).resolve()
    if base not in path.parents:
        raise HTTPException(404, "File not found.")
    if not path.is_file():
        raise HTTPException(404, "File not found.")
    return path
