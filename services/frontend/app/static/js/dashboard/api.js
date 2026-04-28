const DASHBOARD_API_URL = "/api/live-dashboard";

export async function fetchDashboardData() {
    const response = await fetch(DASHBOARD_API_URL, { cache: "no-store" });
    if (!response.ok) {
        throw new Error(`Dashboard fetch failed with status ${response.status}`);
    }
    return response.json();
}


export async function approveDevice(deviceId) {
    return postDeviceAction(deviceId, "approve");
}

export async function blockDevice(deviceId) {
    return postDeviceAction(deviceId, "block");
}

export async function ignoreDevice(deviceId) {
    return postDeviceAction(deviceId, "ignore");
}

async function postDeviceAction(deviceId, action) {
    const response = await fetch(`/api/devices/${deviceId}/${action}`, {
        method: "POST",
        cache: "no-store",
    });

    if (!response.ok) {
        throw new Error(`Device ${action} failed with status ${response.status}`);
    }

    return response.json();
}


