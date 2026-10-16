from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from ..auth import require_admin, require_detector
from ..db import get_db, new_id, next_number, out, utcnow
from ..files import save_upload
from ..settings import settings

router = APIRouter(prefix="/api/violations", tags=["violations"])

STATUSES = ("pending", "flagged", "approved", "rejected")


def with_urls(doc: dict) -> dict:
    ev = doc.get("evidence") or {}
    doc["evidence_urls"] = {k: f"/api/media/{v}" for k, v in ev.items() if v}
    return doc


@router.post("", dependencies=[Depends(require_detector)], status_code=201)
async def create_violation(
    meta: str = Form(..., description="JSON metadata produced by the detector"),
    contact: UploadFile = File(...),
    scene: UploadFile = File(...),
    clip: UploadFile | None = File(default=None),
):
    try:
        m = json.loads(meta)
    except json.JSONDecodeError:
        raise HTTPException(422, "meta must be valid JSON.")
    missing = [k for k in ("event_id", "camera_id", "waste_type", "confidence") if k not in m]
    if missing:
        raise HTTPException(422, f"meta is missing: {', '.join(missing)}")

    db = get_db()
    existing = await db.violations.find_one({"event_id": m["event_id"]})
    if existing:   # the detector retried; don't create a duplicate
        return with_urls(out(existing))

    event_id = str(m["event_id"])
    if not event_id.isalnum():
        raise HTTPException(422, "event_id must be alphanumeric.")
    rel = f"evidence/{event_id}"
    evidence = {
        "contact": f"{rel}/contact.jpg",
        "scene": f"{rel}/scene.jpg",
        "clip": None,
    }
    await save_upload(contact, settings.storage_dir / evidence["contact"], max_mb=20)
    await save_upload(scene, settings.storage_dir / evidence["scene"], max_mb=20)
    if clip is not None:
        evidence["clip"] = f"{rel}/clip.mp4"
        await save_upload(clip, settings.storage_dir / evidence["clip"], max_mb=200)

    now = utcnow()
    detected_at = now
    if isinstance(m.get("detected_at"), (int, float)):
        detected_at = datetime.fromtimestamp(m["detected_at"], tz=timezone.utc)

    n = await next_number(db, "violation")
    doc = {
        "_id": new_id(),
        "code": f"CV-{now.year}-{n:05d}",
        "event_id": event_id,
        "status": "pending",
        "camera_id": m["camera_id"],
        "location": m.get("location") or "",
        "waste_type": m["waste_type"],
        "confidence": float(m["confidence"]),
        "detected_at": detected_at,
        "video_time": m.get("detected_time"),
        "release_time": m.get("release_time"),
        "person_track_id": m.get("person_track_id"),
        "object_track_id": m.get("object_track_id"),
        "verified_new": m.get("verified_new"),
        "source": {
            "job_id": m.get("job_id"),
            "run_id": m.get("run_id"),
            "video_name": m.get("video_name"),
            "live": bool(m.get("live")),
        },
        "evidence": evidence,
        "citizen_id": None,
        "challan_id": None,
        "review": None,
        "created_at": now,
    }
    await db.violations.insert_one(doc)
    if m.get("job_id"):
        await db.jobs.update_one({"_id": m["job_id"]}, {"$inc": {"violations": 1}})
    return with_urls(out(doc))


@router.get("")
async def list_violations(
    status: str | None = Query(default=None),
    waste_type: str | None = None,
    camera_id: str | None = None,
    job_id: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    skip: int = Query(default=0, ge=0),
    _: str = Depends(require_admin),
):
    q: dict = {}
    if status:
        if status not in STATUSES:
            raise HTTPException(422, f"status must be one of {STATUSES}")
        q["status"] = status
    if waste_type:
        q["waste_type"] = waste_type
    if camera_id:
        q["camera_id"] = camera_id
    if job_id:
        q["source.job_id"] = job_id
    db = get_db()
    total = await db.violations.count_documents(q)
    docs = await db.violations.find(q).sort("detected_at", -1).skip(skip).limit(limit).to_list(limit)
    return {"items": [with_urls(out(d)) for d in docs], "total": total}


@router.get("/{violation_id}")
async def get_violation(violation_id: str, _: str = Depends(require_admin)):
    db = get_db()
    doc = await db.violations.find_one({"_id": violation_id})
    if not doc:
        raise HTTPException(404, "Violation not found.")
    result = with_urls(out(doc))
    result["citizen"] = out(await db.citizens.find_one({"_id": doc["citizen_id"]})) if doc.get("citizen_id") else None
    result["challan"] = out(await db.challans.find_one({"_id": doc["challan_id"]})) if doc.get("challan_id") else None
    return result


class ReviewIn(BaseModel):
    action: Literal["approve", "reject", "flag"]
    note: str = Field(default="", max_length=1000)
    citizen_id: str | None = None


ALLOWED = {
    "approve": {"pending", "flagged"},
    "reject": {"pending", "flagged"},
    "flag": {"pending"},
}
NEW_STATUS = {"approve": "approved", "reject": "rejected", "flag": "flagged"}


@router.post("/{violation_id}/review")
async def review_violation(violation_id: str, body: ReviewIn, user: str = Depends(require_admin)):
    db = get_db()
    doc = await db.violations.find_one({"_id": violation_id})
    if not doc:
        raise HTTPException(404, "Violation not found.")
    if doc["status"] not in ALLOWED[body.action]:
        raise HTTPException(409, f"A {doc['status']} violation can't be {NEW_STATUS[body.action]}.")

    now = utcnow()
    update = {
        "status": NEW_STATUS[body.action],
        "review": {"by": user, "action": body.action, "note": body.note.strip(), "at": now},
    }
    if body.action == "approve":
        if not body.citizen_id:
            raise HTTPException(422, "Choose the citizen this violation belongs to before approving.")
        citizen = await db.citizens.find_one({"_id": body.citizen_id})
        if not citizen:
            raise HTTPException(404, "Citizen not found.")
        n = await next_number(db, "challan")
        challan = {
            "_id": new_id(),
            "number": f"CHL-{now.year}-{n:05d}",
            "violation_id": violation_id,
            "violation_code": doc["code"],
            "citizen_id": citizen["_id"],
            "citizen_name": citizen["name"],
            "waste_type": doc["waste_type"],
            "amount": settings.fine_for(doc["waste_type"]),
            "currency": "INR",
            "status": "issued",
            "issued_at": now,
            "due_date": now + timedelta(days=settings.challan_due_days),
            "issued_by": user,
            "simulated": True,
        }
        await db.challans.insert_one(challan)
        update.update({"citizen_id": citizen["_id"], "challan_id": challan["_id"]})

    await db.violations.update_one({"_id": violation_id}, {"$set": update})
    return await get_violation(violation_id, user)
