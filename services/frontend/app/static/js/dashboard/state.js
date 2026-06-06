// state.js er frontendens fælles hukommelse for dashboardet.
// main.js skriver ny dashboardData her, når browseren har hentet nye data fra backend.
// chart.js læser herfra, når grafen skal vide hvilke datapunkter der findes, og hvilket udsnit der skal vises.

// Vigtig idé:
// combined_series er hele tidsserien fra backend.
// viewStartIndex og viewEndIndex vælger kun et udsnit af den serie til grafen.
// Data slettes ikke fra frontend-serien, bare fordi grafen kun viser et udsnit.

// Eksempel:
// combined_series har 300 datapunkter.
// viewStartIndex = 240
// viewEndIndex = 300
// Grafen viser datapunkt 240 til 299, altså de nyeste 60 punkter.

// Dataflow:
// main.js henter freshData fra backend
// └─ setDashboardData(freshData)
//    └─ state.dashboardData.combined_series gemmer hele tidsserien
//       ├─ getSeries() returnerer hele tidsserien
//       ├─ getWindowedSeries() returnerer kun det grafen skal vise lige nu
//       └─ chart.js ændrer viewStartIndex/viewEndIndex ved zoom, pan og live-visning

// LIVE_WINDOW_POINTS er standard-vinduet for grafen.
// 60 betyder: vis de 60 nyeste datapunkter, når grafen er i live-visning.
// MIN_WINDOW_POINTS er mindste zoom-vindue.
// 12 betyder: brugeren må ikke zoome længere ind end 12 datapunkter.
const LIVE_WINDOW_POINTS = 60;
const MIN_WINDOW_POINTS = 12;

// state er objektet hvor frontend gemmer dashboardets aktuelle tilstand.
// Det bruges fordi flere filer skal arbejde med samme data:
// main.js opdaterer data.
// chart.js læser serien og ændrer grafvinduet.
// andre render-filer læser dashboardData indirekte gennem main.js.
const state = {
    // dashboardData er den seneste komplette datastruktur fra backend.
    // Ved første page load kan dashboard.html levere startdata. Derefter overskriver main.js den ved refresh.
    dashboardData: window.__DASHBOARD_INITIAL_DATA__ || {},
    // chartInstance er den graf Chart.js allerede har tegnet.
    // Den gemmes her, så den kan fjernes før en ny graf tegnes.
    chartInstance: null,
    // viewStartIndex og viewEndIndex peger ind i combined_series.
    // De bestemmer første og sidste datapunkt grafen viser.
    viewStartIndex: 0,
    viewEndIndex: 0,
    // Drag-felterne husker musens startposition og grafvinduets start/slut, mens brugeren trækker grafen.
    isDragging: false,
    dragStartX: 0,
    dragStartStartIndex: 0,
    dragStartEndIndex: 0,
};

// getState() giver adgang til hele state-objektet.
// Bruges især af chart.js, fordi grafen skal ændre flere felter under zoom og pan.
export function getState() {
    return state;
}

// getLiveWindowPoints() returnerer standardstørrelsen på live-vinduet.
export function getLiveWindowPoints() {
    return LIVE_WINDOW_POINTS;
}

// getMinWindowPoints() returnerer mindste tilladte grafvindue.
export function getMinWindowPoints() {
    return MIN_WINDOW_POINTS;
}

// setDashboardData() erstatter den gamle dashboardData med ny data fra backend.
// Det er her frontendens kopi af backend-data bliver opdateret.
export function setDashboardData(data) {
    state.dashboardData = data || {};
}

// setChartInstance() gemmer den aktive Chart.js-instans.
// Det gør det muligt at destruere den gamle graf før en ny render.
export function setChartInstance(instance) {
    state.chartInstance = instance;
}

// destroyChartInstance() fjerner den gamle graf fra Chart.js.
// Ellers kan Chart.js ende med flere grafer/listeners på samme canvas.
export function destroyChartInstance() {
    if (state.chartInstance) {
        // destroy() rydder Chart.js' interne listeners, canvas-state og datasæt.
        state.chartInstance.destroy();
        state.chartInstance = null;
    }
}

// getSeries() returnerer hele combined_series.
// Det er hele tidsserien fra backend: trafik, latency, baselines, thresholds, fejl og downtime-felter.
export function getSeries() {
    return state.dashboardData.combined_series || [];
}

