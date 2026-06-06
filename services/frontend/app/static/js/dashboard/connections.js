// connections.js renderer master/slave-forbindelser i dashboardet.
// Data kommer fra dashboardData.connections, som frontend modtager fra backend via /api/live-dashboard.
// Backend bygger connections-data ud fra observed_connections-tabellen og device-status.
// Den omsætter kun forbindelsesdata til HTML-kort og tabeller i dashboardet.


// Dataflow:
// PostgreSQL observed_connections
// └─ backend /api/dashboard
//    └─ dashboardData.connections
//       └─ renderConnections(connectionGroups, dashboardData)
//          └─ bygger ét connection-group-card pr. master
//             └─ viser slaves, status, packets og last_seen

import { escapeHtml } from "./utils.js";

// renderConnections() tegner forbindelses-sektionen i dashboardet.
// connectionGroups er HTML-containeren hvor forbindelserne skal indsættes.
// dashboardData indeholder den nyeste connections-liste fra backend.
export function renderConnections(connectionGroups, dashboardData) {
    // Hvis backend ikke sender connections, bruges en tom liste så renderingen ikke fejler.
    const connections = dashboardData.connections || [];

    // Bygger ét kort pr. master.
    // Hvert kort viser masterens slaves i en tabel.
    connectionGroups.innerHTML = connections.map(group => `
        <div class="connection-group-card">
            <div class="connection-group-head">
                <div>
                    <!-- Master-IP'en vises som overskrift for connection-gruppen. -->
                    <h4>Master ${escapeHtml(group.master)}</h4>
                    <!-- slave_count er antallet af slaves backend har samlet under denne master. -->
                    <p>${escapeHtml(group.slave_count)} slaves connected</p>
                </div>
                <div class="connection-group-meta">
                    <span>Last seen: ${escapeHtml(group.last_seen)}</span>
                </div>
            </div>
            <div class="table-wrap">
                <table>
                    <thead>
                        <tr>
                            <th>Slave</th>
                            <th>Status</th>
                            <th>Packets</th>
                            <th>Last seen</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${/* Hver slave-række viser IP, status, packet-count og seneste observation. */""}
                        ${(group.slaves || []).map(slave => `
                            <tr>
                                <td>${escapeHtml(slave.ip)}</td>
                                <td><span class="badge ${escapeHtml(slave.status)}">${escapeHtml(slave.status)}</span></td>
                                <td>${escapeHtml(slave.packets)}</td>
                                <td>${escapeHtml(slave.last_seen)}</td>
                            </tr>
                        `).join("")}
                    </tbody>
                </table>
            </div>
        </div>
    `).join("");
}

