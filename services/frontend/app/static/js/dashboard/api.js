const DASHBOARD_API_URL = "/api/live-dashboard";

export async function fetchDashboardData() {
    const response = await fetch(DASHBOARD_API_URL, { cache: "no-store" });
    if (!response.ok) {
        throw new Error(`Dashboard fetch failed with status ${response.status}`);
    }
    return response.json();
}


export async function approveDevice(deviceId, payload = {}) {
    return postDeviceAction(deviceId, "approve", payload);
}

export async function blockDevice(deviceId, payload = {}) {
    return postDeviceAction(deviceId, "block", payload);
}

export async function ignoreDevice(deviceId, payload = {}) {
    return postDeviceAction(deviceId, "ignore", payload);
}

async function postDeviceAction(deviceId, action, payload = {}) {
    const response = await fetch(`/api/devices/${deviceId}/${action}`, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
        },
        cache: "no-store",
        body: JSON.stringify(payload),
    });

    if (!response.ok) {
        const errorBody = await response.json().catch(() => ({}));
        throw new Error(errorBody.error || `Device ${action} failed with status ${response.status}`);
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


export async function fetchAlarmApprovals() {
    const response = await fetch("/api/alarm-approvals", {
        cache: "no-store",
    });

    if (!response.ok) {
        throw new Error(`Alarm approvals fetch failed with status ${response.status}`);
    }

    return response.json();
}


export async function saveAlarmApproval(payload) {
    const response = await fetch("/api/alarm-approvals", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
        },
        cache: "no-store",
        body: JSON.stringify(payload),
    });

    if (!response.ok) {
        const errorBody = await response.json().catch(() => ({}));
        throw new Error(errorBody.error || `Alarm approval save failed with status ${response.status}`);
    }

    return response.json();
}


