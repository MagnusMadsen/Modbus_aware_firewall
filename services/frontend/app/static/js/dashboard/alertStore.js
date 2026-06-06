// alertStore.js holder frontendens lokale overblik over håndterede alarmer.
// Backend/database er stadig den persistente kilde: alarm_approvals-tabellen gemmer brugerens beslutninger.
// Denne fil bruger data fra dashboardData.approved_alarm_keys og dashboardData.alarm_approvals, som kommer fra backend /api/dashboard.
// Formålet er at frontend hurtigt kan afgøre om en alert allerede er håndteret, og vise en lokal approval-log i dashboardet.
// Når brugeren håndterer en ny alert, bygges payload her, men selve gemningen sker via frontend main.py -> backend /api/alarm-approvals -> PostgreSQL.

// Dataflow:
// Backend /api/dashboard
// └─ sender approved_alarm_keys og alarm_approvals
//    └─ frontend main.py leverer dashboardData til browseren
//       └─ hydrateApprovalStore(dashboardData)
//          ├─ approvedAlarmKeys bruges til isAlertAcknowledged(alertKey)
//          └─ approvalLogEntries bruges til historikvisning i frontend
//
// Ved ny alarmbeslutning:
// alert modal
// └─ buildApprovalPayload(alert, action)
//    └─ payload sendes til backend /api/alarm-approvals
//       └─ backend gemmer i alarm_approvals og opdaterer events.status

// approvedAlarmKeys er et Set med alarm-keys som allerede er håndteret.
// Set bruges fordi opslag med has() er hurtigt og simpelt.
// Data bliver indlæst fra backend via hydrateApprovalStore().
let approvedAlarmKeys = new Set();

// approvalLogEntries er frontendens liste til visning af seneste alarmbeslutninger.
// Listen kommer primært fra backendens alarm_approvals-data.
let approvalLogEntries = [];

// hydrateApprovalStore() indlæser approval-state fra dashboardData.
// Funktionen kaldes når dashboardet modtager data fra backend.
// Den overskriver lokale værdier med backendens nyeste approved_alarm_keys og alarm_approvals.
// Det betyder at frontendens lokale state synkroniseres med databasen via backend-data.
export function hydrateApprovalStore(dashboardData) {
    // approved_alarm_keys er en simpel liste af keys fra backend.
    // Den laves om til et Set, så isAlertAcknowledged() hurtigt kan slå keys op.
    approvedAlarmKeys = new Set(
        (dashboardData.approved_alarm_keys || []).map((key) => String(key))
    );

    // alarm_approvals fra backend normaliseres til det format frontendens logvisning forventer.
    approvalLogEntries = (dashboardData.alarm_approvals || []).map((entry) => ({
        id: entry.id,
        alertKey: entry.alarm_key,
        eventId: entry.event_id,
        type: entry.alarm_type,
        title: entry.details?.title || entry.alarm_type,
        message: entry.details?.message || "-",
        status: entry.status,
        action: entry.action,
        details: entry.details?.details || [],
        handledBy: entry.handled_by,
        handledAt: entry.handled_at,
    }));
}

// isAlertAcknowledged() bruges af alertRules.js.
// Den afgør om en alert-key allerede er håndteret, så samme alarm ikke vises igen som modal.
export function isAlertAcknowledged(alertKey) {
    // alertKey konverteres til string, så sammenligningen er ens uanset om key kommer som tal eller tekst.
    return approvedAlarmKeys.has(String(alertKey));
}

// acknowledgeAlert() markerer en alert som håndteret lokalt med det samme.
// Det forhindrer at samme modal vises igen før næste fulde synkronisering med backend.
// Den permanente gemning sker stadig i backend via alarm_approvals.
export function acknowledgeAlert(alertKey) {
    approvedAlarmKeys.add(String(alertKey));
}

// buildApprovalPayload() bygger det JSON-payload der sendes til backend /api/alarm-approvals.
// alert kommer fra alertRules.js/modal-flowet.
// action er brugerens valg, f.eks. approve, block, ignore eller critical.
// Payloaden kobles til backendens events-tabel med event_id.
export function buildApprovalPayload(alert, action) {
    // Uden eventId kan backend ikke koble brugerens beslutning til en konkret events.id.
    if (!alert.eventId) {
        throw new Error("Cannot build approval payload without eventId");
    }

    // Feltnavnene matcher backendens forventede alarm approval payload.
    return {
        alarm_key: alert.key,
        alarm_type: alert.type,
        action,
        event_id: alert.eventId,
        details: {
            title: alert.title,
            message: alert.message,
            details: alert.details || [],
        },
    };
}

// saveApprovalLogEntry() tilføjer en ny alarmbeslutning til frontendens lokale logvisning.
// Det giver brugeren hurtig visuel feedback med det samme.
// Den egentlige persistente historik kommer stadig fra alarm_approvals i databasen ved næste backend-sync.
export function saveApprovalLogEntry(alert, action) {
    // entry bygges i samme format som hydrateApprovalStore() bruger til backend-data.
    const entry = {
        id: `${alert.key}:${Date.now()}`,
        alertKey: alert.key,
        eventId: alert.eventId,
        type: alert.type,
        title: alert.title,
        message: alert.message,
        status: mapActionToStatus(action),
        action,
        details: alert.details || [],
        // Midlertidig tekst indtil backend-sync returnerer den rigtige handled_by-værdi.
        handledBy: "Gemmes i SQL...",
        handledAt: new Date().toLocaleString(),
    };

    // Den nye entry lægges øverst, og listen begrænses til 50 for at holde frontend-state lille.
    approvalLogEntries = [entry, ...approvalLogEntries].slice(0, 50);
}

// getApprovalLogEntries() returnerer den aktuelle lokale approval-log til UI-komponenter.
export function getApprovalLogEntries() {
    return approvalLogEntries;
}

// mapActionToStatus() oversætter brugerens handling til den status backend/database bruger.
// Eksempel: action approve bliver status approved.
function mapActionToStatus(action) {
    if (action === "approve") return "approved";
    if (action === "block") return "blocked";
    if (action === "ignore") return "ignored";
    if (action === "critical") return "critical";
    // Fallback hvis der kommer en ukendt action. Backendens validering/constraints bør stadig afvise ugyldige statusser.
    return "handled";
}