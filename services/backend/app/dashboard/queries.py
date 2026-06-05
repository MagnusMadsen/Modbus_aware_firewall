# queries.py indeholder SQL-queries til dashboardet.
# Filen læser kun data fra databasen. Den opretter, ændrer eller sletter ikke rækker.
# query_one() bruges når der forventes én række tilbage, og query_all() bruges når der forventes flere rækker.
# Resultaterne sendes videre til dashboard/formatters.py og dashboard/service.py, som bygger JSON-svaret til frontend.
from storage.base import query_all, query_one



# get_device_count() tæller hvor mange enheder der findes i devices-tabellen.
# Bruges til dashboardets summary-kort for antal observerede devices.
def get_device_count():
    row = query_one("SELECT COUNT(*) AS count FROM devices;")
    return row["count"]



# get_recent_metrics() summerer metrics fra de seneste 60 sekunder.
# COALESCE() sikrer at dashboardet får 0 i stedet for NULL, hvis der ikke findes data i perioden.
# AVG(avg_latency_ms) giver gennemsnitlig latency for perioden, afrundet til 2 decimaler.
def get_recent_metrics():
    return query_one(
        """
        SELECT
            COALESCE(SUM(traffic_count), 0) AS traffic_count,
            COALESCE(SUM(request_count), 0) AS request_count,
            COALESCE(SUM(response_count), 0) AS response_count,
            COALESCE(SUM(failed_count), 0) AS failed_count,
            COALESCE(SUM(arp_count), 0) AS arp_count,
            ROUND(AVG(avg_latency_ms)::numeric, 2) AS avg_latency_ms
        FROM metrics_bucket
        WHERE bucket_ts >= NOW() - INTERVAL '60 seconds'
        """
    )



# get_metric_rows() henter tidsserien til trafik/latency-grafen for de seneste 30 minutter.
# Hver række kommer fra metrics_bucket og repræsenterer ét tidsvindue.
# LEFT JOIN mod events kobler relevante åbne downtime-, failed_requests- og latency_spike-events på samme datapunkt.
# Event-id'er sendes med, så frontend kan vise en alarm og senere gemme alarm_approvals.event_id korrekt.
def get_metric_rows():
    return query_all(
        """
        SELECT
            mb.bucket_ts,
            TO_CHAR(mb.bucket_ts, 'HH24:MI:SS') AS time,
            mb.traffic_count AS traffic,
            COALESCE(mb.avg_latency_ms, 0) AS latency,
            mb.failed_count AS failed_requests,
            CASE WHEN mb.traffic_count = 0 THEN TRUE ELSE FALSE END AS downtime,
            downtime_event.id AS downtime_event_id,
            failed_event.id AS failed_event_id,
            latency_event.id AS latency_event_id
        FROM metrics_bucket mb
        -- Kobler et åbent downtime-event på samme metrics bucket, hvis det findes.
        LEFT JOIN events downtime_event
            ON downtime_event.event_type = 'downtime'
            AND downtime_event.status = 'open'
            AND (downtime_event.details->>'bucket_ts')::timestamp = mb.bucket_ts
        -- Kobler et åbent failed_requests-event på samme metrics bucket, hvis det findes.
        LEFT JOIN events failed_event
            ON failed_event.event_type = 'failed_requests'
            AND failed_event.status = 'open'
            AND (failed_event.details->>'bucket_ts')::timestamp = mb.bucket_ts
        -- Latency-events matches på tid omkring bucket_ts, fordi de ikke gemmes med bucket_ts i details.
        LEFT JOIN events latency_event
            ON latency_event.event_type = 'latency_spike'
            AND latency_event.status = 'open'
            AND latency_event.ts >= mb.bucket_ts - INTERVAL '5 seconds'
            AND latency_event.ts < mb.bucket_ts + INTERVAL '5 seconds'
        WHERE mb.bucket_ts >= NOW() - INTERVAL '30 minutes'
        ORDER BY mb.bucket_ts
        """
    )


