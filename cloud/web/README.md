# OpenMontage Web

A responsive Arabic RTL / English LTR dashboard shell for the optional cloud control plane.

## Run locally

Serve this directory with any static web server (do not open index.html as a file):

```bash
python -m http.server 5173 --directory cloud/web
```

Open `http://127.0.0.1:5173`.

Copy `config.example.js` to `config.js`, include it before `app.js` in `index.html`, and set the API URL. To enable email/password sign-in, configure a Supabase project URL and its public anon key. The anon key is designed for browser use; protect every database table with row-level security. Never put service-role keys or video-provider credentials in the browser.

## Current integration boundary

The dashboard calls:
- `GET /health`
- `GET /api/v1/pipelines`
- `GET /api/v1/projects`
- `POST /api/v1/projects`

The first two endpoints exist in the API foundation. Project endpoints and verified Supabase JWT authentication are the next backend milestone. Until that milestone is deployed, the UI can render but project creation/authenticated project loading will report the API error. This is intentional; the UI does not pretend a project was saved when it was not.

## Cloud rendering

A cloud job worker must be deployed separately from the static web UI and API. The worker needs access to the OpenMontage engine, durable job storage, private object storage, and configured provider credentials. Provider keys belong in server-side secrets only. Free web hosting does not imply free GPU/video generation or uninterrupted worker execution.
