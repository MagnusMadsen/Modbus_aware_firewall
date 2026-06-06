// criticalRegisters.js bygger og styrer dialogen til critical registers.
// Critical registers er brugerdefinerede regler for Modbus-registre der skal overvåges ekstra.
// Filen henter, opretter og sletter regler via api.js.
// api.js kalder frontend Flask, som videresender til backend, og backend læser/skriver i critical_registers-tabellen.


// Dataflow:
// bruger åbner dialogen
// └─ openCriticalRegistersModal()
//    ├─ loadCriticalRegisters() -> api.js -> backend -> critical_registers
//    └─ renderCriticalRegistersModal()
//       ├─ viser formular til ny regel
//       ├─ viser eksisterende regler
//       ├─ submit -> saveCriticalRegister(payload)
//       └─ delete -> deleteCriticalRegister(id)

import {
    fetchCriticalRegisters,
    saveCriticalRegister,
    deleteCriticalRegister,
} from "./api.js";

// Lokal frontend-state for dialogen.
// isOpen styrer om dialogen vises.
// registers holder de regler backend har sendt.
// errorMessage holder fejltekst hvis et API-kald fejler.
let isOpen = false;
let registers = [];
let errorMessage = "";

// openCriticalRegistersModal() åbner dialogen.
// Den nulstiller fejl, henter nyeste regler fra backend og renderer dialogen.
export function openCriticalRegistersModal() {
    // Henter critical-register regler fra backend/databasen.
    isOpen = true;
    errorMessage = "";
    loadCriticalRegisters();
    renderCriticalRegistersModal();
}

// renderCriticalRegistersModal() bygger dialogens HTML i critical-register-modal-root.
// Funktionen bruger den lokale state: isOpen, registers og errorMessage.
export function renderCriticalRegistersModal() {
    // Containeren ligger i dashboard.html og er stedet hvor dialogens HTML indsættes.
    const root = document.getElementById("critical-register-modal-root");
    // Uden container kan dialogen ikke renderes.
    if (!root) return;

    // Hvis dialogen er lukket, fjernes HTML'en fra containeren.
    if (!isOpen) {
        root.innerHTML = "";
        return;
    }

    // Bygger dialogens HTML, formular og liste over eksisterende critical registers.
    root.innerHTML = `
        <div class="critical-register-overlay visible">
            <div class="critical-register-modal">
                <div class="critical-register-header">
                    <div>
                        <h2>Critical registers</h2>
                        <p>Registers som skal overvåges ekstra hårdt ved Modbus writes.</p>
                    </div>
                    <button class="critical-register-close" id="critical-register-close" type="button">×</button>
                </div>

                ${errorMessage ? `<div class="critical-register-error">${escapeHtml(errorMessage)}</div>` : ""}

                ${/* Formularen indsamler de felter backend skal bruge for at oprette en critical_registers-regel. */""}
                <form class="critical-register-form" id="critical-register-form">
                    <label>
                        Slave IP
                        <input name="slave_ip" placeholder="192.168.61.10" required>
                    </label>

                    <label>
                        Unit ID
                        <input name="unit_id" type="number" min="0" max="255" value="1" required>
                    </label>

                    <label>
                        Register type
                        <select name="register_type" required>
                            <option value="holding_register">holding_register</option>
                            <option value="coil">coil</option>
                            <option value="input_register">input_register</option>
                            <option value="discrete_input">discrete_input</option>
                        </select>
                    </label>

                    <label>
                        Register address
                        <input name="register_address" type="number" min="0" max="65535" required>
                    </label>

                    <label>
                        Label
                        <input name="label" placeholder="Pump start / motor speed / safety state">
                    </label>

                    <label>
                        Allowed values
                        <input name="allowed_values" placeholder="0,1 eller tom">
                    </label>

                    <label class="critical-register-checkbox">
                        <input name="pin_on_change" type="checkbox" checked>
                        Pin alarm on change
                    </label>

                    <button type="submit">Add critical register</button>
                </form>

                ${/* Listen viser de regler der allerede findes i critical_registers-tabellen. */""}
                <div class="critical-register-list">
                    ${renderRegisterRows()}
                </div>
            </div>
        </div>
    `;

    // Event listeners sættes på efter HTML'en er indsat i DOM'en.
    document.getElementById("critical-register-close")?.addEventListener("click", closeCriticalRegistersModal);
    document.getElementById("critical-register-form")?.addEventListener("submit", handleSubmit);

    // Hver delete-knap får sin egen click-handler med registerets database-id.
    document.querySelectorAll("[data-critical-register-delete]").forEach((button) => {
        button.addEventListener("click", async () => {
            const id = button.getAttribute("data-critical-register-delete");
            await handleDelete(id);
        });
    });
}

