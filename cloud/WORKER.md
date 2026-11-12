# OpenMontage Cloud Worker

This worker is a durable queue consumer. It is intentionally separate from the
FastAPI process and must run on a persistent CPU/GPU-capable host.

## Required environment

- `SUPABASE_URL`: project URL.
- `SUPABASE_SERVICE_ROLE_KEY`: server-only service-role key. Never put it in the browser, Git, or logs.
- `OPENMONTAGE_EXECUTOR`: trusted adapter in the form
  `cloud_worker_plugins.openmontage:execute` or
  `openmontage_runtime.worker:execute`.
- Optional: `WORKER_ID`, `WORKER_POLL_SECONDS` (default 5),
  `WORKER_LEASE_SECONDS` (default 120), `LOG_LEVEL`.

The executor is installed by the deployment operator and must expose:

```python
def execute(*, job, project, report_progress, stop_event, worker_client) -> dict:
    # Invoke the existing OpenMontage agent/runtime through a reviewed adapter.
    # Use worker_client.upload_artifact(job, local_path, ...) for private outputs.
    # Return JSON-serializable result metadata and artifact references.
    ...
```

Do not import a module path from the job payload. Do not run user shell commands,
Python snippets, or provider calls directly from request data. Provider secrets
belong in the worker's secret manager. The executor must enforce budget approval,
provider allowlists, user quotas, and human review gates before paid calls.

## Run

```bash
python -m cloud.worker
```

The process fails closed before claiming work if the trusted executor is absent.
It uses atomic Postgres claim RPCs, leases, heartbeat, retry classification,
cooperative cancellation, and terminal state updates. Deploy at least one
persistent worker; a free web/API host is not a substitute for this process.

## Current integration boundary

The free adapter `cloud_worker_plugins.openmontage:execute` assembles up to 12
uploaded images/videos plus optional audio into an MP4 with FFmpeg (up to 60
seconds). It does not generate footage from a text prompt and does not invoke a
paid provider. The full agent-directed, headless OpenMontage orchestration
pipeline remains a separate integration task.

## Upload readiness

New Studio clients should create jobs with `defer_queue: true`, upload every
input, then call `POST /api/v1/jobs/{job_id}/complete-uploads`. The API invokes a
scoped database function that verifies all registered objects exist in the
private owner/job prefix and that at least one image or video is present. The
worker claim RPC ignores deferred jobs until this check succeeds. The database
column defaults to `true` only to preserve compatibility with older clients;
new clients must opt into deferred queueing.
