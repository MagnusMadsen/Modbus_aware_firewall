import { parseTimeToSeconds } from "./utils.js";
import {
    getState,
    getSeries,
    getWindowedSeries,
    destroyChartInstance,
    setChartInstance,
    getMinWindowPoints,
    resetToLiveWindow,
} from "./state.js";

function getWindowedChartEvents(series, dashboardData) {
    const times = new Set(series.map(item => item.time));
    return (dashboardData.chart_events || []).filter(event => times.has(event.time));
}

function computeTrafficAxisBounds(series) {
    const values = series.map(item => Number(item.traffic || 0));
    if (!values.length) {
        return { min: 0, max: 10 };
    }

    const minValue = Math.min(...values);
    const maxValue = Math.max(...values);
    const range = Math.max(10, maxValue - minValue);
    const padding = Math.max(5, Math.round(range * 0.15));

    return {
        min: Math.max(0, minValue - padding),
        max: maxValue + padding,
    };
}

function computeLatencyAxisBounds(series) {
    const values = series.flatMap(item => [
        Number(item.latency || 0),
        Number(item.latency_baseline || 0),
        Number(item.latency_threshold || 0),
    ]);

    const maxValue = Math.max(...values, 10);
    const padding = Math.max(2, Math.round(maxValue * 0.15));

    return {
        min: 0,
        max: maxValue + padding,
    };
}

export function findClosestSeriesIndexByTime(timeString) {
    const series = getSeries();
    if (!series.length) {
        return -1;
    }

    const target = parseTimeToSeconds(timeString);
    let bestIndex = -1;
    let bestDistance = Number.MAX_SAFE_INTEGER;

    series.forEach((item, index) => {
        const itemSeconds = parseTimeToSeconds(item.time);
        const distance = Math.abs(itemSeconds - target);
        if (distance < bestDistance) {
            bestDistance = distance;
            bestIndex = index;
        }
    });

    return bestIndex;
}

export function centerViewOnIndex(index, preferredWindowSize = null) {
    const state = getState();
    const series = getSeries();
    const total = series.length;

    if (!total || index < 0) {
        return;
    }

    const currentSize = preferredWindowSize || Math.max(getMinWindowPoints(), state.viewEndIndex - state.viewStartIndex || 60);
    const half = Math.floor(currentSize / 2);

    state.viewStartIndex = Math.max(0, index - half);
    state.viewEndIndex = Math.min(total, state.viewStartIndex + currentSize);

    if (state.viewEndIndex - state.viewStartIndex < currentSize) {
        state.viewStartIndex = Math.max(0, state.viewEndIndex - currentSize);
    }
}

function bindChartInteractions(chartCanvas, rerender) {
    const state = getState();

    chartCanvas.addEventListener("wheel", (event) => {
        event.preventDefault();

        const series = getSeries();
        const total = series.length;
        if (!total) return;

        const rect = chartCanvas.getBoundingClientRect();
        const mouseX = event.clientX - rect.left;
        const ratio = Math.max(0, Math.min(1, mouseX / rect.width));

        const currentSize = state.viewEndIndex - state.viewStartIndex;
        let nextSize;

        if (event.deltaY < 0) {
            nextSize = Math.max(getMinWindowPoints(), Math.floor(currentSize * 0.8));
        } else {
            nextSize = Math.min(total, Math.ceil(currentSize * 1.25));
        }

        const focusIndex = state.viewStartIndex + Math.floor(currentSize * ratio);
        const leftSize = Math.floor(nextSize * ratio);
        const rightSize = nextSize - leftSize;

        state.viewStartIndex = Math.max(0, focusIndex - leftSize);
        state.viewEndIndex = Math.min(total, focusIndex + rightSize);

        if (state.viewEndIndex - state.viewStartIndex < nextSize) {
            if (state.viewStartIndex === 0) {
                state.viewEndIndex = Math.min(total, nextSize);
            } else if (state.viewEndIndex === total) {
                state.viewStartIndex = Math.max(0, total - nextSize);
            }
        }

        rerender();
    }, { passive: false });

    chartCanvas.addEventListener("dblclick", () => {
        resetToLiveWindow();
        rerender();
    });

    chartCanvas.addEventListener("mousedown", (event) => {
        state.isDragging = true;
        state.dragStartX = event.clientX;
        state.dragStartStartIndex = state.viewStartIndex;
        state.dragStartEndIndex = state.viewEndIndex;
    });

    window.addEventListener("mousemove", (event) => {
        if (!state.isDragging) return;

        const series = getSeries();
        const total = series.length;
        const currentSize = state.dragStartEndIndex - state.dragStartStartIndex;
        if (!currentSize || !total) return;

        const rect = chartCanvas.getBoundingClientRect();
        const pixelsPerPoint = rect.width / currentSize;
        const deltaX = event.clientX - state.dragStartX;
        const pointShift = Math.round(deltaX / pixelsPerPoint);

        state.viewStartIndex = Math.max(0, Math.min(total - currentSize, state.dragStartStartIndex - pointShift));
        state.viewEndIndex = state.viewStartIndex + currentSize;

        rerender();
    });

    window.addEventListener("mouseup", () => {
        state.isDragging = false;
    });
}

