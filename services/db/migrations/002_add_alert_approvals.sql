CREATE TABLE IF NOT EXISTS alert_approvals (
    id BIGSERIAL PRIMARY KEY,
    alert_key TEXT NOT NULL UNIQUE,
    alert_type TEXT NOT NULL,
    title TEXT NOT NULL,
    message TEXT,
    action TEXT NOT NULL,
    status TEXT NOT NULL,
    details JSONB NOT NULL DEFAULT '[]'::jsonb,
    device_id INTEGER REFERENCES devices(id) ON DELETE SET NULL,
    handled_by TEXT,
    handled_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_alert_approvals_action
        CHECK (action IN ('approve', 'block', 'ignore')),
    CONSTRAINT chk_alert_approvals_status
        CHECK (status IN ('approved', 'blocked', 'ignored', 'critical', 'handled'))
);

CREATE INDEX IF NOT EXISTS idx_alert_approvals_handled_at
    ON alert_approvals (handled_at DESC);

    