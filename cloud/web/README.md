# OpenMontage Web

Responsive Arabic RTL / English LTR dashboard for the cloud control plane.

## Run locally

Serve this directory with a static web server:

```bash
python -m http.server 5173 --directory cloud/web
```

Open `http://127.0.0.1:5173`. Copy `config.example.js` to `config.js`, then set the API URL, Supabase project URL, and public anon key. Load `config.js` before `app.js` (already wired in `index.html`).

## Authentication and data

Email/password sign-in uses Supabase Auth. The browser sends its access token to FastAPI. FastAPI validates it against Supabase Auth and forwards that same user token to PostgREST. PostgreSQL Row Level Security policies scope projects and jobs to their owner. Never place service-role keys or video-provider credentials in browser configuration.

Apply `supabase/migrations/202611090001_cloud_projects_jobs.sql` before using project endpoints. The dashboard creates a project and a queued job record. The job remains queued until a separately deployed worker is connected; this version does not yet render video.

See `cloud/LOCAL_DEVELOPMENT.md` for the complete setup and API routes.
