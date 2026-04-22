const LIVE_WINDOW_POINTS = 60;
const MIN_WINDOW_POINTS = 12;

const state = {
    dashboardData: window.__DASHBOARD_INITIAL_DATA__ || {},
    chartInstance: null,
    viewStartIndex: 0,
    viewEndIndex: 0,
    isDragging: false,
    dragStartX: 0,
    dragStartStartIndex: 0,
    dragStartEndIndex: 0,
};

export function getState() {
    return state;
}

export function getLiveWindowPoints() {
    return LIVE_WINDOW_POINTS;
}

export function getMinWindowPoints() {
    return MIN_WINDOW_POINTS;
}

export function setDashboardData(data) {
    state.dashboardData = data || {};
}

export function setChartInstance(instance) {
    state.chartInstance = instance;
}

export function destroyChartInstance() {
    if (state.chartInstance) {
        state.chartInstance.destroy();
        state.chartInstance = null;
    }
}

export function getSeries() {
    return state.dashboardData.combined_series || [];
}

export function resetToLiveWindow() {
    const series = getSeries();
    const total = series.length;

    if (!total) {
        state.viewStartIndex = 0;
        state.viewEndIndex = 0;
        return;
    }

    const windowSize = Math.min(LIVE_WINDOW_POINTS, total);
    state.viewEndIndex = total;
    state.viewStartIndex = Math.max(0, total - windowSize);
}

export function ensureValidWindow() {
    const series = getSeries();
    const total = series.length;

    if (!total) {
        state.viewStartIndex = 0;
        state.viewEndIndex = 0;
        return;
    }

    if (state.viewEndIndex <= state.viewStartIndex) {
        resetToLiveWindow();
    }

    state.viewStartIndex = Math.max(0, state.viewStartIndex);
    state.viewEndIndex = Math.min(total, state.viewEndIndex);

    let size = state.viewEndIndex - state.viewStartIndex;
    if (size < MIN_WINDOW_POINTS) {
        state.viewEndIndex = Math.min(total, state.viewStartIndex + MIN_WINDOW_POINTS);
        state.viewStartIndex = Math.max(0, state.viewEndIndex - MIN_WINDOW_POINTS);
    }
}

export function getWindowedSeries() {
    ensureValidWindow();
    return getSeries().slice(state.viewStartIndex, state.viewEndIndex);
}

export function syncWindowAfterRefresh(oldLength) {
    const newLength = getSeries().length;
    const currentSize = Math.max(MIN_WINDOW_POINTS, state.viewEndIndex - state.viewStartIndex);

    if (state.viewEndIndex >= oldLength - 1) {
        state.viewEndIndex = newLength;
        state.viewStartIndex = Math.max(0, newLength - currentSize);
    } else {
        const diff = newLength - oldLength;
        state.viewStartIndex = Math.max(0, state.viewStartIndex + diff);
        state.viewEndIndex = Math.min(newLength, state.viewEndIndex + diff);
    }

    ensureValidWindow();
}

