# metrics.py skriver målinger til metrics_bucket-tabellen.
# Data kommer fra state/metrics.py gennem StorageWriter.insert_metrics_bucket().
# Denne fil modtager ikke rå packets og beregner ikke metrics selv.
# Den får færdige bucket-værdier som traffic_count, request_count, response_count, failed_count, arp_count, latency og active_connections.
# Formålet er kun at gemme ét afsluttet metrics-bucket i databasen.

from storage.base import execute


# insert_metrics_bucket() opretter eller opdaterer én række i metrics_bucket.
# bucket_ts er starttidspunktet for bucket-vinduet, f.eks. et 5-sekunders interval.
# traffic_count er antal Modbus-pakker i bucket'et.
# request_count og response_count er antal Modbus requests/responses.
# failed_count er antal fejl, f.eks. timeouts eller exception responses.
# arp_count er antal ARP-observationer i bucket'et.
# avg_latency_ms og p95_latency_ms kommer fra matched request/response latency-målinger.
# active_connections er antal forbindelser set inden for det seneste aktive tidsvindue.
def insert_metrics_bucket(
    bucket_ts,
    traffic_count,
    request_count,
    response_count,
    failed_count,
    arp_count,
    avg_latency_ms,
    p95_latency_ms,
    active_connections,
):
    # Sender SQL-kommandoen videre til storage/base.py execute(), som åbner connection og kører queryen.
    execute(
        """
        -- Opretter et metrics bucket for dette bucket_ts.
        INSERT INTO metrics_bucket
            (bucket_ts, traffic_count, request_count, response_count, failed_count, arp_count,
             avg_latency_ms, p95_latency_ms, active_connections)
        VALUES
            (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        -- Hvis samme bucket_ts allerede findes, opdateres rækken i stedet for at lave en dublet.
        ON CONFLICT (bucket_ts)
        DO UPDATE SET
            -- EXCLUDED betyder de nye værdier fra INSERT-forsøget.
            traffic_count = EXCLUDED.traffic_count,
            request_count = EXCLUDED.request_count,
            response_count = EXCLUDED.response_count,
            failed_count = EXCLUDED.failed_count,
            arp_count = EXCLUDED.arp_count,
            avg_latency_ms = EXCLUDED.avg_latency_ms,
            p95_latency_ms = EXCLUDED.p95_latency_ms,
            active_connections = EXCLUDED.active_connections
        """,
        # Parametrene bindes separat, så værdierne ikke sættes direkte ind i SQL-strengen.
        # Det er state/metrics.py der har beregnet værdierne. Denne fil gemmer dem kun.
        (
            bucket_ts,
            traffic_count,
            request_count,
            response_count,
            failed_count,
            arp_count,
            avg_latency_ms,
            p95_latency_ms,
            active_connections,
        ),
    )