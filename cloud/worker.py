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

    def report(progress: int, stage: str, message: str = "") -> None:
        current = client.job(job["id"])
        if not current or current["status"] == "cancel_requested":
            raise InterruptedError("job_cancel_requested")
        result = client.heartbeat(job, progress, stage, message)
        if result is False:
            raise InterruptedError("job_lease_lost")

    def beat() -> None:
        interval = max(10, lease // 3)
        while not stop_heartbeat.wait(interval):
            try:
                current = client.job(job["id"])
                if not current or current["status"] == "cancel_requested":
                    return
                result = client.heartbeat(job, int(job.get("progress") or 0),
                                          str(job.get("stage") or "working"), "Worker heartbeat")
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
        result = executor(job=job, project=project, report_progress=report, stop_event=STOP)
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
    LOG.info("Worker %s started", worker_id)
    while not STOP.is_set():
        try:
            if not process_one(client, executor, worker_id):
                STOP.wait(poll)
        except Exception:
            LOG.exception("Worker loop error")
            STOP.wait(min(30, poll * 2))
    LOG.info("Worker %s stopped", worker_id)


if __name__ == "__main__":
    main()
