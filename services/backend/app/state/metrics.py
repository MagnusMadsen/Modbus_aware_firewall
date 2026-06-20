# metrics.py holder styr på tællere og latency-målinger mens backend kører.
# Data kommer fra state/manager.py og state/requests.py, som kalder count_traffic(), count_request(), count_response(), count_failed(), count_arp() og add_latency().
# Denne fil modtager ikke rå Scapy-pakker. Den modtager kun besked om at en bestemt type hændelse er sket.
# Metrics samles midlertidigt i self.current og skrives derefter samlet til metrics_bucket via writer.insert_metrics_bucket().
# Hvis et bucket-vindue har 0 trafik eller failed requests, opretter filen også events via writer.insert_event().
from state.time_utils import compute_p95, floor_bucket, now


# MetricsTracker samler målepunkter i tidsvinduer, også kaldet buckets.
# Et bucket er et fast tidsinterval, f.eks. 5 sekunder, bestemt af flush_interval_seconds.
# current holder tællere for det aktive bucket.
# bucket_ts er starttidspunktet for det aktive bucket.
# connection_last_seen kommer fra ConnectionTracker og bruges til at tælle aktive forbindelser.
class MetricsTracker:
    # __init__() får writer, flush_interval_seconds og connection_last_seen fra ModbusStateManager.
    # writer er forbindelsen videre til storage-laget/databasefunktionerne.
    # flush_interval_seconds bestemmer hvor længe et metrics bucket varer.
    # connection_last_seen er et dict fra ConnectionTracker, hvor hver forbindelse har et last_seen-tidspunkt.
    def __init__(self, writer, flush_interval_seconds: int, connection_last_seen: dict):
        self.writer = writer
        self.flush_interval_seconds = flush_interval_seconds
        self.connection_last_seen = connection_last_seen
        self.bucket_ts = floor_bucket(now(), flush_interval_seconds)
        self.current = self._new_bucket()

    # _new_bucket() opretter en tom metrics-struktur for et nyt tidsvindue.
    # Tællere starter på 0, og latencies_ms starter som en tom liste.
    # Listen bruges fordi gennemsnit og p95 først kan beregnes når bucket'et flushes.
    def _new_bucket(self):
        return {
            "traffic_count": 0,
            "request_count": 0,
            "response_count": 0,
            "failed_count": 0,
            "arp_count": 0,
            "latencies_ms": [],
        }

    # count_traffic() kaldes fra manager.py når en observation er bekræftet som Modbus-trafik.
    def count_traffic(self):
        self.current["traffic_count"] += 1

    # count_request() kaldes når en Modbus request registreres.
    def count_request(self):
        self.current["request_count"] += 1

    # count_response() kaldes når en Modbus response matches eller registreres.
    def count_response(self):
        self.current["response_count"] += 1

    # count_failed() kaldes når en request fejler, f.eks. ved timeout.
    def count_failed(self):
        self.current["failed_count"] += 1

    # count_arp() kaldes fra manager.py når en ARP-observation håndteres.
    def count_arp(self):
        self.current["arp_count"] += 1

    # add_latency() kaldes når RequestTracker har matchet en request og response og beregnet latency.
    # latency_ms gemmes i bucket'et, så avg_latency_ms og p95_latency_ms kan beregnes ved flush.
    def add_latency(self, latency_ms: float):
        self.current["latencies_ms"].append(latency_ms)

    # flush_if_due() er hovedfunktionen i denne fil.
    # Den kaldes løbende fra manager.process(data) og managerens maintenance loop.
    # Funktionen tjekker om tiden er gået videre til et nyt bucket.
    # Hvis bucket'et stadig er det samme, returnerer den uden at skrive til databasen.
    # Hvis bucket'et er slut, beregnes metrics og skrives til metrics_bucket.
    def flush_if_due(self):
        # Beregner hvilket bucket den aktuelle tid hører til.
        current_bucket = floor_bucket(now(), self.flush_interval_seconds)

        # Hvis vi stadig er i samme bucket, er der ikke noget at flushe endnu.
        if current_bucket <= self.bucket_ts:
            return

        # En forbindelse tælles som aktiv, hvis den er set inden for de seneste 60 sekunder.
        # connection_last_seen kommer fra ConnectionTracker.
        active_connections = sum(
            1
            for last_seen in self.connection_last_seen.values()
            if (now() - last_seen).total_seconds() <= 60
        )

        # Latency-listen bruges til at beregne gennemsnit og p95 for det afsluttede bucket.
        latencies = self.current["latencies_ms"]
        avg_latency_ms = round(sum(latencies) / len(latencies), 2) if latencies else None
        p95_latency_ms = round(compute_p95(latencies), 2) if latencies else None

        # Sender det afsluttede bucket videre til storage-laget, som skriver rækken i metrics_bucket.
        self.writer.insert_metrics_bucket(
            bucket_ts=self.bucket_ts,
            traffic_count=self.current["traffic_count"],
            request_count=self.current["request_count"],
            response_count=self.current["response_count"],
            failed_count=self.current["failed_count"],
            arp_count=self.current["arp_count"],
            avg_latency_ms=avg_latency_ms,
            p95_latency_ms=p95_latency_ms,
            active_connections=active_connections,
        )

        # bucket_label bruges som stabil del af event_key, så samme bucket ikke opretter dublet-events.
        bucket_label = self.bucket_ts.isoformat()

        # Hvis der ikke blev set trafik i bucket'et, oprettes et downtime-event.
        if self.current["traffic_count"] == 0:
            # Sender downtime-hændelsen videre til events-tabellen via storage-laget.
            self.writer.insert_event(
                event_key=f"downtime:{bucket_label}",
                event_type="downtime",
                severity="high",
                details={
                    "message": "No traffic observed in metrics bucket",
                    "bucket_ts": bucket_label,
                    "traffic_count": self.current["traffic_count"],
                    "request_count": self.current["request_count"],
                    "response_count": self.current["response_count"],
                    "failed_count": self.current["failed_count"],
                    "is_pinned": True,
                    "pin_reason": "Traffic count was zero in this bucket",
                },
            )


        # Når bucket'et er skrevet til databasen, starter trackerens næste bucket.
        self.bucket_ts = current_bucket
        self.current = self._new_bucket()
