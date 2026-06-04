-- devices er asset-listen.
-- Hver IP-adresse må kun ligge én gang, fordi ip-feltet er UNIQUE.
-- state/devices.py kalder storage/devices.py, som laver INSERT/UPDATE i denne tabel.
-- Formålet er at kunne sige: denne IP/MAC er set, hvilken rolle har den, og er den godkendt?

    -- INET bruges fordi PostgreSQL så forstår værdien som en IP-adresse og ikke bare tekst.
    -- UNIQUE gør IP-adressen til den naturlige nøgle for enheden.
    -- MAC kan være NULL, fordi ikke alle observationer nødvendigvis har en MAC-adresse.
    -- Rollen sættes ud fra trafikretningen: master sender request, slave modtager request.
    -- Nye enheder starter som pending, så frontend kan bede brugeren godkende eller ignorere dem.
    -- first_seen ændres ikke efter oprettelse. Den viser hvornår enheden først blev set.
    -- last_seen opdateres løbende, så dashboardet kan vise om enheden stadig er aktiv.
    -- CHECK begrænser status til de værdier frontend/backend forstår.
    -- CHECK forhindrer stavefejl eller ukendte roller i databasen.

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

-- observed_connections gemmer hvem der taler Modbus med hvem.
-- Den gemmer ikke alle pakker. Den samler relationen master_ip -> slave_ip -> unit_id i én række.
-- state/connections.py opdaterer request_count og last_seen hver gang samme relation ses igen.
-- unit_id kan være NULL, fordi nogle observationer kan mangle Modbus unit-id.
-- request_count tæller hvor mange Modbus requests der er set på denne relation.
-- UNIQUE (master_ip, slave_ip, unit_id) gør at samme relation opdateres i stedet for at oprette en ny række hver gang.
-- chk_observed_connections_unit_id sikrer at Modbus unit_id holder sig inden for 0-255.
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

-- modbus_register_state gemmer seneste kendte værdi for hvert register.
-- Tabellen er ikke en historik over alle ændringer. Den viser nuværende/seneste tilstand.
-- state/registers.py opdaterer denne tabel, når der ses write-operationer i Modbus-trafikken.
-- last_value gemmes som TEXT, så både coils og registerværdier kan gemmes enkelt.
-- write_count bruges til at se hvor ofte samme register er blevet skrevet til.
-- UNIQUE (slave_ip, unit_id, register_type, register_address) er registerets identitet.
-- chk_register_state_register_type sikrer at kun kendte Modbus-registertyper gemmes.
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

-- Events er den tekniske IDS-hændelseslog.
-- Når noget er relevant som alarm, skal det først oprettes her.
-- Frontend viser typisk events med status = open.
-- Når brugeren håndterer alarmen, opdateres status og alarm_approvals peger tilbage på events.id.
-- event_key er den nøgle backend bruger til at genkende den samme alarm igen.
-- Eksempel: register_value_changed:192.168.61.22:1:holding_register:1 betyder samme slave, unit_id, registertype og registeradresse.
-- event_key er UNIQUE, så gentagne observationer opdaterer samme event i stedet for at lave dubletter.
-- event_type fortæller typen, f.eks. new_device, port_active eller register_value_changed.
-- severity bruges af frontend til at prioritere hvad der skal vises som alarm.
-- status starter som open og ændres når brugeren trykker godkend/ignorer/bloker/kritisk.
-- source_ip og target_ip bruges til at vise hvem hændelsen handler om.
-- old_value og new_value gør det muligt at forklare præcis hvad der ændrede sig.
-- details JSONB bruges til ekstra information, som ikke passer rent ind i faste kolonner.
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

-- app_users er brugerne i dashboardet.
-- Tabellen bruges ved login og til at gemme hvilken rolle en bruger har.
-- Selve passwordet gemmes ikke i klartekst, kun password_hash.
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

