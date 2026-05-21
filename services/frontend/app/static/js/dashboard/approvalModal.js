import { approveDevice, blockDevice, ignoreDevice, saveAlertApproval } from "./api.js";
import { acknowledgeAlert, saveApprovalLogEntry } from "./alertStore.js";
import { escapeHtml } from "./utils/html.js";
import { findNextAlert } from "./alertRules.js";

let activeAlertKey = null;

export function renderApprovalModal(dashboardData, onHandled) {
    const root = document.getElementById("approval-modal-root");
    if (!root) return;

    const alert = findNextAlert(dashboardData);

    if (!alert) {
        root.innerHTML = "";
        activeAlertKey = null;
        return;
    }

    if (activeAlertKey === alert.key) {
        return;
    }

    activeAlertKey = alert.key;

    root.innerHTML = `
        <div class="approval-overlay visible">
            <div class="approval-modal" role="dialog" aria-modal="true">
                <h2>${escapeHtml(alert.title)}</h2>

                <p class="approval-message">
                    ${escapeHtml(alert.message)}
                </p>

                <div class="approval-details">
                    ${(alert.details || []).map((item) => `
                        <div class="approval-detail">
                            <span>${escapeHtml(item.label)}</span>
                            <strong>${escapeHtml(item.value)}</strong>
                        </div>
                    `).join("")}
                </div>

                <div class="approval-actions">
                    <button class="approval-approve" data-action="approve">${escapeHtml(alert.approveText)}</button>
                    <button class="approval-block" data-action="block">${escapeHtml(alert.blockText)}</button>
                    <button class="approval-ignore" data-action="ignore">${escapeHtml(alert.ignoreText)}</button>
                </div>
            </div>
        </div>
    `;

    root.querySelector("[data-action='approve']").addEventListener("click", async () => {
        await handleAlert(alert, "approve");
        activeAlertKey = null;
        onHandled();
    });

    root.querySelector("[data-action='block']").addEventListener("click", async () => {
        await handleAlert(alert, "block");
        activeAlertKey = null;
        onHandled();
    });

    root.querySelector("[data-action='ignore']").addEventListener("click", async () => {
        await handleAlert(alert, "ignore");
        activeAlertKey = null;
        onHandled();
    });
}

async function handleAlert(alert, action) {
    saveApprovalLogEntry(alert, action);

    const payload = {
        alert_key: alert.key,
        alert_type: alert.type,
        title: alert.title,
        message: alert.message,
        action,
        details: alert.details || [],
        device_id: alert.deviceId || null,
    };

    if (alert.type === "device" && alert.deviceId) {
        if (action === "approve") await approveDevice(alert.deviceId);
        if (action === "block") await blockDevice(alert.deviceId);
        if (action === "ignore") await ignoreDevice(alert.deviceId);
    }

    await saveAlertApproval(payload);
    acknowledgeAlert(alert.key);
}