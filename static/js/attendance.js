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
    caption.textContent = new Date(year, monthNumber - 1, 1).toLocaleDateString(undefined, { month: "long", year: "numeric" });
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
  const term = String(query || "").trim().toLocaleLowerCase();
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
    emptyRow.innerHTML = '<td colspan="4" class="individual-attendance-empty">No matching attendance records.</td>';
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
  const [year, month] = (input.value || currentAttendanceMonthValue()).split("-").map(Number);
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
      if (caption) caption.textContent = new Date(year, month - 1, 1).toLocaleDateString(undefined, { month: "long", year: "numeric" });
    }
  });
}
document.getElementById("individual-attendance-previous")?.addEventListener("click", () => shiftIndividualAttendanceMonth(-1));
document.getElementById("individual-attendance-next")?.addEventListener("click", () => shiftIndividualAttendanceMonth(1));

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
  document.querySelectorAll("#attendance .attendance-panel").forEach((panel) => {
    panel.classList.toggle("active", panel.id === `attendance-panel-${panelName}`);
  });
  document.querySelectorAll("#attendance .attendance-nav-button").forEach((navButton) => {
    const isActive = navButton === button;
    navButton.classList.toggle("active", isActive);
    navButton.setAttribute("aria-selected", String(isActive));
  });
  updateAttendanceGoTop();
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
