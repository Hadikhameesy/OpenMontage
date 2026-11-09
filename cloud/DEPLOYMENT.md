# Deployment runbook

## Local / VPS deployment

1. Copy `.env.example` to `.env` in this directory.
2. Set the Supabase URL, public anon key, and server-only service-role key.
3. Install a reviewed runtime adapter exposing `execute(job, project, report_progress, stop_event)`.
4. Set `OPENMONTAGE_EXECUTOR` to the trusted adapter import path.
5. Set a strong, unique `WORKER_ID`; configure provider secrets only in the host secret manager.
6. Run `docker compose -f cloud/docker-compose.yml up -d --build` from the repository root.
7. Verify `/health`, `/api/docs`, authentication, RLS isolation, queue claim, cancellation, and artifact access before inviting users.

## Public hosting

The API and worker are separate processes. Deploy the API as a Docker web service and the worker as a persistent background service on a host that supports long-running containers. Do not use a serverless request function for the worker. The static UI can be hosted separately; inject `apiBaseUrl`, `supabaseUrl`, and the Supabase publishable/anon key into the public browser config at build time.

## Required before production

- A reviewed agent-runtime adapter: the repository's current pipeline execution is agent-directed and does not yet provide a cloud-safe headless runner.
- A secret manager for `SUPABASE_SERVICE_ROLE_KEY` and provider credentials.
- CORS allowlist and HTTPS reverse proxy for the API.
- SMTP configured in Supabase Auth for production email confirmation/password reset.
- Rate limiting, per-user quotas, upload limits, retention/deletion policy, backups, monitoring, and budget approvals.
- Configure Supabase Storage private bucket and verify policies with two distinct test users.
- Add CI tests for worker lease expiry/retry/cancel and real integration tests against a disposable Supabase project.

Never commit `.env`, service-role keys, provider keys, or user media.
