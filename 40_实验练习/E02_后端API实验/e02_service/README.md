# E02 Task API

E02-01, E02-02, and E02-03 share this single FastAPI application and repository.

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.lock
python -m pip install -e .
python -m pytest -q
python -m uvicorn app.main:app --reload
```

Endpoints:

- `POST /tasks`
- `GET /tasks/{task_id}`
- `GET /metrics`

All runtime endpoints require one of the deliberately non-secret fixture credentials, for example
`Authorization: Bearer alice-fixture`. The server maps that credential to a server-owned `Principal`; the
request body cannot set identity or authorization fields. `alice-fixture` and `bob-fixture` are separate owners,
while `reader-fixture` lacks write and metrics scopes. These fixtures teach the boundary only: production code
must validate signed token issuer, audience, expiry, and revocation.

The server generates distinct `task_id` values and timezone-aware UTC `created_at` values. Client-controlled
identity, authorization, `task_id`, `status`, timestamps, and other unknown fields are rejected. Task reads and
metrics are scoped to the authenticated tenant and owner; a missing task and another owner's task both return 404.
