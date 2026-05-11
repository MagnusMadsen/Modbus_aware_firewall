import { escapeHtml } from "./utils.js";

export function renderEvents(eventList, dashboardData, onEventClick) {
    const events = dashboardData.events || [];

    eventList.innerHTML = events.map(event => {
        const severity = String(event.severity || "info").toLowerCase();
        const pinnedClass = event.is_pinned ? " pinned" : "";
        const pinnedLabel = event.is_pinned ? `<span class="event-pin">PINNED</span>` : "";

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

    eventList.querySelectorAll(".chart-focus-event").forEach(item => {
        item.style.cursor = "pointer";
        item.addEventListener("click", () => {
            const time = item.dataset.eventTime;
            onEventClick(time);
        });
    });
}


