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

const POLL_INTERVAL_MS = 10000;

const elements = {
    chartShell: document.querySelector(".chart-shell"),
    summaryGrid: document.getElementById("summary-grid"),
    connectionGroups: document.getElementById("connection-groups"),
    eventList: document.getElementById("event-list"),
    arp: {
        statusBadge: document.getElementById("arp-status-badge"),
        summary: document.getElementById("arp-summary"),
        expected: document.getElementById("arp-expected"),
        seen: document.getElementById("arp-seen"),
        criticalPairs: document.getElementById("arp-critical-pairs"),
        eventList: document.getElementById("arp-event-list"),
    },
    portsGrid: document.getElementById("ports-grid"),
    generatedAt: document.getElementById("generated-at"),
    sensorStatus: document.getElementById("sensor-status"),
    sensorMode: document.getElementById("sensor-mode"),
    sensorInterface: document.getElementById("sensor-interface"),
    sensorPill: document.getElementById("sensor-pill"),
    combinedNote: document.getElementById("combined-note"),

    approvalLogList: document.getElementById("approval-log-list"),
};

function renderHeader(dashboardData) {
    elements.generatedAt.textContent = dashboardData.generated_at || "live";
    elements.sensorStatus.textContent = dashboardData.sensor?.status || "-";
    elements.sensorMode.textContent = dashboardData.sensor?.mode || "-";
    elements.sensorInterface.textContent = dashboardData.sensor?.interface || "-";
    elements.sensorPill.textContent = dashboardData.sensor?.status || "-";
    elements.combinedNote.textContent = dashboardData.combined_note || "";
}

function focusChartOnEvent(timeString) {
    const index = findClosestSeriesIndexByTime(timeString);
    if (index >= 0) {
        centerViewOnIndex(index, 24);
        renderAll();
    }
}

function renderAll() {
    const dashboardData = getState().dashboardData;
    renderHeader(dashboardData);
    renderSummary(elements.summaryGrid, dashboardData);
    renderConnections(elements.connectionGroups, dashboardData);
    renderEvents(elements.eventList, dashboardData, focusChartOnEvent);
    renderArp(elements.arp, dashboardData);
    renderPorts(elements.portsGrid, dashboardData);
    renderChart(elements.chartShell, dashboardData, renderAll);

    renderApprovalModal(dashboardData, refreshDashboardData);
    renderApprovalLog(elements.approvalLogList);
}

async function refreshDashboardData() {
    try {
        const oldLength = getSeries().length;
        const freshData = await fetchDashboardData();
        setDashboardData(freshData);
        syncWindowAfterRefresh(oldLength);
        renderAll();
    } catch (error) {
        console.error("Dashboard refresh failed", error);
    }
}

resetToLiveWindow();
renderAll();
setInterval(refreshDashboardData, POLL_INTERVAL_MS);


