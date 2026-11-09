"""OpenMontage cloud control-plane API.

Run from the repository root with:
    uvicorn cloud.api.main:app --host 127.0.0.1 --port 8000

Project and job data access always forwards the verified caller JWT to
Supabase PostgREST, leaving row ownership enforcement to PostgreSQL RLS.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import JSONResponse

from cloud.api.auth import current_session
from cloud.api.schemas import JobCreate, ProjectCreate
from cloud.api.storage import insert_row, list_rows, update_rows
from lib.pipeline_loader import list_pipelines, load_pipeline

API_VERSION = "v1"
APP_VERSION = "0.2.0"

app = FastAPI(
    title="OpenMontage Cloud API",
    version=APP_VERSION,
    description="Authenticated project and durable job-record API for OpenMontage.",
    docs_url="/api/docs",
    redoc_url=None,
    openapi_url="/api/openapi.json",
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
            "id": name,
            "name": manifest.get("name", name),
            "version": str(manifest.get("version", "unknown")),
            "category": manifest.get("category", "unknown"),
            "available": True,
            "stages": [stage.get("name") for stage in manifest.get("stages", [])],
        })
    return {"items": catalog}


@app.get("/api/v1/projects", tags=["projects"])
def get_projects(session: dict[str, Any] = Depends(current_session)):
    rows = list_rows(
        "projects", _token(session),
        params={"select": "id,name,brief,pipeline_id,aspect_ratio,created_at,updated_at",
                "order": "created_at.desc"},
    )
    return {"items": rows}


@app.post("/api/v1/projects", tags=["projects"], status_code=201)
def create_project(payload: ProjectCreate, session: dict[str, Any] = Depends(current_session)):
    if payload.pipeline_id not in list_pipelines():
        raise HTTPException(status_code=422, detail="Unknown pipeline")
    row = insert_row("projects", _token(session), {
        "owner_id": session["user"]["id"],
        "name": payload.name,
        "brief": payload.brief,
        "pipeline_id": payload.pipeline_id,
        "aspect_ratio": payload.aspect_ratio,
    })
    return row


@app.get("/api/v1/projects/{project_id}/jobs", tags=["jobs"])
def get_project_jobs(project_id: UUID, session: dict[str, Any] = Depends(current_session)):
    rows = list_rows(
        "jobs", _token(session),
        params={"select": "*", "project_id": f"eq.{project_id}", "order": "created_at.desc"},
    )
    return {"items": rows}


@app.post("/api/v1/projects/{project_id}/jobs", tags=["jobs"], status_code=202)
def create_job(project_id: UUID, payload: JobCreate, session: dict[str, Any] = Depends(current_session)):
    token = _token(session)
    projects = list_rows(
        "projects", token,
        params={"select": "id,pipeline_id", "id": f"eq.{project_id}", "limit": "1"},
    )
    if not projects:
        raise HTTPException(status_code=404, detail="Project not found")
    project = projects[0]
    row = insert_row("jobs", token, {
        "owner_id": session["user"]["id"],
        "project_id": str(project_id),
        "pipeline_id": project["pipeline_id"],
        "status": "queued",
        "payload": payload.options,
    })
    return row


@app.get("/api/v1/jobs/{job_id}", tags=["jobs"])
def get_job(job_id: UUID, session: dict[str, Any] = Depends(current_session)):
    rows = list_rows(
        "jobs", _token(session),
        params={"select": "*", "id": f"eq.{job_id}", "limit": "1"},
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Job not found")
    return rows[0]


@app.post("/api/v1/jobs/{job_id}/cancel", tags=["jobs"])
def cancel_job(job_id: UUID, session: dict[str, Any] = Depends(current_session)):
    rows = update_rows(
        "jobs", _token(session),
        params={"id": f"eq.{job_id}", "status": "eq.queued"},
        values={"status": "cancelled"},
    )
    if not rows:
        raise HTTPException(status_code=409, detail="Job is not queued or is not accessible")
    return rows[0]


@app.exception_handler(HTTPException)
async def api_http_exception_handler(request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": "http_error", "message": exc.detail}},
        headers=exc.headers,
    )
