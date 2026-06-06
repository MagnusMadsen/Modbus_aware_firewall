# time_utils.py samler små hjælpefunktioner til tid og beregning.
# Filen bruges af state-laget, især metrics.py, requests.py, devices.py og connections.py.
# Den modtager ikke packets og skriver ikke til databasen.
# Den returnerer kun tidsværdier eller beregnede tal, som andre state-filer bruger.
from datetime import datetime


# now() returnerer det aktuelle tidspunkt som datetime.
# Funktionen bruges i state-laget, så alle filer henter nuværende tid på samme måde.
# Eksempel: requests.py gemmer tidspunktet for en Modbus request.
# Senere kalder requests.py now() igen og sammenligner nuværende tid med requestens gemte tidspunkt.
# Hvis forskellen er større end request_timeout_seconds, betragtes requesten som udløbet.
def now() -> datetime:
    # datetime.now() bruger systemets lokale tid i backend-containeren.
    return datetime.now()


# floor_bucket() runder et tidspunkt ned til starten af et fast tidsvindue.
# Den bruges af metrics.py til at samle traffic, requests, responses, latency og ARP i buckets.
# Eksempel ved seconds=5: 09:32:17 bliver til 09:32:15.
# Eksempel ved seconds=10: 09:32:17 bliver til 09:32:10.
def floor_bucket(dt: datetime, seconds: int) -> datetime:
    # dt.second % seconds finder hvor langt inde i bucket'et tidspunktet er.
    # Det trækkes fra dt.second, så sekundet flyttes tilbage til bucket-start.
    floored_second = dt.second - (dt.second % seconds)
    # Beholder samme minut/time/dato, men sætter sekundet til bucket-start og fjerner microseconds.
    return dt.replace(second=floored_second, microsecond=0)


# compute_p95() beregner cirka 95-percentilen for en liste af tal.
# Den bruges af metrics.py til p95_latency_ms.
# p95 betyder at cirka 95% af målingerne ligger på eller under denne værdi.
# Det er nyttigt, fordi p95 viser høje latency-udsving bedre end et almindeligt gennemsnit.
def compute_p95(values):
    # Hvis listen er tom, kan der ikke beregnes p95.
    if not values:
        return None

    # Værdierne sorteres, så percentilen kan findes ud fra placeringen i listen.
    ordered = sorted(values)
    # Finder den position i den sorterede liste, der svarer til 95-percentilen.
    # len(ordered) - 1 bruges fordi listeindeks starter ved 0.
    index = int(round(0.95 * (len(ordered) - 1)))
    # Returnerer p95-værdien som float, så metrics.py kan gemme den som tal i databasen.
    return float(ordered[index])
