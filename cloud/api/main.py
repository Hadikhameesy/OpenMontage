"""Minimal read-only ASGI API for the OpenMontage cloud foundation.

Run from the repository root:
    uvicorn cloud.api.main:app --host 127.0.0.1 --port 8000

This service intentionally does not execute production tools or expose the
local Backlot server. Authentication and persistent job execution are later
milestones; do not expose write operations until those controls exist.
"""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from lib.pipeline_loader import list_pipelines, load_pipeline

API_VERSION = "v1"
APP_VERSION = "0.1.0"

app = FastAPI(
    title="OpenMontage Cloud API",
    version=APP_VERSION,
    description="Read-only foundation API for the optional OpenMontage web control plane.",
    docs_url="/api/docs",
    redoc_url=None,
    openapi_url="/api/openapi.json",
)


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    """Return process health without exposing configuration or secrets."""
    return {"status": "ok", "service": "openmontage-cloud-api"}


@app.get("/api/v1/version", tags=["system"])
def version() -> dict[str, str]:
    return {"application": "OpenMontage", "version": APP_VERSION, "api": API_VERSION}


@app.get("/api/v1/pipelines", tags=["catalog"])
def pipelines() -> dict[str, list[dict[str, Any]]]:
    """Return validated pipeline metadata; never execute pipeline stages."""
    catalog: list[dict[str, Any]] = []
    for name in sorted(list_pipelines()):
        try:
            manifest = load_pipeline(name)
        except Exception as exc:
            # Keep the catalog available while making invalid manifests visible
            # without returning internal paths or exception details.
            catalog.append({"id": name, "available": False, "error": "manifest_invalid"})
            continue
        catalog.append(
            {
                "id": name,
                "name": manifest.get("name", name),
                "version": str(manifest.get("version", "unknown")),
                "category": manifest.get("category", "unknown"),
                "available": True,
                "stages": [stage.get("name") for stage in manifest.get("stages", [])],
            }
        )
    return {"items": catalog}


@app.exception_handler(HTTPException)
async def api_http_exception_handler(request, exc: HTTPException):
    """Keep API errors in a predictable JSON shape."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": "http_error", "message": exc.detail}},
        headers=exc.headers,
    )
