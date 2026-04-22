import { escapeHtml } from "./utils.js";

export function renderArp(elements, dashboardData) {
    const arp = dashboardData.arp_monitor || {};

    elements.statusBadge.textContent = arp.status || "Normal";
    elements.statusBadge.className = `badge ${(arp.status || "normal").toLowerCase()}`;
    elements.summary.textContent = arp.summary || "-";
    elements.expected.textContent = arp.gateway_expected_mac || "-";
    elements.seen.textContent = arp.gateway_seen_mac || "-";

    elements.criticalPairs.innerHTML = (arp.critical_pairs || []).map(item => `
        <tr>
            <td>${escapeHtml(item.label)}</td>
            <td>${escapeHtml(item.ip)}</td>
            <td>${escapeHtml(item.expected_mac)}</td>
            <td>${escapeHtml(item.seen_mac)}</td>
            <td><span class="badge ${escapeHtml(item.state)}">${escapeHtml(item.state)}</span></td>
        </tr>
    `).join("");

    elements.eventList.innerHTML = (arp.events || []).map(event => `
        <div class="arp-event-item">
            <div class="event-top">
                <strong>${escapeHtml(event.type)}</strong>
                <span class="badge ${escapeHtml(event.severity)}">${escapeHtml(event.severity)}</span>
            </div>
            <p>${escapeHtml(event.details)}</p>
            <small>${escapeHtml(event.time)}</small>
        </div>
    `).join("");
}

