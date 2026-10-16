from __future__ import annotations

import re
from collections import Counter
from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..auth import check_login, make_token, require_admin
from ..db import get_db, out, utcnow
from ..files import resolve_media
from ..settings import settings

router = APIRouter(prefix="/api", tags=["registry"])


# ---------------------------------------------------------------- auth
class LoginIn(BaseModel):
    username: str
    password: str


@router.post("/auth/login")
async def login(body: LoginIn):
    if not check_login(body.username, body.password):
        raise HTTPException(401, "Wrong username or password.")
    return {"token": make_token(body.username), "username": body.username,
            "expires_in_hours": settings.token_ttl_hours}


@router.get("/auth/me")
async def me(user: str = Depends(require_admin)):
    return {"username": user}


# --------------------------------------------------------------- media
@router.get("/media/{rel_path:path}")
async def media(rel_path: str, _: str = Depends(require_admin)):
    if not rel_path.startswith("evidence/"):
        raise HTTPException(404, "File not found.")
    return FileResponse(resolve_media(rel_path))


# ------------------------------------------------------------ citizens
@router.get("/citizens")
async def list_citizens(q: str = "", limit: int = Query(default=50, ge=1, le=200),
                        _: str = Depends(require_admin)):
    query: dict = {}
    if q.strip():
        pattern = {"$regex": re.escape(q.strip()), "$options": "i"}
        query = {"$or": [{"name": pattern}, {"citizen_ref": pattern}, {"address": pattern}]}
    db = get_db()
    docs = await db.citizens.find(query).sort("name", 1).limit(limit).to_list(limit)
    items = []
    for d in docs:
        item = out(d)
        item["violation_count"] = await db.violations.count_documents({"citizen_id": d["_id"]})
        items.append(item)
    return {"items": items}


@router.get("/citizens/{citizen_id}")
async def get_citizen(citizen_id: str, _: str = Depends(require_admin)):
    db = get_db()
    doc = await db.citizens.find_one({"_id": citizen_id})
    if not doc:
        raise HTTPException(404, "Citizen not found.")
    result = out(doc)
    result["violations"] = [out(v) for v in await db.violations.find({"citizen_id": citizen_id})
                            .sort("detected_at", -1).to_list(100)]
    result["challans"] = [out(c) for c in await db.challans.find({"citizen_id": citizen_id})
                          .sort("issued_at", -1).to_list(100)]
    return result


# ------------------------------------------------------------- challans
@router.get("/challans")
async def list_challans(status: str | None = None, limit: int = Query(default=100, ge=1, le=500),
                        _: str = Depends(require_admin)):
    q = {"status": status} if status else {}
    docs = await get_db().challans.find(q).sort("issued_at", -1).limit(limit).to_list(limit)
    return {"items": [out(d) for d in docs]}


class ChallanUpdate(BaseModel):
    status: Literal["paid", "cancelled"]


@router.patch("/challans/{challan_id}")
async def update_challan(challan_id: str, body: ChallanUpdate, user: str = Depends(require_admin)):
    db = get_db()
    doc = await db.challans.find_one({"_id": challan_id})
    if not doc:
        raise HTTPException(404, "Challan not found.")
    if doc["status"] != "issued":
        raise HTTPException(409, f"This challan is already {doc['status']}.")
    stamp = "paid_at" if body.status == "paid" else "cancelled_at"
    await db.challans.update_one({"_id": challan_id},
                                 {"$set": {"status": body.status, stamp: utcnow(), "updated_by": user}})
    return out(await db.challans.find_one({"_id": challan_id}))


# ---------------------------------------------------------------- stats
@router.get("/stats")
async def stats(days: int = Query(default=14, ge=1, le=90), _: str = Depends(require_admin)):
    db = get_db()
    since = utcnow() - timedelta(days=days - 1)
    since = since.replace(hour=0, minute=0, second=0, microsecond=0)

    by_status = Counter()
    by_type = Counter()
    by_day = Counter()
    by_camera = Counter()
    async for v in db.violations.find({}, {"status": 1, "waste_type": 1, "detected_at": 1, "camera_id": 1}):
        by_status[v["status"]] += 1
        by_type[v["waste_type"]] += 1
        by_camera[v["camera_id"]] += 1
        dt = v.get("detected_at")
        if dt is not None:
            if dt.tzinfo is None:
                from datetime import timezone
                dt = dt.replace(tzinfo=timezone.utc)
            if dt >= since:
                by_day[dt.date().isoformat()] += 1

    fines = Counter()
    fine_counts = Counter()
    async for c in db.challans.find({}, {"status": 1, "amount": 1}):
        fines[c["status"]] += c["amount"]
        fine_counts[c["status"]] += 1

    daily = []
    for i in range(days):
        d = (since + timedelta(days=i)).date().isoformat()
        daily.append({"date": d, "count": by_day.get(d, 0)})

    return {
        "total": sum(by_status.values()),
        "by_status": {s: by_status.get(s, 0) for s in ("pending", "flagged", "approved", "rejected")},
        "by_waste_type": dict(by_type.most_common()),
        "by_camera": dict(by_camera.most_common()),
        "daily": daily,
        "fines": {
            "issued_amount": fines.get("issued", 0),
            "paid_amount": fines.get("paid", 0),
            "issued_count": fine_counts.get("issued", 0),
            "paid_count": fine_counts.get("paid", 0),
            "cancelled_count": fine_counts.get("cancelled", 0),
        },
        "active_jobs": await db.jobs.count_documents({"status": {"$in": ["queued", "starting", "running"]}}),
    }
