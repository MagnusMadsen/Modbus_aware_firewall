# events.py er det sted hvor backend opretter eller opdaterer rækker i events-tabellen.
# En event er en IDS-hændelse, f.eks. ny device, MAC-skift, registerændring, timeout eller aktiv switch-port.
# Denne fil beslutter ikke om noget er farligt. Den får allerede færdigvurderede event-data fra state-laget eller dashboard/ports.py.
# Opgaven her er kun at skrive eventen til databasen og returnere events.id.
# events.id bruges bagefter som den stabile database-reference, så alarm_approvals.event_id kan pege på præcis den event brugeren håndterer i frontend.

# Dataflow for event og alarm approval:
#
# state/manager.py eller en tracker
# └─ opdager en hændelse, f.eks. MAC-skift eller registerændring
#    └─ self.writer.insert_event(...)
#       └─ StorageWriter.insert_event(...)
#          └─ storage/events.py insert_event(...)
#             └─ INSERT/UPDATE i events-tabellen
#                └─ RETURNING id
#                   └─ event_id sendes tilbage til den kode der oprettede eventen
#                      └─ frontend får event_id i API-svaret
#                         └─ bruger godkender/blokerer/ignorerer alarmen
#                            └─ alarm_approvals.event_id gemmes som reference til events.id
#
# Relation i databasen:
# events.id  <── alarm_approvals.event_id
#
# events.id er den tekniske primærnøgle i databasen.
# event_key er den logiske nøgle, der bruges til at genkende samme hændelse igen.
# alarm_approvals.event_id bruges til at dokumentere præcis hvilken event brugeren har håndteret.

from psycopg2.extras import Json

from storage.base import query_one


# insert_event() er den fælles funktion til at gemme IDS-events.
# Trackerne kalder funktionen, når de har fundet noget der skal vises i dashboardet.
# event_key er en fast tekstnøgle for samme logiske hændelse.
# Eksempel: register_value_changed:192.168.61.22:1:holding_register:9 betyder samme register på samme slave/unit hver gang.
# Hvis samme event_key kommer igen, opdateres den eksisterende række i stedet for at lave en dublet.
# Hvis event_key er None, kan eventen ikke deduplikeres, og databasen opretter en ny række.
def insert_event(
    event_type,
    severity="info",
    event_key=None,
    status="open",
    source_ip=None,
    target_ip=None,
    unit_id=None,
    function_code=None,
    register_type=None,
    register_address=None,
    old_value=None,
    new_value=None,
    details=None,
):
    # SQL'en slutter med RETURNING id.
    # Derfor bruger vi query_one(), så vi får events.id tilbage fra den række der blev oprettet eller opdateret.
    # Det id sendes videre til frontend, og når brugeren håndterer alarmen, gemmes det i alarm_approvals.event_id.
    row = query_one(
        """
        -- Forsøger at oprette en ny event-række.
        INSERT INTO events
            (ts, event_key, event_type, severity, status, source_ip, target_ip, unit_id, function_code,
             register_type, register_address, old_value, new_value, details)
        VALUES
            (NOW(), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        -- Hvis event_key allerede findes, rammer vi samme logiske event og opdaterer den eksisterende række.
        ON CONFLICT (event_key)
        DO UPDATE SET
            ts = NOW(),
            severity = EXCLUDED.severity,
            -- Håndterede events må ikke åbnes igen bare fordi samme hændelse observeres igen.
            status = CASE
                WHEN events.status IN ('approved', 'blocked', 'ignored', 'critical', 'closed') THEN events.status
                ELSE EXCLUDED.status
            END,
            source_ip = EXCLUDED.source_ip,
            target_ip = EXCLUDED.target_ip,
            unit_id = EXCLUDED.unit_id,
            function_code = EXCLUDED.function_code,
            register_type = EXCLUDED.register_type,
            register_address = EXCLUDED.register_address,
            old_value = EXCLUDED.old_value,
            new_value = EXCLUDED.new_value,
            details = EXCLUDED.details
        -- Returnerer primærnøglen events.id til backend/frontend-flowet.
        RETURNING id
        """,
        (
            # Værdierne sendes som SQL-parametre, ikke som tekst direkte ind i SQL-strengen.
            # old_value/new_value laves til tekst, fordi events kan handle om både tal, MAC, roller og andre værdier.
            # details gemmes som JSONB til ekstra forklaring, der varierer fra eventtype til eventtype.
            event_key,
            event_type,
            severity,
            status,
            source_ip,
            target_ip,
            unit_id,
            function_code,
            register_type,
            register_address,
            None if old_value is None else str(old_value),
            None if new_value is None else str(new_value),
            Json(details or {}),
        ),
    )

    # Returnerer events.id til den kode der oprettede eventen.
    # Det er koblingen frontend senere bruger til alarm_approvals.event_id.
    return row["id"] if row else None