// resetToLiveWindow() flytter grafvinduet til slutningen af tidsserien.
// Det betyder at grafen viser de nyeste datapunkter.
// Bruges ved første load og når brugeren dobbeltklikker på grafen.
export function resetToLiveWindow() {
    // total er antal datapunkter i hele combined_series.
    const series = getSeries();
    const total = series.length;

    // Hvis serien er tom, kan grafen ikke vise noget.
    if (!total) {
        state.viewStartIndex = 0;
        state.viewEndIndex = 0;
        return;
    }

    // windowSize bliver 60, medmindre serien har færre end 60 datapunkter.
    // viewEndIndex sættes til total, så vinduet slutter ved det nyeste datapunkt.
    const windowSize = Math.min(LIVE_WINDOW_POINTS, total);
    state.viewEndIndex = total;
    state.viewStartIndex = Math.max(0, total - windowSize);
}

// ensureValidWindow() retter grafvinduet, hvis start/slut er ugyldige.
// Den bruges før grafen læser windowed data.
// Den sikrer tre ting:
// 1. vinduet ligger inden for combined_series
// 2. viewEndIndex er større end viewStartIndex
// 3. vinduet ikke bliver mindre end MIN_WINDOW_POINTS
export function ensureValidWindow() {
    const series = getSeries();
    const total = series.length;

    if (!total) {
        state.viewStartIndex = 0;
        state.viewEndIndex = 0;
        return;
    }

    // Hvis slut-index ikke ligger efter start-index, er vinduet ugyldigt.
    if (state.viewEndIndex <= state.viewStartIndex) {
        resetToLiveWindow();
    }

    // Klipper start/slut ind, så de ikke peger uden for serien.
    state.viewStartIndex = Math.max(0, state.viewStartIndex);
    state.viewEndIndex = Math.min(total, state.viewEndIndex);

    // Hvis brugeren har zoomet for langt ind, udvides vinduet til mindst 12 datapunkter.
    let size = state.viewEndIndex - state.viewStartIndex;
    if (size < MIN_WINDOW_POINTS) {
        state.viewEndIndex = Math.min(total, state.viewStartIndex + MIN_WINDOW_POINTS);
        state.viewStartIndex = Math.max(0, state.viewEndIndex - MIN_WINDOW_POINTS);
    }
}

// getWindowedSeries() returnerer udsnittet af combined_series som grafen skal vise.
// Eksempel: getSeries().slice(240, 300) viser kun datapunkt 240-299.
// Det er denne funktion der gør zoom og pan muligt uden at ændre selve dataen.
export function getWindowedSeries() {
    ensureValidWindow();
    return getSeries().slice(state.viewStartIndex, state.viewEndIndex);
}

// syncWindowAfterRefresh() justerer grafvinduet efter en ny backend-refresh.
// Problemet er at combined_series kan få flere datapunkter hvert 10. sekund.
// Hvis brugeren kigger live, skal grafen følge med de nye datapunkter.
// Hvis brugeren har panoreret tilbage i historikken, skal grafen blive på samme område i stedet for at hoppe til live.
export function syncWindowAfterRefresh(oldLength) {
    // oldLength er længden før refresh. newLength er længden efter refresh.
    const newLength = getSeries().length;
    const currentSize = Math.max(MIN_WINDOW_POINTS, state.viewEndIndex - state.viewStartIndex);

    // Hvis viewEndIndex lå ved seriens slutning før refresh, betragtes grafen som live.
    // Derfor flyttes vinduet til den nye slutning.
    if (state.viewEndIndex >= oldLength - 1) {
        state.viewEndIndex = newLength;
        state.viewStartIndex = Math.max(0, newLength - currentSize);
    } else {
        // Hvis brugeren ikke var ved live-enden, bevares det historiske udsnit bedst muligt.
        // diff fortæller hvor mange nye datapunkter der er kommet siden sidste refresh.
        const diff = newLength - oldLength;
        state.viewStartIndex = Math.max(0, state.viewStartIndex + diff);
        state.viewEndIndex = Math.min(newLength, state.viewEndIndex + diff);
    }

    // Sikrer at det nye vindue stadig er gyldigt efter justeringen.
    ensureValidWindow();
}

