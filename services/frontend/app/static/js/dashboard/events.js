// events.js renderer IDS-hændelser i dashboardets eventliste.
// Data kommer fra dashboardData.events, som frontend modtager fra backend via /api/live-dashboard.
// Backend har allerede oprettet og vurderet eventen med type, severity, details, impact og event_id.
// Den viser events som klikbare HTML-kort og kobler klik på en event til grafens tidsvindue.


// Dataflow:
// PostgreSQL events
// └─ backend /api/dashboard
//    └─ dashboardData.events
//       └─ renderEvents(eventList, dashboardData, onEventClick)
//          ├─ bygger ét HTML-kort pr. event
//          ├─ viser type, severity, pinned-label, details og impact
//          └─ click på event -> onEventClick(eventTime)
//             └─ main/chart-logik centrerer grafen omkring eventens tidspunkt

import { escapeHtml } from "./utils.js";

// renderEvents() tegner eventlisten i dashboardet.
// eventList er containeren hvor event-kortene indsættes.
// dashboardData indeholder events-listen fra backend.
// onEventClick er en callback fra main.js, som bruges til at fokusere grafen på eventens tidspunkt.
export function renderEvents(eventList, dashboardData, onEventClick) {
    // Hvis backend ikke sender events, bruges en tom liste så renderingen ikke fejler.
    const events = dashboardData.events || [];

    // Bygger ét synligt HTML-kort pr. event.
    eventList.innerHTML = events.map(event => {
        // Severity normaliseres til lowercase, så CSS-klasserne bliver ensartede.
        const severity = String(event.severity || "info").toLowerCase();

        // Pinned events får ekstra CSS-klasse og label, så de fremhæves visuelt.
        const pinnedClass = event.is_pinned ? " pinned" : "";
        const pinnedLabel = event.is_pinned ? `<span class="event-pin">PINNED</span>` : "";

        // data-event-time gemmer eventens klokkeslæt, så klik på eventen kan fokusere grafen.
        // escapeHtml() bruges på backend-data, så værdier vises som tekst og ikke som rå HTML.
        return `
            <div class="event-item chart-focus-event severity-${escapeHtml(severity)}${pinnedClass}" data-event-time="${escapeHtml((event.time || "").slice(11, 19))}">
                <div class="event-top">
                    <div>
                        <strong>${escapeHtml(event.type)}</strong>
                        ${pinnedLabel}
                    </div>
                    <span>${escapeHtml(event.time)}</span>
                </div>

                <div class="event-badges">
                    <span class="badge ${escapeHtml(severity)}">${escapeHtml(severity)}</span>
                    ${event.critical_label ? `<span class="badge critical-label">${escapeHtml(event.critical_label)}</span>` : ""}
                </div>

                <p>${escapeHtml(event.details)}</p>
                <small>${escapeHtml(event.impact)}</small>
            </div>
        `;
    }).join("");

    // Efter HTML'en er indsat, kobles click-handlers på alle event-kort.
    eventList.querySelectorAll(".chart-focus-event").forEach(item => {
        // Gør det tydeligt i browseren at event-kortet kan klikkes.
        item.style.cursor = "pointer";
        item.addEventListener("click", () => {
            // Henter eventens klokkeslæt fra data-event-time attributten.
            const time = item.dataset.eventTime;
            // Sender tidspunktet tilbage til main.js, som kan flytte grafens fokus.
            onEventClick(time);
        });
    });
}
