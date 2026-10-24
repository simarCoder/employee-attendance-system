/**
 * attendance.js
 * Handles Check-in, Check-out, and Attendance History.
 */

// Ensure global access if utils loaded, otherwise define locally or wait
window.addEventListener("employeesLoaded", (e) => {
  const employees = e.detail;
  if (typeof populateEmployeeDropdown === "function") {
    populateEmployeeDropdown("att-employee-select", employees);
  }
});

async function handleCheckIn() {
  const empId = document.getElementById("att-employee-select").value;

  // Get manual inputs if exist (Admin/Head features)
  const manualTimeInput = document.getElementById("att-manual-time");
  const manualDateInput = document.getElementById("att-manual-date");

  const manualTime = manualTimeInput ? manualTimeInput.value : null;
  const manualDate = manualDateInput ? manualDateInput.value : null;

  const role = sessionStorage.getItem("role");

  if (!empId) {
    if (window.showToast) showToast("Please select an employee", "error");
    else alert("Please select an employee");
    return;
  }

  try {
    const payload = {
      employee_id: parseInt(empId),
      manual_time: manualTime,
      manual_date: manualDate,
      role: role,
    };

    const response = await fetch(`${API_BASE}/attendance/checkin`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (response.ok) {
      if (window.showToast) showToast("Check-in Successful", "success");

      // Clear manual inputs if success
      if (manualTimeInput) manualTimeInput.value = "";
      if (manualDateInput) manualDateInput.value = "";

      setTimeout(() => loadAttendanceHistory(empId), 100);
    } else {
      const data = await response.json();
      if (window.showToast)
        showToast(data.message || "Check-in failed", "error");
    }
  } catch (error) {
    console.error(error);
    if (window.showToast) showToast("Server error", "error");
  }
}

async function handleCheckOut() {
  const empId = document.getElementById("att-employee-select").value;

  const manualTimeInput = document.getElementById("att-manual-time");
  const manualDateInput = document.getElementById("att-manual-date");

  const manualTime = manualTimeInput ? manualTimeInput.value : null;
  const manualDate = manualDateInput ? manualDateInput.value : null;

  const role = sessionStorage.getItem("role");

  if (!empId) {
    if (window.showToast) showToast("Please select an employee", "error");
    return;
  }

  try {
    const payload = {
      employee_id: parseInt(empId),
      manual_time: manualTime,
      manual_date: manualDate,
      role: role,
    };

    const response = await fetch(`${API_BASE}/attendance/checkout`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (response.ok) {
      if (window.showToast) showToast("Check-out Successful", "success");

      if (manualTimeInput) manualTimeInput.value = "";
      if (manualDateInput) manualDateInput.value = "";

      setTimeout(() => loadAttendanceHistory(empId), 200);
    } else {
      const data = await response.json();
      if (window.showToast)
        showToast(data.message || "Check-out failed", "error");
    }
  } catch (error) {
    console.error(error);
    if (window.showToast) showToast("Server error", "error");
  }
}

function formatTime12Hour(timeStr) {
  if (!timeStr) return "-";
  // Assuming timeStr is "HH:MM:SS" or "HH:MM"
  const [hours24, minutes] = timeStr.split(":");
  let hours = parseInt(hours24, 10);
  const suffix = hours >= 12 ? "PM" : "AM";

  hours = hours % 12 || 12; // Convert 0 to 12

  return `${hours}:${minutes} ${suffix}`;
}

function escapeHtml(value) {
  const div = document.createElement("div");
  div.textContent = value ?? "";
  return div.innerHTML;
}

function formatPendingDate(dateStr) {
  if (!dateStr) return "-";

  const parts = String(dateStr).split("-");

  if (parts.length !== 3) {
    return dateStr;
  }

  const [year, month, day] = parts;

  return `${day}-${month}-${year}`;
}

function formatTimeForInput(timeStr) {
  if (!timeStr) return "";

  const [hours, minutes] = timeStr.split(":");

  if (!hours || !minutes) {
    return "";
  }

  return `${hours}:${minutes}`;
}

async function loadPendingAttendance() {
  const tbody = document.getElementById("pending-attendance-body");

  if (!tbody) return;

  tbody.innerHTML = `
    <tr>
      <td
        colspan="4"
        class="individual-attendance-empty"
      >
        Loading pending attendance...
      </td>
    </tr>
  `;

  try {
    const response = await fetch(
      `${API_BASE}/attendance/pending?t=${Date.now()}`,
    );

    const data = await response.json();

    if (!response.ok || !data.success) {
      throw new Error(data.message || "Failed to load pending attendance.");
    }

    updatePendingAttendanceCount(data.count);

    tbody.innerHTML = "";

    if (!data.records || data.records.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td
            colspan="4"
            class="individual-attendance-empty"
          >
            ✓ No pending attendance
          </td>
        </tr>
      `;

      return;
    }

    data.records.forEach((record) => {
      const row = document.createElement("tr");

      row.dataset.attendanceId = record.attendance_id;

      row.innerHTML = `

        <td>
          <strong>
            ${escapeHtml(record.name)}
          </strong>
        </td>

        <td>
          ${formatPendingDate(record.date)}
        </td>

        <td>
          ${createPendingTimeEditor(
            record.check_in,
            record.attendance_id,
            "check_in",
          )}
        </td>

        <td>
          ${createPendingTimeEditor(
            record.check_out,
            record.attendance_id,
            "check_out",
          )}
        </td>

      `;

      tbody.appendChild(row);
    });
    tbody.querySelectorAll(".pending-time-editor").forEach((editor) => {
      updatePendingTimeEditorState(editor);

      editor.querySelectorAll("select").forEach((select) => {
        select.addEventListener("change", () => {
          updatePendingTimeEditorState(editor);
        });
      });
    });

    filterPendingAttendance(
      document.getElementById("pending-attendance-search")?.value || "",
    );
  } catch (error) {
    console.error("Error loading pending attendance:", error);

    tbody.innerHTML = `
      <tr>
        <td
          colspan="4"
          class="individual-attendance-empty"
        >
          Unable to load pending attendance.
        </td>
      </tr>
    `;
  }
}
function updatePendingAttendanceCount(count) {
  const countElement = document.getElementById("pending-attendance-count");

  if (!countElement) return;

  countElement.textContent = Number(count || 0);
}
function convert12HourTo24Hour(hour, minute, period) {
  let hours = parseInt(hour, 10);
  const minutes = parseInt(minute, 10);

  if (Number.isNaN(hours) || Number.isNaN(minutes)) {
    return null;
  }

  if (hours < 1 || hours > 12 || minutes < 0 || minutes > 59) {
    return null;
  }

  if (period === "AM") {
    if (hours === 12) {
      hours = 0;
    }
  } else {
    if (hours !== 12) {
      hours += 12;
    }
  }

  return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}`;
}

function createPendingTimeEditor(time, attendanceId, punchType) {
  const hasTime =
    time !== null && time !== undefined && String(time).trim() !== "";

  let selectedHour = "";
  let selectedMinute = "";
  let selectedPeriod = "";

  // --------------------------------------------------
  // EXISTING TIME
  // --------------------------------------------------

  if (hasTime) {
    const parts = String(time).split(":");

    if (parts.length >= 2) {
      let hours = parseInt(parts[0], 10);

      selectedMinute = String(parts[1]).padStart(2, "0");

      selectedPeriod = hours >= 12 ? "PM" : "AM";

      hours = hours % 12 || 12;

      selectedHour = String(hours).padStart(2, "0");
    }
  }

  // --------------------------------------------------
  // HOUR OPTIONS
  // --------------------------------------------------

  const hourOptions = `
    <option value="" ${!selectedHour ? "selected" : ""}>
      --
    </option>

    ${Array.from({ length: 12 }, (_, index) => {
      const hour = String(index + 1).padStart(2, "0");

      return `
        <option
          value="${hour}"
          ${hour === selectedHour ? "selected" : ""}
        >
          ${hour}
        </option>
      `;
    }).join("")}
  `;

  // --------------------------------------------------
  // MINUTE OPTIONS
  // --------------------------------------------------

  const minuteOptions = `
    <option value="" ${!selectedMinute ? "selected" : ""}>
      --
    </option>

    ${Array.from({ length: 60 }, (_, index) => {
      const minute = String(index).padStart(2, "0");

      return `
        <option
          value="${minute}"
          ${minute === selectedMinute ? "selected" : ""}
        >
          ${minute}
        </option>
      `;
    }).join("")}
  `;

  // --------------------------------------------------
  // AM / PM OPTIONS
  // --------------------------------------------------

  const periodOptions = `
    <option value="" ${!selectedPeriod ? "selected" : ""}>
      --
    </option>

    <option
      value="AM"
      ${selectedPeriod === "AM" ? "selected" : ""}
    >
      AM
    </option>

    <option
      value="PM"
      ${selectedPeriod === "PM" ? "selected" : ""}
    >
      PM
    </option>
  `;

  return `
    <div
      class="pending-time-editor"
      data-attendance-id="${attendanceId}"
      data-punch-type="${punchType}"
    >

      <select
        class="pending-time-hour"
        aria-label="Hour"
      >
        ${hourOptions}
      </select>

      <span class="pending-time-separator">:</span>

      <select
        class="pending-time-minute"
        aria-label="Minute"
      >
        ${minuteOptions}
      </select>

      <select
        class="pending-time-period"
        aria-label="AM or PM"
      >
        ${periodOptions}
      </select>

      <button
        type="button"
        class="btn btn-primary pending-save-btn"
        onclick="savePendingAttendance(this)"
        title="Save ${punchType === "check_in" ? "check-in" : "check-out"}"
      >
        ✓
      </button>

    </div>
  `;
}
async function savePendingAttendance(button) {
  const editor = button.closest(".pending-time-editor");

  if (!editor) return;

  const attendanceId = editor.dataset.attendanceId;

  const punchType = editor.dataset.punchType;

  const hour = editor.querySelector(".pending-time-hour").value;

  const minute = editor.querySelector(".pending-time-minute").value;

  const period = editor.querySelector(".pending-time-period").value;

  // --------------------------------------------------
  // DO NOT SAVE AN EMPTY TIME
  // --------------------------------------------------

  if (!hour || !minute || !period) {
    if (window.showToast) {
      showToast(
        `Please select a complete ${
          punchType === "check_in" ? "check-in" : "check-out"
        } time.`,
        "error",
      );
    }

    return;
  }

  const manualTime = convert12HourTo24Hour(hour, minute, period);

  if (!manualTime) {
    if (window.showToast) {
      showToast("Please select a valid time.", "error");
    }

    return;
  }

  button.disabled = true;

  try {
    const response = await fetch(`${API_BASE}/attendance/pending/update`, {
      method: "POST",

      headers: {
        "Content-Type": "application/json",
      },

      body: JSON.stringify({
        attendance_id: attendanceId,
        punch_type: punchType,
        manual_time: manualTime,
        role: sessionStorage.getItem("role"),
      }),
    });

    const data = await response.json();

    if (!response.ok || !data.success) {
      throw new Error(data.message || "Failed to update attendance.");
    }

    if (window.showToast) {
      showToast(
        `${
          punchType === "check_in" ? "Check-in" : "Check-out"
        } updated successfully.`,
        "success",
      );
    }

    // Refresh only the pending list
    await loadPendingAttendance();

    // Refresh only selected employee history
    const employeeId = document.getElementById("att-employee-select")?.value;

    if (employeeId) {
      await loadAttendanceHistory(employeeId);
    }
  } catch (error) {
    console.error("Pending attendance update failed:", error);

    if (window.showToast) {
      showToast(error.message || "Attendance update failed.", "error");
    }
  } finally {
    button.disabled = false;
  }
}
function updatePendingTimeEditorState(editor) {
  const hour = editor.querySelector(".pending-time-hour");

  const minute = editor.querySelector(".pending-time-minute");

  const period = editor.querySelector(".pending-time-period");

  if (!hour || !minute || !period) return;

  hour.classList.toggle("is-empty", !hour.value);

  minute.classList.toggle("is-empty", !minute.value);

  period.classList.toggle("is-empty", !period.value);
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

async function loadAttendanceHistory(empId) {
  // If no ID passed, try to get from dropdown
  if (!empId) empId = document.getElementById("att-employee-select").value;
  if (!empId) return;

  const tbody = document.getElementById("attendance-table-body");
  const monthInput = document.getElementById("individual-attendance-month");
  const month = monthInput?.value || new Date().toISOString().slice(0, 7);
  const caption = document.getElementById("individual-attendance-caption");
  if (caption) {
    const [year, monthNumber] = month.split("-").map(Number);
    caption.textContent = new Date(year, monthNumber - 1, 1).toLocaleDateString(
      undefined,
      { month: "long", year: "numeric" },
    );
  }
  if (tbody)
    tbody.innerHTML = `<tr><td colspan="4" class="individual-attendance-empty">Loading attendance…</td></tr>`;

  try {
    // Cache busting timestamp
    const response = await fetch(
      `${API_BASE}/attendance/${empId}?month=${encodeURIComponent(month)}&t=${new Date().getTime()}`,
    );

    if (response.ok) {
      const data = await response.json();
      if (tbody) {
        tbody.innerHTML = "";

        if (data.length === 0) {
          tbody.innerHTML = `<tr><td colspan="4" class="individual-attendance-empty">No attendance records for this month.</td></tr>`;
          return;
        }

        data.forEach((record) => {
          const tr = document.createElement("tr");
          const checkInTime = record.check_in
            ? formatTime12Hour(record.check_in)
            : "-";
          const checkOutTime = record.check_out
            ? formatTime12Hour(record.check_out)
            : "-";

          tr.innerHTML = `
                        <td>${formatDateDDMMYYYY(record.date)}</td>
                        <td>${checkInTime}</td>
                        <td>${checkOutTime}</td>
                        <td>${formatDuration(record.worked_minutes)}</td>
                    `;
          tbody.appendChild(tr);
        });
        filterIndividualAttendance(
          document.getElementById("individual-attendance-search")?.value || "",
        );
      }
    } else {
      console.error("Failed to fetch attendance history");
      if (tbody)
        tbody.innerHTML = `<tr><td colspan="4" class="individual-attendance-empty">Error loading records.</td></tr>`;
    }
  } catch (error) {
    console.error("Error fetching attendance:", error);
    if (tbody)
      tbody.innerHTML = `<tr><td colspan="4" class="individual-attendance-empty">Unable to connect. Please try again.</td></tr>`;
  }
}

function filterIndividualAttendance(query) {
  const tbody = document.getElementById("attendance-table-body");
  if (!tbody) return;
  const term = String(query || "")
    .trim()
    .toLocaleLowerCase();
  let visibleCount = 0;
  let hasRecords = false;
  tbody.querySelectorAll("tr").forEach((row) => {
    if (row.cells.length === 1 && row.cells[0].colSpan > 1) return;
    hasRecords = true;
    const matches = row.textContent.toLocaleLowerCase().includes(term);
    row.hidden = !matches;
    if (matches) visibleCount += 1;
  });
  let emptyRow = document.getElementById("individual-attendance-no-results");
  if (!emptyRow) {
    emptyRow = document.createElement("tr");
    emptyRow.id = "individual-attendance-no-results";
    emptyRow.innerHTML =
      '<td colspan="4" class="individual-attendance-empty">No matching attendance records.</td>';
    tbody.appendChild(emptyRow);
  }
  emptyRow.hidden = !hasRecords || visibleCount > 0 || !term;
}

function filterPendingAttendance(query) {
  const tbody = document.getElementById("pending-attendance-body");

  if (!tbody) return;

  const term = String(query || "")
    .trim()
    .toLocaleLowerCase();

  let visibleCount = 0;
  let hasRecords = false;

  tbody.querySelectorAll("tr").forEach((row) => {
    // Ignore empty/status rows
    if (row.cells.length === 1 && row.cells[0].colSpan > 1) {
      return;
    }

    hasRecords = true;

    /*
     * Search only employee + date.
     *
     * We intentionally DON'T search row.textContent
     * because the time dropdown contains every option:
     * 01, 02, 03...12, AM, PM.
     *
     * Searching "AM" would otherwise match every row.
     */

    const employee = row.cells[0]?.textContent.toLocaleLowerCase() || "";

    const date = row.cells[1]?.textContent.toLocaleLowerCase() || "";

    const searchableText = `${employee} ${date}`;

    const matches = searchableText.includes(term);

    row.hidden = !matches;

    if (matches) {
      visibleCount += 1;
    }
  });

  let emptyRow = document.getElementById("pending-attendance-no-results");

  if (!emptyRow) {
    emptyRow = document.createElement("tr");

    emptyRow.id = "pending-attendance-no-results";

    emptyRow.innerHTML = `
      <td
        colspan="4"
        class="individual-attendance-empty"
      >
        No matching pending attendance.
      </td>
    `;

    tbody.appendChild(emptyRow);
  }

  emptyRow.hidden = !hasRecords || visibleCount > 0 || !term;
}

function currentAttendanceMonthValue() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}

function shiftIndividualAttendanceMonth(offset) {
  const input = document.getElementById("individual-attendance-month");
  if (!input) return;
  const [year, month] = (input.value || currentAttendanceMonthValue())
    .split("-")
    .map(Number);
  const next = new Date(year, month - 1 + offset, 1);
  input.value = `${next.getFullYear()}-${String(next.getMonth() + 1).padStart(2, "0")}`;
  const employeeId = document.getElementById("att-employee-select")?.value;
  if (employeeId) loadAttendanceHistory(employeeId);
}

const individualMonth = document.getElementById("individual-attendance-month");
if (individualMonth) {
  individualMonth.value = currentAttendanceMonthValue();
  individualMonth.addEventListener("change", () => {
    const employeeId = document.getElementById("att-employee-select")?.value;
    if (employeeId) loadAttendanceHistory(employeeId);
    else {
      const [year, month] = individualMonth.value.split("-").map(Number);
      const caption = document.getElementById("individual-attendance-caption");
      if (caption)
        caption.textContent = new Date(year, month - 1, 1).toLocaleDateString(
          undefined,
          { month: "long", year: "numeric" },
        );
    }
  });
}
document
  .getElementById("individual-attendance-previous")
  ?.addEventListener("click", () => shiftIndividualAttendanceMonth(-1));
document
  .getElementById("individual-attendance-next")
  ?.addEventListener("click", () => shiftIndividualAttendanceMonth(1));

// Trigger history load when dropdown changes
const attSelect = document.getElementById("att-employee-select");
if (attSelect) {
  attSelect.addEventListener("change", (e) => {
    loadAttendanceHistory(e.target.value);
  });
}

async function syncSecureye() {
  const button = document.getElementById("secureye-sync-btn");

  if (!button) return;

  const originalText = button.innerText;

  button.disabled = true;
  button.innerText = "Fetching...";

  try {
    const response = await fetch(`${API_BASE}/attendance/device-sync`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
    });

    const data = await response.json();

    if (!response.ok || !data.success) {
      throw new Error(data.error || "Device sync failed");
    }

    if (window.showToast) {
      showToast(
        `Sync complete. ${data.inserted} new, ${data.skipped} duplicate.`,
        "success",
      );
    } else {
      alert(
        `Sync complete.\n` +
          `New: ${data.inserted}\n` +
          `Duplicates: ${data.skipped}`,
      );
    }
    // Refresh attendance table after biometric sync
    const empId = document.getElementById("att-employee-select")?.value;

    if (empId) {
      await loadAttendanceHistory(empId);
    }
  } catch (error) {
    console.error("Secureye sync failed:", error);

    if (window.showToast) {
      showToast("Secureye sync failed: " + error.message, "error");
    } else {
      alert("Secureye sync failed: " + error.message);
    }
  } finally {
    button.disabled = false;
    button.innerText = originalText;
  }
}

// function  DashboardAttendance() {
//   const dateInput = document.getElementById("dashboard-attendance-date");

//   const today = new Date().toISOString().split("T")[0];

//   dateInput.value = today;

//   dateInput.addEventListener("change", function () {
//     loadDashboardAttendance(this.value);
//   });

//   loadDashboardAttendance(today);
// }

function showAttendancePanel(panelName, button) {
  document
    .querySelectorAll("#attendance .attendance-panel")
    .forEach((panel) => {
      panel.classList.toggle(
        "active",
        panel.id === `attendance-panel-${panelName}`,
      );
    });

  document
    .querySelectorAll("#attendance .attendance-nav-button")
    .forEach((navButton) => {
      const isActive = navButton === button;

      navButton.classList.toggle("active", isActive);

      navButton.setAttribute("aria-selected", String(isActive));
    });

  /*
   * When entering Individual,
   * always show the normal logs view.
   */

  if (panelName === "individual") {
    const logsView = document.getElementById("individual-logs-view");

    const pendingView = document.getElementById("pending-attendance-view");

    const pendingButton = document.getElementById("pending-attendance-toggle");

    const title = document.getElementById("individual-attendance-title");

    const caption = document.getElementById("individual-attendance-caption");

    const logTools = document.getElementById("individual-log-tools");

    if (logsView) {
      logsView.hidden = false;
    }

    if (pendingView) {
      pendingView.hidden = true;
    }

    if (pendingButton) {
      pendingButton.classList.remove("active");
    }

    if (title) {
      title.textContent = "Individual Attendance";
    }

    if (caption) {
      caption.textContent = "Select an employee to view monthly records";
    }

    if (logTools) {
      logTools.style.display = "";
    }

    /*
     * Load count only.
     * Do NOT open pending automatically.
     */
    loadPendingAttendanceCount();
  }

  updateAttendanceGoTop();
}

async function loadPendingAttendanceCount() {
  try {
    const response = await fetch(
      `${API_BASE}/attendance/pending?t=${Date.now()}`,
    );

    const data = await response.json();

    if (response.ok && data.success) {
      updatePendingAttendanceCount(data.count);
    }
  } catch (error) {
    console.error("Failed to load pending count:", error);
  }
}

function togglePendingAttendance() {
  const logsView = document.getElementById("individual-logs-view");
  const pendingView = document.getElementById("pending-attendance-view");

  const toggleButton = document.getElementById("pending-attendance-toggle");

  const title = document.getElementById("individual-attendance-title");

  const caption = document.getElementById("individual-attendance-caption");

  const logTools = document.getElementById("individual-log-tools");

  if (!logsView || !pendingView || !toggleButton) {
    return;
  }

  const showingPending = !pendingView.hidden;

  if (showingPending) {
    // Switch back to Individual Logs
    pendingView.hidden = true;
    logsView.hidden = false;

    toggleButton.classList.remove("active");

    if (title) {
      title.textContent = "Individual Attendance";
    }

    if (caption) {
      caption.textContent = "Select an employee to view monthly records";
    }

    if (logTools) {
      logTools.style.display = "";
    }
  } else {
    // Switch to Pending Attendance
    logsView.hidden = true;
    pendingView.hidden = false;

    toggleButton.classList.add("active");

    if (title) {
      title.textContent = "Pending Attendance";
    }

    if (caption) {
      caption.textContent = "Complete missing or incorrect attendance punches";
    }

    if (logTools) {
      logTools.style.display = "none";
    }

    loadPendingAttendance();
  }
}

function updateAttendanceGoTop() {
  const attendance = document.getElementById("attendance");
  const button = document.getElementById("attendance-go-top");
  if (!attendance || !button) return;
  button.classList.toggle(
    "visible",
    attendance.classList.contains("active") && window.scrollY > 300,
  );
}

window.addEventListener("scroll", updateAttendanceGoTop, { passive: true });
document.addEventListener("DOMContentLoaded", updateAttendanceGoTop);
