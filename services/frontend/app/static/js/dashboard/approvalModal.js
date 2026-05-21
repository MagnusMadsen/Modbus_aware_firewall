import { fetchPendingAlerts, handleBackendAlert } from "./api.js";
import { invalidateApprovalLogCache } from "./approvalLog.js";
import { escapeHtml } from "./utils/html.js";

let activeAlertId = null;
let pendingAlertsCache = [];
let lastFetchAt = 0;
const CACHE_MS = 5000;

export function invalidatePendingAlertsCache() {
    pendingAlertsCache = [];
    lastFetchAt = 0;
}

async function loadPendingAlerts() {
    const now = Date.now();

    if (pendingAlertsCache.length && now - lastFetchAt < CACHE_MS) {
        return pendingAlertsCache;
    }

    pendingAlertsCache = await fetchPendingAlerts();
    lastFetchAt = now;
    return pendingAlertsCache;
}

export async function renderApprovalModal(_dashboardData, onHandled) {
    const root = document.getElementById("approval-modal-root");
    if (!root) return;

    let alerts = [];
    try {
        alerts = await loadPendingAlerts();
    } catch (error) {
        console.error("Pending alerts fetch failed", error);
        return;
    }

    const alert = Array.isArray(alerts) ? alerts[0] : null;

    if (!alert) {
        root.innerHTML = "";
        activeAlertId = null;
        return;
    }

    if (activeAlertId === alert.id) {
        return;
    }

    activeAlertId = alert.id;
    const details = normalizeDetails(alert.details);

    root.innerHTML = `
        <div class="approval-overlay visible">
            <div class="approval-modal" role="dialog" aria-modal="true">
                <h2>${escapeHtml(alert.title)}</h2>

                <p class="approval-message">
                    ${escapeHtml(alert.message || "Alarm requires user review.")}
                </p>

                <div class="approval-details">
                    ${details.map((item) => `
                        <div class="approval-detail">
                            <span>${escapeHtml(item.label)}</span>
                            <strong>${escapeHtml(item.value)}</strong>
                        </div>
                    `).join("")}
                </div>

                <div class="approval-actions">
                    <button class="approval-approve" data-action="approve">GODKEND</button>
                    <button class="approval-block" data-action="block">BLOKER / KRITISK</button>
                    <button class="approval-ignore" data-action="ignore">IGNORER</button>
                </div>
            </div>
        </div>
    `;

    root.querySelector("[data-action='approve']").addEventListener("click", async () => {
        await handleAlert(alert.id, "approve");
        activeAlertId = null;
        onHandled();
    });

    root.querySelector("[data-action='block']").addEventListener("click", async () => {
        await handleAlert(alert.id, "block");
        activeAlertId = null;
        onHandled();
    });

    root.querySelector("[data-action='ignore']").addEventListener("click", async () => {
        await handleAlert(alert.id, "ignore");
        activeAlertId = null;
        onHandled();
    });
}

async function handleAlert(alertId, action) {
    await handleBackendAlert(alertId, action);
    invalidatePendingAlertsCache();
    invalidateApprovalLogCache();
}

function normalizeDetails(details) {
    const normalized = [];

    if (!details || typeof details !== "object" || Array.isArray(details)) {
        return normalized;
    }

    Object.entries(details)
        .filter(([, value]) => value !== null && value !== undefined && value !== "")
        .slice(0, 8)
        .forEach(([key, value]) => {
            normalized.push({
                label: key.replaceAll("_", " "),
                value: String(value),
            });
        });

    return normalized;
}
