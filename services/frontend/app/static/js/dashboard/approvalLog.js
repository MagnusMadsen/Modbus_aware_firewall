import { getApprovalLogEntries } from "./alertStore.js";
import { escapeHtml } from "./utils/html.js";


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
                    <strong>Bruger</strong>
                    <span>${escapeHtml(entry.handledBy || "-")}</span>
                </div>

                <div>
                    <span class="approval-log-status ${escapeHtml(entry.status || "")}">
                        ${escapeHtml(entry.status || "-")}
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