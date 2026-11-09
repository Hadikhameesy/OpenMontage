"""Contract tests for public and authenticated cloud API routes."""
from uuid import UUID
from fastapi.testclient import TestClient

from cloud.api.main import app
from cloud.api.auth import current_session

client = TestClient(app)


def test_health_does_not_expose_environment():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "openmontage-cloud-api"}


def test_version_contract():
    response = client.get("/api/v1/version")
    assert response.status_code == 200
    payload = response.json()
    assert payload["application"] == "OpenMontage"
    assert payload["api"] == "v1"
    assert payload["version"]


def test_pipeline_catalog_is_read_only_and_well_shaped():
    response = client.get("/api/v1/pipelines")
    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload["items"], list)
    assert payload["items"]
    for item in payload["items"]:
        assert {"id", "available"} <= item.keys()
        if item["available"]:
            assert {"name", "version", "category", "stages"} <= item.keys()


def test_projects_require_authentication():
    response = client.get("/api/v1/projects")
    assert response.status_code == 401


def test_project_and_job_lifecycle_contract(monkeypatch):
    from cloud.api import main

    user_id = "11111111-1111-4111-8111-111111111111"
    project_id = "22222222-2222-4222-8222-222222222222"
    job_id = "33333333-3333-4333-8333-333333333333"
    app.dependency_overrides[current_session] = lambda: {
        "user": {"id": user_id}, "access_token": "verified-test-token"
    }
    monkeypatch.setattr(main, "list_pipelines", lambda: ["demo"])
    monkeypatch.setattr(main, "insert_row", lambda table, token, values: (
        {"id": project_id, **values} if table == "projects"
        else {"id": job_id, **values}
    ))
    monkeypatch.setattr(main, "list_rows", lambda table, token, params: (
        [{"id": project_id, "pipeline_id": "demo"}] if table == "projects"
        else [{"id": job_id, "status": "queued"}]
    ))
    monkeypatch.setattr(main, "update_rows", lambda table, token, params, values: [
        {"id": job_id, **values}
    ])

    try:
        created = client.post("/api/v1/projects", json={
            "name": "Demo", "brief": "A short demo", "pipeline_id": "demo",
            "aspect_ratio": "16:9"
        })
        assert created.status_code == 201
        assert created.json()["owner_id"] == user_id

        queued = client.post(f"/api/v1/projects/{project_id}/jobs", json={"options": {}})
        assert queued.status_code == 202
        assert queued.json()["status"] == "queued"

        cancelled = client.post(f"/api/v1/jobs/{job_id}/cancel")
        assert cancelled.status_code == 200
        assert cancelled.json()["status"] == "cancelled"
    finally:
        app.dependency_overrides.clear()
