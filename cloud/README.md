# OpenMontage Cloud Foundation

This directory is the starting point for the optional cloud/web control plane. It is deliberately additive: the existing agent-first production engine, local CLI, tools, pipelines, and Backlot remain intact.

## Current status

This is an additive cloud control plane. The web dashboard, Supabase Auth token verification, owner-scoped project/job persistence contracts, and initial durable queued-job records are now implemented. A separate worker still needs to claim and execute queued jobs; cloud video rendering is not yet available.

## Design goals

- Web-first, responsive interface with Arabic RTL and English LTR support.
- Modular services with explicit contracts.
- Keep the existing OpenMontage engine as the production capability layer.
- Support local development and cloud deployment from the same codebase.
- Free-tier-friendly control plane; heavy rendering and AI generation remain optional workers.
- No provider API keys in browser code. Secrets are server-side only.
- Jobs must be durable, observable, cancellable where safe, and resumable after worker restarts.

## Proposed modules

| Module | Responsibility |
|---|---|
| Web UI | Sign-in, projects, create-production brief, progress, approvals, deliverables |
| API | Authentication, project/job APIs, validation, capability discovery |
| Queue | Durable job dispatch and retry policy |
| Worker | Executes approved OpenMontage pipeline stages |
| Storage | Project metadata, checkpoints, artifacts, renders |
| Events | Progress/activity stream to the browser |
| Provider adapters | Server-side credentials, quotas, cost estimates, provider calls |

## Development sequence

1. **Foundation** — document contracts, threat model, environment configuration, and service boundaries.
2. **Read-only API and web shell** — health/version/catalog plus responsive RTL/LTR dashboard (implemented).
3. **Auth and persistence foundation** — Supabase Auth token verification, owner-scoped project/job tables with RLS, and protected project/job-record endpoints (implemented; requires applying the migration and configuring Supabase).
4. **Queue and worker** — atomically claim queued jobs, leases/heartbeats, retry/cancel/checkpoint behavior, and safe pipeline execution (next milestone).
5. **Artifacts and events** — private object storage and authenticated progress streaming.
6. **Provider adapters** — server-side credentials, quotas, explicit cost approvals, and provider integration.
7. **Deployment** — deploy the lightweight web/API separately from workers; document free-tier limits and paid-resource escape hatches.

## Important deployment reality

A free web host can often serve a small UI/API, but it cannot promise unlimited CPU time, persistent background workers, large file storage, or GPU inference. AI image/video generation usually depends on a provider's free quota, paid API, or user-managed local hardware. The platform must display estimated costs and resource requirements before starting consequential work.

## Existing local mode

The existing local OpenMontage workflow remains the reference implementation. Backlot is currently a local, read-only storyboard bound to local project files; it must not be exposed publicly as-is. The cloud control plane will use authenticated APIs and explicit storage adapters rather than opening local project folders to the internet.

## Security baseline

- Never commit .env files, tokens, provider keys, or user media.
- Validate every upload by size, type, and ownership; store outside the web root.
- Authenticate and authorize every project/job/artifact request.
- Use signed, short-lived artifact URLs where object storage supports them.
- Apply per-user quotas, request limits, and job concurrency limits.
- Treat prompts, uploaded files, provider responses, and generated metadata as untrusted data.
- Keep an append-only audit trail for approvals, provider choices, cost reservations, and job state changes.
- Do not execute user-supplied shell commands or arbitrary Python from API requests.

## Local development (planned)

The first API milestone will add a dedicated ASGI application under `cloud/api/`. It will be launched separately from Backlot so local-only protections and cloud-facing security boundaries remain explicit.
