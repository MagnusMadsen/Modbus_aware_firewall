import { escapeHtml } from "./utils.js";

export function renderPorts(portsGrid, dashboardData) {
    const ports = dashboardData.ports || [];

    portsGrid.innerHTML = ports.map(port => `
        <div class="port-card ${escapeHtml(port.state)}">
            <div class="port-head">
                <strong>${escapeHtml(port.port)}</strong>
                <span class="badge ${escapeHtml(port.state)}">${escapeHtml(port.state)}</span>
            </div>
            <h4>${escapeHtml(port.name)}</h4>
            <p>Speed: ${escapeHtml(port.speed)}</p>
            <p>Activity: ${escapeHtml(port.activity)}</p>
        </div>
    `).join("");
}