export function renderChart(chartShell, dashboardData, rerender) {
    const combinedSeries = getWindowedSeries();

    destroyChartInstance();

    if (!combinedSeries.length) {
        chartShell.innerHTML = `
            <div class="chart-empty-state">
                No traffic or latency data available yet.
            </div>
        `;
        return;
    }

    chartShell.innerHTML = '<canvas id="trafficLatencyChart"></canvas>';
    const chartCanvas = document.getElementById("trafficLatencyChart");
    const ctx = chartCanvas.getContext("2d");

    const labels = combinedSeries.map(item => item.time);
    const trafficData = combinedSeries.map(item => item.traffic);
    const latencyData = combinedSeries.map(item => item.latency);
    const trafficBaselineData = combinedSeries.map(item => item.traffic_baseline);
    const latencyBaselineData = combinedSeries.map(item => item.latency_baseline);
    const latencyThresholdData = combinedSeries.map(item => item.latency_threshold);
    const failedRequestsData = combinedSeries.map(item => item.failed_requests);

    const chartEvents = getWindowedChartEvents(combinedSeries, dashboardData);

    const downtimeBoxes = combinedSeries.map((item, index) => ({
        x: index,
        active: item.downtime,
    }));

    const eventPoints = chartEvents.map(event => {
        let closestIndex = -1;
        let closestDistance = Number.MAX_SAFE_INTEGER;

        labels.forEach((label, index) => {
            const eventSeconds = parseTimeToSeconds(event.time);
            const labelSeconds = parseTimeToSeconds(label);
            const distance = Math.abs(eventSeconds - labelSeconds);

            if (distance < closestDistance) {
                closestDistance = distance;
                closestIndex = index;
            }
        });

        if (closestIndex === -1) {
            return null;
        }

        return {
            x: labels[closestIndex],
            y: combinedSeries[closestIndex]?.latency ?? 0,
            label: event.label,
            severity: event.severity,
        };
    }).filter(Boolean);

    const downtimePlugin = {
        id: "downtimePlugin",
        beforeDraw(chart) {
            const { ctx, chartArea, scales } = chart;
            if (!chartArea) return;

            ctx.save();

            downtimeBoxes.forEach((item) => {
                if (!item.active) return;

                const x = scales.x.getPixelForValue(item.x);
                const nextX = scales.x.getPixelForValue(Math.min(item.x + 1, labels.length - 1));
                const width = Math.max(20, nextX - x);

                ctx.fillStyle = "rgba(255, 107, 107, 0.08)";
                ctx.fillRect(x - (width / 2), chartArea.top, width, chartArea.bottom - chartArea.top);
            });

            ctx.restore();
        }
    };

    const eventLabelPlugin = {
        id: "eventLabelPlugin",
        afterDatasetsDraw(chart) {
            const { ctx } = chart;
            const eventDatasetIndex = chart.data.datasets.findIndex(d => d.label === "Event markers");
            if (eventDatasetIndex === -1) return;

            const meta = chart.getDatasetMeta(eventDatasetIndex);
            ctx.save();
            ctx.font = "12px Inter, Arial, sans-serif";
            ctx.fillStyle = "#c7d3e2";

            meta.data.forEach((point, index) => {
                const event = eventPoints[index];
                if (!event) return;
                ctx.fillText(event.label, point.x + 8, point.y - 10);
            });

            ctx.restore();
        }
    };

    const trafficBounds = computeTrafficAxisBounds(combinedSeries);
    const latencyBounds = computeLatencyAxisBounds(combinedSeries);

    const instance = new Chart(ctx, {
        type: "line",
        data: {
            labels,
            datasets: [
                {
                    label: "Traffic volume",
                    data: trafficData,
                    yAxisID: "yTraffic",
                    borderColor: "rgba(111, 207, 255, 1)",
                    backgroundColor: "rgba(111, 207, 255, 0.18)",
                    fill: true,
                    tension: 0.35,
                    pointRadius: 2,
                    pointHoverRadius: 4,
                    order: 5,
                },
                {
                    label: "Traffic baseline",
                    data: trafficBaselineData,
                    yAxisID: "yTraffic",
                    borderColor: "rgba(111, 207, 255, 0.65)",
                    borderDash: [6, 6],
                    fill: false,
                    tension: 0,
                    pointRadius: 0,
                    pointHoverRadius: 0,
                    order: 4,
                },
                {
                    label: "Latency",
                    data: latencyData,
                    yAxisID: "yLatency",
                    borderColor: "rgba(167, 139, 250, 1)",
                    backgroundColor: "rgba(167, 139, 250, 1)",
                    fill: false,
                    tension: 0.35,
                    pointRadius: 2,
                    pointHoverRadius: 4,
                    order: 3,
                },
                {
                    label: "Latency baseline",
                    data: latencyBaselineData,
                    yAxisID: "yLatency",
                    borderColor: "rgba(167, 139, 250, 0.65)",
                    borderDash: [6, 6],
                    fill: false,
                    tension: 0,
                    pointRadius: 0,
                    pointHoverRadius: 0,
                    order: 2,
                },
                {
                    label: "Latency threshold",
                    data: latencyThresholdData,
                    yAxisID: "yLatency",
                    borderColor: "rgba(255, 107, 107, 0.85)",
                    borderDash: [3, 6],
                    fill: false,
                    tension: 0,
                    pointRadius: 0,
                    pointHoverRadius: 0,
                    order: 1,
                },
                {
                    type: "bar",
                    label: "Failed requests",
                    data: failedRequestsData,
                    yAxisID: "yFailed",
                    backgroundColor: "rgba(255, 158, 66, 0.50)",
                    borderColor: "rgba(255, 158, 66, 1)",
                    borderWidth: 1,
                    barThickness: 10,
                    order: 6,
                },
                {
                    type: "scatter",
                    label: "Event markers",
                    data: eventPoints,
                    yAxisID: "yLatency",
                    pointRadius: 5,
                    pointHoverRadius: 7,
                    pointBackgroundColor: "rgba(255, 255, 255, 1)",
                    pointBorderColor: "rgba(255, 107, 107, 1)",
                    pointBorderWidth: 2,
                    showLine: false,
                    order: 0,
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: false,
            interaction: {
                mode: "index",
                intersect: false,
            },
            plugins: {
                legend: {
                    display: false,
                },
                tooltip: {
                    backgroundColor: "rgba(10, 17, 28, 0.95)",
                    borderColor: "rgba(255,255,255,0.08)",
                    borderWidth: 1,
                    titleColor: "#e8eef8",
                    bodyColor: "#c8d4e3",
                    callbacks: {
                        afterBody(context) {
                            const label = context[0]?.label;
                            const event = eventPoints.find(item => item.x === label);
                            return event ? ["Event: " + event.label] : [];
                        }
                    }
                }
            },
            scales: {
                x: {
                    grid: {
                        color: "rgba(255,255,255,0.05)",
                    },
                    ticks: {
                        color: "#91a5be",
                        maxTicksLimit: 12,
                    }
                },
                yTraffic: {
                    position: "left",
                    beginAtZero: false,
                    min: trafficBounds.min,
                    max: trafficBounds.max,
                    grid: {
                        color: "rgba(255,255,255,0.05)",
                    },
                    ticks: {
                        color: "#91a5be",
                    },
                    title: {
                        display: true,
                        text: "Traffic",
                        color: "#91a5be",
                    }
                },
                yLatency: {
                    position: "right",
                    beginAtZero: true,
                    min: latencyBounds.min,
                    max: latencyBounds.max,
                    grid: {
                        drawOnChartArea: false,
                    },
                    ticks: {
                        color: "#91a5be",
                    },
                    title: {
                        display: true,
                        text: "Latency (ms)",
                        color: "#91a5be",
                    }
                },
                yFailed: {
                    display: false,
                    beginAtZero: true,
                }
            }
        },
        plugins: [downtimePlugin, eventLabelPlugin],
    });

    setChartInstance(instance);
    bindChartInteractions(chartCanvas, rerender);
}