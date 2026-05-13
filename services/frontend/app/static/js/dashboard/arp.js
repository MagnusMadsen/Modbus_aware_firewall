import { escapeHtml } from "./utils.js";

function formatArpTitle(event) {
    return event.type || "ARP event";
}

function formatArpDetails(event) {
    return event.details || "-";
}

export function renderArp(elements, dashboardData) {
    const arp = dashboardData.arp_monitor || {};
    const events = arp.events || [];
    const criticalPairs = arp.critical_pairs || [];

    elements.statusBadge.textContent = arp.status || "Normal";
    elements.statusBadge.className = `badge ${(arp.status || "normal").toLowerCase()}`;
    elements.summary.textContent = arp.summary || "-";
    elements.expected.textContent = arp.gateway_expected_mac || "-";
    elements.seen.textContent = arp.gateway_seen_mac || "-";

    if (!criticalPairs.length) {
        elements.criticalPairs.innerHTML = `
            <tr>
                <td colspan="5" class="arp-empty-row">No pinned ARP pairs configured.</td>
            </tr>
        `;
    } else {
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

    const visibleEvents = events.slice(0, 4);

    if (!visibleEvents.length) {
        elements.eventList.innerHTML = `
            <div class="arp-empty-state">No ARP anomalies detected.</div>
        `;
        return;
    }

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