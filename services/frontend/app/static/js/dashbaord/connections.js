import { escapeHtml } from "./utils.js";

export function renderConnections(connectionGroups, dashboardData) {
    const connections = dashboardData.connections || [];

    connectionGroups.innerHTML = connections.map(group => `
        <div class="connection-group-card">
            <div class="connection-group-head">
                <div>
                    <h4>Master ${escapeHtml(group.master)}</h4>
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

