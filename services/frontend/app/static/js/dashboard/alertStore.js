const APPROVAL_LOG_KEY = "approval-log";

export function isAlertAcknowledged(alertKey) {
    return Boolean(localStorage.getItem(getAckKey(alertKey)));
}

export function acknowledgeAlert(alertKey) {
    localStorage.setItem(getAckKey(alertKey), new Date().toISOString());
}

export function saveApprovalLogEntry(alert, action) {
    const entries = getApprovalLogEntries();

    const entry = {
        id: `${alert.key}:${Date.now()}`,
        alertKey: alert.key,
        type: alert.type,
        title: alert.title,
        message: alert.message,
        status: mapActionToStatus(action),
        action,
        details: alert.details || [],
        handledAt: new Date().toLocaleString(),
    };

    const updated = [entry, ...entries].slice(0, 50);
    localStorage.setItem(APPROVAL_LOG_KEY, JSON.stringify(updated));
}

export function getApprovalLogEntries() {
    try {
        return JSON.parse(localStorage.getItem(APPROVAL_LOG_KEY) || "[]");
    } catch {
        return [];
    }
}

function getAckKey(alertKey) {
    return `ack:${alertKey}`;
}

function mapActionToStatus(action) {
    if (action === "approve") return "approved";
    if (action === "block") return "blocked";
    if (action === "ignore") return "ignored";
    if (action === "critical") return "critical";
    return "handled";
}