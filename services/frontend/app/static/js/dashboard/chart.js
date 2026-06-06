// chart.js renderer trafik- og latency-grafen i dashboardet med Chart.js.
// Data kommer fra dashboardData.combined_series og dashboardData.chart_events, som backend sender via /api/dashboard.
// Backend har allerede beregnet metrics, baselines, thresholds, downtime og event-id'er.
// Denne fil viser dataene grafisk og håndterer zoom/pan i browseren.
// Den skriver ikke til backend eller databasen.


// Dataflow:
// backend /api/dashboard
// └─ combined_series + chart_events
//    └─ frontend main.js gemmer data i state.js
//       └─ renderChart(chartShell, dashboardData, rerender)
//          ├─ henter aktuelt tidsvindue fra state.js
//          ├─ bygger Chart.js datasets for traffic, latency, failed requests og events
//          ├─ tegner downtime-baggrund og event-labels med plugins
//          └─ binder zoom/pan/dobbeltklik på canvas-elementet

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

// getWindowedChartEvents() filtrerer chart_events ned til de events der ligger i det aktuelle grafvindue.
// Det sikrer at grafen kun viser event-markører for de datapunkter brugeren ser lige nu.
function getWindowedChartEvents(series, dashboardData) {
    // Set bruges til hurtigt at slå tider op uden at gennemløbe hele serien for hvert event.
    const times = new Set(series.map(item => item.time));
    return (dashboardData.chart_events || []).filter(event => times.has(event.time));
}

