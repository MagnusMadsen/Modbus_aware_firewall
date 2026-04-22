import { escapeHtml } from "./utils.js";

export function renderSummary(summaryGrid, dashboardData) {
    const summary = dashboardData.summary || [];

    summaryGrid.innerHTML = summary.map(item => `
        <div class="card summary-card">
            <p class="summary-label">${escapeHtml(item.label)}</p>
            <h3>${escapeHtml(item.value)}</h3>
            <p class="summary-note">${escapeHtml(item.note)}</p>
        </div>
    `).join("");
}

