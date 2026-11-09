# OpenMontage Web

Responsive Arabic RTL / English LTR dashboard for the cloud control plane.

## Run locally

Start the API from the repository root:

```bash
uvicorn cloud.api.main:app --host 127.0.0.1 --port 8000
```

In another terminal, serve this directory:

```bash
python -m http.server 5500 --directory cloud/web
```

Open `http://127.0.0.1:5500`. The committed `config.js` contains only the public Supabase URL/publishable key and the local API address. For another deployment, update the public API URL and exact CORS origin allowlist.

## Authentication and data

Email/password sign-in uses Supabase Auth. The browser sends its access token to FastAPI. FastAPI validates it against Supabase Auth and forwards that same user token to PostgREST. PostgreSQL Row Level Security scopes projects and jobs to their owner. Job cancellation uses a restricted database RPC; browser users cannot update worker state, progress, leases, or results.

Never place service-role keys or video-provider credentials in browser configuration.

## Database status

The schema is already applied to the linked Supabase project. Migration filenames in this repository match the recorded Supabase migration versions. The dashboard creates a project and a durable queued job record. The job remains queued until the separately deployed worker and trusted agent-runtime adapter are connected; this is not yet a live video-rendering service.

See `cloud/LOCAL_DEVELOPMENT.md`, `cloud/WORKER.md`, and `cloud/DEPLOYMENT.md`.
