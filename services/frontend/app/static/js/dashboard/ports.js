// ports.js renderer switch-port oversigten i dashboardet.
// Data kommer fra dashboardData.ports, som frontend modtager via /api/live-dashboard.
// Backend bygger portdata ved at kombinere SNMP-data fra switch_monitor.py med devices og events.
// Den viser kun porte, portstatus og de devices backend har mappet til hver port.


// Dataflow:
// switch_monitor.py + backend dashboard/ports.py
// └─ backend /api/dashboard
//    └─ dashboardData.ports
//       └─ renderPorts(container, dashboardData)
//          ├─ bygger ét port-card pr. switch-port
//          └─ renderDevice(device) viser device-info under porten
import { escapeHtml } from "./utils.js";

// renderDevice() bygger HTML for én device der er mappet til en switch-port.
// Device-data er allerede koblet til porten af backend.
function renderDevice(device) {
    // unit_ids vises kun hvis backend har fundet Modbus unit IDs for devicen.
    const unitText = (device.unit_ids && device.unit_ids.length)
        ? ` | unit ${device.unit_ids.join(", ")}`
        : "";

    // Returnerer HTML-kortet for devicen inde i port-cardet.
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

// renderPorts() tegner hele switch-port sektionen.
// container er HTML-elementet hvor port-kortene indsættes.
// dashboardData indeholder ports-listen fra backend.
export function renderPorts(container, dashboardData) {
    // Hvis backend ikke sender ports, bruges en tom liste så renderingen ikke fejler.
    const ports = dashboardData.ports || [];

    // Hvis der ikke er portdata, vises en tom-tilstand i dashboardet.
    if (!ports.length) {
        container.innerHTML = `<div class="chart-empty-state">No switch port data available.</div>`;
        return;
    }

    // Bygger ét synligt port-card pr. switch-port.
    container.innerHTML = ports.map((port) => {
        // devices er de enheder backend har mappet til denne fysiske port.
        const devices = port.devices || [];
        // Hvis der ikke er mapped devices, vises en neutral tom-tekst under porten.
        const devicesHtml = devices.length
            ? `<div class="port-devices">${devices.map(renderDevice).join("")}</div>`
            : `<div class="port-devices-empty">No mapped device</div>`;

        // Port-cardet viser portnavn, fysisk/interface-navn, state, speed, activity og mapped devices.
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
