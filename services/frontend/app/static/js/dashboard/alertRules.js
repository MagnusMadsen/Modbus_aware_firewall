
import { isAlertAcknowledged } from "./alertStore.js";

export function findNextAlert(dashboardData) {
    return (
        findPendingDeviceAlert(dashboardData) ||
        findArpAlert(dashboardData) ||
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

    const key = `device:${device.id || device.ip || device.mac}`;
    if (isAlertAcknowledged(key)) return null;

    return {
        type: "device",
        key,
        deviceId: device.id,
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

    const key = `arp:${event.time}:${event.details}`;
    if (isAlertAcknowledged(key)) return null;

    return {
        type: "arp",
        key,
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

function findDowntimeAlert(dashboardData) {
    const series = dashboardData.combined_series || [];
    const lastDowntime = [...series].reverse().find((item) => item.downtime === true);

    if (!lastDowntime) return null;

    const key = `downtime:${lastDowntime.time}`;
    if (isAlertAcknowledged(key)) return null;

    return {
        type: "downtime",
        key,
        title: "NETVÆRKSUDFALD",
        message: "Der er registreret et tidsvindue uden trafik.",
        approveText: "GODKEND",
        blockText: "KRITISK",
        ignoreText: "IGNORER",
        details: [
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

    const key = `failed:${lastFailed.time}:${lastFailed.failed_requests}`;
    if (isAlertAcknowledged(key)) return null;

    return {
        type: "failed_requests",
        key,
        title: "FAILED MODBUS REQUESTS",
        message: "Der er registreret fejlede requests. Dette kan ske ved afbrydelse, bridge/MITM eller ustabil slave.",
        approveText: "GODKEND",
        blockText: "KRITISK",
        ignoreText: "IGNORER",
        details: [
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

    const key = `latency:${spike.time}:${spike.latency}`;
    if (isAlertAcknowledged(key)) return null;

    return {
        type: "latency",
        key,
        title: "LATENCY OVER THRESHOLD",
        message: "Latency er over den beregnede threshold.",
        approveText: "GODKEND",
        blockText: "KRITISK",
        ignoreText: "IGNORER",
        details: [
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
        const key = `port-active:${port.port}`;
        return state === "active" && !isAlertAcknowledged(key);
    });

    if (!activePort) return null;

    return {
        type: "port_active",
        key: `port-active:${activePort.port}`,
        title: "SWITCH PORT AKTIV",
        message: "En switch-port er aktiv og skal godkendes.",
        approveText: "GODKEND PORT",
        blockText: "MARKÉR KRITISK",
        ignoreText: "IGNORER",
        details: [
            { label: "Port", value: activePort.port || "-" },
            { label: "Interface", value: activePort.name || "-" },
            { label: "State", value: activePort.state || "-" },
            { label: "Activity", value: activePort.activity || "-" },
        ],
    };
}