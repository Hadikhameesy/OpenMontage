# Cloud Architecture Decision Record

**Status:** Proposed foundation  
**Scope:** Optional hosted web control plane for OpenMontage  
**Compatibility rule:** Existing local agent-first workflow remains supported and unchanged.

## 1. Architectural decision

Build a modular control plane around the existing engine rather than converting the engine into a monolithic web application.

The current project is agent-orchestrated: an assistant reads pipeline manifests and stage-director skills, invokes registered tools, reviews outputs, and writes checkpoints. Python supplies tools and persistence; it is not currently a general-purpose cloud job orchestrator.

The hosted product therefore introduces an explicit orchestration boundary. It must not assume that the local coding assistant exists in a cloud request.

## 2. Target topology

```text
Browser
  |
  | HTTPS / authenticated session
  v
Web UI  <------>  API service
                       |
             +---------+----------+
             |                    |
         Database             Object storage
             |
         Job records
             |
       Durable queue
             |
        Worker pool
             |
      OpenMontage adapter
             |
   Existing pipeline/tool registry
             |
  Checkpoints, events, artifacts, renders
             |
        Event gateway (SSE)
             |
          Browser
```

The UI/API and worker pool are separate deployable processes. The worker is the only service allowed to execute production tools.

## 3. Service contracts

### API

Initial read-only endpoints:

- `GET /health` — process health, no secrets or environment dump.
- `GET /api/v1/version` — application and API contract version.
- `GET /api/v1/pipelines` — validated pipeline catalog.
- `GET /api/v1/capabilities` — discovered tool capabilities, with secret values omitted.

Later authenticated endpoints:

- `POST /api/v1/projects`
- `GET /api/v1/projects`
- `GET /api/v1/projects/{project_id}`
- `POST /api/v1/projects/{project_id}/jobs`
- `GET /api/v1/jobs/{job_id}`
- `POST /api/v1/jobs/{job_id}/cancel`
- `POST /api/v1/jobs/{job_id}/approvals`
- `GET /api/v1/jobs/{job_id}/events` (SSE)

All write endpoints require authentication, ownership checks, schema validation, idempotency where retries can duplicate work, and audit events.

### Queue and worker

A job is a durable request, not an in-memory background task. Minimum job fields:

- `id`, `owner_id`, `project_id`, `pipeline_id`
- validated brief and approved execution options
- `status`, `stage`, `progress`, `attempt`
- cost estimate, reserved amount, reconciled spend
- created/started/finished timestamps
- cancellation request and safe checkpoint reference

Worker rules:

1. Claim jobs with a lease/heartbeat.
2. Revalidate ownership, pipeline, inputs, budget, and provider availability.
3. Never start paid or consequential generation before explicit approval.
4. Persist checkpoint and event after each stage transition.
5. Retry only transient failures and only when the stage is safe to retry.
6. Reconcile actual provider cost and release unused reservations.
7. On worker loss, recover from the last valid checkpoint; never silently restart a paid stage.

### Storage

- Relational database: users, sessions, projects, jobs, approvals, audit events, provider usage.
- Object storage: uploads, generated assets, previews, renders, export bundles.
- Checkpoint adapter: preserve the existing checkpoint schema where possible.
- Local filesystem adapter: development only; never assume local disk is durable in hosted environments.

### Event model

Events are append-only and include a monotonically increasing sequence:

`job.queued`, `job.started`, `stage.started`, `stage.progress`, `approval.required`, `stage.completed`, `job.completed`, `job.failed`, `job.cancelled`.

SSE reconnects must support a last-event cursor. Event payloads must not expose credentials, signed storage secrets, or internal exception traces.

## 4. Web application

The browser UI is a separate presentation layer. It must not import Python modules, provider SDKs, or secrets.

Primary screens:

- Dashboard / project library
- New production brief
- Pipeline and output format selection
- Cost and provider approval
- Live production board
- Review and approval gates
- Deliverables and export history
- Account, usage, and provider settings

Internationalization is built in from the start: Arabic RTL and English LTR. User-entered Arabic text and filenames must be preserved without lossy normalization.

## 5. Backlot integration

Backlot is documented as a local, read-only board that binds to local project files and localhost. It is not a public cloud API.

Cloud integration should reuse its visual concepts and event vocabulary, not expose its local server or filesystem watcher to the public internet. A future adapter may translate cloud job/project records into a board-compatible read model.

## 6. Security and trust boundaries

- Browser: untrusted; no provider credentials.
- API: authenticated boundary; validates all input and ownership.
- Queue: contains identifiers and validated payload references, not raw secrets.
- Worker: isolated execution boundary; least-privilege filesystem and network access.
- Providers: external processors; enforce data disclosure and cost policy.
- Object storage: private by default; access via short-lived signed URLs.
- User uploads and generated files: untrusted; never execute as code.

Required controls before public beta: secure cookies, CSRF protection for cookie sessions, CORS allowlist, rate limits, upload limits, per-user quotas, secret manager/environment injection, dependency scanning, audit logging, and deletion/retention policy.

## 7. Free-tier deployment strategy

Keep the UI and lightweight API deployable on free tiers where available. Do not promise free continuous workers or GPU rendering. Worker deployment is an independent option and may run on a user's own machine, a self-hosted server, or a paid compute provider.

A practical hybrid mode is acceptable: hosted UI/API + user-owned worker that securely polls for assigned jobs. This keeps expensive rendering off the free web tier while preserving a browser-based experience.

## 8. Rollout gates

| Gate | Deliverable | Exit criteria |
|---|---|---|
| 0 | Architecture and security boundary | Existing local mode unchanged |
| 1 | Read-only API | Health/version/catalog tests pass |
| 2 | Web shell | RTL/LTR responsive UI, no secrets in client |
| 3 | Auth and persistence | Isolation tests pass across users |
| 4 | Queue and worker | Lease, retry, cancel, checkpoint recovery tests |
| 5 | Events and artifacts | Authenticated SSE and private artifact access |
| 6 | Deployment | Reproducible deploy docs, quotas, rollback plan |

No gate is considered complete solely because a service starts; automated tests and documented operational behavior are required.
