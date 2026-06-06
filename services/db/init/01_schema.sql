-- 01_schema.sql definerer PostgreSQL-databasens struktur for backend.
-- Filen opretter tabeller, kolonner, relationer, constraints, migrationer og indexes.
-- db.py apply_schema() kører denne fil mod databasen ved startup/setup.
-- db.py verify_schema() tjekker bagefter kun om de nødvendige tabeller findes.

-- Vigtige database-regler:
-- PRIMARY KEY giver hver række et stabilt database-id.
-- UNIQUE forhindrer dubletter af samme logiske objekt, f.eks. samme IP eller event_key.
-- FOREIGN KEY kobler tabeller sammen, f.eks. alarm_approvals.event_id -> events.id.
-- CHECK begrænser kolonner til gyldige værdier, som backend/frontend forstår.
-- DEFAULT giver en startværdi, f.eks. status='pending' eller created_at=NOW().
-- INDEXES gør ofte brugte opslag hurtigere, men ændrer ikke data.


-- devices definerer enheder backend kan gemme.
-- Hver række repræsenterer én IP-adresse, fordi ip er UNIQUE.
-- INET bruges så PostgreSQL behandler ip som en IP-adresse og ikke bare tekst.
-- mac kan være NULL, fordi ikke alle observationer har en MAC-adresse.
-- role er begrænset til master, slave eller unknown, så databasen ikke får ukendte roller.
-- status er begrænset til pending, approved, blocked eller ignored, så dashboardet kun møder kendte statusværdier.
-- first_seen og last_seen bruges til første og seneste observation.

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

-- observed_connections definerer Modbus-relationer mellem master og slave.
-- master_ip og slave_ip er IP-adresser og bruger INET.
-- unit_id er Modbus unit-id og må være NULL, hvis værdien ikke er kendt.
-- UNIQUE (master_ip, slave_ip, unit_id) gør relationen unik, så request_count og last_seen kan opdateres på samme række.
-- CHECK sikrer at unit_id holder sig inden for Modbus-området 0-255.
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

-- modbus_register_state definerer seneste kendte state for Modbus-registre/coils.
-- slave_ip og unit_id identificerer Modbus-enheden registeret hører til.
-- register_type og register_address identificerer selve registeret.
-- UNIQUE (slave_ip, unit_id, register_type, register_address) gør at samme register kun har én state-række.
-- last_value gemmes som TEXT, fordi coils og registerværdier kan have forskellige værdiformater.
-- write_count kan bruges til at se hvor mange writes backend har registreret til registeret.
-- CHECK constraints beskytter mod ugyldig unit_id, registeradresse og register_type.
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

