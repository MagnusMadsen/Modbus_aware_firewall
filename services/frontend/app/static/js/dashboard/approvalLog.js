import { fetchAlertHistory } from "./api.js";
import { escapeHtml } from "./utils/html.js";

let cachedEntries = [];
let lastFetchAt = 0;
const CACHE_MS = 10000;

export function invalidateApprovalLogCache() {
    cachedEntries = [];
    lastFetchAt = 0;
}

async function loadAlertHistory() {
    const now = Date.now();

    if (cachedEntries.length && now - lastFetchAt < CACHE_MS) {
        return cachedEntries;
    }

    cachedEntries = await fetchAlertHistory();
    lastFetchAt = now;
    return cachedEntries;
}

function normalizeEntry(entry) {
    return {
        title: entry.title || "-",
        handledAt: entry.handled_at || entry.updated_at || entry.created_at || "-",
        type: entry.alert_type || "-",
        status: entry.status || "-",
        action: entry.action || "-",
        message: entry.message || "-",
        details: entry.details && typeof entry.details === "object" ? entry.details : {},
    };
}

export async function renderApprovalLog(container) {
    if (!container) return;

    let entries = [];

    try {
        entries = await loadAlertHistory();
    } catch (error) {
        console.error("Alert history fetch failed", error);
        entries = [];
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
        const detailText = formatDetails(entry.details);

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

function formatDetails(details) {
    if (!details || typeof details !== "object" || Array.isArray(details)) {
        return "";
    }

    return Object.entries(details)
        .filter(([, value]) => value !== null && value !== undefined && value !== "")
        .slice(0, 2)
        .map(([key, value]) => `${key}: ${value}`)
        .join(" | ");
}
