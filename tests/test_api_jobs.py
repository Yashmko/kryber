"""Job API endpoints (§8)."""
from __future__ import annotations

VALID_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


def test_create_job_endpoint(client):
    resp = client.post("/api/jobs", json={"url": VALID_URL})
    assert resp.status_code == 201
    body = resp.json()
    assert body["job_id"].startswith("kr_")
    assert body["status"] == "queued"


def test_create_job_rejects_invalid_url(client):
    resp = client.post("/api/jobs", json={"url": "https://vimeo.com/1"})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "URL_VALIDATION_FAILED"


def test_create_job_rejects_missing_url(client):
    resp = client.post("/api/jobs", json={})
    assert resp.status_code == 422


def test_get_job_status(client):
    job_id = client.post("/api/jobs", json={"url": VALID_URL}).json()["job_id"]
    resp = client.get(f"/api/jobs/{job_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == job_id
    assert body["status"] == "queued"
    assert body["progress"] == 0
    assert body["source_url"] == VALID_URL
    assert body["source_platform"] == "youtube"


def test_get_job_not_found(client):
    resp = client.get("/api/jobs/kr_nope")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "JOB_NOT_FOUND"


def test_create_job_with_clip_length(client):
    resp = client.post("/api/jobs", json={"url": VALID_URL, "clip_length": 45})
    assert resp.status_code == 201
    job_id = resp.json()["job_id"]
    body = client.get(f"/api/jobs/{job_id}").json()
    assert body["clip_length"] == 45


def test_create_job_rejects_invalid_clip_length(client):
    resp = client.post("/api/jobs", json={"url": VALID_URL, "clip_length": 25})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INVALID_CLIP_LENGTH"


def test_get_job_clips_empty_before_render(client):
    job_id = client.post("/api/jobs", json={"url": VALID_URL}).json()["job_id"]
    resp = client.get(f"/api/jobs/{job_id}/clips")
    assert resp.status_code == 200
    assert resp.json() == []


def test_clip_not_found(client):
    resp = client.get("/api/clips/cl_nope")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "CLIP_NOT_FOUND"


def test_healthz(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
