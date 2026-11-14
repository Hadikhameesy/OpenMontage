"""Durable OpenMontage cloud worker.

The worker only runs a trusted executor installed with the deployment.
It never evaluates user-provided code, shell commands, or module names.
"""
from __future__ import annotations

import importlib
import logging
import os
import signal
import socket
import threading
import time
import uuid
from typing import Any, Callable

import requests

LOG = logging.getLogger("openmontage.worker")
STOP = threading.Event()


class WorkerError(RuntimeError):
    pass


class SupabaseWorkerClient:
    def __init__(self) -> None:
        self.url = os.environ["SUPABASE_URL"].rstrip("/")
        self.key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
        self.http = requests.Session()
        self.http.headers.update({
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
        })

    def request(self, method: str, path: str, *, params=None, body=None):
        response = self.http.request(
            method, f"{self.url}/rest/v1/{path.lstrip('/')}",
            params=params, json=body, timeout=20,
        )
        if response.status_code >= 400:
            raise WorkerError(f"Supabase request failed ({response.status_code})")
        return response.json() if response.content else None

    def rpc(self, name: str, body: dict[str, Any]):
        return self.request("POST", f"rpc/{name}", body=body)

    def claim(self, worker_id: str, lease_seconds: int):
        rows = self.rpc("claim_openmontage_job", {
            "p_worker_id": worker_id, "p_lease_seconds": lease_seconds,
        })
        return rows[0] if isinstance(rows, list) and rows else None

    def project(self, project_id: str):
        rows = self.request("GET", "projects", params={
            "id": f"eq.{project_id}", "select": "id,owner_id,name,brief,pipeline_id,aspect_ratio", "limit": "1",
        })
        if not rows:
            raise WorkerError("project_not_found")
        return rows[0]

    def job(self, job_id: str):
        rows = self.request("GET", "jobs", params={
            "id": f"eq.{job_id}", "select": "id,status,cancel_requested_at,lease_token", "limit": "1",
        })
        return rows[0] if rows else None

    def input_artifacts(self, job: dict):
        return self.request("GET", "job_artifacts", params={
            "job_id": f"eq.{job['id']}", "artifact_type": "eq.input",
            "select": "id,bucket_id,object_path,content_type,size_bytes,created_at",
            "order": "created_at.asc", "limit": "12",
        }) or []

    def download_artifact(self, artifact: dict, destination: str):
        from pathlib import Path
        from urllib.parse import quote
        path = Path(destination)
        path.parent.mkdir(parents=True, exist_ok=True)
        bucket = artifact.get("bucket_id") or "openmontage-private"
        object_path = quote(str(artifact["object_path"]), safe="/")
        url = f"{self.url}/storage/v1/object/{bucket}/{object_path}"
        total = 0
        with self.http.get(url, stream=True, timeout=(15, 180)) as response:
            if response.status_code >= 400:
                raise WorkerError(f"Input download failed ({response.status_code})")
            with path.open("wb") as stream:
                for chunk in response.iter_content(chunk_size=1 << 16):
                    if not chunk:
                        continue
                    total += len(chunk)
                    if total > 268435456:
                        raise WorkerError("input_file_too_large")
                    stream.write(chunk)
        if total < 1:
            raise WorkerError("input_file_empty")
        return path

    def heartbeat(self, job: dict, progress: int, stage: str, message: str):
        return self.rpc("heartbeat_openmontage_job", {
            "p_job_id": job["id"], "p_lease_token": job["lease_token"],
            "p_lease_seconds": int(os.getenv("WORKER_LEASE_SECONDS", "120")),
            "p_progress": progress, "p_stage": stage, "p_message": message[:500],
        })

    def finish(self, job: dict, result: dict):
        return self.rpc("finish_openmontage_job", {
            "p_job_id": job["id"], "p_lease_token": job["lease_token"], "p_result": result,
        })

    def fail(self, job: dict, code: str, retryable: bool):
        return self.rpc("fail_openmontage_job", {
            "p_job_id": job["id"], "p_lease_token": job["lease_token"],
            "p_error_code": code[:100], "p_retryable": retryable,
        })

    def cancel(self, job: dict):
        return self.rpc("cancel_openmontage_job", {
            "p_job_id": job["id"], "p_lease_token": job["lease_token"],
        })

    def upload_artifact(self, job: dict, local_path: str, *, artifact_type: str = "output",
                        content_type: str = "application/octet-stream") -> dict[str, Any]:
        """Upload a trusted worker output to the user's private object prefix."""
        from pathlib import Path
        path = Path(local_path)
        if not path.is_file():
            raise WorkerError("artifact_file_not_found")
        size = path.stat().st_size
        if size < 1 or size > 1073741824:
            raise WorkerError("artifact_size_out_of_range")
        safe_name = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in path.name)[:120]
        object_path = f"{job['owner_id']}/{job['id']}/{uuid.uuid4().hex}-{safe_name}"
        url = f"{self.url}/storage/v1/object/openmontage-private/{object_path}"
        with path.open("rb") as stream:
            response = self.http.post(
                url, data=stream,
                headers={"Content-Type": content_type, "x-upsert": "false"},
                timeout=(15, 300),
            )
        if response.status_code >= 400:
            raise WorkerError(f"Storage upload failed ({response.status_code})")
        metadata = {
            "job_id": job["id"], "owner_id": job["owner_id"],
            "bucket_id": "openmontage-private", "object_path": object_path,
            "artifact_type": artifact_type, "content_type": content_type,
            "size_bytes": size,
        }
        self.request("POST", "job_artifacts", body=metadata)
        return metadata


