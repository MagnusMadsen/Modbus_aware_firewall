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

export async function fetchCriticalRegisters() {
    const response = await fetch("/api/critical-registers", {
        cache: "no-store",
    });

    if (!response.ok) {
        throw new Error(`Critical registers fetch failed with status ${response.status}`);
    }

    return response.json();
}

export async function saveCriticalRegister(payload) {
    const response = await fetch("/api/critical-registers", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
        },
        cache: "no-store",
        body: JSON.stringify(payload),
    });

    if (!response.ok) {
        const errorBody = await response.json().catch(() => ({}));
        throw new Error(errorBody.error || `Critical register save failed with status ${response.status}`);
    }

    return response.json();
}

export async function deleteCriticalRegister(registerId) {
    const response = await fetch(`/api/critical-registers/${registerId}`, {
        method: "DELETE",
        cache: "no-store",
    });

    if (!response.ok) {
        throw new Error(`Critical register delete failed with status ${response.status}`);
    }

    return response.json();
}


