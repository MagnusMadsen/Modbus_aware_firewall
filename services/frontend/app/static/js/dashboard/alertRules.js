import { isAlertAcknowledged } from "./alertStore.js";

export function findNextAlert(dashboardData) {
    return (
        findPendingDeviceAlert(dashboardData) ||
        findArpAlert(dashboardData) ||
        findEventAlert(dashboardData) ||
        findDowntimeAlert(dashboardData) ||
        findFailedRequestAlert(dashboardData) ||
        findLatencyAlert(dashboardData) ||
        findActivePortAlert(dashboardData)
    );
}


function findPendingDeviceAlert(dashboardData) {
    const devices = dashboardData.devices || [];
    const device = devices.find((item) => {
        const status = String(item.status || "").toLowerCase();
        return status === "pending" || status === "unknown";
    });

    if (!device) return null;
    if (!device.event_id) return null;

    const key = `event:${device.event_id}:new_device`;
    if (isAlertAcknowledged(key)) return null;

    return {
        type: "device",
        key,
        deviceId: device.id,
        eventId: device.event_id,
        title: "UKENDT ENHED FUNDET",
        message: "En ny enhed er observeret på netværket.",
        approveText: "GODKEND",
        blockText: "BLOKER",
        ignoreText: "IGNORER",
        details: [
            { label: "IP-adresse", value: device.ip || "-" },
            { label: "MAC-adresse", value: device.mac || "-" },
            { label: "Rolle", value: device.role || "unknown" },
            { label: "Først set", value: device.first_seen || "-" },
        ],
    };
}

function findArpAlert(dashboardData) {
    const events = dashboardData.arp_monitor?.events || [];
    const event = events[0];

    if (!event) return null;
    if (!event.event_id) return null;

    const key = `event:${event.event_id}:arp`;
    if (isAlertAcknowledged(key)) return null;

    return {
        type: "arp",
        key,
        eventId: event.event_id || null,
        title: "ARP MAC ÆNDRING",
        message: "En IP-adresse har skiftet MAC-adresse. Dette kan indikere MITM eller ARP spoofing.",
        approveText: "GODKEND HÆNDELSE",
        blockText: "KRITISK",
        ignoreText: "IGNORER",
        details: [
            { label: "Type", value: event.type || "ARP event" },
            { label: "Alvorlighed", value: event.severity || "high" },
            { label: "Tid", value: event.time || "-" },
            { label: "Detaljer", value: event.details || "-" },
        ],
    };
}

function findEventAlert(dashboardData) {
    const events = dashboardData.events || [];

    const event = events.find((item) => {
        const severity = String(item.severity || "").toLowerCase();
        const isPinned = item.is_pinned === true;
        const key = `event:${item.event_id || item.time}:${item.type}`;

        return (
            item.event_id &&
            !isAlertAcknowledged(key) &&
            (isPinned || severity === "high" || severity === "critical")
        );
    });

    if (!event) return null;

    const key = `event:${event.event_id}:${event.type}`;
    if (isAlertAcknowledged(key)) return null;

    return {
        type: event.type || "event",
        key,
        eventId: event.event_id,
        title: "SIKKERHEDSHÆNDELSE FUNDET",
        message: event.impact || event.details || "Der er registreret en hændelse i IDS-systemet.",
        approveText: "GODKEND",
        blockText: "KRITISK",
        ignoreText: "IGNORER",
        details: [
            { label: "Event ID", value: String(event.event_id) },
            { label: "Type", value: event.type || "-" },
            { label: "Alvorlighed", value: event.severity || "-" },
            { label: "Tid", value: event.time || "-" },
            { label: "Detaljer", value: event.details || "-" },
        ],
    };
}

