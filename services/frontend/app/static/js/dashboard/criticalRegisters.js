import {
    fetchCriticalRegisters,
    saveCriticalRegister,
    deleteCriticalRegister,
} from "./api.js";

let isOpen = false;
let registers = [];
let errorMessage = "";

export function openCriticalRegistersModal() {
    isOpen = true;
    errorMessage = "";
    loadCriticalRegisters();
    renderCriticalRegistersModal();
}

export function renderCriticalRegistersModal() {
    const root = document.getElementById("critical-register-modal-root");
    if (!root) return;

    if (!isOpen) {
        root.innerHTML = "";
        return;
    }

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

                <div class="critical-register-list">
                    ${renderRegisterRows()}
                </div>
            </div>
        </div>
    `;

    document.getElementById("critical-register-close")?.addEventListener("click", closeCriticalRegistersModal);
    document.getElementById("critical-register-form")?.addEventListener("submit", handleSubmit);

    document.querySelectorAll("[data-critical-register-delete]").forEach((button) => {
        button.addEventListener("click", async () => {
            const id = button.getAttribute("data-critical-register-delete");
            await handleDelete(id);
        });
    });
}

function renderRegisterRows() {
    if (!registers.length) {
        return `<div class="critical-register-empty">Ingen critical registers endnu.</div>`;
    }

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

async function loadCriticalRegisters() {
    try {
        registers = await fetchCriticalRegisters();
        renderCriticalRegistersModal();
    } catch (error) {
        errorMessage = error.message;
        renderCriticalRegistersModal();
    }
}

async function handleSubmit(event) {
    event.preventDefault();

    const formData = new FormData(event.currentTarget);
    const allowedValuesRaw = String(formData.get("allowed_values") || "").trim();

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
        await saveCriticalRegister(payload);
        errorMessage = "";
        await loadCriticalRegisters();
    } catch (error) {
        errorMessage = error.message;
        renderCriticalRegistersModal();
    }
}

async function handleDelete(id) {
    try {
        await deleteCriticalRegister(id);
        errorMessage = "";
        await loadCriticalRegisters();
    } catch (error) {
        errorMessage = error.message;
        renderCriticalRegistersModal();
    }
}

function closeCriticalRegistersModal() {
    isOpen = false;
    renderCriticalRegistersModal();
}

function parseAllowedValues(raw) {
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

function formatAllowedValues(values) {
    if (!values || !Array.isArray(values) || !values.length) {
        return "any";
    }

    return values.map((value) => escapeHtml(value)).join(", ");
}

function escapeHtml(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}