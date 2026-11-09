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
def execute(*, job, project, report_progress, stop_event) -> dict:
    # Invoke the existing OpenMontage agent/runtime through a reviewed adapter.
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

OpenMontage pipelines are agent-directed: manifests declare stages, tools, and
human gates, but the repository does not yet expose a single cloud-safe
headless orchestration entry point. The adapter is therefore a required
integration boundary, not a fake claim that a queued record already renders
video. Until the adapter is implemented and deployed, the dashboard must show
jobs as queued/waiting for a worker.
