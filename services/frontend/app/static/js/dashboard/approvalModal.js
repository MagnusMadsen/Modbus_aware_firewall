import { approveDevice, blockDevice, ignoreDevice } from "./api.js";

let activeDeviceId = null;

export function renderApprovalModal(dashboardData, onHandled) {
    const root = document.getElementById("approval-modal-root");
    if (!root) return;

    const pendingDevice = findPendingDevice(dashboardData);

    if (!pendingDevice) {
        root.innerHTML = "";
        activeDeviceId = null;
        return;
    }

    if (activeDeviceId === pendingDevice.id) {
        return;
    }

    activeDeviceId = pendingDevice.id;

    root.innerHTML = `
        <div class="approval-overlay visible">
            <div class="approval-modal" role="dialog" aria-modal="true">
                <h2>UKENDT ENHED FUNDET</h2>

                <p class="approval-message">
                    En ny enhed er observeret på netværket. Brugeren skal tage stilling,
                    før alarmen fjernes fra dashboardet.
                </p>

                <div class="approval-details">
                    <div class="approval-detail">
                        <span>IP-adresse</span>
                        <strong>${escapeHtml(pendingDevice.ip_address || pendingDevice.ip || "-")}</strong>
                    </div>

                    <div class="approval-detail">
                        <span>MAC-adresse</span>
                        <strong>${escapeHtml(pendingDevice.mac_address || pendingDevice.mac || "-")}</strong>
                    </div>

                    <div class="approval-detail">
                        <span>Først set</span>
                        <strong>${escapeHtml(pendingDevice.first_seen || "-")}</strong>
                    </div>

                    <div class="approval-detail">
                        <span>Status</span>
                        <strong>${escapeHtml(pendingDevice.status || "pending")}</strong>
                    </div>
                </div>

                <div class="approval-actions">
                    <button class="approval-approve" data-action="approve">GODKEND</button>
                    <button class="approval-block" data-action="block">BLOKER</button>
                    <button class="approval-ignore" data-action="ignore">IGNORER</button>
                </div>
            </div>
        </div>
    `;

    root.querySelector("[data-action='approve']").addEventListener("click", async () => {
        await approveDevice(pendingDevice.id);
        activeDeviceId = null;
        onHandled();
    });

    root.querySelector("[data-action='block']").addEventListener("click", async () => {
        await blockDevice(pendingDevice.id);
        activeDeviceId = null;
        onHandled();
    });

    root.querySelector("[data-action='ignore']").addEventListener("click", async () => {
        await ignoreDevice(pendingDevice.id);
        activeDeviceId = null;
        onHandled();
    });
}

function findPendingDevice(dashboardData) {
    const devices = dashboardData.devices || [];
    return devices.find((device) => {
        const status = String(device.status || "").toLowerCase();
        return status === "pending" || status === "unknown";
    });
}

function escapeHtml(value) {
    return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}