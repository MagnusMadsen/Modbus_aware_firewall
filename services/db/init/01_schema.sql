CREATE TABLE IF NOT EXISTS devices (
    id SERIAL PRIMARY KEY,
    ip INET NOT NULL UNIQUE,
    mac TEXT,
    role TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    first_seen TIMESTAMP NOT NULL DEFAULT NOW(),
    last_seen TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_devices_status
        CHECK (status IN ('pending', 'approved', 'blocked', 'ignored')),
    CONSTRAINT chk_devices_role
        CHECK (role IS NULL OR role IN ('master', 'slave', 'unknown'))
);

CREATE TABLE IF NOT EXISTS observed_connections (
    id SERIAL PRIMARY KEY,
    master_ip INET NOT NULL,
    slave_ip INET NOT NULL,
    unit_id INTEGER,
    first_seen TIMESTAMP NOT NULL DEFAULT NOW(),
    last_seen TIMESTAMP NOT NULL DEFAULT NOW(),
    request_count BIGINT NOT NULL DEFAULT 1,
    UNIQUE (master_ip, slave_ip, unit_id),
    CONSTRAINT chk_observed_connections_unit_id
        CHECK (unit_id IS NULL OR unit_id BETWEEN 0 AND 255)
);

CREATE TABLE IF NOT EXISTS modbus_register_state (
    id SERIAL PRIMARY KEY,
    slave_ip INET NOT NULL,
    unit_id INTEGER NOT NULL,
    register_type TEXT NOT NULL,
    register_address INTEGER NOT NULL,
    last_value TEXT,
    first_seen TIMESTAMP NOT NULL DEFAULT NOW(),
    last_seen TIMESTAMP NOT NULL DEFAULT NOW(),
    write_count BIGINT NOT NULL DEFAULT 0,
    UNIQUE (slave_ip, unit_id, register_type, register_address),
    CONSTRAINT chk_register_state_unit_id
        CHECK (unit_id BETWEEN 0 AND 255),
    CONSTRAINT chk_register_state_register_address
        CHECK (register_address BETWEEN 0 AND 65535),
    CONSTRAINT chk_register_state_register_type
        CHECK (register_type IN (
            'coil',
            'discrete_input',
            'input_register',
            'holding_register'
        ))
);

CREATE TABLE IF NOT EXISTS events (
    id BIGSERIAL PRIMARY KEY,
    ts TIMESTAMP NOT NULL DEFAULT NOW(),
    event_type TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'info',
    source_ip INET,
    target_ip INET,
    unit_id INTEGER,
    function_code INTEGER,
    register_type TEXT,
    register_address INTEGER,
    old_value TEXT,
    new_value TEXT,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT chk_events_severity
        CHECK (severity IN ('info', 'low', 'medium', 'high', 'critical')),
    CONSTRAINT chk_events_unit_id
        CHECK (unit_id IS NULL OR unit_id BETWEEN 0 AND 255),
    CONSTRAINT chk_events_function_code
        CHECK (function_code IS NULL OR function_code BETWEEN 1 AND 127),
    CONSTRAINT chk_events_register_address
        CHECK (register_address IS NULL OR register_address BETWEEN 0 AND 65535),
    CONSTRAINT chk_events_register_type
        CHECK (
            register_type IS NULL OR register_type IN (
                'coil',
                'discrete_input',
                'input_register',
                'holding_register'
            )
        )
);

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

CREATE TABLE IF NOT EXISTS metrics_bucket (
    id BIGSERIAL PRIMARY KEY,
    bucket_ts TIMESTAMP NOT NULL UNIQUE,
    traffic_count BIGINT NOT NULL DEFAULT 0,
    request_count BIGINT NOT NULL DEFAULT 0,
    response_count BIGINT NOT NULL DEFAULT 0,
    failed_count BIGINT NOT NULL DEFAULT 0,
    arp_count BIGINT NOT NULL DEFAULT 0,
    avg_latency_ms DOUBLE PRECISION,
    p95_latency_ms DOUBLE PRECISION,
    active_connections INTEGER NOT NULL DEFAULT 0,
    CONSTRAINT chk_metrics_non_negative
        CHECK (
            traffic_count >= 0
            AND request_count >= 0
            AND response_count >= 0
            AND failed_count >= 0
            AND arp_count >= 0
            AND active_connections >= 0
        )
);

CREATE TABLE IF NOT EXISTS critical_registers (
    id SERIAL PRIMARY KEY,
    slave_ip INET NOT NULL,
    unit_id INTEGER NOT NULL,
    register_type TEXT NOT NULL,
    register_address INTEGER NOT NULL,
    label TEXT,
    allowed_values JSONB,
    pin_on_change BOOLEAN NOT NULL DEFAULT TRUE,
    is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (slave_ip, unit_id, register_type, register_address),
    CONSTRAINT chk_critical_registers_unit_id
        CHECK (unit_id BETWEEN 0 AND 255),
    CONSTRAINT chk_critical_registers_register_address
        CHECK (register_address BETWEEN 0 AND 65535),
    CONSTRAINT chk_critical_registers_register_type
        CHECK (register_type IN (
            'coil',
            'discrete_input',
            'input_register',
            'holding_register'
        ))
);

CREATE INDEX IF NOT EXISTS idx_devices_last_seen
    ON devices (last_seen DESC);

CREATE INDEX IF NOT EXISTS idx_connections_last_seen
    ON observed_connections (last_seen DESC);

CREATE INDEX IF NOT EXISTS idx_register_state_slave
    ON modbus_register_state (slave_ip, unit_id);

CREATE INDEX IF NOT EXISTS idx_events_ts
    ON events (ts DESC);

CREATE INDEX IF NOT EXISTS idx_events_type_ts
    ON events (event_type, ts DESC);

CREATE INDEX IF NOT EXISTS idx_metrics_bucket_ts
    ON metrics_bucket (bucket_ts DESC);

CREATE INDEX IF NOT EXISTS idx_critical_registers_lookup
    ON critical_registers (slave_ip, unit_id, register_type, register_address);