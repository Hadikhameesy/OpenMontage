# Local API development

Run commands from the repository root.

```bash
python -m pip install -r requirements.txt
uvicorn cloud.api.main:app --host 127.0.0.1 --port 8000 --reload
```

Verify:

- `GET http://127.0.0.1:8000/health`
- `GET http://127.0.0.1:8000/api/v1/version`
- `GET http://127.0.0.1:8000/api/v1/pipelines`
- Interactive API docs: `http://127.0.0.1:8000/api/docs`

This milestone is read-only. It does not create projects, enqueue jobs, execute tools, or expose Backlot. Do not bind this API to a public interface until authentication, authorization, rate limiting, CORS policy, and deployment configuration are implemented.