function findDowntimeAlert(dashboardData) {
    const series = dashboardData.combined_series || [];
    const lastDowntime = [...series].reverse().find((item) => item.downtime === true);

    if (!lastDowntime) return null;
    if (!lastDowntime.downtime_event_id) return null;

    const key = `event:${lastDowntime.downtime_event_id}:downtime`;
    if (isAlertAcknowledged(key)) return null;

    return {
        type: "downtime",
        key,
        eventId: lastDowntime.downtime_event_id || null,
        title: "NETVÆRKSUDFALD",
        message: "Der er registreret et tidsvindue uden trafik.",
        approveText: "GODKEND",
        blockText: "KRITISK",
        ignoreText: "IGNORER",
        details: [
            { label: "Event ID", value: String(lastDowntime.downtime_event_id || "-") },
            { label: "Tid", value: lastDowntime.time || "-" },
            { label: "Traffic", value: String(lastDowntime.traffic ?? "-") },
            { label: "Failed requests", value: String(lastDowntime.failed_requests ?? "-") },
            { label: "Latency", value: `${lastDowntime.latency ?? "-"} ms` },
        ],
    };
}

function findFailedRequestAlert(dashboardData) {
    const series = dashboardData.combined_series || [];
    const lastFailed = [...series].reverse().find((item) => Number(item.failed_requests || 0) > 0);

    if (!lastFailed) return null;
    if (!lastFailed.failed_event_id) return null;

    const key = `event:${lastFailed.failed_event_id}:failed_requests`;
    if (isAlertAcknowledged(key)) return null;

    return {
        type: "failed_requests",
        key,
        eventId: lastFailed.failed_event_id || null,
        title: "FAILED MODBUS REQUESTS",
        message: "Der er registreret fejlede requests. Dette kan ske ved afbrydelse, bridge/MITM eller ustabil slave.",
        approveText: "GODKEND",
        blockText: "KRITISK",
        ignoreText: "IGNORER",
        details: [
            { label: "Event ID", value: String(lastFailed.failed_event_id || "-") },
            { label: "Tid", value: lastFailed.time || "-" },
            { label: "Failed requests", value: String(lastFailed.failed_requests) },
            { label: "Traffic", value: String(lastFailed.traffic ?? "-") },
            { label: "Latency", value: `${lastFailed.latency ?? "-"} ms` },
        ],
    };
}

function findLatencyAlert(dashboardData) {
    const series = dashboardData.combined_series || [];
    const spike = [...series].reverse().find((item) => {
        const latency = Number(item.latency || 0);
        const threshold = Number(item.latency_threshold || 0);
        return threshold > 0 && latency > threshold;
    });

    if (!spike) return null;
    if (!spike.latency_event_id) return null;

    const key = `event:${spike.latency_event_id}:latency`;
    if (isAlertAcknowledged(key)) return null;

    return {
        type: "latency",
        key,
        eventId: spike.latency_event_id,
        title: "LATENCY OVER THRESHOLD",
        message: "Latency er over den beregnede threshold.",
        approveText: "GODKEND",
        blockText: "KRITISK",
        ignoreText: "IGNORER",
        details: [
            { label: "Event ID", value: String(spike.latency_event_id) },
            { label: "Tid", value: spike.time || "-" },
            { label: "Latency", value: `${spike.latency} ms` },
            { label: "Threshold", value: `${spike.latency_threshold} ms` },
            { label: "Baseline", value: `${spike.latency_baseline ?? "-"} ms` },
        ],
    };
}

function findActivePortAlert(dashboardData) {
    const ports = dashboardData.ports || [];
    const activePort = ports.find((port) => {
        const state = String(port.state || "").toLowerCase();
        const key = port.event_id ? `event:${port.event_id}:port_active` : `port-active:${port.port}`;
        return state === "active" && !isAlertAcknowledged(key);
    });

    if (!activePort) return null;
    if (!activePort.event_id) return null;

    return {
        type: "port_active",
        key: `event:${activePort.event_id}:port_active`,
        eventId: activePort.event_id,
        title: "SWITCH PORT AKTIV",
        message: "En switch-port er aktiv og skal godkendes.",
        approveText: "GODKEND PORT",
        blockText: "MARKÉR KRITISK",
        ignoreText: "IGNORER",
        details: [
            { label: "Event ID", value: String(activePort.event_id) },
            { label: "Port", value: activePort.port || "-" },
            { label: "Interface", value: activePort.name || "-" },
            { label: "State", value: activePort.state || "-" },
            { label: "Activity", value: activePort.activity || "-" },
        ],
    };
}