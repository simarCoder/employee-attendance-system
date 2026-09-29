/**
 * utils.js
 * Handles global UI interactions like Toasts and Modals.
 */

// --- TOAST NOTIFICATIONS ---
function showToast(message, type = "success") {
  let container = document.getElementById("toast-container");
  if (!container) {
    container = document.createElement("div");
    container.id = "toast-container";
    document.body.appendChild(container);
  }

  const toast = document.createElement("div");
  toast.className = `toast ${type}`;
  toast.innerHTML = `<span>${message}</span>`;

  container.appendChild(toast);

  setTimeout(() => {
    toast.style.animation = "fadeOut 0.3s ease-out forwards";
    setTimeout(() => {
      toast.remove();
    }, 300);
  }, 3000);
}

// --- CONFIRMATION MODAL ---
let confirmCallback = null;

function showConfirmModal(message, callback) {
  const modal = document.getElementById("custom-modal");
  const msgEl = document.getElementById("modal-message");

  if (msgEl) msgEl.innerText = message;
  confirmCallback = callback;

  if (modal) modal.classList.add("active");
}

function closeConfirmModal() {
  const modal = document.getElementById("custom-modal");
  if (modal) modal.classList.remove("active");
  confirmCallback = null;
}

function handleConfirmYes() {
  if (confirmCallback) confirmCallback();
  closeConfirmModal();
}

// --- SHARED HELPERS ---

/** Format stored ISO dates as DD-MM-YYYY for attendance screens. */
function formatDateDDMMYYYY(dateString) {
  if (!dateString) return "-";
  const match = String(dateString).match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!match) return String(dateString);
  return `${match[3]}-${match[2]}-${match[1]}`;
}

window.formatDateDDMMYYYY = formatDateDDMMYYYY;

function filterTableBodyRows(tbodyId, query) {
  const tbody = document.getElementById(tbodyId);
  if (!tbody) return;
  const term = String(query || "").trim().toLocaleLowerCase();
  let recordCount = 0;
  let matchCount = 0;
  Array.from(tbody.rows).forEach((row) => {
    if (row.cells.length === 1 && row.cells[0].colSpan > 1) return;
    recordCount += 1;
    const matches = row.textContent.toLocaleLowerCase().includes(term);
    row.hidden = !matches;
    if (matches) matchCount += 1;
  });
  const emptyId = `${tbodyId}-search-empty`;
  let emptyRow = document.getElementById(emptyId);
  if (!emptyRow && recordCount) {
    emptyRow = document.createElement("tr");
    emptyRow.id = emptyId;
    const colSpan = tbody.rows[0]?.cells.length || 1;
    emptyRow.innerHTML = `<td colspan="${colSpan}" class="individual-attendance-empty">No matching records.</td>`;
    tbody.appendChild(emptyRow);
  }
  if (emptyRow) emptyRow.hidden = !term || matchCount > 0 || recordCount === 0;
}

window.filterTableBodyRows = filterTableBodyRows;

/**
 * Populates a select dropdown with employee options.
 * Used by Attendance and Salary modules.
 */
function populateEmployeeDropdown(selectId, employees) {
  const select = document.getElementById(selectId);
  if (!select) return;

  select.innerHTML = '<option value="">Select Employee...</option>';

  employees.forEach((emp) => {
    const option = document.createElement("option");
    option.value = emp.id || emp.employee_id;
    option.textContent = `${emp.name} (${emp.role})`;
    select.appendChild(option);
  });
}

// Expose to window
window.showToast = showToast;
window.showConfirmModal = showConfirmModal;
window.populateEmployeeDropdown = populateEmployeeDropdown;
