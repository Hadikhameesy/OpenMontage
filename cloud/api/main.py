"""OpenMontage cloud control-plane API."""
from __future__ import annotations

import json
import os
import time
from typing import Any
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

from cloud.api.auth import current_session
from cloud.api.schemas import JobCreate, ProjectCreate
from cloud.api.storage import call_rpc, insert_row, list_rows
from lib.pipeline_loader import list_pipelines, load_pipeline

API_VERSION = "v1"
APP_VERSION = "0.3.0"
app = FastAPI(
    title="OpenMontage Cloud API", version=APP_VERSION,
    description="Authenticated project and durable job-record API for OpenMontage.",
    docs_url="/api/docs", redoc_url=None, openapi_url="/api/openapi.json",
)

_allowed_origins = [
    item.strip() for item in os.getenv(
        "CORS_ALLOW_ORIGINS",
        "http://127.0.0.1:5500,http://localhost:5500,http://127.0.0.1:3000,http://localhost:3000",
    ).split(",") if item.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Last-Event-ID"],
)


def _token(session: dict[str, Any]) -> str:
    return session["access_token"]


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok", "service": "openmontage-cloud-api"}


@app.get("/api/v1/version", tags=["system"])
def version() -> dict[str, str]:
    return {"application": "OpenMontage", "version": APP_VERSION, "api": API_VERSION}


@app.get("/api/v1/pipelines", tags=["catalog"])
def pipelines() -> dict[str, list[dict[str, Any]]]:
    catalog: list[dict[str, Any]] = []
    for name in sorted(list_pipelines()):
        try:
            manifest = load_pipeline(name)
        except Exception:
            catalog.append({"id": name, "available": False, "error": "manifest_invalid"})
            continue
        catalog.append({
            "id": name, "name": manifest.get("name", name),
            "version": str(manifest.get("version", "unknown")),
            "category": manifest.get("category", "unknown"), "available": True,
            "stages": [stage.get("name") for stage in manifest.get("stages", [])],
        })
    return {"items": catalog}


@app.get("/api/v1/projects", tags=["projects"])
def get_projects(session: dict[str, Any] = Depends(current_session)):
    rows = list_rows("projects", _token(session), params={
        "select": "id,name,brief,pipeline_id,aspect_ratio,created_at,updated_at",
        "order": "created_at.desc",
    })
    return {"items": rows}


@app.post("/api/v1/projects", tags=["projects"], status_code=201)
def create_project(payload: ProjectCreate, session: dict[str, Any] = Depends(current_session)):
    if payload.pipeline_id not in list_pipelines():
        raise HTTPException(status_code=422, detail="Unknown pipeline")
    return insert_row("projects", _token(session), {
        "owner_id": session["user"]["id"], "name": payload.name,
        "brief": payload.brief, "pipeline_id": payload.pipeline_id,
        "aspect_ratio": payload.aspect_ratio,
    })


@app.get("/api/v1/jobs", tags=["jobs"])
def get_jobs(session: dict[str, Any] = Depends(current_session)):
    rows = list_rows("jobs", _token(session), params={
        "select": "id,project_id,pipeline_id,status,progress,stage,error_code,created_at,started_at,finished_at",
        "order": "created_at.desc", "limit": "100",
    })
    return {"items": rows}


@app.get("/api/v1/projects/{project_id}/jobs", tags=["jobs"])
def get_project_jobs(project_id: UUID, session: dict[str, Any] = Depends(current_session)):
    rows = list_rows("jobs", _token(session), params={
        "select": "*", "project_id": f"eq.{project_id}", "order": "created_at.desc",
    })
    return {"items": rows}


@app.post("/api/v1/projects/{project_id}/jobs", tags=["jobs"], status_code=202)
def create_job(project_id: UUID, payload: JobCreate, session: dict[str, Any] = Depends(current_session)):
    token = _token(session)
    projects = list_rows("projects", token, params={
        "select": "id,pipeline_id", "id": f"eq.{project_id}", "limit": "1",
    })
    if not projects:
        raise HTTPException(status_code=404, detail="Project not found")
    return insert_row("jobs", token, {
        "owner_id": session["user"]["id"], "project_id": str(project_id),
        "pipeline_id": projects[0]["pipeline_id"], "status": "queued",
        "payload": payload.options,
    })


@app.get("/api/v1/jobs/{job_id}", tags=["jobs"])
def get_job(job_id: UUID, session: dict[str, Any] = Depends(current_session)):
    rows = list_rows("jobs", _token(session), params={
        "select": "*", "id": f"eq.{job_id}", "limit": "1",
    })
    if not rows:
        raise HTTPException(status_code=404, detail="Job not found")
    return rows[0]


@app.get("/api/v1/jobs/{job_id}/events", tags=["jobs"])
def get_job_events(
    job_id: UUID, session: dict[str, Any] = Depends(current_session),
    after: int = 0,
):
    rows = list_rows("job_events", _token(session), params={
        "select": "sequence,event_type,stage,progress,message,data,created_at",
        "job_id": f"eq.{job_id}", "sequence": f"gt.{max(0, after)}",
        "order": "sequence.asc", "limit": "500",
    })
    return {"items": rows}


@app.get("/api/v1/jobs/{job_id}/events/stream", tags=["jobs"])
def stream_job_events(
    job_id: UUID,
    session: dict[str, Any] = Depends(current_session),
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
):
    token = _token(session)
    try:
        cursor = max(0, int(last_event_id or "0"))
    except ValueError:
        cursor = 0

    # Verify ownership before opening a long-lived stream.
    owned = list_rows("jobs", token, params={
        "select": "id", "id": f"eq.{job_id}", "limit": "1",
    })
    if not owned:
        raise HTTPException(status_code=404, detail="Job not found")

    def events():
        nonlocal cursor
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            rows = list_rows("job_events", token, params={
                "select": "sequence,event_type,stage,progress,message,data,created_at",
                "job_id": f"eq.{job_id}", "sequence": f"gt.{cursor}",
                "order": "sequence.asc", "limit": "100",
            })
            for item in rows:
                cursor = max(cursor, int(item["sequence"]))
                yield f"id: {cursor}\nevent: {item['event_type']}\ndata: {json.dumps(item, ensure_ascii=False)}\n\n"
            if not rows:
                yield ": keep-alive\n\n"
            time.sleep(1)
    return StreamingResponse(events(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no",
    })


@app.post("/api/v1/jobs/{job_id}/cancel", tags=["jobs"])
def cancel_job(job_id: UUID, session: dict[str, Any] = Depends(current_session)):
    rows = call_rpc(
        "request_openmontage_job_cancel", _token(session), {"p_job_id": str(job_id)},
    )
    if not rows:
        raise HTTPException(status_code=409, detail="Job is not cancellable or is not accessible")
    return rows[0]


@app.exception_handler(HTTPException)
async def api_http_exception_handler(request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": "http_error", "message": exc.detail}},
        headers=exc.headers,
    )
