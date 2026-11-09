# Local cloud development

Run commands from the repository root:

```bash
python -m pip install -r requirements.txt
uvicorn cloud.api.main:app --host 127.0.0.1 --port 8000 --reload
```

In a second terminal:

```bash
python -m http.server 5500 --directory cloud/web
```

Open `http://127.0.0.1:5500`. The browser config is `cloud/web/config.js`; it contains only the public Supabase publishable key. Set the server-side variables in `cloud/.env` and load them before starting FastAPI.

## Supabase

The linked OpenMontage project already has the schema migrations applied. The migration files use the exact versions recorded in Supabase migration history. For a different project, link that project and apply the ordered files in `supabase/migrations/`.

Required API environment:
- `SUPABASE_URL`
- `SUPABASE_ANON_KEY` (publishable/legacy anon key)
- `CORS_ALLOW_ORIGINS` (exact static-site origins)

Never configure a service-role key in the API browser config. The worker alone requires `SUPABASE_SERVICE_ROLE_KEY`.

## API

- `GET /health`
- `GET /api/v1/version`
- `GET /api/v1/pipelines`
- `GET /api/v1/projects` — Bearer token required
- `POST /api/v1/projects` — Bearer token required
- `GET /api/v1/jobs` — Bearer token required
- `GET /api/v1/projects/{project_id}/jobs`
- `POST /api/v1/projects/{project_id}/jobs`
- `GET /api/v1/jobs/{job_id}`
- `GET /api/v1/jobs/{job_id}/events`
- `GET /api/v1/jobs/{job_id}/events/stream` — short-lived SSE stream
- `POST /api/v1/jobs/{job_id}/cancel`

Interactive docs: `/api/docs`.

## Execution status

Project and durable queue records are operational in Supabase. A worker queue consumer is implemented in `cloud/worker.py`; it requires a reviewed trusted agent-runtime adapter before it will claim jobs. The current repository is agent-directed and does not yet expose a single cloud-safe headless production entry point. Do not claim video rendering is active until that adapter is implemented, configured, and integration-tested.
