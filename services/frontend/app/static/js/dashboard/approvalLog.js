const APPROVAL_LOG_KEY = "approval-log";

export function saveApprovalLogEntry(alert, action) {
    const entries = getApprovalLogEntries();

    const status = mapActionToStatus(action);

    const entry = {
        id: `${alert.key}:${Date.now()}`,
        alertKey: alert.key,
        type: alert.type,
        title: alert.title,
        message: alert.message,
        status,
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

export function renderApprovalLog(container) {
    if (!container) return;

    const entries = getApprovalLogEntries();

    if (!entries.length) {
        container.innerHTML = `
            <div class="approval-log-empty">
                Ingen alarmgodkendelser endnu.
            </div>
        `;
        return;
    }

    container.innerHTML = entries.map((entry) => {
        const detailText = (entry.details || [])
            .slice(0, 2)
            .map((item) => `${item.label}: ${item.value}`)
            .join(" | ");

        return `
            <div class="approval-log-item">
                <div>
                    <strong>${escapeHtml(entry.title || "-")}</strong>
                    <span>${escapeHtml(entry.handledAt || "-")}</span>
                </div>

                <div>
                    <strong>${escapeHtml(entry.type || "-")}</strong>
                    <span>${escapeHtml(detailText || entry.message || "-")}</span>
                </div>

                <div>
                    <span class="approval-log-status ${escapeHtml(entry.status)}">
                        ${escapeHtml(entry.status)}
                    </span>
                </div>

                <div>
                    <strong>Handling</strong>
                    <span>${escapeHtml(entry.action || "-")}</span>
                </div>
            </div>
        `;
    }).join("");
}

function mapActionToStatus(action) {
    if (action === "approve") return "approved";
    if (action === "block") return "blocked";
    if (action === "ignore") return "ignored";
    if (action === "critical") return "critical";
    return "handled";
}

function escapeHtml(value) {
    return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}