CREATE TABLE IF NOT EXISTS devices (
    id SERIAL PRIMARY KEY,
    ip INET,
    mac VARCHAR(32) NOT NULL,
    first_seen TIMESTAMP NOT NULL DEFAULT NOW(),
    last_seen TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE(ip, mac)
);

CREATE TABLE IF NOT EXISTS packet_logs (
    id BIGSERIAL PRIMARY KEY,
    ts TIMESTAMP NOT NULL DEFAULT NOW(),
    src_mac VARCHAR(32),
    dst_mac VARCHAR(32),
    src_ip INET,
    dst_ip INET,
    protocol VARCHAR(16),
    src_port INTEGER,
    dst_port INTEGER,
    length INTEGER
);