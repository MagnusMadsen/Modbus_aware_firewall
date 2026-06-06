# alarm_approvals.py gemmer brugerens håndtering af alarmer.
# Data kommer fra API-routes/frontend, når brugeren godkender, blokerer, ignorerer eller markerer en alarm.
# Denne fil modtager ikke rå packets og vurderer ikke selv om en alarm er farlig.
# Den gemmer kun brugerens beslutning i alarm_approvals-tabellen og opdaterer status på den tilknyttede event i events-tabellen.
# Koblingen mellem alarm_approvals og events sker via event_id -> events.id.
from psycopg2.extras import Json

from storage.base import execute, query_all, query_one


# save_alarm_approval() bruges når frontend sender en alarm-beslutning til backend.
# payload indeholder alarm_key, alarm_type, action, status, handled_by og event_id.
# alarm_key er den logiske nøgle for alarmen i frontend/backend-flowet.
# event_id er den tekniske database-reference til events.id, hvis alarmen kommer fra en konkret event-række.
# Funktionen skriver først brugerens beslutning i alarm_approvals.
# Hvis payload har event_id, opdateres den samme event også i events-tabellen, så dashboardet ved at alarmen er håndteret.
def save_alarm_approval(payload):
    # Første SQL gemmer selve brugerens alarm-beslutning i alarm_approvals.
    execute(
        """
        -- Opretter en ny alarm approval-række.
        INSERT INTO alarm_approvals
            (alarm_key, alarm_type, action, status, handled_by, event_id, details)
        VALUES
            (%s, %s, %s, %s, %s, %s, %s)
        -- Hvis samme alarm_key allerede findes, opdateres den eksisterende approval i stedet for at lave en dublet.
        ON CONFLICT (alarm_key)
        DO UPDATE SET
            alarm_type = EXCLUDED.alarm_type,
            action = EXCLUDED.action,
            status = EXCLUDED.status,
            handled_by = EXCLUDED.handled_by,
            handled_at = NOW(),
            -- Beholder gammelt event_id hvis den nye approval ikke sender event_id med.
            event_id = COALESCE(EXCLUDED.event_id, alarm_approvals.event_id),
            details = EXCLUDED.details
        """,
        # Parametrene bindes separat, så frontend-input ikke sættes direkte ind i SQL-strengen.
        # details gemmes som JSONB, fordi forskellige alarmtyper kan have forskellig ekstra kontekst.
        (
            payload["alarm_key"],
            payload["alarm_type"],
            payload["action"],
            payload["status"],
            payload["handled_by"],
            payload.get("event_id"),
            Json(payload.get("details") or {}),
        ),
    )

    # event_id bruges til at opdatere den konkrete event-række, som alarmen stammer fra.
    event_id = payload.get("event_id")
    # Hvis der ikke er event_id, kan approval stadig gemmes, men der er ingen bestemt events-række at opdatere.
    if event_id is not None:
        # Anden SQL opdaterer status på den tilknyttede event i events-tabellen.
        # Det gør at en håndteret alarm ikke længere står som åben i dashboardet.
        execute(
            """
            -- Opdaterer status på den event som alarm_approvals.event_id peger på.
            UPDATE events
            SET status = %s
            WHERE id = %s
            """,
            (payload["status"], event_id),
        )


# list_alarm_approvals() bruges af API-routes/frontend til at vise tidligere håndterede alarmer.
# Funktionen returnerer alle approvals sorteret med den nyeste håndtering først.
def list_alarm_approvals():
    # query_all() bruges fordi frontend skal have en liste med flere approval-rækker.
    return query_all(
        """
        -- Henter alle gemte alarm approvals til historik/visning.
        SELECT
            id,
            alarm_key,
            alarm_type,
            action,
            status,
            handled_by,
            TO_CHAR(handled_at, 'YYYY-MM-DD HH24:MI:SS') AS handled_at,
            event_id,
            details
        FROM alarm_approvals
        ORDER BY handled_at DESC
        """
    )


# get_alarm_approval() slår én approval op ud fra alarm_key.
# Den bruges når backend/frontend skal vide om en bestemt alarm allerede er håndteret.
# alarm_key bør være unik i alarm_approvals-tabellen.
# Der bruges ikke LIMIT 1, fordi dubletter på alarm_key bør opdages som et database-/schema-problem i stedet for at blive skjult.
def get_alarm_approval(alarm_key):
    # query_one() bruges fordi der forventes højst én approval for en alarm_key.
    return query_one(
        """
        -- Finder approval for én bestemt alarm_key.
        SELECT
            id,
            alarm_key,
            alarm_type,
            action,
            status,
            handled_by,
            TO_CHAR(handled_at, 'YYYY-MM-DD HH24:MI:SS') AS handled_at,
            event_id,
            details
        FROM alarm_approvals
        WHERE alarm_key = %s
        """,
        (alarm_key,),
    )


# get_approved_alarm_keys() bruges af dashboard/service.py til at sende håndterede alarm_keys til frontend.
# Frontend bruger listen til at skjule eller markere alarmer der allerede er approved, blocked, ignored eller critical.
def get_approved_alarm_keys():
    # Henter kun alarm_keys for de statusser der betyder at alarmen allerede er håndteret.
    rows = query_all(
        """
        -- Henter nøgler for alarmer der allerede er håndteret.
        SELECT alarm_key
        FROM alarm_approvals
        WHERE status IN ('approved', 'blocked', 'ignored', 'critical')
        """
    )

    # Konverterer database-rækkerne til en simpel liste af alarm_key-strenge til frontend.
    return [row["alarm_key"] for row in rows]
