// approvalLog.js viser historikken over alarmbeslutninger i dashboardet.
// Databasen gemmer selve historikken i alarm_approvals-tabellen.
// Backend sender historikken til frontend som dashboardData.alarm_approvals.
// alertStore.js holder den data midlertidigt i browseren som approvalLogEntries.
// Denne fil omsætter approvalLogEntries til HTML, så brugeren kan se historikken i dashboardet.
// Filen henter ikke selv data fra backend og skriver ikke noget til databasen.
// Uden denne fil ville data stadig findes i databasen, men approval-loggen ville ikke blive vist på siden.

// Dataflow:
// PostgreSQL alarm_approvals
// └─ backend /api/dashboard
//    └─ dashboardData.alarm_approvals
//       └─ alertStore.js -> approvalLogEntries
//          └─ approvalLog.js -> HTML i approval-log containeren

import { getApprovalLogEntries } from "./alertStore.js";
import { escapeHtml } from "./utils/html.js";

// renderApprovalLog() tegner approval-loggen i dashboardet.
// container er det HTML-element hvor listen skal indsættes.
// Funktionen læser allerede hentet data fra alertStore.js og bygger HTML-rækker ud fra det.
export function renderApprovalLog(container) {
    // Hvis containeren ikke findes på siden, er der ikke noget at rendere.
    if (!container) return;

    // Henter approval-loggen fra browserens lokale alertStore.
    // alertStore blev tidligere fyldt med data fra backend/database.
    const entries = getApprovalLogEntries();

    // Hvis databasen/backend ikke har sendt nogen approvals, vises en forklarende tom-tekst.
    if (!entries.length) {
        // Tom-tilstanden gør det tydeligt at der endnu ikke er nogen håndterede alarmer at vise.
        container.innerHTML = `
            <div class="approval-log-empty">
                Ingen alarmgodkendelser endnu.
            </div>
        `;
        return;
    }

    // Bygger én synlig HTML-række pr. alarmbeslutning.
    container.innerHTML = entries.map((entry) => {
        // Viser kun de første to detail-felter, så hver log-række ikke bliver for lang.
        const detailText = (entry.details || [])
            .slice(0, 2)
            .map((item) => `${item.label}: ${item.value}`)
            .join(" | ");

        // escapeHtml() sikrer at tekst fra backend vises som tekst og ikke som rå HTML.
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