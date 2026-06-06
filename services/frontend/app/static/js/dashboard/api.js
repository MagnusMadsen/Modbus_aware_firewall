// api.js samler browserens HTTP-kald til frontendens Flask-endpoints.
// Browseren kalder ikke backend-containeren direkte fra disse funktioner.
// Kaldet går først til frontend Flask, som derefter videresender til backend API'et i services/frontend/app/main.py.
// Derfor er denne fil frontendens lille API-klient mellem JavaScript-koden og frontendens Flask-routes.

// Dataflow:
// Browser JavaScript
// └─ api.js fetch(...)
//    └─ frontend Flask route i main.py
//       └─ requests.* til backend API med X-API-Token
//          └─ backend API-route
//             └─ storage/state/dashboard-lag
//                └─ PostgreSQL eller runtime-state
// Frontend endpoint der returnerer samlet dashboardData til browseren.

const DASHBOARD_API_URL = "/api/live-dashboard";

// fetchDashboardData() henter nyeste dashboardData fra frontendens /api/live-dashboard.
// Frontend main.py henter bagvedliggende data fra backend /api/dashboard og /api/devices.
// Funktionen bruges når dashboardet loader første gang og ved løbende refresh.
export async function fetchDashboardData() {
    // cache: "no-store" sikrer at browseren ikke bruger gamle dashboard-data fra cache.
    const response = await fetch(DASHBOARD_API_URL, { cache: "no-store" });
    // response.ok er false ved HTTP-fejl som 401, 500 eller 502.
    if (!response.ok) {
        throw new Error(`Dashboard fetch failed with status ${response.status}`);
    }
    // Returnerer JSON-data til dashboardets render-funktioner.
    return response.json();
}


// Device actions bruges når brugeren godkender, blokerer eller ignorerer en device i dashboardet.
// deviceId er id'et fra devices-tabellen.
// payload indeholder event_id/alarm-data, så backend kan koble handlingen til en event hvis relevant.
export async function approveDevice(deviceId, payload = {}) {
    return postDeviceAction(deviceId, "approve", payload);
}

export async function blockDevice(deviceId, payload = {}) {
    return postDeviceAction(deviceId, "block", payload);
}

export async function ignoreDevice(deviceId, payload = {}) {
    return postDeviceAction(deviceId, "ignore", payload);
}

// postDeviceAction() er fælles helper for approveDevice(), blockDevice() og ignoreDevice().
// Den sender brugerens device-beslutning til frontend Flask, som videresender til backendens device endpoint.
async function postDeviceAction(deviceId, action, payload = {}) {
    // Kaldet rammer frontendens proxy-route i main.py, ikke backend direkte fra browseren.
    const response = await fetch(`/api/devices/${deviceId}/${action}`, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
        },
        cache: "no-store",
        // Payload sendes som JSON, så backend kan gemme handling, event_id og handled_by.
        body: JSON.stringify(payload),
    });

    if (!response.ok) {
        // Hvis backend sender en JSON-fejl, bruges den. Ellers bruges en generisk fejltekst.
        const errorBody = await response.json().catch(() => ({}));
        throw new Error(errorBody.error || `Device ${action} failed with status ${response.status}`);
    }

    // Returnerer backendens svar til den kode der håndterede brugerens klik.
    return response.json();
}

// fetchCriticalRegisters() henter reglerne for kritiske Modbus-registre.
// Frontend main.py videresender kaldet til backend, som læser fra critical_registers-tabellen.
export async function fetchCriticalRegisters() {
    const response = await fetch("/api/critical-registers", {
        cache: "no-store",
    });

    if (!response.ok) {
        throw new Error(`Critical registers fetch failed with status ${response.status}`);
    }

    return response.json();
}

// saveCriticalRegister() sender en ny eller ændret critical-register regel til frontend Flask.
// Backend validerer og gemmer reglen i critical_registers-tabellen.
export async function saveCriticalRegister(payload) {
    const response = await fetch("/api/critical-registers", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
        },
        cache: "no-store",
        // Payload indeholder registerets slave_ip, unit_id, register_type, register_address og regel-felter.
        body: JSON.stringify(payload),
    });

    if (!response.ok) {
        const errorBody = await response.json().catch(() => ({}));
        throw new Error(errorBody.error || `Critical register save failed with status ${response.status}`);
    }

    return response.json();
}

// deleteCriticalRegister() sletter en critical-register regel via dens database-id.
// registerId er id'et fra critical_registers-tabellen.
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


// fetchAlarmApprovals() henter historik over håndterede alarmer.
// Backend læser data fra alarm_approvals-tabellen.
export async function fetchAlarmApprovals() {
    const response = await fetch("/api/alarm-approvals", {
        cache: "no-store",
    });

    if (!response.ok) {
        throw new Error(`Alarm approvals fetch failed with status ${response.status}`);
    }

    return response.json();
}


// saveAlarmApproval() sender brugerens beslutning på en alarm til frontend Flask.
// Backend gemmer beslutningen i alarm_approvals og opdaterer events.status via event_id.
export async function saveAlarmApproval(payload) {
    const response = await fetch("/api/alarm-approvals", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
        },
        cache: "no-store",
        // Payload indeholder alarm_key, alarm_type, action, status, event_id og details.
        body: JSON.stringify(payload),
    });

    if (!response.ok) {
        const errorBody = await response.json().catch(() => ({}));
        throw new Error(errorBody.error || `Alarm approval save failed with status ${response.status}`);
    }

    return response.json();
}


