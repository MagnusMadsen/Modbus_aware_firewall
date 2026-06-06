// arp.js renderer ARP-sektionen i dashboardet.
// Data kommer fra dashboardData.arp_monitor, som frontend modtager fra backend via /api/live-dashboard.
// Backend har allerede samlet ARP-status, pinned/critical ARP pairs og ARP-events.
// Denne fil vurderer ikke selv ARP-trafik og skriver ikke til backend eller databasen.
// Den omsætter kun ARP-data til synlig HTML i dashboardet.


// Dataflow:
// backend /api/dashboard
// └─ arp_monitor
//    └─ frontend main.js henter dashboardData
//       └─ renderArp(elements, dashboardData)
//          ├─ opdaterer status, summary, expected MAC og seen MAC
//          ├─ viser critical/pinned ARP pairs i tabel
//          └─ viser de seneste ARP-events i eventlisten

import { escapeHtml } from "./utils.js";

// formatArpTitle() vælger titlen der vises for en ARP-event.
// Hvis backend ikke har sendt en type, bruges en neutral fallback-titel.
function formatArpTitle(event) {
    return event.type || "ARP event";
}

// formatArpDetails() vælger detailteksten for en ARP-event.
// Hvis backend ikke har sendt details, vises "-".
function formatArpDetails(event) {
    return event.details || "-";
}

// renderArp() opdaterer hele ARP-kortet i dashboardet.
// elements indeholder DOM-referencer til ARP-sektionens HTML-elementer.
// dashboardData indeholder de nyeste data hentet fra backend.
export function renderArp(elements, dashboardData) {
    // Hvis arp_monitor mangler, bruges et tomt objekt så renderingen ikke fejler.
    const arp = dashboardData.arp_monitor || {};
    // events er ARP-hændelser som backend allerede har fundet og sendt med dashboardData.
    const events = arp.events || [];
    // critical_pairs er de ARP/IP/MAC-par backend vil fremhæve som vigtige i tabellen.
    const criticalPairs = arp.critical_pairs || [];

    // Opdaterer de simple statusfelter øverst i ARP-sektionen.
    elements.statusBadge.textContent = arp.status || "Normal";
    elements.statusBadge.className = `badge ${(arp.status || "normal").toLowerCase()}`;
    elements.summary.textContent = arp.summary || "-";
    elements.expected.textContent = arp.gateway_expected_mac || "-";
    elements.seen.textContent = arp.gateway_seen_mac || "-";

    // Hvis der ikke er pinned/critical ARP pairs, vises en tom-række i tabellen.
    if (!criticalPairs.length) {
        elements.criticalPairs.innerHTML = `
            <tr>
                <td colspan="5" class="arp-empty-row">No pinned ARP pairs configured.</td>
            </tr>
        `;
    } else {
        // Bygger én tabelrække pr. critical ARP pair.
        // escapeHtml() sikrer at tekst fra backend vises som tekst og ikke som rå HTML.
        elements.criticalPairs.innerHTML = criticalPairs.map(item => `
            <tr>
                <td>${escapeHtml(item.label)}</td>
                <td>${escapeHtml(item.ip)}</td>
                <td>${escapeHtml(item.expected_mac)}</td>
                <td>${escapeHtml(item.seen_mac)}</td>
                <td><span class="badge ${escapeHtml(item.state)}">${escapeHtml(item.state)}</span></td>
            </tr>
        `).join("");
    }

    // Viser kun de første fire ARP-events, så sektionen ikke bliver for lang.
    const visibleEvents = events.slice(0, 4);

    // Hvis backend ikke har sendt ARP-events, vises en normal tom-tilstand.
    if (!visibleEvents.length) {
        elements.eventList.innerHTML = `
            <div class="arp-empty-state">No ARP anomalies detected.</div>
        `;
        return;
    }

    // Bygger eventlisten med titel, details, tidspunkt og severity for hver ARP-event.
    elements.eventList.innerHTML = visibleEvents.map(event => `
        <div class="arp-event-row">
            <div class="arp-event-main">
                <strong>${escapeHtml(formatArpTitle(event))}</strong>
                <p>${escapeHtml(formatArpDetails(event))}</p>
                <small>${escapeHtml(event.time || "-")}</small>
            </div>
            <span class="badge ${escapeHtml(event.severity || "high")}">
                ${escapeHtml(event.severity || "high")}
            </span>
        </div>
    `).join("");
}