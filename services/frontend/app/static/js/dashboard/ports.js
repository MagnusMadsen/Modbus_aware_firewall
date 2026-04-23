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


function renderDevice(device) {
    const unitText = (device.unit_ids && device.unit_ids.length)
        ? ` | unit ${device.unit_ids.join(", ")}`
        : "";

    return `
        <div class="port-device">
            <div class="port-device-top">
                <strong>${device.label || "Device"}</strong>
                <span class="badge ${device.role || "inactive"}">${device.role || "unknown"}</span>
            </div>
            <p>${device.ip || "-"}</p>
            <p>${device.mac || "-"}${unitText}</p>
        </div>
    `;
}

export function renderPorts(container, dashboardData) {
    const ports = dashboardData.ports || [];

    if (!ports.length) {
        container.innerHTML = `<div class="chart-empty-state">No switch port data available.</div>`;
        return;
    }

    container.innerHTML = ports.map((port) => {
        const devices = port.devices || [];
        const devicesHtml = devices.length
            ? `<div class="port-devices">${devices.map(renderDevice).join("")}</div>`
            : `<div class="port-devices-empty">No mapped device</div>`;

        return `
            <div class="port-card ${port.state || "inactive"}">
                <div class="port-head">
                    <div>
                        <h4>${port.port}</h4>
                        <p>${port.name || "-"}</p>
                    </div>
                    <span class="badge ${port.state || "inactive"}">${port.state || "inactive"}</span>
                </div>
                <p><strong>Speed:</strong> ${port.speed || "-"}</p>
                <p><strong>Activity:</strong> ${port.activity || "-"}</p>
                ${devicesHtml}
            </div>
        `;
    }).join("");
}
