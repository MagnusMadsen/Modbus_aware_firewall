// utils.js indeholder små hjælpefunktioner som flere dashboard-filer kan genbruge.
// Formålet er at undgå at samme simple logik skrives flere steder.
// escapeHtml() bruges når tekst fra backend eller brugerinput skal indsættes i innerHTML.
// parseTimeToSeconds() bruges når klokkeslæt skal sammenlignes numerisk, f.eks. i chart.js.

// Dataflow:
// andre dashboard-moduler
// ├─ escapeHtml(value)
// │  └─ sikker tekst til HTML-rendering
// └─ parseTimeToSeconds("HH:MM:SS")
//    └─ sekunder siden midnat, så tider kan sammenlignes og sorteres

// escapeHtml() konverterer specialtegn til HTML entities.
// Det betyder at værdier vises som tekst i browseren og ikke tolkes som HTML.
// Bruges før data sættes ind i innerHTML.
//
// Eksempel:
// "<script>" bliver til "&lt;script&gt;"

export function escapeHtml(value) {
    // null og undefined laves om til tom tekst, så funktionen altid returnerer en string.
    return String(value ?? "")
        // & skal erstattes først, så de andre entities ikke bliver dobbeltbehandlet.
        .replace(/&/g, "&amp;")
        // < og > fjernes som HTML-tegn, så tekst ikke kan blive til tags.
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        // Anførselstegn escapes, så tekst også er sikker i HTML-attributter.
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

// parseTimeToSeconds() laver et klokkeslæt fra "HH:MM:SS" om til sekunder.
// Det gør det muligt at sammenligne tidspunkter med almindelig tal-matematik.
// Bruges f.eks. når chart.js skal finde hvilket datapunkt der ligger tættest på en event.

// Eksempel:
// "01:02:03" bliver til 3723 sekunder.
export function parseTimeToSeconds(timeString) {
    // Splitter teksten i timer, minutter og sekunder og konverterer dem til tal.
    const parts = String(timeString).split(":").map(Number);
    // Hvis formatet ikke er HH:MM:SS, returneres 0 som neutral fallback.
    if (parts.length !== 3 || parts.some(Number.isNaN)) {
        return 0;
    }
    // Timer og minutter regnes om til sekunder og lægges sammen med sekund-delen.
    return (parts[0] * 3600) + (parts[1] * 60) + parts[2];
}
