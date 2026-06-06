// alertRules.js indeholder frontendens visningslogik for alarm-modalen.
// Backend har allerede vurderet og oprettet hændelserne/events.
// Filens formål er kun at vælge hvilken allerede modtaget backend-hændelse der skal vises først i frontend.

// Dataflow:
// Backend
// └─ opretter events i events-tabellen og sender dashboardData via /api/dashboard og /api/devices
//    └─ Frontend main.py henter data og leverer det til browseren via /api/live-dashboard
//       └─ alertRules.js modtager dashboardData
//          ├─ finder første relevante alert efter prioritet
//          ├─ springer alerts over hvis de allerede er acknowledged lokalt
//          └─ returnerer ét alert-objekt til modal-koden
//             └─ modal-koden viser alerten og sender brugerens valg videre til backend

// Kort sagt:
// Backend = opdager, vurderer og gemmer hændelser.
// alertRules.js = vælger og formaterer den hændelse brugeren skal se i modal-vinduet.

import { isAlertAcknowledged } from "./alertStore.js";

// findNextAlert() vælger den næste alert som frontend skal vise via dashboardData som er fra backend.
// Funktionen gennemgår alert-typer i fast prioritet og returnerer den første der matcher.
// Den ændrer ikke backend-data og opretter ikke nye hændelser. 
// Hvis ingen alert skal vises, returneres null.
export function findNextAlert(dashboardData) {
    // || stopper ved første funktion der returnerer et alert-objekt.
    // Det er derfor rækkefølgen her bestemmer hvilken alarm brugeren ser først.
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


// Finder en pending/unknown device som backend allerede har sendt til frontend.
// Device-data kommer fra backend /api/devices og stammer fra devices-tabellen.
// Denne funktion beslutter ikke om devicen er ny. Den vælger kun om den skal vises som modal.
// Alerten kræver event_id, så brugerens handling kan kobles til events.id i backend.
function findPendingDeviceAlert(dashboardData) {
    // Hvis dashboardData.devices mangler, bruges en tom liste så funktionen ikke fejler.
    const devices = dashboardData.devices || [];

    // Finder første device som backend har markeret som pending eller unknown.
    const device = devices.find((item) => {
        const status = String(item.status || "").toLowerCase();
        return status === "pending" || status === "unknown";
    });

    // Ingen relevant device betyder ingen device-alert.
    if (!device) return null;

    // Uden event_id kan alerten ikke kobles til en konkret events-række i backend.
    if (!device.event_id) return null;

    // key bruges af alertStore.js til at huske om denne alert allerede er vist/håndteret lokalt.
    const key = `event:${device.event_id}:new_device`;

    if (isAlertAcknowledged(key)) return null;

    // Returnerer det objekt modal-koden skal bruge til titel, tekst, knapper og detaljer.
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

// Finder en ARP/MAC-change alert som backend allerede har oprettet som event.
// ARP-events ligger i dashboardData.arp_monitor.events og kommer fra backendens events-flow.
// Denne funktion vælger kun om eventen skal vises i modal-vinduet.
function findArpAlert(dashboardData) {
    // Optional chaining gør at koden ikke fejler hvis arp_monitor mangler.
    const events = dashboardData.arp_monitor?.events || [];

    // Kun den første ARP-event vises som modal ad gangen.
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

// Finder generelle IDS-events fra dashboardData.events.
// Disse events er allerede oprettet af backend og kommer fra events-tabellen via /api/dashboard.
// Frontend viser kun pinned, high eller critical events som modal her.
// Severity er altså bestemt af backend; denne fil bruger kun severity til UI-prioritering.
function findEventAlert(dashboardData) {
    // Finder første event der er vigtig nok og ikke allerede acknowledged.
    const events = dashboardData.events || [];

    const event = events.find((item) => {
        // severity normaliseres til lowercase, så HIGH og high behandles ens.
        const severity = String(item.severity || "").toLowerCase();
        // pinned events skal vises uanset om severity ikke er high/critical.
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

// Finder downtime-alerts i dashboardData.combined_series.
// Backend har allerede vurderet downtime og sendt downtime_event_id med.
// Denne funktion finder kun den nyeste downtime-alert der skal vises i frontend.
function findDowntimeAlert(dashboardData) {
    // reverse() bruges på en kopi, så vi finder den nyeste downtime uden at ændre originaldata.
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

// Finder alerts for failed Modbus requests i combined_series.
// Backendens request/metrics-logik har allerede registreret failed_requests og event_id.
// Denne funktion vælger kun den nyeste failed-request alert til modal-visning.
function findFailedRequestAlert(dashboardData) {
    // Finder nyeste datapunkt hvor failed_requests er større end 0.
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

// Finder latency-alerts i combined_series.
// Backend har allerede beregnet latency, threshold og latency_event_id.
// Frontend sammenligner værdierne for at vælge om den modtagne alert skal vises som modal.
function findLatencyAlert(dashboardData) {
    // Finder nyeste datapunkt hvor latency overstiger threshold.
    const series = dashboardData.combined_series || [];
    const spike = [...series].reverse().find((item) => {
        // Værdierne konverteres til Number, fordi data fra API/JSON kan være tomme eller tekstlignende.
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

// Finder aktive switch-porte i dashboardData.ports.
// Backend/dashboard-laget har allerede kombineret SNMP-portdata med event_id.
// Denne funktion vælger kun om en aktiv port skal vises som modal.
// Alerten kræver event_id, så brugerens handling kan gemmes som alarm approval på den konkrete events-række.
function findActivePortAlert(dashboardData) {
    // Finder første aktive port som ikke allerede er acknowledged lokalt.
    const ports = dashboardData.ports || [];
    const activePort = ports.find((port) => {
        const state = String(port.state || "").toLowerCase();
        // event_id giver en stabil key bundet til backendens events.id.
        // portnavnet bruges kun som fallback til lokalt acknowledged-check.
        const key = port.event_id ? `event:${port.event_id}:port_active` : `port-active:${port.port}`;
        return state === "active" && !isAlertAcknowledged(key);
    });

    if (!activePort) return null;

    // Uden event_id vises port-alerten ikke, fordi alarm approvals skal kunne pege på events.id.
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