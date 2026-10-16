"""
CleanVision API.

Run from the project root:
    uvicorn backend.app.main:app --reload --port 8000
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .db import ensure_indexes, get_db
from .jobs_runner import runner
from .routers import jobs, registry, violations
from .seed import seed_citizens
from .settings import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("cleanvision")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.evidence_dir.mkdir(parents=True, exist_ok=True)
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    db = get_db()
    await ensure_indexes(db)
    added = await seed_citizens(db)
    if added:
        log.info("Seeded %d simulated citizens", added)
    if settings.use_mock_db:
        log.warning("USE_MOCK_DB=1: data lives in memory and is lost on restart")
    if settings.admin_password == "cleanvision" or settings.secret_key.startswith("dev-"):
        log.warning("Using default admin password / secret key. Change them in backend/.env")
    task = asyncio.create_task(runner.loop(get_db))
    try:
        yield
    finally:
        task.cancel()


app = FastAPI(title="CleanVision API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(registry.router)
app.include_router(violations.router)
app.include_router(jobs.router)


@app.get("/api/health")
async def health():
    db_ok = True
    if not settings.use_mock_db:
        try:
            await get_db().command("ping")
        except Exception:
            db_ok = False
    return {"ok": db_ok, "database": "memory" if settings.use_mock_db else "mongodb"}