// computeTrafficAxisBounds() beregner min/max for trafik-aksen.
// Aksen får lidt padding, så grafen ikke presses helt op mod kanten.
function computeTrafficAxisBounds(series) {
    // Trafikværdier konverteres til tal, så manglende værdier bliver 0.
    const values = series.map(item => Number(item.traffic || 0));
    // Fallback hvis der endnu ikke er trafikdata.
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

// computeLatencyAxisBounds() beregner min/max for latency-aksen.
// Den tager både aktuel latency, baseline og threshold med, så alle linjer kan ses i grafen.
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

// findClosestSeriesIndexByTime() finder datapunktet i hele serien der ligger tættest på et tidspunkt.
// Funktionen bruges når dashboardet skal centrere grafen omkring en event eller et valgt tidspunkt.
export function findClosestSeriesIndexByTime(timeString) {
    const series = getSeries();
    if (!series.length) {
        return -1;
    }

    // Tider laves om til sekunder, så afstand mellem tidspunkter kan beregnes numerisk.
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

// centerViewOnIndex() flytter grafens synlige tidsvindue, så et bestemt datapunkt kommer i centrum.
// state.viewStartIndex og state.viewEndIndex bestemmer hvilken del af serien der vises.
export function centerViewOnIndex(index, preferredWindowSize = null) {
    const state = getState();
    const series = getSeries();
    const total = series.length;

    // Hvis der ikke er data, eller index er ugyldigt, ændres visningen ikke.
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

// bindChartInteractions() kobler brugerinteraktioner på grafens canvas.
// Scroll zoomer ind/ud, dobbeltklik nulstiller til live-vinduet, og drag flytter tidsvinduet.
// Funktionerne ændrer kun frontend-state i state.js og kalder rerender().
function bindChartInteractions(chartCanvas, rerender) {
    const state = getState();

    // Mouse wheel bruges til zoom ind/ud omkring musens position i grafen.
    chartCanvas.onwheel = (event) => {
        event.preventDefault();

        const series = getSeries();
        const total = series.length;
        if (!total) return;

        // ratio fortæller hvor i grafen musen står, så zoom kan holde fokus omkring samme punkt.
        const rect = chartCanvas.getBoundingClientRect();
        const mouseX = event.clientX - rect.left;
        const ratio = Math.max(0, Math.min(1, mouseX / rect.width));

        const currentSize = state.viewEndIndex - state.viewStartIndex;
        let nextSize;

        // Negativ deltaY zoomer ind. Positiv deltaY zoomer ud.
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
    };

    // Dobbeltklik nulstiller grafen til live-vinduet.
    chartCanvas.ondblclick = () => {
        resetToLiveWindow();
        rerender();
    };

    // Mouse down starter drag/pan af grafens tidsvindue.
    chartCanvas.onmousedown = (event) => {
        state.isDragging = true;
        state.dragStartX = event.clientX;
        state.dragStartStartIndex = state.viewStartIndex;
        state.dragStartEndIndex = state.viewEndIndex;
    };

    // Global mousemove/mouseup bindes kun én gang, så der ikke oprettes dublet-listeners ved hver render.
    if (!window.__dashboardChartMousemoveBound) {
        window.__dashboardChartMousemoveBound = true;

        window.addEventListener("mousemove", (event) => {
            const state = getState();
            if (!state.isDragging) return;

            const chartCanvas = document.getElementById("trafficLatencyChart");
            if (!chartCanvas) return;

            const series = getSeries();
            const total = series.length;
            const currentSize = state.dragStartEndIndex - state.dragStartStartIndex;
            if (!currentSize || !total) return;

            // Regner musebevægelse i pixels om til hvor mange datapunkter vinduet skal flyttes.
            const rect = chartCanvas.getBoundingClientRect();
            const pixelsPerPoint = rect.width / currentSize;
            const deltaX = event.clientX - state.dragStartX;
            const pointShift = Math.round(deltaX / pixelsPerPoint);

            state.viewStartIndex = Math.max(0, Math.min(total - currentSize, state.dragStartStartIndex - pointShift));
            state.viewEndIndex = state.viewStartIndex + currentSize;
        });

        window.addEventListener("mouseup", () => {
            const state = getState();
            state.isDragging = false;
        });
    }
}

// renderChart() bygger hele grafen på ny ud fra det aktuelle tidsvindue.
// chartShell er HTML-containeren hvor canvas-elementet placeres.
// dashboardData indeholder backend-data, især chart_events.
// rerender er callbacken der bruges efter zoom/pan for at tegne grafen igen.
export function renderChart(chartShell, dashboardData, rerender) {
    // Henter kun den del af serien der aktuelt skal vises i grafen.
    const combinedSeries = getWindowedSeries();

    // Fjerner gammel Chart.js-instans før grafen bygges igen.
    destroyChartInstance();

    // Hvis der ikke er datapunkter, vises en tom-tilstand i stedet for en graf.
    if (!combinedSeries.length) {
        chartShell.innerHTML = `
            <div class="chart-empty-state">
                No traffic or latency data available yet.
            </div>
        `;
        return;
    }

    // Canvas-elementet er det område Chart.js tegner grafen på.
    chartShell.innerHTML = '<canvas id="trafficLatencyChart"></canvas>';
    const chartCanvas = document.getElementById("trafficLatencyChart");
    const ctx = chartCanvas.getContext("2d");

    // Her pakkes backendens tidsserie ud i separate arrays til Chart.js datasets.
    const labels = combinedSeries.map(item => item.time);
    const trafficData = combinedSeries.map(item => item.traffic);
    const latencyData = combinedSeries.map(item => item.latency);
    const trafficBaselineData = combinedSeries.map(item => item.traffic_baseline);
    const latencyBaselineData = combinedSeries.map(item => item.latency_baseline);
    const latencyThresholdData = combinedSeries.map(item => item.latency_threshold);
    const failedRequestsData = combinedSeries.map(item => item.failed_requests);

    // Henter kun de event-markører der passer til det synlige tidsvindue.
    const chartEvents = getWindowedChartEvents(combinedSeries, dashboardData);

    // downtimeBoxes bruges af downtimePlugin til at tegne baggrundsmarkeringer ved downtime.
    const downtimeBoxes = combinedSeries.map((item, index) => ({
        x: index,
        active: item.downtime,
    }));

    // Event-markører placeres på det nærmeste tidspunkt i den synlige serie.
    const eventPoints = chartEvents.map(event => {
        let closestIndex = -1;
        let closestDistance = Number.MAX_SAFE_INTEGER;

        // Finder det label/datapunkt der tidsmæssigt ligger tættest på eventens tidspunkt.
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

    // downtimePlugin er et Chart.js plugin der tegner røde baggrundsfelter ved downtime.
    // Det ændrer ikke data; det er kun en visuel markering i grafen.
    const downtimePlugin = {
        id: "downtimePlugin",
        beforeDraw(chart) {
            // ctx er canvas-tegnefladen, chartArea er grafområdet, og scales bruges til at placere markeringen korrekt.
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

    // eventLabelPlugin skriver korte labels ved event-markørerne i grafen.
    // Event-markørerne kommer fra dashboardData.chart_events.
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

    // Beregner passende aksegrænser før Chart.js-instansen oprettes.
    const trafficBounds = computeTrafficAxisBounds(combinedSeries);
    const latencyBounds = computeLatencyAxisBounds(combinedSeries);

    // Opretter Chart.js-grafen.
    // Grafen kombinerer line datasets, bar dataset og scatter dataset i samme canvas.
    const instance = new Chart(ctx, {
        type: "line",
        data: {
            labels,
            datasets: [
                // Trafikmålinger som udfyldt linje på venstre akse.
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
                // Trafik-baseline som stiplet linje på samme akse som trafik.
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
                // Aktuel latency som linje på højre akse.
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
                // Latency-baseline som stiplet linje.
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
                // Latency-threshold viser grænsen hvor latency kan blive relevant som alarm.
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
                // Failed requests vises som søjler, så fejl kan ses oven på tidsserien.
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
                // Event markers vises som punkter ved relevante tidspunkter.
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
                        // Tilføjer event-label til tooltip, hvis datapunktet matcher en event-marker.
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

    // Gemmer Chart.js-instansen i state.js, så den kan destrueres ved næste render.
    setChartInstance(instance);
    // Binder zoom, pan og reset-interaktioner på den nye graf.
    bindChartInteractions(chartCanvas, rerender);
}