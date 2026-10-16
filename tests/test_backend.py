"""
End-to-end API test with an in-memory database:
detector uploads a violation -> admin reviews -> challan is issued -> paid.
"""
import io
import json
import os

import pytest

os.environ["USE_MOCK_DB"] = "1"
os.environ["DETECTOR_TOKEN"] = "test-detector"
os.environ["ADMIN_PASSWORD"] = "test-pass"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from backend.app import db as dbmod
    from backend.app.settings import settings

    monkeypatch.setattr(settings, "storage_dir", tmp_path)
    monkeypatch.setattr(settings, "detector_token", "test-detector")
    monkeypatch.setattr(settings, "admin_password", "test-pass")
    monkeypatch.setattr(settings, "use_mock_db", True)
    dbmod.reset_client()
    from backend.app.main import app

    with TestClient(app) as c:
        yield c


def login(c):
    r = c.post("/api/auth/login", json={"username": "admin", "password": "test-pass"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}"}


def upload(c, event_id="abc123def456", waste="bottle"):
    meta = {"event_id": event_id, "camera_id": "CAM-01", "location": "Gate 2",
            "waste_type": waste, "confidence": 0.71, "detected_time": 6.2,
            "person_track_id": 3, "object_track_id": 9, "detected_at": 1789000000}
    files = {
        "contact": ("contact.jpg", io.BytesIO(b"\xff\xd8contact"), "image/jpeg"),
        "scene": ("scene.jpg", io.BytesIO(b"\xff\xd8scene"), "image/jpeg"),
        "clip": ("clip.mp4", io.BytesIO(b"fakevideo"), "video/mp4"),
    }
    return c.post("/api/violations", data={"meta": json.dumps(meta)}, files=files,
                  headers={"X-Detector-Token": "test-detector"})


def test_health_and_auth(client):
    assert client.get("/api/health").json()["ok"] is True
    assert client.get("/api/violations").status_code == 401
    bad = client.post("/api/auth/login", json={"username": "admin", "password": "nope"})
    assert bad.status_code == 401
    h = login(client)
    assert client.get("/api/auth/me", headers=h).json()["username"] == "admin"


def test_detector_needs_token(client):
    r = client.post("/api/violations", data={"meta": "{}"},
                    files={"contact": ("a.jpg", b"x"), "scene": ("b.jpg", b"x")})
    assert r.status_code == 401


def test_full_review_flow(client, tmp_path):
    h = login(client)
    r = upload(client)
    assert r.status_code == 201, r.text
    v = r.json()
    assert v["status"] == "pending"
    assert v["code"].startswith("CV-")
    assert (tmp_path / "evidence" / "abc123def456" / "clip.mp4").exists()

    # retry from the detector does not duplicate
    assert upload(client).json()["id"] == v["id"]
    assert client.get("/api/violations", headers=h).json()["total"] == 1

    # evidence is served only with a token
    url = v["evidence_urls"]["contact"]
    assert client.get(url).status_code == 401
    token = h["Authorization"].split()[1]
    assert client.get(f"{url}?token={token}").content == b"\xff\xd8contact"
    assert client.get("/api/media/evidence/../../secret?token=" + token).status_code == 404

    # approve needs a citizen
    r = client.post(f"/api/violations/{v['id']}/review", json={"action": "approve"}, headers=h)
    assert r.status_code == 422

    citizens = client.get("/api/citizens", headers=h).json()["items"]
    assert len(citizens) == 30
    cid = citizens[0]["id"]

    r = client.post(f"/api/violations/{v['id']}/review", json={"action": "flag", "note": "blurry"}, headers=h)
    assert r.json()["status"] == "flagged"

    r = client.post(f"/api/violations/{v['id']}/review",
                    json={"action": "approve", "citizen_id": cid, "note": "clear"}, headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "approved"
    assert body["challan"]["amount"] == 500
    assert body["citizen"]["id"] == cid

    # cannot review twice
    r = client.post(f"/api/violations/{v['id']}/review", json={"action": "reject"}, headers=h)
    assert r.status_code == 409

    challan_id = body["challan"]["id"]
    r = client.patch(f"/api/challans/{challan_id}", json={"status": "paid"}, headers=h)
    assert r.json()["status"] == "paid"
    assert client.patch(f"/api/challans/{challan_id}", json={"status": "cancelled"}, headers=h).status_code == 409

    detail = client.get(f"/api/citizens/{cid}", headers=h).json()
    assert len(detail["violations"]) == 1 and len(detail["challans"]) == 1

    s = client.get("/api/stats", headers=h).json()
    assert s["total"] == 1
    assert s["by_status"]["approved"] == 1
    assert s["fines"]["paid_amount"] == 500


def test_reject_and_filters(client):
    h = login(client)
    a = upload(client, "aaa111", "wrapper").json()
    upload(client, "bbb222", "can")
    client.post(f"/api/violations/{a['id']}/review", json={"action": "reject", "note": "shadow"}, headers=h)
    assert client.get("/api/violations?status=pending", headers=h).json()["total"] == 1
    assert client.get("/api/violations?status=rejected", headers=h).json()["items"][0]["waste_type"] == "wrapper"
    assert client.get("/api/violations?waste_type=can", headers=h).json()["total"] == 1
    assert client.get("/api/citizens?q=SIM-0001", headers=h).json()["items"][0]["citizen_ref"] == "SIM-0001"


def test_job_upload_validation_and_progress(client, monkeypatch):
    from backend.app.jobs_runner import runner

    async def no_kick(db):
        return None
    monkeypatch.setattr(runner, "kick", no_kick)
    h = login(client)
    bad = client.post("/api/jobs", files={"video": ("notes.txt", b"hello")}, headers=h)
    assert bad.status_code == 422
    r = client.post("/api/jobs", files={"video": ("demo clip.mp4", b"00")},
                    data={"camera_id": "CAM-9", "location": "Lab"}, headers=h)
    assert r.status_code == 201
    job = r.json()
    assert job["status"] == "queued" and job["camera_id"] == "CAM-9"
    r = client.patch(f"/api/jobs/{job['id']}", json={"status": "running", "progress": 0.5},
                     headers={"X-Detector-Token": "test-detector"})
    assert r.json()["progress"] == 0.5
    r = client.patch(f"/api/jobs/{job['id']}", json={"status": "completed", "progress": 1},
                     headers={"X-Detector-Token": "test-detector"})
    assert r.json()["finished_at"]
    assert client.get("/api/jobs", headers=h).json()["items"][0]["status"] == "completed"
