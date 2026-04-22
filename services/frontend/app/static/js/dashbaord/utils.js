export function escapeHtml(value) {
    return String(value ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

export function parseTimeToSeconds(timeString) {
    const parts = String(timeString).split(":").map(Number);
    if (parts.length !== 3 || parts.some(Number.isNaN)) {
        return 0;
    }
    return (parts[0] * 3600) + (parts[1] * 60) + parts[2];
}
