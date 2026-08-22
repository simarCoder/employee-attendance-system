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

  return `${hours}:${minutes} ${suffix}`;
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

function setAttendanceLoading(message = "Loading attendance...") {
  const tbody = document.getElementById("dashboard-attendance-body");

  if (!tbody) return;

  tbody.innerHTML = `
    <tr>
      <td colspan="8" style="text-align:center;">
        ${escapeHtml(message)}
      </td>
    </tr>
  `;
}

function renderAttendanceRecords(records) {
  const tbody = document.getElementById("dashboard-attendance-body");

  if (!tbody) {
    console.error("Dashboard attendance table body not found.");
    return;
  }

  tbody.innerHTML = "";

  if (!records || records.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="8"
            style="text-align:center; color:var(--text-muted);">
          No attendance records found.
        </td>
      </tr>
    `;

    return;
  }

  records.forEach((record) => {
    const row = document.createElement("tr");

    row.innerHTML = `
      <td>${formatDateDisplay(record.date)}</td>

      <td>#${escapeHtml(record.employee_id)}</td>

      <td>${escapeHtml(record.name)}</td>

      <td>${escapeHtml(record.role || "-")}</td>

      <td>${formatTime12Hour(record.check_in)}</td>

      <td>${formatTime12Hour(record.check_out)}</td>

      <td>
    ${
      record.worked_hours !== null && record.worked_hours !== undefined
        ? formatDuration(Math.round(Number(record.worked_hours) * 60))
        : "-"
    }
</td>

      <td>${escapeHtml(record.status || "-")}</td>
    `;

    tbody.appendChild(row);
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

async function loadDashboardAttendance(selectedDate) {
  setAttendanceLoading();

  try {
    const response = await fetch(
      `/api/attendance?date=${encodeURIComponent(selectedDate)}`,
    );

    const data = await response.json();

    if (!response.ok || !data.success) {
      throw new Error(data.error || "Failed to load attendance");
    }

    renderAttendanceRecords(data.records);
  } catch (error) {
    console.error("Dashboard attendance loading failed:", error);

    setAttendanceLoading("Failed to load attendance.");
  }
}

async function loadDashboardAttendanceRange(startDate, endDate) {
  setAttendanceLoading();

  try {
    const response = await fetch(
      `/api/attendance/range?start_date=${encodeURIComponent(startDate)}&end_date=${encodeURIComponent(endDate)}`,
    );

    const data = await response.json();

    if (!response.ok || !data.success) {
      throw new Error(data.error || "Failed to load attendance");
    }

    renderAttendanceRecords(data.records);
  } catch (error) {
    console.error("Dashboard attendance range loading failed:", error);

    setAttendanceLoading("Failed to load attendance.");
  }
}

function getMonthRange(year, month) {
  const startDate = `${year}-${String(month).padStart(2, "0")}-01`;

  const lastDay = new Date(Number(year), Number(month), 0).getDate();

  const endDate = `${year}-${String(month).padStart(2, "0")}-${String(lastDay).padStart(2, "0")}`;

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

function loadAttendanceBySelectedView() {
  const mode = document.getElementById("attendance-view-mode").value;

  if (mode === "day") {
    const date = document.getElementById("dashboard-attendance-date").value;

    if (!date) return;

    loadDashboardAttendance(date);
    return;
  }

  if (mode === "month") {
    const month = document.getElementById("dashboard-attendance-month").value;

    const year = document.getElementById(
      "dashboard-attendance-month-year",
    ).value;

    if (!month || !year) return;

    const range = getMonthRange(year, month);

    loadDashboardAttendanceRange(range.startDate, range.endDate);

    return;
  }

  if (mode === "year") {
    const year = document.getElementById("dashboard-attendance-year").value;

    if (!year) return;

    const range = getYearRange(year);

    loadDashboardAttendanceRange(range.startDate, range.endDate);
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

  updateAttendanceControls();

  // Default view = today
  loadDashboardAttendance(today);
}
