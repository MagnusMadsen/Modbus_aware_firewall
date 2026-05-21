import { approveDevice, blockDevice, ignoreDevice, saveAlarmApproval } from "./api.js";
import {
    acknowledgeAlert,
    buildApprovalPayload,
    saveApprovalLogEntry,
} from "./alertStore.js";
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
                    ${alert.details.map((item) => `
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
    const approvalAction = normalizeApprovalAction(alert, action);
    const approvalPayload = buildApprovalPayload(alert, approvalAction);

    if (alert.type === "device" && alert.deviceId) {
        if (action === "approve") await approveDevice(alert.deviceId, approvalPayload);
        if (action === "block") await blockDevice(alert.deviceId, approvalPayload);
        if (action === "ignore") await ignoreDevice(alert.deviceId, approvalPayload);
    } else {
        await saveAlarmApproval(approvalPayload);
    }

    acknowledgeAlert(alert.key);
    saveApprovalLogEntry(alert, approvalAction);
}


function normalizeApprovalAction(alert, action) {
    if (alert.type === "device") {
        return action;
    }

    if (action === "block") {
        return "critical";
    }

    return action;
}