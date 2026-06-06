// main.js er dashboardets centrale frontend-controller.
// Filen henter dashboardData via api.js, gemmer data i state.js og kalder de render-funktioner der tegner hver sektion.
// Den bygger ikke selv alle HTML-sektioner. Den fordeler data videre til summary.js, chart.js, events.js, ports.js osv.


// Dataflow:
// browser loader dashboard.html
// └─ main.js starter
//    ├─ refreshDashboardData()
//    │  ├─ fetchDashboardData() -> frontend Flask /api/live-dashboard -> backend API
//    │  ├─ hydrateApprovalStore(freshData)
//    │  ├─ setDashboardData(freshData)
//    │  ├─ syncWindowAfterRefresh(oldLength)
//    │  └─ renderAll()
//    │     ├─ renderHeader()
//    │     ├─ renderSummary()
//    │     ├─ renderConnections()
//    │     ├─ renderEvents()
//    │     ├─ renderArp()
//    │     ├─ renderPorts()
//    │     ├─ renderChart()
//    │     ├─ renderApprovalModal()
//    │     └─ renderApprovalLog()
//    └─ setInterval(refreshDashboardData, POLL_INTERVAL_MS)
//       └─ henter nye data hvert 10. sekund

import { fetchDashboardData } from "./api.js";

import {
    getState,
    setDashboardData,
    getSeries,
    resetToLiveWindow,
    syncWindowAfterRefresh,
} from "./state.js";

import { renderSummary } from "./summary.js";
import { renderConnections } from "./connections.js";
import { renderEvents } from "./events.js";
import { renderArp } from "./arp.js";
import { renderPorts } from "./ports.js";
import { renderChart, findClosestSeriesIndexByTime, centerViewOnIndex } from "./chart.js";
import { renderApprovalModal } from "./approvalModal.js";
import { renderApprovalLog } from "./approvalLog.js";
import { hydrateApprovalStore } from "./alertStore.js";

import {
    openCriticalRegistersModal,
} from "./criticalRegisters.js";


// Dashboardet poller backend med fast interval.
// 10000 ms betyder at browseren henter nye dashboard-data hvert 10. sekund.
const POLL_INTERVAL_MS = 10000;

// elements samler DOM-referencer til de HTML-elementer dashboardet opdaterer.
// Render-funktionerne får kun de elementer de skal bruge, i stedet for selv at søge efter dem hver gang.
const elements = {
    // Grafens container.
    chartShell: document.querySelector(".chart-shell"),
    // Summary cards øverst i dashboardet.
    summaryGrid: document.getElementById("summary-grid"),
    // Master/slave-forbindelser.
    connectionGroups: document.getElementById("connection-groups"),
    // IDS-eventlisten.
    eventList: document.getElementById("event-list"),
    // ARP-sektionens under-elementer.
    arp: {
        statusBadge: document.getElementById("arp-status-badge"),
        summary: document.getElementById("arp-summary"),
        expected: document.getElementById("arp-expected"),
        seen: document.getElementById("arp-seen"),
        criticalPairs: document.getElementById("arp-critical-pairs"),
        eventList: document.getElementById("arp-event-list"),
    },
    // Switch-port oversigten.
    portsGrid: document.getElementById("ports-grid"),
    // Header/sensor-felter.
    generatedAt: document.getElementById("generated-at"),
    sensorStatus: document.getElementById("sensor-status"),
    sensorMode: document.getElementById("sensor-mode"),
    sensorInterface: document.getElementById("sensor-interface"),
    sensorPill: document.getElementById("sensor-pill"),
    combinedNote: document.getElementById("combined-note"),
    // Knap til critical registers-dialogen.
    criticalRegistersOpen: document.getElementById("critical-registers-open"),
    // Liste over håndterede alarms.
    approvalLogList: document.getElementById("approval-log-list"),
};

