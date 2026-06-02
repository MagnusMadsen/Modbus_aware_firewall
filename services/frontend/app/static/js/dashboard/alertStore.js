let approvedAlarmKeys = new Set();
let approvalLogEntries = [];


export function hydrateApprovalStore(dashboardData) {
    approvedAlarmKeys = new Set(
        (dashboardData.approved_alarm_keys || []).map((key) => String(key))
    );

    approvalLogEntries = (dashboardData.alarm_approvals || []).map((entry) => ({
        id: entry.id,
        alertKey: entry.alarm_key,
        type: entry.alarm_type,
        title: entry.details?.title || entry.alarm_type,
        message: entry.details?.message || "-",
        status: entry.status,
        action: entry.action,
        details: entry.details?.details || [],
        handledBy: entry.handled_by,
        handledAt: entry.handled_at,
    }));
}s


export function isAlertAcknowledged(alertKey) {
    return approvedAlarmKeys.has(String(alertKey));
}


export function acknowledgeAlert(alertKey) {
    approvedAlarmKeys.add(String(alertKey));
}


export function buildApprovalPayload(alert, action) {
    return {
        alarm_key: alert.key,
        alarm_type: alert.type,
        action,
        event_id: alert.eventId || null,
        details: {
            title: alert.title,
            message: alert.message,
            details: alert.details || [],
        },
    };
}


export function saveApprovalLogEntry(alert, action) {
    const entry = {
        id: `${alert.key}:${Date.now()}`,
        alertKey: alert.key,
        type: alert.type,
        title: alert.title,
        message: alert.message,
        status: mapActionToStatus(action),
        action,
        details: alert.details || [],
        handledBy: "Gemmes i SQL...",
        handledAt: new Date().toLocaleString(),
    };

    approvalLogEntries = [entry, ...approvalLogEntries].slice(0, 50);
}


export function getApprovalLogEntries() {
    return approvalLogEntries;
}


function mapActionToStatus(action) {
    if (action === "approve") return "approved";
    if (action === "block") return "blocked";
    if (action === "ignore") return "ignored";
    if (action === "critical") return "critical";
    return "handled";
}