-- Alarm_approvals gemmer brugerens beslutning på en alarm.
-- Den opretter ikke selve hændelsen. Hændelsen ligger i events.
-- event_id er foreign key til events.id.
-- Det betyder at en række i alarm_approvals kan pege tilbage på den konkrete hændelse i events.
-- Eksempel: hvis events.id = 93531, så kan alarm_approvals.event_id = 93531 vise hvem der håndterede netop den hændelse.
-- alarm_key bruges til at sikre at samme frontend-alarm ikke godkendes flere gange.
-- alarm_type er en kort type til frontend, f.eks. arp, downtime, device eller port_active.
-- action er den knap brugeren trykkede på.
-- status er den database-status som beslutningen giver alarmen.
-- handled_by og handled_at giver audit trail på hvem der håndterede alarmen og hvornår.
-- ON DELETE SET NULL betyder: hvis den tilknyttede række i events slettes, bliver event_id sat til NULL.
-- Selve approval-rækken bliver liggende, så man stadig kan se at brugeren har håndteret en alarm.
-- Det bruges for ikke at miste audit-loggen, selv hvis den oprindelige event senere ryddes op.
-- details JSONB gemmer den tekst og de felter brugeren så i modal-vinduet.
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

-- metrics_bucket gemmer opsummerede målinger i tidsvinduer.
-- Den bruges fordi dashboardet ikke skal læse hver enkelt frame/pakke fra databasen.
-- I stedet gemmes antal og latency-tal, så databasen og dashboardet ikke bliver unødigt belastet.
-- state/metrics.py skriver trafik, requests, responses, fejl, ARP og latency ind her.
-- bucket_ts er tidsvinduets start/tidspunkt. UNIQUE betyder én række pr. tidsvindue.
-- traffic_count tæller observerede Modbus-pakker i tidsvinduet.
-- failed_count bruges til at opdage fejl eller timeouts i kommunikationen.
-- avg_latency_ms og p95_latency_ms bruges til graf og latency-alarmer.
-- active_connections viser hvor mange relationer der var aktive i tidsvinduet.
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

-- critical_registers er brugerens liste over vigtige Modbus-registre.
-- Tabellen gemmer ikke registerets aktuelle værdi.
-- Den fortæller state/registers.py hvordan bestemte registre skal vurderes, når de ændrer sig.
-- label er et menneskeligt navn, f.eks. "Start/stop motor" eller "Setpoint".
-- allowed_values kan bruges til at definere hvilke værdier der er accepterede for registeret.
-- pin_on_change gør ændringer i dette register ekstra synlige i dashboardet.
-- is_enabled gør det muligt at slå reglen fra uden at slette den.
-- UNIQUE (slave_ip, unit_id, register_type, register_address) gør at samme kritiske register kun defineres én gang.
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
-- db.py verify_schema() tjekker kun om de nødvendige tabeller findes; den opretter eller ændrer ikke tabeller.
-- Denne SQL-migration ændrer selve databasen, f.eks. ved at tilføje nye kolonner og constraints.
-- CREATE TABLE IF NOT EXISTS ændrer ikke en eksisterende tabel.
-- Derfor tilføjes nye kolonner/constraints også med ALTER TABLE.
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

-- Indexes bruges for at gøre de mest brugte opslag hurtigere.
-- De ændrer ikke data. De hjælper kun PostgreSQL med at finde/sortere rækker hurtigere.
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

CREATE INDEX IF NOT EXISTS idx_events_key
    ON events (event_key);

-- Bruges når dashboardet henter åbne events sorteret efter tid.
CREATE INDEX IF NOT EXISTS idx_events_status_ts
    ON events (status, ts DESC);

CREATE INDEX IF NOT EXISTS idx_metrics_bucket_ts
    ON metrics_bucket (bucket_ts DESC);

CREATE INDEX IF NOT EXISTS idx_critical_registers_lookup
    ON critical_registers (slave_ip, unit_id, register_type, register_address);

CREATE INDEX IF NOT EXISTS idx_app_users_username
    ON app_users (username);

-- Bruges når backend tjekker om en alarm allerede er håndteret.
CREATE INDEX IF NOT EXISTS idx_alarm_approvals_alarm_key
    ON alarm_approvals (alarm_key);

CREATE INDEX IF NOT EXISTS idx_alarm_approvals_handled_at
    ON alarm_approvals (handled_at DESC);

CREATE INDEX IF NOT EXISTS idx_alarm_approvals_type
    ON alarm_approvals (alarm_type);
