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

export async function fetchPendingAlerts() {
    const response = await fetch("/api/alerts/pending", {
        cache: "no-store",
    });

    if (!response.ok) {
        throw new Error(`Pending alerts fetch failed with status ${response.status}`);
    }

    return response.json();
}

export async function fetchAlertHistory() {
    const response = await fetch("/api/alerts/history", {
        cache: "no-store",
    });

    if (!response.ok) {
        throw new Error(`Alert history fetch failed with status ${response.status}`);
    }

    return response.json();
}

export async function handleBackendAlert(alertId, action) {
    const response = await fetch(`/api/alerts/${alertId}/handle`, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
        },
        cache: "no-store",
        body: JSON.stringify({ action }),
    });

    if (!response.ok) {
        const errorBody = await response.json().catch(() => ({}));
        throw new Error(errorBody.error || `Alert ${action} failed with status ${response.status}`);
    }

    return response.json();
}

// Legacy compatibility helpers. The active dashboard flow uses /api/alerts/*.
export async function saveAlertApproval(payload) {
    const response = await fetch("/api/alert-approvals", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
        },
        cache: "no-store",
        body: JSON.stringify(payload),
    });

    if (!response.ok) {
        throw new Error(`Alert approval save failed with status ${response.status}`);
    }

    return response.json();
}

export async function fetchAlertApprovals() {
    const response = await fetch("/api/alert-approvals", {
        cache: "no-store",
    });

    if (!response.ok) {
        throw new Error(`Alert approvals fetch failed with status ${response.status}`);
    }

    return response.json();
}
