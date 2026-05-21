import { fetchAlertApprovals } from "./api.js";
import { getApprovalLogEntries } from "./alertStore.js";
import { escapeHtml } from "./utils/html.js";

function normalizeEntry(entry) {
    return {
        title: entry.title || "-",
        handledAt: entry.handled_at || entry.handledAt || "-",
        type: entry.alert_type || entry.type || "-",
        status: entry.status || "-",
        action: entry.action || "-",
        message: entry.message || "-",
        details: Array.isArray(entry.details) ? entry.details : [],
    };
}

export async function renderApprovalLog(container) {
    if (!container) return;

    let entries = [];

    try {
        entries = await fetchAlertApprovals();
    } catch (error) {
        console.error("Approval log fetch failed, using local fallback", error);
        entries = getApprovalLogEntries();
    }

    if (!Array.isArray(entries) || !entries.length) {
        container.innerHTML = `
            <div class="approval-log-empty">
                Ingen alarmgodkendelser endnu.
            </div>
        `;
        return;
    }

    container.innerHTML = entries.map((rawEntry) => {
        const entry = normalizeEntry(rawEntry);

        const detailText = entry.details
            .slice(0, 2)
            .map((item) => `${item.label}: ${item.value}`)
            .join(" | ");

        return `
            <div class="approval-log-item">
                <div>
                    <strong>${escapeHtml(entry.title)}</strong>
                    <span>${escapeHtml(entry.handledAt)}</span>
                </div>

                <div>
                    <strong>${escapeHtml(entry.type)}</strong>
                    <span>${escapeHtml(detailText || entry.message)}</span>
                </div>

                <div>
                    <span class="approval-log-status ${escapeHtml(entry.status)}">
                        ${escapeHtml(entry.status)}
                    </span>
                </div>

                <div>
                    <strong>Handling</strong>
                    <span>${escapeHtml(entry.action)}</span>
                </div>
            </div>
        `;
    }).join("");
}