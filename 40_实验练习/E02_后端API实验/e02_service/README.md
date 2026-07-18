# E02 Task API

E02-01 through E02-04 share this single FastAPI application, service, and repository.

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
- `GET /tasks` with owner-scoped cursor pagination
- `GET /tasks/{task_id}`
- `PATCH /tasks/{task_id}` with a quoted `If-Match` version
- `GET /metrics`
- `GET /livez`
- `GET /readyz`

All business endpoints require one of the deliberately non-secret fixture credentials, for example
`Authorization: Bearer alice-fixture`. The server maps that credential to a server-owned `Principal`; the
request body cannot set identity or authorization fields. `alice-fixture` and `bob-fixture` are separate owners in
the same tenant; `carol-fixture` belongs to a different tenant, while `reader-fixture` lacks write and metrics
scopes. These fixtures teach the boundary only: production code
must validate signed token issuer, audience, expiry, and revocation.

The server generates distinct `task_id` values and timezone-aware UTC `created_at` values. Client-controlled
identity, authorization, `task_id`, `status`, timestamps, and other unknown fields are rejected. Task reads and
metrics are scoped to the authenticated tenant and owner; a missing task and another owner's task both return 404.

`X-Request-ID` crosses middleware, dependencies, service, repository, error responses, and redacted audit logs.
Unexpected exceptions log a controlled exception type and file/line/function frame locations, never the exception
message. Expected failures use RFC 9457-style Problem Details with a stable `code`; OpenAPI declares their actual
`application/problem+json` media type, including the generic 500 path, and every emitted local schema reference
resolves from the OpenAPI document root. Cursors accept only canonical, unpadded
Base64URL; invalid characters, padding, and noncanonical aliases return 400. The reference also demonstrates
dependency-aware readiness, recoverable connection-capacity and rate-limit errors, request deadlines checked at
commit, owner-scoped idempotency keys, and optimistic updates using `ETag`/`If-Match` versions.

The Python 3.13 reference currently collects 29 tests: 11 basic API cases, 16 lifecycle/reliability/concurrency
cases, and 2 OpenAPI contract cases.

This remains an in-memory, single-process teaching reference. It does not provide durable transactions,
cross-replica idempotency/rate limiting, client-disconnect cancellation, or production authentication.
