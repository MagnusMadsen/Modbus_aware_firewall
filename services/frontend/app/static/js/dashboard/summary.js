// summary.js renderer summary-cards øverst i dashboardet.
// main.js sender dashboardData ind i renderSummary(), når dashboardet har hentet nye data.
// dashboardData.summary er en liste af korte nøgletal fra backend, f.eks. antal devices, pakker, events eller statusfelter.
// Denne fil bestemmer ikke tallene. Den viser kun label, value og note som HTML-kort.

// Dataflow:
// backend /api/dashboard
// └─ dashboardData.summary
//    └─ main.js
//       └─ renderSummary(summaryGrid, dashboardData)
//          └─ ét summary-item bliver til ét summary-card i HTML

// Eksempel:
// summary = [
//   { label: "Online devices", value: 4, note: "Seen recently" }
// ]
// bliver vist som ét kort med label, tal og forklarende note.

import { escapeHtml } from "./utils.js";


// renderSummary() tegner summary-sektionen.
// summaryGrid er HTML-containeren hvor kortene indsættes.
// dashboardData indeholder den nyeste summary-liste fra backend.
export function renderSummary(summaryGrid, dashboardData) {
    // Hvis backend ikke sender summary, bruges en tom liste så renderingen ikke fejler.
    const summary = dashboardData.summary || [];

    // Bygger ét synligt summary-card pr. item i summary-listen.
    // map() laver hvert item om til HTML, og join("") samler kortene til én HTML-streng.
    summaryGrid.innerHTML = summary.map(item => `
        <div class="card summary-card">
            ${/* label er navnet på nøgletallet, f.eks. Online devices. */""}
            <p class="summary-label">${escapeHtml(item.label)}</p>
            ${/* value er selve værdien/tallet som backend har sendt. */""}
            <h3>${escapeHtml(item.value)}</h3>
            ${/* note er den korte forklaring under værdien. */""}
            <p class="summary-note">${escapeHtml(item.note)}</p>
        </div>
    `
    // escapeHtml() sikrer at tekst fra backend vises som tekst og ikke som rå HTML.
    ).join("");
}

