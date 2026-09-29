/**
 * bulk_attendance.js
 * Handles bulk marking of employee attendance.
 */

// Use var or check existence to prevent "Identifier has already been declared" SyntaxError
if (typeof bulkEmployeeList === "undefined") {
  var bulkEmployeeList = [];
}

async function loadBulkAttendanceList() {
  try {
    const response = await fetch(`${API_BASE}/employees`);
    if (!response.ok) return;

    // Update the global variable
    bulkEmployeeList = await response.json();
    renderBulkTable(bulkEmployeeList);
  } catch (error) {
    console.error("Bulk list load error:", error);
  }
}

function renderBulkTable(employees) {
  const tbody = document.getElementById("bulk-attendance-body");
  if (!tbody) return;

  tbody.innerHTML = "";

  const activeEmployees = employees.filter((emp) => emp.status === "active");

  if (activeEmployees.length === 0) {
    tbody.innerHTML = `<tr><td colspan="5" style="text-align:center;">No active employees found.</td></tr>`;
    return;
  }

  activeEmployees.forEach((emp) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
            <td style="text-align: center;">
                <input type="checkbox" class="bulk-check" value="${emp.id}" onchange="updateBulkButtonState()">
            </td>
            <td>#${emp.id}</td>
            <td>${emp.name}</td>
            <td>${emp.role}</td>
            <td><span class="status-badge" style="padding:2px 6px; font-size:0.75rem;">Ready</span></td>
        `;
    tbody.appendChild(tr);
  });
  filterBulkAttendance(document.getElementById("bulk-attendance-search")?.value || "");
}

function filterBulkAttendance(query) {
  const tbody = document.getElementById("bulk-attendance-body");
  if (!tbody) return;
  const term = String(query || "").trim().toLocaleLowerCase();
  tbody.querySelectorAll("tr").forEach((row) => {
    row.hidden = !row.textContent.toLocaleLowerCase().includes(term);
  });
}

function toggleAllBulkChecks(masterCheckbox) {
  const checks = document.querySelectorAll(".bulk-check");
  checks.forEach((chk) => {
    if (!chk.disabled && !chk.closest("tr")?.hidden) {
      chk.checked = masterCheckbox.checked;
    }
  });
  updateBulkButtonState();
}

function updateBulkButtonState() {
  const checkedBoxes = document.querySelectorAll(".bulk-check:checked");
  const btn = document.getElementById("bulk-mark-btn");

  if (btn) {
    btn.disabled = checkedBoxes.length === 0;
    btn.innerText = `Mark Present (${checkedBoxes.length})`;
  }
}

async function submitBulkAttendance() {
  const checkedBoxes = document.querySelectorAll(".bulk-check:checked");
  const idsToMark = Array.from(checkedBoxes).map((chk) => parseInt(chk.value));

  if (idsToMark.length === 0) return;

  const btn = document.getElementById("bulk-mark-btn");
  btn.disabled = true;
  btn.innerText = "Processing...";

  let successCount = 0;
  let failCount = 0;

  for (const id of idsToMark) {
    try {
      const res = await fetch(`${API_BASE}/attendance/checkin`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ employee_id: id }),
      });

      if (res.ok) {
        successCount++;
        const chk = document.querySelector(`.bulk-check[value="${id}"]`);
        if (chk) {
          chk.checked = false;
          chk.disabled = true;
          chk.parentElement.innerHTML = "✅";
        }
      } else {
        failCount++;
      }
    } catch (err) {
      failCount++;
    }
  }

  const masterCheck = document.getElementById("bulk-check-all");
  if (masterCheck) masterCheck.checked = false;

  if (window.showToast) {
    if (failCount === 0)
      showToast(`Successfully marked ${successCount} employees!`, "success");
    else showToast(`Marked ${successCount}, Failed ${failCount}`, "warning");
  }

  btn.innerText = "Mark Present (0)";
}