# get_recent_event_rows() henter de seneste åbne events til event-listen i dashboardet.
# Kun status='open' hentes, fordi håndterede events ikke længere skal vises som aktive alarmer.
# Pinned events sorteres først ved hjælp af details->>'is_pinned'.
# LIMIT bruges for at undgå at sende hele events-tabellen til frontend.
def get_recent_event_rows(limit=20):
    return query_all(
        """
        SELECT
            id,
            event_key,
            TO_CHAR(ts, 'YYYY-MM-DD HH24:MI:SS') AS time,
            event_type,
            severity,
            status,
            source_ip::text AS source_ip,
            target_ip::text AS target_ip,
            register_address,
            old_value,
            new_value,
            details
        FROM events
        WHERE status = 'open'
        ORDER BY
            COALESCE((details->>'is_pinned')::boolean, FALSE) DESC,
            ts DESC
        LIMIT %s
        """,
        (limit,),
    )


# get_arp_event_rows() henter de seneste ARP/MAC-relaterede events til ARP detection-sektionen.
# Her filtreres der ikke på status, fordi ARP-sektionen også skal kunne vise hændelser efter de er håndteret.
# LIMIT 4 bruges fordi frontend kun viser et kort udsnit af de nyeste ARP-hændelser.
def get_arp_event_rows(limit=4):
    return query_all(
        """
        SELECT
            id,
            event_key,
            TO_CHAR(ts, 'YYYY-MM-DD HH24:MI:SS') AS time,
            event_type,
            status,
            source_ip::text AS source_ip,
            old_value,
            new_value
        FROM events
        WHERE event_type IN ('arp_mac_changed', 'identity_mac_changed')
        ORDER BY ts DESC
        LIMIT %s
        """,
        (limit,),
    )


# get_devices() henter devices-listen til dashboardet.
# LEFT JOIN mod events finder et åbent new_device-event for samme IP, hvis enheden stadig afventer håndtering.
# new_device_event.id sendes med som event_id, så frontend kan koble device approval tilbage til events.id.
# Hvis der ikke findes et åbent new_device-event, bliver event_id NULL.
def get_devices():
    return query_all(
        """
        SELECT
            d.id,
            d.ip::text AS ip,
            d.mac,
            d.role,
            d.status,
            new_device_event.id AS event_id,
            TO_CHAR(d.first_seen, 'YYYY-MM-DD HH24:MI:SS') AS first_seen,
            TO_CHAR(d.last_seen, 'YYYY-MM-DD HH24:MI:SS') AS last_seen
        FROM devices d
        -- Finder det åbne new_device-event der hører til samme IP-adresse som device-rækken.
        LEFT JOIN events new_device_event
            ON new_device_event.event_type = 'new_device'
            AND new_device_event.status = 'open'
            AND new_device_event.source_ip = d.ip
        ORDER BY d.last_seen DESC
        """
    )


# get_chart_event_rows() henter åbne events fra de seneste 30 minutter til graf-markører.
# LIMIT 50 bruges for at holde dashboard-responsen lille og grafen overskuelig.
def get_chart_event_rows():
    return query_all(
        """
        SELECT
            id,
            event_key,
            TO_CHAR(ts, 'HH24:MI:SS') AS time,
            event_type,
            severity,
            status,
            source_ip::text AS source_ip,
            target_ip::text AS target_ip,
            register_address,
            old_value,
            new_value
        FROM events
        WHERE ts >= NOW() - INTERVAL '30 minutes'
            AND status = 'open'
        ORDER BY ts DESC
        LIMIT 50
        """
    )


# get_connection_rows() henter master/slave-relationer fra observed_connections.
# COALESCE(unit_id, 0) gør at frontend altid får et tal, også hvis unit_id mangler i databasen.
# Data bruges senere i dashboard/ports.py til at vise hvilke masters der taler med hvilke slaves.
def get_connection_rows():
    return query_all(
        """
        SELECT
            master_ip::text AS master_ip,
            slave_ip::text AS slave_ip,
            COALESCE(unit_id, 0) AS unit_id,
            request_count,
            TO_CHAR(last_seen, 'YYYY-MM-DD HH24:MI:SS') AS last_seen
        FROM observed_connections
        ORDER BY master_ip, slave_ip, unit_id
        """
    )
