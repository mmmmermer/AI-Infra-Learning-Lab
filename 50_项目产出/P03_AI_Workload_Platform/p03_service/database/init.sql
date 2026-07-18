CREATE TABLE IF NOT EXISTS tasks (
    task_id UUID PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    allowed_permission_groups TEXT[] NOT NULL CHECK (
        cardinality(allowed_permission_groups) > 0
    ),
    task_type TEXT NOT NULL,
    priority INTEGER NOT NULL CHECK (priority BETWEEN 1 AND 10),
    estimated_duration_ms INTEGER NOT NULL CHECK (estimated_duration_ms >= 0),
    idempotency_key TEXT NOT NULL,
    input_json JSONB NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('pending', 'queued', 'running', 'succeeded', 'failed', 'retrying', 'cancelled')
    ),
    result_json JSONB,
    error_type TEXT,
    retry_count INTEGER NOT NULL DEFAULT 0 CHECK (retry_count >= 0),
    max_retries INTEGER NOT NULL DEFAULT 2 CHECK (max_retries >= 0),
    worker_id TEXT,
    lease_until TIMESTAMPTZ,
    delivery_count INTEGER NOT NULL DEFAULT 0 CHECK (delivery_count >= 0),
    created_at TIMESTAMPTZ NOT NULL,
    queued_at TIMESTAMPTZ,
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    runtime_ms DOUBLE PRECISION,
    version INTEGER NOT NULL DEFAULT 0 CHECK (version >= 0),
    UNIQUE (tenant_id, user_id, idempotency_key)
);

CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks (status);
CREATE INDEX IF NOT EXISTS idx_tasks_owner ON tasks (tenant_id, user_id, task_id);
CREATE INDEX IF NOT EXISTS idx_tasks_expired_lease
    ON tasks (lease_until)
    WHERE status = 'running';

CREATE TABLE IF NOT EXISTS outbox (
    event_id BIGSERIAL PRIMARY KEY,
    task_id UUID NOT NULL REFERENCES tasks(task_id),
    event_type TEXT NOT NULL,
    payload_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    claimed_at TIMESTAMPTZ,
    claimed_by TEXT,
    published_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_outbox_unpublished
    ON outbox (event_id)
    WHERE published_at IS NULL;