// renderRegisterRows() bygger HTML for listen over eksisterende critical registers.
// Data kommer fra registers-arrayet, som blev fyldt af loadCriticalRegisters().
function renderRegisterRows() {
    // Hvis backend ikke har sendt nogen regler, vises en tom-tilstand.
    if (!registers.length) {
        return `<div class="critical-register-empty">Ingen critical registers endnu.</div>`;
    }

    // Bygger én synlig række pr. critical-register regel.
    return registers.map((item) => `
        <div class="critical-register-row">
            <div>
                <strong>${escapeHtml(item.label || "Unnamed register")}</strong>
                <span>${escapeHtml(item.slave_ip)} | unit ${escapeHtml(item.unit_id)} | ${escapeHtml(item.register_type)}:${escapeHtml(item.register_address)}</span>
                <small>Allowed: ${formatAllowedValues(item.allowed_values)} | Pin: ${item.pin_on_change ? "yes" : "no"}</small>
            </div>
            <button type="button" data-critical-register-delete="${item.id}">Delete</button>
        </div>
    `).join("");
}

// loadCriticalRegisters() henter reglerne fra backend via api.js.
// Backend læser reglerne fra critical_registers-tabellen.
// Efter hentning renderes dialogen igen, så listen viser nyeste data.
async function loadCriticalRegisters() {
    try {
        // Gemmer backendens svar i lokal frontend-state.
        registers = await fetchCriticalRegisters();
        renderCriticalRegistersModal();
    } catch (error) {
        errorMessage = error.message;
        renderCriticalRegistersModal();
    }
}

// handleSubmit() håndterer formular-submit for en ny critical-register regel.
// Den bygger et payload-objekt i det format backend forventer.
async function handleSubmit(event) {
    // Forhindrer browseren i at reloade siden ved formular-submit.
    event.preventDefault();

    // Læser formularens inputfelter.
    const formData = new FormData(event.currentTarget);
    const allowedValuesRaw = String(formData.get("allowed_values") || "").trim();

    // Payload matcher backendens critical_registers endpoint.
    const payload = {
        slave_ip: String(formData.get("slave_ip") || "").trim(),
        unit_id: Number(formData.get("unit_id")),
        register_type: String(formData.get("register_type") || "").trim(),
        register_address: Number(formData.get("register_address")),
        label: String(formData.get("label") || "").trim() || null,
        allowed_values: parseAllowedValues(allowedValuesRaw),
        pin_on_change: formData.get("pin_on_change") === "on",
        is_enabled: true,
    };

    try {
        // Sender reglen til backend, som validerer og gemmer den i critical_registers.
        await saveCriticalRegister(payload);
        errorMessage = "";
        // Henter listen igen, så den nye regel vises med database-id fra backend.
        await loadCriticalRegisters();
    } catch (error) {
        errorMessage = error.message;
        renderCriticalRegistersModal();
    }
}

// handleDelete() sletter en critical-register regel via dens database-id.
// Sletningen sendes til backend gennem api.js.
async function handleDelete(id) {
    try {
        // Backend sletter reglen fra critical_registers-tabellen.
        await deleteCriticalRegister(id);
        errorMessage = "";
        await loadCriticalRegisters();
    } catch (error) {
        errorMessage = error.message;
        renderCriticalRegistersModal();
    }
}

// closeCriticalRegistersModal() lukker dialogen og fjerner den fra siden ved næste render.
function closeCriticalRegistersModal() {
    isOpen = false;
    renderCriticalRegistersModal();
}

// parseAllowedValues() laver brugerens komma-separerede input om til en liste.
// Tal bliver gemt som numbers, mens tekstværdier bliver bevaret som strings.
// Eksempel: "0,1,auto" bliver til [0, 1, "auto"].
function parseAllowedValues(raw) {
    // Tomt felt betyder at alle værdier accepteres.
    if (!raw) return null;

    return raw
        .split(",")
        .map((value) => value.trim())
        .filter(Boolean)
        .map((value) => {
            const numberValue = Number(value);
            return Number.isNaN(numberValue) ? value : numberValue;
        });
}

// formatAllowedValues() laver allowed_values fra backend om til tekst til listen.
// Hvis der ikke er sat allowed_values, vises "any".
function formatAllowedValues(values) {
    if (!values || !Array.isArray(values) || !values.length) {
        return "any";
    }

    return values.map((value) => escapeHtml(value)).join(", ");
}

// escapeHtml() sikrer at tekst vises som tekst og ikke som rå HTML.
// Bruges på data fra backend og brugerinput før det indsættes i innerHTML.
function escapeHtml(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}