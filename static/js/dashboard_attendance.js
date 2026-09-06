let dashboardAttendanceRecords = [];
let dashboardAttendanceLoading = false;

function escapeHtml(value) {
  if (value === null || value === undefined) {
    return "";
  }

  const div = document.createElement("div");
  div.textContent = String(value);
  return div.innerHTML;
}

function getLocalDateString() {
  const now = new Date();

  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");

  return `${year}-${month}-${day}`;
}

function formatTime12Hour(timeStr) {
  if (!timeStr) return "-";

  const [hours24, minutes] = timeStr.split(":");

  let hours = parseInt(hours24, 10);

  if (Number.isNaN(hours)) {
    return "-";
  }

  const suffix = hours >= 12 ? "PM" : "AM";

  hours = hours % 12 || 12;

  return `${hours}:${minutes}\u00a0${suffix}`;
}

function formatDateDisplay(dateStr) {
  if (!dateStr) return "-";

  const parts = dateStr.split("-");

  if (parts.length !== 3) {
    return dateStr;
  }

  const [year, month, day] = parts;

  const date = new Date(Number(year), Number(month) - 1, Number(day));

  return date.toLocaleDateString("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

function formatDuration(minutes) {
  if (
    minutes === null ||
    minutes === undefined ||
    Number.isNaN(Number(minutes))
  ) {
    return "-";
  }

  minutes = Math.max(0, Math.round(Number(minutes)));

  const hours = Math.floor(minutes / 60);
  const mins = minutes % 60;

  if (hours === 0) {
    return `${mins}m`;
  }

  if (mins === 0) {
    return `${hours}h`;
  }

  return `${hours}h ${mins}m`;
}

function calculateDashboardOvertime(record) {
  if (
    record.worked_minutes === null ||
    record.worked_minutes === undefined ||
    record.daily_hours === null ||
    record.daily_hours === undefined
  ) {
    return null;
  }

  const workedMinutes = Number(record.worked_minutes);
  const dailyHours = Number(record.daily_hours);

  if (!Number.isFinite(workedMinutes) || !Number.isFinite(dailyHours)) {
    return null;
  }

  return Math.max(0, Math.round(workedMinutes - dailyHours * 60));
}

function setAttendanceLoading(message = "Loading attendance...") {
  const tbody = document.getElementById("dashboard-attendance-body");

  if (!tbody) return;

  tbody.innerHTML = `
    <tr>
      <td colspan="9" style="text-align:center;">
        ${escapeHtml(message)}
      </td>
    </tr>
  `;

  dashboardAttendanceLoading = true;
}

function renderAttendanceRecords(records) {
  const tbody = document.getElementById("dashboard-attendance-body");

  if (!tbody) return;

  dashboardAttendanceRecords = Array.isArray(records) ? records : [];

  tbody.innerHTML = "";

  if (dashboardAttendanceRecords.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td
          colspan="9"
          style="
            text-align:center;
            color:var(--text-muted);
          "
        >
          No attendance records found.
        </td>
      </tr>
    `;

    updateAttendanceSummary([]);
    dashboardAttendanceLoading = false;
    return;
  }

  dashboardAttendanceRecords.forEach((record) => {
    const row = document.createElement("tr");

    // Calculate on every dashboard render so this view never depends on a
    // previously stored overtime value.
    const overtimeMinutes = calculateDashboardOvertime(record);

    row.innerHTML = `
        <td>
          ${formatDateDisplay(record.date)}
        </td>

        <td>
          #${escapeHtml(record.employee_id)}
        </td>

        <td>
          ${escapeHtml(record.name)}
        </td>

        <td>
          ${escapeHtml(record.role || "-")}
        </td>

        <td>
          ${formatTime12Hour(record.check_in)}
        </td>

        <td>
          ${formatTime12Hour(record.check_out)}
        </td>

        <td>
          ${
            record.worked_minutes !== null &&
            record.worked_minutes !== undefined
              ? formatDuration(record.worked_minutes)
              : "-"
          }
        </td>

        <td>
          ${overtimeMinutes > 0 ? formatDuration(overtimeMinutes) : "-"}
        </td>

        <td>
          ${escapeHtml(record.status || "-")}
        </td>
      `;

    tbody.appendChild(row);
  });

  updateAttendanceSummary(dashboardAttendanceRecords);

  dashboardAttendanceLoading = false;
}

function updateAttendanceSummary(records) {
  const present = records.filter(
    (record) => record.status === "Present",
  ).length;

  const incomplete = records.filter(
    (record) => record.status === "Incomplete",
  ).length;

  const absent = records.filter((record) => record.status === "Absent").length;

  const scheduledDays = records.filter(
    (record) => record.scheduled === true,
  ).length;

  const presentElement = document.getElementById("attendance-present-count");

  const incompleteElement = document.getElementById(
    "attendance-incomplete-count",
  );

  const absentElement = document.getElementById("attendance-absent-count");

  const scheduledElement = document.getElementById(
    "attendance-scheduled-count",
  );

  if (presentElement) {
    presentElement.textContent = present;
  }

  if (incompleteElement) {
    incompleteElement.textContent = incomplete;
  }

  if (absentElement) {
    absentElement.textContent = absent;
  }

  if (scheduledElement) {
    scheduledElement.textContent = scheduledDays;
  }
}

function getSelectedAttendanceRange() {
  const mode = document.getElementById("attendance-view-mode").value;

  if (mode === "day") {
    const date = document.getElementById("dashboard-attendance-date").value;

    if (!date) {
      return null;
    }

    return {
      mode: "day",
      startDate: date,
      endDate: date,
    };
  }

  if (mode === "month") {
    const month = document.getElementById("dashboard-attendance-month").value;

    const year = document.getElementById(
      "dashboard-attendance-month-year",
    ).value;

    if (!month || !year) {
      return null;
    }

    const range = getMonthRange(year, month);

    return {
      mode: "month",
      ...range,
    };
  }

  if (mode === "year") {
    const year = document.getElementById("dashboard-attendance-year").value;

    if (!year) {
      return null;
    }

    const range = getYearRange(year);

    return {
      mode: "year",
      ...range,
    };
  }

  return null;
}

async function loadDashboardAttendance(
  selectedDate,
  { preserveTable = false } = {},
) {
  if (!preserveTable) {
    setAttendanceLoading();
  }

  try {
    const response = await fetch(
      `/api/attendance?date=${encodeURIComponent(selectedDate)}`,
    );

    const data = await response.json();

    if (!response.ok || !data.success) {
      throw new Error(data.error || "Failed to load attendance");
    }

    renderAttendanceRecords(data.records);

    return true;
  } catch (error) {
    console.error("Dashboard attendance loading failed:", error);

    if (!preserveTable) {
      setAttendanceLoading("Failed to load attendance.");
    }

    return false;
  }
}

async function loadDashboardAttendanceRange(
  startDate,
  endDate,
  { preserveTable = false } = {},
) {
  if (!preserveTable) {
    setAttendanceLoading();
  }

  try {
    const response = await fetch(
      `/api/attendance/range?start_date=${encodeURIComponent(startDate)}&end_date=${encodeURIComponent(endDate)}`,
    );

    const data = await response.json();

    if (!response.ok || !data.success) {
      throw new Error(data.error || "Failed to load attendance");
    }

    renderAttendanceRecords(data.records);

    return true;
  } catch (error) {
    console.error("Dashboard attendance range loading failed:", error);

    if (!preserveTable) {
      setAttendanceLoading("Failed to load attendance.");
    }

    return false;
  }
}

function getMonthRange(year, month) {
  const startDate = `${year}-${String(month).padStart(2, "0")}-01`;

  const lastDay = new Date(Number(year), Number(month), 0).getDate();

  const endDate = `${year}-${String(month).padStart(2, "0")}-${String(
    lastDay,
  ).padStart(2, "0")}`;

  return {
    startDate,
    endDate,
  };
}

function getYearRange(year) {
  return {
    startDate: `${year}-01-01`,
    endDate: `${year}-12-31`,
  };
}

function updateAttendanceControls() {
  const mode = document.getElementById("attendance-view-mode").value;

  const dayControls = document.getElementById("attendance-day-controls");

  const monthControls = document.getElementById("attendance-month-controls");

  const yearControls = document.getElementById("attendance-year-controls");

  dayControls.style.display = "none";

  monthControls.style.display = "none";

  yearControls.style.display = "none";

  if (mode === "day") {
    dayControls.style.display = "flex";
  }

  if (mode === "month") {
    monthControls.style.display = "flex";
  }

  if (mode === "year") {
    yearControls.style.display = "flex";
  }
}

function ensureAttendanceYearOption(select, year) {
  if (!select) return;

  if (!Array.from(select.options).some((option) => Number(option.value) === year)) {
    const option = document.createElement("option");
    option.value = String(year);
    option.textContent = String(year);
    select.appendChild(option);
  }
}

async function navigateAttendancePeriod(direction) {
  const mode = document.getElementById("attendance-view-mode").value;

  if (mode === "day") {
    const input = document.getElementById("dashboard-attendance-date");
    const [year, month, day] = input.value.split("-").map(Number);
    const date = new Date(year, month - 1, day);
    date.setDate(date.getDate() + direction);
    input.value = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
  }

  if (mode === "month") {
    const month = document.getElementById("dashboard-attendance-month");
    const year = document.getElementById("dashboard-attendance-month-year");
    const date = new Date(Number(year.value), Number(month.value) - 1 + direction, 1);
    ensureAttendanceYearOption(year, date.getFullYear());
    year.value = String(date.getFullYear());
    month.value = String(date.getMonth() + 1);
  }

  if (mode === "year") {
    const year = document.getElementById("dashboard-attendance-year");
    const nextYear = Number(year.value) + direction;
    ensureAttendanceYearOption(year, nextYear);
    year.value = String(nextYear);
  }

  await loadAttendanceBySelectedView();
}

async function loadAttendanceBySelectedView(options = {}) {
  const mode = document.getElementById("attendance-view-mode").value;

  if (mode === "day") {
    const date = document.getElementById("dashboard-attendance-date").value;

    if (!date) return false;

    return await loadDashboardAttendance(date, options);
  }

  if (mode === "month") {
    const month = document.getElementById("dashboard-attendance-month").value;

    const year = document.getElementById(
      "dashboard-attendance-month-year",
    ).value;

    if (!month || !year) return false;

    const range = getMonthRange(year, month);

    return await loadDashboardAttendanceRange(
      range.startDate,
      range.endDate,
      options,
    );
  }

  if (mode === "year") {
    const year = document.getElementById("dashboard-attendance-year").value;

    if (!year) return false;

    const range = getYearRange(year);

    return await loadDashboardAttendanceRange(
      range.startDate,
      range.endDate,
      options,
    );
  }

  return false;
}

async function reloadDashboardAttendanceTable() {
  const container = document.querySelector(
    ".dashboard-attendance-table-container",
  );

  const button = document.getElementById("dashboard-attendance-reload");

  if (!container || !button) {
    return;
  }

  if (button.classList.contains("is-loading")) {
    return;
  }

  const reloadText = button.querySelector(".reload-text");

  button.classList.add("is-loading");
  container.classList.add("is-reloading");

  if (reloadText) {
    reloadText.textContent = "Refreshing";
  }

  try {
    const success = await loadAttendanceBySelectedView({
      preserveTable: true,
    });

    if (success) {
      container.classList.remove("is-reloading");

      /*
       * Force the animation to restart even when
       * the same table content is returned.
       */
      container.classList.remove("table-refreshed");

      void container.offsetWidth;

      container.classList.add("table-refreshed");

      setTimeout(() => {
        container.classList.remove("table-refreshed");
      }, 500);
    }
  } finally {
    container.classList.remove("is-reloading");

    button.classList.remove("is-loading");

    if (reloadText) {
      reloadText.textContent = "Reload";
    }
  }
}

function populateAttendanceYears() {
  const currentYear = new Date().getFullYear();

  const yearSelects = [
    document.getElementById("dashboard-attendance-month-year"),
    document.getElementById("dashboard-attendance-year"),
  ];

  yearSelects.forEach((select) => {
    if (!select) return;

    select.innerHTML = "";

    for (let year = currentYear - 5; year <= currentYear + 1; year++) {
      const option = document.createElement("option");

      option.value = year;
      option.textContent = year;

      if (year === currentYear) {
        option.selected = true;
      }

      select.appendChild(option);
    }
  });
}

function setCurrentMonth() {
  const monthSelect = document.getElementById("dashboard-attendance-month");

  if (!monthSelect) return;

  monthSelect.value = String(new Date().getMonth() + 1);
}

function setReloadButtonState(loading) {
  const button = document.getElementById("dashboard-attendance-reload");

  if (!button) return;

  button.disabled = loading;

  button.textContent = loading ? "↻ Loading..." : "↻ Reload";
}

async function reloadDashboardAttendance() {
  setReloadButtonState(true);

  try {
    await loadAttendanceBySelectedView();
  } finally {
    setReloadButtonState(false);
  }
}

function initAttendanceSummaryCards() {
  const cards = document.querySelectorAll(".attendance-summary-card");

  cards.forEach((card) => {
    card.addEventListener("click", () => {
      // Employee-list modal can be added here
      // without changing attendance calculations.
      console.log("Attendance summary card clicked.");
    });
  });
}

function initDashboardAttendance() {
  const modeSelect = document.getElementById("attendance-view-mode");

  const dateInput = document.getElementById("dashboard-attendance-date");

  if (!modeSelect || !dateInput) {
    console.error("Dashboard attendance controls not found.");

    return;
  }

  const today = getLocalDateString();

  dateInput.value = today;

  populateAttendanceYears();

  setCurrentMonth();

  modeSelect.addEventListener("change", function () {
    updateAttendanceControls();
    loadAttendanceBySelectedView();
  });

  dateInput.addEventListener("change", function () {
    if (modeSelect.value === "day") {
      loadDashboardAttendance(this.value);
    }
  });

  document
    .getElementById("dashboard-attendance-month")
    .addEventListener("change", loadAttendanceBySelectedView);

  document
    .getElementById("dashboard-attendance-month-year")
    .addEventListener("change", loadAttendanceBySelectedView);

  document
    .getElementById("dashboard-attendance-year")
    .addEventListener("change", loadAttendanceBySelectedView);

  const reloadButton = document.getElementById("dashboard-attendance-reload");

  if (reloadButton) {
    reloadButton.addEventListener("click", reloadDashboardAttendanceTable);
  }

  document
    .getElementById("dashboard-attendance-previous")
    .addEventListener("click", () => navigateAttendancePeriod(-1));

  document
    .getElementById("dashboard-attendance-next")
    .addEventListener("click", () => navigateAttendancePeriod(1));

  updateAttendanceControls();

  initAttendanceSummaryCards();

  loadDashboardAttendance(today);
}

document.addEventListener("DOMContentLoaded", initDashboardAttendance);
