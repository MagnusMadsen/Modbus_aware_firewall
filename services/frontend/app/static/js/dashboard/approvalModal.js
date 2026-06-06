// approvalModal.js bygger og viser alarm-dialogen i dashboardet.
// Filen får dashboardData fra main.js, finder næste alert via alertRules.js og indsætter dialogens HTML i approval-modal-root.
// Når brugeren trykker approve, block eller ignore, sendes handlingen videre til backend via api.js.
// Device-alerts bruger device endpoints. Andre alerts gemmes som alarm approvals.


// Dataflow:
// main.js
// └─ renderApprovalModal(dashboardData, refreshDashboardData)
//    └─ findNextAlert(dashboardData)
//       ├─ ingen alert -> approval-modal-root tømmes
//       └─ alert fundet -> dialog-HTML indsættes i approval-modal-root
//          └─ bruger vælger approve/block/ignore
//             └─ handleAlert(alert, action)
//                ├─ device alert -> api.js -> backend /api/devices/<id>/<action>
//                └─ anden alert -> api.js -> backend /api/alarm-approvals
//                   └─ backend gemmer beslutningen og dashboardet henter nye data


import { approveDevice, blockDevice, ignoreDevice, saveAlarmApproval } from "./api.js";
import {
    acknowledgeAlert,
    buildApprovalPayload,
    saveApprovalLogEntry,
} from "./alertStore.js";
import { escapeHtml } from "./utils/html.js";
import { findNextAlert } from "./alertRules.js";

// activeAlertKey husker hvilken alert der vises lige nu.
// Det forhindrer at samme dialog bliver renderet igen ved hver dashboard-refresh.
let activeAlertKey = null;

// renderApprovalModal() kaldes fra main.js, når dashboardet har nye data.
// Funktionen finder næste alert, bygger dialogens HTML og kobler knapperne til handleAlert().
// onHandled kaldes efter en brugerhandling, så dashboardet kan hente opdaterede data.
export function renderApprovalModal(dashboardData, onHandled) {
    // approval-modal-root er containeren i dashboard.html hvor dialogens HTML indsættes.
    const root = document.getElementById("approval-modal-root");

    // Uden container kan dialogen ikke renderes.
    if (!root) return;

    // alertRules.js vælger hvilken alert der skal vises først.
    const alert = findNextAlert(dashboardData);

    // Hvis der ikke er en alert, fjernes dialogen fra siden.
    if (!alert) {
        root.innerHTML = "";
        // Nulstiller aktiv key, så en senere alert kan vises.
        activeAlertKey = null;
        return;
    }

    // Hvis samme alert allerede vises, renderes dialogen ikke igen.
    if (activeAlertKey === alert.key) {
        return;
    }

    // Gemmer hvilken alert der nu er aktiv.
    activeAlertKey = alert.key;

    // Bygger dialogens HTML.
    // escapeHtml() sikrer at tekst ikke indsættes som rå HTML.
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

    // Knapperne får event listeners efter HTML'en er indsat.
    // Hver knap sender brugerens valg til handleAlert().
    root.querySelector("[data-action='approve']").addEventListener("click", async () => {
        // Behandler approve-valget.
        await handleAlert(alert, "approve");
        // Tillader at næste alert kan vises efter opdatering.
        activeAlertKey = null;
        // Henter nye dashboard-data via callbacken fra main.js.
        onHandled();
    });

    root.querySelector("[data-action='block']").addEventListener("click", async () => {
        // Behandler block-valget.
        await handleAlert(alert, "block");
        activeAlertKey = null;
        onHandled();
    });

    root.querySelector("[data-action='ignore']").addEventListener("click", async () => {
        // Behandler ignore-valget.
        await handleAlert(alert, "ignore");
        activeAlertKey = null;
        onHandled();
    });
}

// handleAlert() sender brugerens valg videre til backend.
// Device-alerts opdaterer device-status via device endpoints.
// Andre alerts gemmes som alarm approvals.
// alert.eventId svarer til events.id i backend.
async function handleAlert(alert, action) {
    // eventId kræves, fordi handlingen skal kobles til en konkret events-række.
    if (!alert.eventId) {
        console.error("Cannot handle alert without eventId", alert);
        return;
    }

    // Oversætter knapvalg til den action/status backend skal gemme.
    const approvalAction = normalizeApprovalAction(alert, action);

    // Bygger payload til backend-kaldet.
    const approvalPayload = buildApprovalPayload(alert, approvalAction);

    // Device-alerts går til device endpoints.
    if (alert.type === "device" && alert.deviceId) {
        if (action === "approve") await approveDevice(alert.deviceId, approvalPayload);
        if (action === "block") await blockDevice(alert.deviceId, approvalPayload);
        if (action === "ignore") await ignoreDevice(alert.deviceId, approvalPayload);
    } else {
        // Andre alerts går til alarm approvals endpointet.
        await saveAlarmApproval(approvalPayload);
    }

    // Marker alerten som håndteret lokalt, så den ikke vises igen med det samme.
    acknowledgeAlert(alert.key);

    // Tilføjer handlingen til den lokale logvisning indtil næste backend-sync.
    saveApprovalLogEntry(alert, approvalAction);
}

// normalizeApprovalAction() oversætter brugerens knapvalg til backendens forventede action/status.
// Device-alerts bruger approve, block og ignore direkte.
// For generelle alerts betyder block at eventen markeres som critical.
function normalizeApprovalAction(alert, action) {
    // Device endpoints forventer approve, block eller ignore.
    if (alert.type === "device") {
        return action;
    }

    // Generelle alerts bruger critical i stedet for block.
    if (action === "block") {
        return "critical";
    }

    // approve og ignore sendes videre uændret.
    return action;
}