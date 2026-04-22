CREATE TABLE IF NOT EXISTS devices (
    id SERIAL PRIMARY KEY,
    ip INET NOT NULL,
    mac TEXT,
    role TEXT,
    first_seen TIMESTAMP NOT NULL DEFAULT NOW(),
    last_seen TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE (ip)
);

CREATE TABLE IF NOT EXISTS observed_connections (
    id SERIAL PRIMARY KEY,
    master_ip INET NOT NULL,
    slave_ip INET NOT NULL,
    unit_id INTEGER,
    first_seen TIMESTAMP NOT NULL DEFAULT NOW(),
    last_seen TIMESTAMP NOT NULL DEFAULT NOW(),
    request_count BIGINT NOT NULL DEFAULT 1,
    UNIQUE (master_ip, slave_ip, unit_id)
);