-- events definerer IDS-hændelser/alarmer.
-- id er den tekniske primærnøgle og bruges som reference fra alarm_approvals.event_id.
-- event_key er en logisk nøgle for samme hændelse og er UNIQUE, så gentagne observationer kan opdatere samme event.
-- event_type, severity og status beskriver hændelsens type, alvor og aktuelle tilstand.
-- source_ip, target_ip, unit_id, function_code, register_type og register_address er valgfrie kontekstfelter.
-- old_value og new_value kan bruges til før/efter-værdier ved ændringer.
-- details JSONB bruges til ekstra kontekst, som varierer mellem eventtyper.
-- CHECK constraints er sidste sikkerhedsnet mod ugyldige eventværdier.
CREATE TABLE IF NOT EXISTS events (
    id BIGSERIAL PRIMARY KEY,
    ts TIMESTAMP NOT NULL DEFAULT NOW(),
    event_key TEXT UNIQUE,
    event_type TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'info',
    status TEXT NOT NULL DEFAULT 'open',
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
    CONSTRAINT chk_events_status
        CHECK (status IN ('open', 'approved', 'blocked', 'ignored', 'critical', 'closed')),
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

-- app_users definerer dashboard-brugere.
-- username er UNIQUE, så to brugere ikke kan have samme login-navn.
-- password_hash gemmer det hashede password, ikke det rå password.
-- role er begrænset til admin eller operator, så backend/frontend ikke får ukendte adgangsroller.
-- is_active kan deaktivere en bruger uden at slette rækken.
-- last_login kan opdateres efter succesfuldt login.
CREATE TABLE IF NOT EXISTS app_users (
    id SERIAL PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT,
    role TEXT NOT NULL DEFAULT 'operator',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    last_login TIMESTAMP,

    CONSTRAINT chk_app_users_role
        CHECK (role IN ('admin', 'operator'))
);

-- alarm_approvals definerer brugerens beslutning på alarmer.
-- event_id er en foreign key til events.id og kan pege på den konkrete event brugeren håndterer.
-- Relation: events.id <── alarm_approvals.event_id.
-- ON DELETE SET NULL betyder at event_id sættes til NULL, hvis eventen slettes, mens brugerens beslutning bevares.
-- alarm_key er UNIQUE, så samme logiske alarm kun bør have én approval-række.
-- action beskriver brugerens valg, og status beskriver den status alarmen får.
-- details JSONB kan indeholde ekstra kontekst fra frontend/backend.
-- CHECK constraints forhindrer ugyldige alarmbeslutninger eller statusværdier.
CREATE TABLE IF NOT EXISTS alarm_approvals (
    id BIGSERIAL PRIMARY KEY,
    alarm_key TEXT NOT NULL UNIQUE,
    alarm_type TEXT NOT NULL,
    action TEXT NOT NULL,
    status TEXT NOT NULL,
    handled_by TEXT NOT NULL,
    handled_at TIMESTAMP NOT NULL DEFAULT NOW(),
    event_id BIGINT REFERENCES events(id) ON DELETE SET NULL,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT chk_alarm_approvals_action
        CHECK (action IN ('approve', 'block', 'ignore', 'critical')),
    CONSTRAINT chk_alarm_approvals_status
        CHECK (status IN ('approved', 'blocked', 'ignored', 'critical'))
);

-- metrics_bucket definerer opsummerede målinger i tidsvinduer.
-- bucket_ts er starttidspunktet for tidsvinduet og er UNIQUE.
-- Tabellen er lavet til aggregerede tællere, ikke rå pakker eller frames.
-- traffic_count, request_count, response_count, failed_count og arp_count er tæller-kolonner.
-- avg_latency_ms og p95_latency_ms er latency-kolonner for matchede request/response-målinger.
-- active_connections er en tæller for aktive Modbus-relationer i tidsvinduet.
-- CHECK sikrer at tællere ikke bliver negative.
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

-- critical_registers definerer regler for vigtige Modbus-registre.
-- slave_ip, unit_id, register_type og register_address identificerer det register reglen gælder for.
-- UNIQUE forhindrer modstridende regler for samme slave_ip/unit_id/register_type/register_address.
-- label er et valgfrit menneskeligt navn, som frontend kan vise.
-- allowed_values JSONB kan indeholde de værdier backend skal acceptere for registeret.
-- pin_on_change og is_enabled styrer hvordan reglen kan bruges af backend.
-- CHECK constraints sikrer at regler kun kan oprettes for Modbus-værdier backend kan forstå.
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

-- Migration til databaser der allerede findes.
-- CREATE TABLE IF NOT EXISTS ændrer ikke eksisterende tabeller.
-- Derfor bruges ALTER TABLE til nye kolonner/constraints på databaser der allerede er oprettet.
-- apply_schema() kører ændringerne. verify_schema() tjekker kun at tabellerne findes.
ALTER TABLE events
    ADD COLUMN IF NOT EXISTS event_key TEXT;

ALTER TABLE events
    ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'open';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'events_event_key_key'
    ) THEN
        ALTER TABLE events
            ADD CONSTRAINT events_event_key_key UNIQUE (event_key);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'chk_events_status'
    ) THEN
        ALTER TABLE events
            ADD CONSTRAINT chk_events_status
            CHECK (status IN ('open', 'approved', 'blocked', 'ignored', 'critical', 'closed'));
    END IF;
