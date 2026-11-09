# OpenMontage Cloud

This is the additive cloud control plane for OpenMontage. It preserves the existing local agent-first production engine and Backlot.

## Hosted preview\n\n- Studio: https://liiakopnrrseubfglayv.supabase.co/functions/v1/openmontage-studio\n- API: https://liiakopnrrseubfglayv.supabase.co/functions/v1/openmontage-api\n\n## Current status

- Responsive Arabic RTL / English LTR dashboard: implemented.
- Supabase Auth token verification: implemented.
- Owner-scoped projects and durable jobs with RLS: deployed to the linked Supabase project.
- Durable queue: claim leases, heartbeats, retry/cancel RPCs, job events, private artifact metadata: deployed.
- FastAPI project/job API, event history and SSE: implemented.
- Separate worker consumer and Docker deployment: implemented.
- Trusted headless agent-runtime adapter: not yet implemented; worker fails closed until installed.
- Public API/worker hosting and production secrets: not yet configured.
- End-to-end cloud video rendering: not yet available.

## Architecture

| Module | Responsibility |
|---|---|
| Web UI | Sign-in, projects, job status, create-production brief |
| Supabase Auth | Identity and access tokens |
| PostgreSQL + RLS | Owner-scoped projects, jobs, events and artifact metadata |
| Supabase Storage | Private user assets and output objects |
| FastAPI | Auth verification, project/job APIs, SSE |
| Worker | Durable queue consumer with leases and retries |
| Agent-runtime adapter | Connects worker to the existing agent-directed OpenMontage engine |
| Provider adapters | Server-side credentials, quotas, costs and provider calls |

## Development sequence

1. Foundation and read-only API — complete.
2. Responsive RTL/LTR web shell — complete.
3. Supabase Auth and owner-scoped persistence — complete and deployed.
4. Durable queue, worker lifecycle and cancellation — database and consumer implemented.
5. Headless agent-runtime integration — next engineering gate.
6. Private artifact upload/download, provider approvals and budget enforcement — remaining.
7. Public deployment, monitoring, backups and production security review — remaining.

See `LOCAL_DEVELOPMENT.md`, `WORKER.md`, and `DEPLOYMENT.md`.

## Important reality

A free web host does not guarantee persistent background workers, large storage, or GPU rendering. The UI/API and worker are separate services. Video generation may require provider quotas, paid APIs, or user-managed compute. Costs and approvals must be enforced before provider calls.

Never commit `.env`, service-role keys, provider credentials, or user media.