def load_executor() -> Callable:
    """Load only a deployment-configured, trusted Python executor."""
    target = os.getenv("OPENMONTAGE_EXECUTOR", "").strip()
    if not target or ":" not in target:
        raise WorkerError(
            "OPENMONTAGE_EXECUTOR is not configured. Install the trusted "
            "OpenMontage agent-runtime adapter before enabling job execution."
        )
    module_name, function_name = target.rsplit(":", 1)
    if not module_name.startswith(("cloud_worker_plugins.", "openmontage_runtime.")):
        raise WorkerError("Executor must be inside cloud_worker_plugins or openmontage_runtime")
    function = getattr(importlib.import_module(module_name), function_name, None)
    if not callable(function):
        raise WorkerError("Configured executor is not callable")
    return function


def process_one(client: SupabaseWorkerClient, executor: Callable, worker_id: str) -> bool:
    lease = int(os.getenv("WORKER_LEASE_SECONDS", "120"))
    job = client.claim(worker_id, lease)
    if not job:
        return False

    stop_heartbeat = threading.Event()
    heartbeat_error: list[BaseException] = []
    progress_state = {"progress": 1, "stage": "starting"}

    def report(progress: int, stage: str, message: str = "") -> None:
        current = client.job(job["id"])
        if not current or current["status"] == "cancel_requested":
            raise InterruptedError("job_cancel_requested")
        result = client.heartbeat(job, progress, stage, message)
        if result is False:
            raise InterruptedError("job_lease_lost")
        progress_state["progress"] = max(0, min(99, int(progress)))
        progress_state["stage"] = str(stage)[:100]

    def beat() -> None:
        interval = max(10, lease // 3)
        while not stop_heartbeat.wait(interval):
            try:
                current = client.job(job["id"])
                if not current or current["status"] == "cancel_requested":
                    return
                result = client.heartbeat(job, progress_state["progress"],
                                          progress_state["stage"], "Worker heartbeat")
                if result is False:
                    heartbeat_error.append(WorkerError("job_lease_lost"))
                    return
            except BaseException as exc:
                heartbeat_error.append(exc)
                return

    thread = threading.Thread(target=beat, name=f"heartbeat-{job['id']}", daemon=True)
    thread.start()
    try:
        project = client.project(job["project_id"])
        report(1, "starting", "Worker accepted job")
        # The executor is trusted deployment code, never data supplied by a user.
        result = executor(job=job, project=project, report_progress=report, stop_event=STOP, worker_client=client)
        if heartbeat_error:
            raise WorkerError("heartbeat_failed")
        current = client.job(job["id"])
        if current and current["status"] == "cancel_requested":
            client.cancel(job)
        else:
            client.finish(job, result if isinstance(result, dict) else {"output": result})
    except InterruptedError:
        client.cancel(job)
    except Exception as exc:
        LOG.exception("Job %s failed", job.get("id"))
        retryable = not isinstance(exc, (ValueError, PermissionError, FileNotFoundError))
        client.fail(job, type(exc).__name__.lower(), retryable)
    finally:
        stop_heartbeat.set()
        thread.join(timeout=2)
    return True


def run_worker_loop(
    client: SupabaseWorkerClient,
    executor: Callable,
    worker_id: str,
    *,
    poll_seconds: int = 5,
    max_jobs: int = 0,
    max_idle_polls: int = 0,
    stop_event: threading.Event = STOP,
) -> int:
    """Run jobs until stopped; optionally exit after consecutive empty queue polls."""
    processed = 0
    idle_polls = 0
    while not stop_event.is_set():
        try:
            if process_one(client, executor, worker_id):
                processed += 1
                idle_polls = 0
                if max_jobs and processed >= max_jobs:
                    break
            else:
                idle_polls += 1
                if max_idle_polls and idle_polls >= max_idle_polls:
                    break
                stop_event.wait(poll_seconds)
        except Exception:
            LOG.exception("Worker loop error")
            stop_event.wait(min(30, max(1, poll_seconds * 2)))
    return processed


def main() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    client = SupabaseWorkerClient()
    executor = load_executor()  # Fail closed before claiming any job.
    worker_id = os.getenv("WORKER_ID") or f"{socket.gethostname()}-{os.getpid()}"
    poll = max(1, int(os.getenv("WORKER_POLL_SECONDS", "5")))
    signal.signal(signal.SIGTERM, lambda *_: STOP.set())
    signal.signal(signal.SIGINT, lambda *_: STOP.set())
    max_jobs = max(0, int(os.getenv("WORKER_MAX_JOBS", "0")))
    max_idle_polls = max(0, int(os.getenv("WORKER_MAX_IDLE_POLLS", "0")))
    LOG.info("Worker %s started", worker_id)
    processed = run_worker_loop(
        client, executor, worker_id, poll_seconds=poll,
        max_jobs=max_jobs, max_idle_polls=max_idle_polls,
    )
    LOG.info("Worker %s stopped after %s jobs", worker_id, processed)


if __name__ == "__main__":
    main()
