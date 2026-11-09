"""Contract tests for the read-only cloud API foundation."""
from fastapi.testclient import TestClient

from cloud.api.main import app

client = TestClient(app)


def test_health_does_not_expose_environment():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "openmontage-cloud-api",
    }


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