// renderHeader() opdaterer dashboardets øverste statuslinje.
// Data kommer fra dashboardData.sensor og dashboardData.generated_at.
function renderHeader(dashboardData) {
    // Fallback-værdier bruges hvis backend mangler enkelte felter.
    elements.generatedAt.textContent = dashboardData.generated_at || "live";
    elements.sensorStatus.textContent = dashboardData.sensor?.status || "-";
    elements.sensorMode.textContent = dashboardData.sensor?.mode || "-";
    elements.sensorInterface.textContent = dashboardData.sensor?.interface || "-";
    elements.sensorPill.textContent = dashboardData.sensor?.status || "-";
    elements.combinedNote.textContent = dashboardData.combined_note || "";
}

// focusChartOnEvent() kaldes når brugeren klikker på en event i eventlisten.
// Funktionen finder det datapunkt der ligger tættest på eventens tidspunkt og centrerer grafen omkring det.
function focusChartOnEvent(timeString) {
    // chart.js finder nærmeste index i hele tidsserien.
    const index = findClosestSeriesIndexByTime(timeString);
    if (index >= 0) {
        // Viser et mindre vindue omkring eventen, så hændelsen bliver nemmere at se i grafen.
        centerViewOnIndex(index, 24);
        renderAll();
    }
}

// renderAll() tegner hele dashboardet ud fra den nyeste state.
// Funktionen henter dashboardData fra state.js og sender samme data videre til de enkelte render-moduler.
function renderAll() {
    // state.js er frontendens aktuelle kopi af dashboardData.
    const dashboardData = getState().dashboardData;
    // Hver render-funktion opdaterer sin egen del af dashboardet.
    renderHeader(dashboardData);
    renderSummary(elements.summaryGrid, dashboardData);
    renderConnections(elements.connectionGroups, dashboardData);
    renderEvents(elements.eventList, dashboardData, focusChartOnEvent);
    renderArp(elements.arp, dashboardData);
    renderPorts(elements.portsGrid, dashboardData);
    renderChart(elements.chartShell, dashboardData, renderAll);

    // Alarm-dialogen får en callback, så den kan hente nye data efter brugerens handling.
    renderApprovalModal(dashboardData, refreshDashboardData);
    // Approval-loggen læser data fra alertStore.js, som blev hydrateret under refreshDashboardData().
    renderApprovalLog(elements.approvalLogList);
}

// refreshDashboardData() henter nyeste dashboard-data og opdaterer hele visningen.
// Det er her browseren starter frontend -> backend dataflowet.
async function refreshDashboardData() {
    try {
        // Gemmer seriens gamle længde, så grafens tidsvindue kan bevares efter refresh.
        const oldLength = getSeries().length;
        // Henter nye data gennem api.js og frontend Flask-proxyen.
        const freshData = await fetchDashboardData();
        // Synkroniserer frontendens alarm approval-state med backendens data.
        hydrateApprovalStore(freshData);
        // Gemmer nyeste dashboardData i state.js.
        setDashboardData(freshData);
        // Bevarer grafens zoom/pan-vindue bedst muligt efter nye datapunkter.
        syncWindowAfterRefresh(oldLength);
        // Tegner dashboardet igen med de nye data.
        renderAll();
    } catch (error) {
        // Fejl logges i browserens console, men siden bliver stående med seneste kendte data.
        console.error("Dashboard refresh failed", error);
    }
}

// Åbner critical registers-dialogen når brugeren klikker på knappen.
// Optional chaining gør at koden ikke fejler hvis knappen mangler i HTML'en.
elements.criticalRegistersOpen?.addEventListener("click", openCriticalRegistersModal);
// Initialiserer grafen til live-vinduet før første data-refresh.
resetToLiveWindow();
// Første datahentning når dashboardet loader.
refreshDashboardData();
// Starter automatisk refresh, så dashboardet løbende opdateres.
setInterval(refreshDashboardData, POLL_INTERVAL_MS);


