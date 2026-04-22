import { escapeHtml } from "./utils.js";

export function renderEvents(eventList, dashboardData, onEventClick) {
    const events = dashboardData.events || [];

    eventList.innerHTML = events.map(event => `
        <div class="event-item chart-focus-event" data-event-time="${escapeHtml((event.time || "").slice(11, 19))}">
            <div class="event-top">
                <strong>${escapeHtml(event.type)}</strong>
                <span>${escapeHtml(event.time)}</span>
            </div>
            <p>${escapeHtml(event.details)}</p>
            <small>${escapeHtml(event.impact)}</small>
        </div>
    `).join("");

    eventList.querySelectorAll(".chart-focus-event").forEach(item => {
        item.style.cursor = "pointer";
        item.addEventListener("click", () => {
            const time = item.dataset.eventTime;
            onEventClick(time);
        });
    });
}

