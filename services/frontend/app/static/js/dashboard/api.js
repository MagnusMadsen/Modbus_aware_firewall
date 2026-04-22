const DASHBOARD_API_URL = "/api/live-dashboard";

export async function fetchDashboardData() {
    const response = await fetch(DASHBOARD_API_URL, { cache: "no-store" });
    if (!response.ok) {
        throw new Error(`Dashboard fetch failed with status ${response.status}`);
    }
    return response.json();
}

