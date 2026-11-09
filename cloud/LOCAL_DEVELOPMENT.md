# Local API development

Run commands from the repository root:

```bash
python -m pip install -r requirements.txt
uvicorn cloud.api.main:app --host 127.0.0.1 --port 8000 --reload
```

## Configure Supabase

1. Create a Supabase project.
2. Apply `supabase/migrations/202611090001_cloud_projects_jobs.sql` with the Supabase CLI or SQL editor.
3. Set server-side `SUPABASE_URL` and `SUPABASE_ANON_KEY` from `cloud/.env.example`.
4. Set browser `apiBaseUrl`, `supabaseUrl`, and the public anon key in `cloud/web/config.js`.
5. Never expose a service-role key. The API validates access tokens through Supabase Auth `/auth/v1/user`, then forwards the caller JWT to PostgREST so database RLS is enforced.

## Authenticated API

- `GET /health`
- `GET /api/v1/version`
- `GET /api/v1/pipelines`
- `GET /api/v1/projects` — Bearer token required
- `POST /api/v1/projects` — Bearer token required
- `GET /api/v1/projects/{project_id}/jobs` — Bearer token required
- `POST /api/v1/projects/{project_id}/jobs` — creates a durable queued record
- `GET /api/v1/jobs/{job_id}` — Bearer token required
- `POST /api/v1/jobs/{job_id}/cancel` — queued jobs only

The migration creates owner-scoped projects/jobs tables and RLS policies. The jobs table is a durable queue record foundation; there is not yet a worker claiming and executing jobs. The UI therefore reports that queued work awaits a worker. Do not claim cloud video rendering is active until the worker and provider adapter milestones are deployed.

Interactive docs: `/api/docs`.