END $$;

-- Indexes gør opslag hurtigere på kolonner backend ofte søger, filtrerer eller sorterer på.
-- Et index kan sammenlignes med et register i en bog: PostgreSQL kan finde relevante rækker uden at læse hele tabellen.
-- Indexes ændrer ikke data og bestemmer ikke hvad der må gemmes. Det gør constraints.
-- Indexes bruges her især til dashboard-visninger, sortering efter tid, statusfiltrering og opslag på nøgler.

-- Gør det hurtigere at hente devices sorteret efter seneste observation.
-- Bruges typisk når dashboardet skal vise de nyeste eller senest aktive enheder først.
CREATE INDEX IF NOT EXISTS idx_devices_last_seen
    ON devices (last_seen DESC);

-- Gør det hurtigere at hente Modbus-forbindelser sorteret efter seneste aktivitet.
-- Bruges når dashboardet viser aktive eller nyligt sete master/slave-relationer.
CREATE INDEX IF NOT EXISTS idx_connections_last_seen
    ON observed_connections (last_seen DESC);

-- Gør det hurtigere at finde register-state for en bestemt slave og unit_id.
-- Bruges når backend/frontend skal vise registre for én bestemt Modbus-enhed.
CREATE INDEX IF NOT EXISTS idx_register_state_slave
    ON modbus_register_state (slave_ip, unit_id);

-- Gør det hurtigere at hente de nyeste events først.
-- DESC matcher typisk dashboardets behov for at vise seneste hændelser øverst.
CREATE INDEX IF NOT EXISTS idx_events_ts
    ON events (ts DESC);

-- Gør det hurtigere at hente events af en bestemt type sorteret efter tid.
-- Eksempel: alle register_value_changed eller request_timeout events.
CREATE INDEX IF NOT EXISTS idx_events_type_ts
    ON events (event_type, ts DESC);

-- Gør opslag på event_key hurtigere.
-- event_key bruges til at genkende samme logiske hændelse igen.
CREATE INDEX IF NOT EXISTS idx_events_key
    ON events (event_key);

-- Gør det hurtigere at hente events efter status sorteret efter tid.
-- Eksempel: åbne events i dashboardet, nyeste først.
CREATE INDEX IF NOT EXISTS idx_events_status_ts
    ON events (status, ts DESC);

-- Gør det hurtigere at hente metrics i tidsorden.
-- Bruges til grafer hvor backend/frontend henter de nyeste metrics buckets.
CREATE INDEX IF NOT EXISTS idx_metrics_bucket_ts
    ON metrics_bucket (bucket_ts DESC);

-- Gør opslag efter en critical_registers-regel hurtigere.
-- Matcher den nøgle backend bruger: slave_ip, unit_id, register_type og register_address.
CREATE INDEX IF NOT EXISTS idx_critical_registers_lookup
    ON critical_registers (slave_ip, unit_id, register_type, register_address);

-- Gør opslag efter username hurtigere ved login og brugeradministration.
-- username er også UNIQUE, men dette index gør formålet tydeligt i schemaet.
CREATE INDEX IF NOT EXISTS idx_app_users_username
    ON app_users (username);

-- Gør opslag på alarm_key hurtigere.
-- Bruges når backend/frontend tjekker om en alarm allerede er håndteret.
CREATE INDEX IF NOT EXISTS idx_alarm_approvals_alarm_key
    ON alarm_approvals (alarm_key);

-- Gør det hurtigere at vise alarm approvals sorteret efter seneste håndtering.
-- Bruges til historikvisning med nyeste beslutninger først.
CREATE INDEX IF NOT EXISTS idx_alarm_approvals_handled_at
    ON alarm_approvals (handled_at DESC);

-- Gør det hurtigere at filtrere alarm approvals efter alarm_type.
-- Eksempel: device-, port- eller registerrelaterede approvals.
CREATE INDEX IF NOT EXISTS idx_alarm_approvals_type
    ON alarm_approvals (alarm_type);
