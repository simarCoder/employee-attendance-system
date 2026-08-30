//
//   salary.js
//   Handles Salary Generation and Viewing.
//

// Initialize Date Pickers on Load
// document.addEventListener("DOMContentLoaded", () => {
//   populateDateSelectors();
// });

// function populateDateSelectors() {
//   const monthSelect = document.getElementById("salary-month-select");
//   const yearSelect = document.getElementById("salary-year-select");

//   if (!monthSelect || !yearSelect) return;

// Populate Months
//   const months = [
//     "January",
//     "February",
//     "March",
//     "April",
//     "May",
//     "June",
//     "July",
//     "August",
//     "September",
//     "October",
//     "November",
//     "December",
//   ];

//   months.forEach((m, index) => {
//     const option = document.createElement("option");
//     option.value = (index + 1).toString().padStart(2, "0"); // 01, 02...
//     option.textContent = m;
//     monthSelect.appendChild(option);
//   });

//   // Set current month
//   const currentMonth = new Date().getMonth();
//   monthSelect.selectedIndex = currentMonth;

//   // Populate Years (Current year - 2 to Current year + 1)
//   const currentYear = new Date().getFullYear();
//   for (let i = currentYear - 2; i <= currentYear + 1; i++) {
//     const option = document.createElement("option");
//     option.value = i;
//     option.textContent = i;
//     yearSelect.appendChild(option);
//   }

//   // Set current year
//   yearSelect.value = currentYear;
// }

// // Listen for employee load to populate dropdown
// window.addEventListener("employeesLoaded", (e) => {
//   populateEmployeeDropdown("salary-employee-select", e.detail);
// });

// // Helper to construct YYYY-MM
// function getSelectedMonthStr() {
//   const month = document.getElementById("salary-month-select").value;
//   const year = document.getElementById("salary-year-select").value;

//   if (!month || !year) return null;
//   return `${year}-${month}`;
// }

// async function generateSalary() {
//   const empId = document.getElementById("salary-employee-select").value;
//   const monthStr = getSelectedMonthStr();
//   const role = sessionStorage.getItem("role"); // Get current user role

//   if (!empId || !monthStr) {
//     if (window.showToast)
//       showToast("Please select employee, month and year", "error");
//     return;
//   }

//   try {
//     // 1. Attempt to Generate
//     const genRes = await fetch(`${API_BASE}/salary/generate`, {
//       method: "POST",
//       headers: { "Content-Type": "application/json" },
//       body: JSON.stringify({
//         employee_id: parseInt(empId),
//         month: monthStr,
//         role: role, // Send role to authenticate possible override
//       }),
//     });

//     const genData = await genRes.json();

//     if (genData.status === "new") {
//       if (window.showToast)
//         showToast("Success: Salary Slip Generated!", "success");
//       fetchSalaryView(empId, monthStr);
//     } else if (genData.status === "exists") {
//       if (window.showToast)
//         showToast("Salary already exists. Loading details...", "success");
//       fetchSalaryView(empId, monthStr);
//     } else {
//       if (window.showToast)
//         showToast("Error: " + (genData.message || "Unknown error"), "error");
//     }
//   } catch (error) {
//     console.error(error);
//     if (window.showToast) showToast("Server Connection Error", "error");
//   }
// }

// async function viewSalary() {
//   const empId = document.getElementById("salary-employee-select").value;
//   const monthStr = getSelectedMonthStr();

//   if (!empId || !monthStr) {
//     if (window.showToast)
//       showToast("Please select employee, month and year", "error");
//     return;
//   }

//   fetchSalaryView(empId, monthStr);
// }

// async function fetchSalaryView(empId, month) {
//   try {
//     const viewRes = await fetch(
//       `${API_BASE}/salary/view?employee_id=${empId}&month=${month}`,
//     );

//     if (!viewRes.ok) {
//       if (window.showToast)
//         showToast("No salary slip found for this selection.", "error");
//       document.getElementById("salary-result-container").innerHTML = "";
//       return;
//     }

//     const data = await viewRes.json();
//     displaySalaryCard(data);
//   } catch (error) {
//     console.error(error);
//   }
// }
// function formatDuration(minutes) {
//   if (
//     minutes === null ||
//     minutes === undefined ||
//     Number.isNaN(Number(minutes))
//   ) {
//     return "-";
//   }

//   minutes = Math.max(0, Math.round(Number(minutes)));

//   const hours = Math.floor(minutes / 60);
//   const mins = minutes % 60;

//   if (hours === 0) {
//     return `${mins}m`;
//   }

//   if (mins === 0) {
//     return `${hours}h`;
//   }

//   return `${hours}h ${mins}m`;
// }

// function displaySalaryCard(data) {
//   // Format hours to max 2 decimals
//   const formattedHours =
//     data.total_hours !== null && data.total_hours !== undefined
//       ? formatDuration(Math.round(Number(data.total_hours) * 60))
//       : "-";

//   const currentRole = sessionStorage.getItem("role");
//   const isHead = currentRole === "head";

//   // Allow edit if NOT locked OR if user is HEAD
//   const canEdit = !data.locked || isHead;

//   const container = document.getElementById("salary-result-container");
//   container.innerHTML = `
//         <div class="card" style="border-left: 4px solid var(--primary);">
//             <h3>Salary Slip Generated</h3>
//             <div style="margin-top: 1rem; display: grid; grid-template-columns: 1fr 1fr; gap: 1rem;">
//                 <div>
//                     <label class="form-label">Month</label>
//                     <div class="value">${data.month}</div>
//                 </div>
//                 <div>
//                     <label class="form-label">Employee ID</label>
//                     <div class="value">#${data.employee_id}</div>
//                 </div>
//                 <div>
//                     <label class="form-label">Total Hours</label>
//                     <div class="value" style="color: var(--text-main); font-size: 1.25rem; font-weight: bold;">
//                         ${formattedHours}
//                     </div>
//                 </div>
//             <div>
//               <label class="form-label">Total Payout</label>
//               <div style="display:flex; align-items:center; gap:5px;">
//                   <span style="font-size:1.2rem; font-weight:bold;">₹</span>
//                   ${
//                     !canEdit
//                       ? `<input type="number" value="${data.total_salary}" disabled class="form-control" />`
//                       : `
//                         <input type="number" id="editable-salary" value="${data.total_salary}" class="form-control admin-only" />
//                       `
//                   }
//               </div>

//               ${
//                 canEdit
//                   ? `
//                 <button onclick="saveEditedSalary(${data.employee_id}, '${data.month}')"
//                         class="btn btn-primary admin-only" style="margin-top:10px; width:100%;">
//                     Save Changes
//                 </button>
//                 ${data.locked && isHead ? '<small style="color:#f59e0b; display:block; margin-top:5px;">* Unlocked via God Mode</small>' : ""}
//               `
//                   : '<small style="color:var(--text-muted); display:block; margin-top:5px;">* Locked</small>'
//               }

//           </div>

//             </div>
//         </div>
//     `;
// }

// function saveEditedSalary(empId, month) {
//   const newSalary = document.getElementById("editable-salary").value;
//   const role = sessionStorage.getItem("role");

//   fetch(`${API_BASE}/salary/update`, {
//     method: "POST",
//     headers: { "Content-Type": "application/json" },
//     body: JSON.stringify({
//       employee_id: empId,
//       month: month,
//       total_salary: parseFloat(newSalary),
//       role: role, // Send role to authenticate God Mode edit
//     }),
//   })
//     .then((res) => res.json())
//     .then((data) => {
//       // Use showToast if available, else alert
//       if (window.showToast) {
//         if (data.message && data.message.includes("success"))
//           showToast(data.message, "success");
//         else showToast(data.message, "error");
//       } else {
//         // Fallback if toast not available
//         console.log(data.message);
//       }
//       fetchSalaryView(empId, month);
//     });
// }

/**
 * salary.js
 * Handles Salary Generation and Viewing.
 */

// Initialize Date Pickers on Load
document.addEventListener("DOMContentLoaded", () => {
  populateDateSelectors();
  setTimeout(loadSalaryRecords, 100);
});

function populateDateSelectors() {
  const monthSelect = document.getElementById("salary-month-select");
  const yearSelect = document.getElementById("salary-year-select");

  if (!monthSelect || !yearSelect) return;

  // Populate Months
  const months = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
  ];

  months.forEach((m, index) => {
    const option = document.createElement("option");
    option.value = (index + 1).toString().padStart(2, "0"); // 01, 02...
    option.textContent = m;
    monthSelect.appendChild(option);
  });

  // Set current month
  const currentMonth = new Date().getMonth();
  monthSelect.selectedIndex = currentMonth;

  // Populate Years (Current year - 2 to Current year + 1)
  const currentYear = new Date().getFullYear();
  for (let i = currentYear - 2; i <= currentYear + 1; i++) {
    const option = document.createElement("option");
    option.value = i;
    option.textContent = i;
    yearSelect.appendChild(option);
  }

  // Set current year
  yearSelect.value = currentYear;
}

// Listen for employee load to populate dropdown
window.addEventListener("employeesLoaded", (e) => {
  populateEmployeeDropdown("salary-employee-select", e.detail);
});

// Helper to construct YYYY-MM
function getSelectedMonthStr() {
  const month = document.getElementById("salary-month-select").value;
  const year = document.getElementById("salary-year-select").value;

  if (!month || !year) return null;
  return `${year}-${month}`;
}

async function generateSalary() {
  const empId = document.getElementById("salary-employee-select").value;
  const monthStr = getSelectedMonthStr();
  const role = sessionStorage.getItem("role"); // Get current user role

  if (!empId || !monthStr) {
    if (window.showToast)
      showToast("Please select employee, month and year", "error");
    return;
  }

  try {
    // 1. Attempt to Generate
    const genRes = await fetch(`${API_BASE}/salary/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        employee_id: parseInt(empId),
        month: monthStr,
        role: role, // Send role to authenticate possible override
      }),
    });

    const genData = await genRes.json();

    if (genData.status === "new") {
      if (window.showToast)
        showToast("Success: Salary Slip Generated!", "success");
      fetchSalaryView(empId, monthStr);
    } else if (genData.status === "exists") {
      if (window.showToast)
        showToast("Salary already exists. Loading details...", "success");
      fetchSalaryView(empId, monthStr);
    } else {
      if (window.showToast)
        showToast("Error: " + (genData.message || "Unknown error"), "error");
    }
  } catch (error) {
    console.error(error);
    if (window.showToast) showToast("Server Connection Error", "error");
  }
}

async function viewSalary() {
  const empId = document.getElementById("salary-employee-select").value;
  const monthStr = getSelectedMonthStr();

  if (!empId || !monthStr) {
    if (window.showToast)
      showToast("Please select employee, month and year", "error");
    return;
  }

  fetchSalaryView(empId, monthStr);
}

async function fetchSalaryView(empId, month) {
  try {
    const viewRes = await fetch(
      `${API_BASE}/salary/view?employee_id=${empId}&month=${month}`,
    );

    if (!viewRes.ok) {
      let errorMessage = "Unable to load salary slip.";

      try {
        const errorData = await viewRes.json();
        errorMessage = errorData.error || errorData.message || errorMessage;
      } catch (_) {
        // Ignore invalid/non-JSON error responses
      }

      if (window.showToast) {
        showToast(errorMessage, "error");
      }

      document.getElementById("salary-result-container").innerHTML = "";
      return;
    }

    const data = await viewRes.json();
    displaySalaryCard(data);
  } catch (error) {
    console.error(error);
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

function displaySalaryCard(data) {
  const formattedHours = formatDuration(data.actual_worked_minutes);

  const currentRole = sessionStorage.getItem("role");
  const isHead = currentRole === "head";
  const canEdit = !data.locked || isHead;

  const container = document.getElementById("salary-result-container");

  container.innerHTML = `
  <div class="card" style="border-left: 4px solid var(--primary);">
    <h3>Salary Slip Generated</h3>

    <div style="
      margin-top: 1rem;
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 1rem;
    ">

      <div>
        <label class="form-label">Employee</label>
        <div class="value">
          ${data.employee_name || `#${data.employee_id}`}
        </div>
      </div>

      <div>
        <label class="form-label">Role</label>
        <div class="value">
          ${data.employee_role || "-"}
        </div>
      </div>

      <div>
        <label class="form-label">Month</label>
        <div class="value">
          ${data.month}
        </div>
      </div>

      <div>
        <label class="form-label">Salary Type</label>
        <div class="value">
          ${data.salary_type || "-"}
        </div>
      </div>

      <div>
        <label class="form-label">Total Worked</label>
        <div
          class="value"
          style="font-size:1.25rem;font-weight:bold;"
        >
          ${formattedHours}
        </div>
      </div>

      <div>
        <label class="form-label">Working Days</label>
        <div class="value">
          ${data.working_days ?? "-"}
        </div>
      </div>

      <div>
        <label class="form-label">Base Salary</label>
        <div class="value">
          ₹${Number(data.base_salary || 0).toFixed(2)}
        </div>
      </div>

      <div>
        <label class="form-label">Salary Deduction</label>
        <div class="value">
          ₹${Math.max(
            0,
            Number(data.monthly_salary || 0) - Number(data.base_salary || 0),
          ).toFixed(2)}
        </div>
      </div>

      <div>
        <label class="form-label">Overtime</label>
        <div class="value">
          ${formatDuration(data.overtime_minutes)}
        </div>
      </div>

      <div>
        <label class="form-label">Overtime Pay</label>
        <div class="value">
          ₹${Number(data.overtime_pay || 0).toFixed(2)}
        </div>
      </div>

      <div>
        <label class="form-label">Final Salary</label>
        <div
          class="value"
          style="font-size:1.25rem;font-weight:bold;"
        >
          ₹${Number(data.total_salary || 0).toFixed(2)}
        </div>
      </div>

      <div>
        <label class="form-label">Status</label>
        <div class="value">
          ${data.locked ? "Locked" : "Draft"}
        </div>
      </div>

    </div>

    <div style="margin-top:1.25rem;">

      <label class="form-label">Final Payout</label>

      <div style="
        display:flex;
        align-items:center;
        gap:5px;
      ">
        <span style="
          font-size:1.2rem;
          font-weight:bold;
        ">₹</span>

        ${
          !canEdit
            ? `
              <input
                type="number"
                value="${data.total_salary}"
                disabled
                class="form-control"
              />
            `
            : `
              <input
                type="number"
                id="editable-salary"
                value="${data.total_salary}"
                class="form-control admin-only"
              />
            `
        }
      </div>

      ${
        canEdit
          ? `
            <button
              onclick="saveEditedSalary(
                ${data.employee_id},
                '${data.month}'
              )"
              class="btn btn-primary admin-only"
              style="
                margin-top:10px;
                width:100%;
              "
            >
              Save Changes
            </button>

            ${
              data.locked && isHead
                ? `
                  <small
                    style="
                      color:#f59e0b;
                      display:block;
                      margin-top:5px;
                    "
                  >
                    * Unlocked via Head Developer access
                  </small>
                `
                : ""
            }
          `
          : `
            <small
              style="
                color:var(--text-muted);
                display:block;
                margin-top:5px;
              "
            >
              * Locked
            </small>
          `
      }

    </div>

    <div class="salary-result-actions">

      <button
        type="button"
        class="btn"
        onclick="
          viewSalaryReceipt(
            ${data.employee_id},
            '${data.month}'
          )
        "
      >
        Generate Receipt / Print
      </button>

    </div>

  </div>
`;

  loadSalaryRecords();
}
function renderSalaryRecords(records) {
  const container = document.getElementById("salary-records-container");
  if (!container) return;

  if (!records.length) {
    container.innerHTML = `
      <div class="card">
        <h3>Salary Records</h3>
        <p style="color:var(--text-muted);margin-top:.5rem;">
          No salary records have been generated yet.
        </p>
      </div>
    `;
    return;
  }

  const rows = records
    .map(
      (record) => `
      <!-- Main salary row -->
      <tr>

        <td>
          #${record.employee_id}
        </td>

        <td>
          ${record.employee_name || "-"}
        </td>

        <td>
          ${record.month}
        </td>

        <td>
          ${record.salary_type || "-"}
        </td>

        <td>
          ${formatDuration(record.actual_worked_minutes)}
        </td>

        <td>
          ₹${Number(record.monthly_salary || 0).toFixed(2)}
        </td>

        <td>
          ₹${Number(record.total_salary || 0).toFixed(2)}
        </td>

        <td>
          ${record.locked ? "Locked" : "Draft"}
        </td>

        <td>
          <button
            class="btn salary-details-btn"
            style="
              background:var(--bg-input);
              color:var(--text-main);
              min-width:100px;
            "
            onclick="
              showSalaryRecordDetails(
                ${record.salary_id}
              )
            "
          >
            Details
          </button>
        </td>

      </tr>

      <!-- Expandable details row -->
      <tr class="salary-detail-row">

        <td
          colspan="9"
          style="
            padding:0;
            border:0;
            width:100%;
          "
        >

          <div
            id="salary-detail-${record.salary_id}"
            class="salary-detail-inner"
            style="
              width:100%;
              max-width:100%;
              box-sizing:border-box;
              max-height:0;
              opacity:0;
              overflow:hidden;
              transition:
                max-height 0.35s ease,
                opacity 0.25s ease,
                padding 0.35s ease;
              padding:0 1rem;
            "
          >

            <div
              style="
                width:100%;
                box-sizing:border-box;
                border:1px solid var(--border);
                border-radius:12px;
                padding:1.25rem;
                background:var(--bg-input);
                margin:0.5rem 0 1rem 0;
              "
            >

              <h4 style="margin-bottom:1rem;">
                Salary Record Details
              </h4>

              <div
                class="salary-detail-grid"
                style="
                  display:grid;
                  grid-template-columns:
                    repeat(auto-fit,minmax(220px,1fr));
                  gap:.8rem 1.5rem;
                "
              >

                <div>
                  <strong>Salary ID:</strong>
                  #${record.salary_id}
                </div>

                <div>
                  <strong>Employee ID:</strong>
                  #${record.employee_id}
                </div>

                <div>
                  <strong>Employee:</strong>
                  ${record.employee_name || "-"}
                </div>

                <div>
                  <strong>Role:</strong>
                  ${record.employee_role || "-"}
                </div>

                <div>
                  <strong>Month:</strong>
                  ${record.month}
                </div>

                <div>
                  <strong>Salary Type:</strong>
                  ${record.salary_type || "-"}
                </div>

                <div>
                  <strong>Monthly Salary:</strong>
                  ₹${Number(record.monthly_salary || 0).toFixed(2)}
                </div>

                <div>
                  <strong>Working Days:</strong>
                  ${record.working_days ?? "-"}
                </div>

                <div>
                  <strong>Total Worked:</strong>
                  ${formatDuration(record.actual_worked_minutes)}
                </div>

                <div>
                  <strong>Base Salary:</strong>
                  ₹${Number(record.base_salary || 0).toFixed(2)}
                </div>

                <div>
                  <strong>Salary Deduction:</strong>
                  ₹${Math.max(
                    0,
                    Number(record.monthly_salary || 0) -
                      Number(record.base_salary || 0),
                  ).toFixed(2)}
                </div>

                <div>
                  <strong>Overtime:</strong>
                  ${formatDuration(record.overtime_minutes)}
                </div>

                <div>
                  <strong>Overtime Pay:</strong>
                  ₹${Number(record.overtime_pay || 0).toFixed(2)}
                </div>

                <div>
                  <strong>Final Salary:</strong>
                  ₹${Number(record.total_salary || 0).toFixed(2)}
                </div>

                <div>
                  <strong>Status:</strong>
                  ${record.locked ? "Locked" : "Draft"}
                </div>

                <div>
                  <strong>Created:</strong>
                  ${record.created_at || "-"}
                </div>

                <div>
                  <strong>Updated:</strong>
                  ${record.updated_at || "-"}
                </div>

              </div>

            </div>

          </div>

        </td>

      </tr>
    `,
    )
    .join("");

  container.innerHTML = `
    <div class="card" style="margin-top:2rem;">
      <div
        style="
          display:flex;
          justify-content:space-between;
          align-items:center;
          gap:1rem;
          flex-wrap:wrap;
        "
      >
        <div>
          <h3>Salary Records</h3>
          <p style="color:var(--text-muted);margin-top:.25rem;">
            Monthly payroll history and calculation snapshots.
          </p>
        </div>

        <button
          class="btn"
          style="
            background:var(--bg-input);
            color:var(--text-main);
          "
          onclick="loadSalaryRecords()"
        >
          Refresh
        </button>
      </div>

      <div style="overflow-x:auto;margin-top:1rem;">
        <table class="table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Employee</th>
              <th>Month</th>
              <th>Type</th>
              <th>Worked</th>
              <th>Monthly Salary</th>
              <th>Total Salary</th>
              <th>Status</th>
              <th>Action</th>
            </tr>
          </thead>

          <tbody>
            ${rows}
          </tbody>
        </table>
      </div>
    </div>
  `;
}
function showSalaryRecordDetails(salaryId) {
  const selected = document.getElementById(`salary-detail-${salaryId}`);

  if (!selected) return;

  const allDetails = document.querySelectorAll(".salary-detail-inner");

  const isAlreadyOpen =
    selected.style.maxHeight !== "0px" && selected.style.maxHeight !== "";

  // Close every detail panel first
  allDetails.forEach((detail) => {
    detail.style.maxHeight = "0px";
    detail.style.opacity = "0";
    detail.style.padding = "0 1rem";
  });

  // If the selected one was already open,
  // leave everything closed.
  if (isAlreadyOpen) {
    return;
  }

  // Open selected record
  selected.style.maxHeight = "1000px";
  selected.style.opacity = "1";
  selected.style.padding = "0 1rem";
}

async function loadSalaryRecords() {
  const container = document.getElementById("salary-records-container");
  if (!container) return;

  try {
    const response = await fetch(`${API_BASE}/salary/records`);

    if (!response.ok) {
      throw new Error("Failed to load salary records");
    }

    const payload = await response.json();
    renderSalaryRecords(payload.records || []);
  } catch (error) {
    console.error(error);
    container.innerHTML = `
      <div class="card">
        <h3>Salary Records</h3>
        <p style="color:#ef4444;margin-top:.5rem;">
          Unable to load salary records.
        </p>
      </div>
    `;
  }
}

function saveEditedSalary(empId, month) {
  const newSalary = document.getElementById("editable-salary").value;
  const role = sessionStorage.getItem("role");

  fetch(`${API_BASE}/salary/update`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      employee_id: empId,
      month: month,
      total_salary: parseFloat(newSalary),
      role: role, // Send role to authenticate God Mode edit
    }),
  })
    .then((res) => res.json())
    .then((data) => {
      // Use showToast if available, else alert
      if (window.showToast) {
        if (data.message && data.message.includes("success"))
          showToast(data.message, "success");
        else showToast(data.message, "error");
      } else {
        // Fallback if toast not available
        console.log(data.message);
      }
      fetchSalaryView(empId, month);
      loadSalaryRecords();
    });
}

/* =========================
   SALARY RECEIPT
========================= */
async function viewSalaryReceipt(employeeId, month) {
  try {
    const [salaryRes, employeeRes] = await Promise.all([
      fetch(
        `${API_BASE}/salary/view?employee_id=${employeeId}&month=${encodeURIComponent(month)}`,
      ),
      fetch(`${API_BASE}/employee/${employeeId}`),
    ]);

    if (!salaryRes.ok) {
      const data = await salaryRes.json().catch(() => ({}));
      throw new Error(data.error || "Salary record not found");
    }
    if (!employeeRes.ok)
      throw new Error("Employee details could not be loaded");

    const salary = await salaryRes.json();
    const employee = await employeeRes.json();
    renderSalaryReceipt(salary, employee);
  } catch (error) {
    console.error("Receipt error:", error);
    if (window.showToast)
      showToast(error.message || "Unable to generate receipt", "error");
  }
}

function renderSalaryReceipt(salary, employee = {}) {
  const target = document.getElementById("salary-receipt-print-area");
  if (!target) return;

  const money = (value) =>
    `₹${Number(value || 0).toLocaleString("en-IN", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    })}`;
  const formatMonth = (value) => {
    if (!value || !value.includes("-")) return value || "-";
    const [year, month] = value.split("-");
    return new Date(Number(year), Number(month) - 1, 1).toLocaleDateString(
      "en-IN",
      {
        month: "long",
        year: "numeric",
      },
    );
  };
  const deductions = Math.max(
    0,
    Number(salary.base_salary || 0) - Number(salary.total_salary || 0),
  );
  const generatedAt = new Date().toLocaleString("en-IN", {
    dateStyle: "medium",
    timeStyle: "short",
  });

  target.innerHTML = `
    <div class="salary-receipt">
      <div class="salary-receipt-header">
        <div>
          <div class="salary-receipt-company">OPERON SOLUTIONS</div>
          <div class="salary-receipt-subtitle">HR MANAGEMENT SYSTEM</div>
        </div>
        <div>
          <div class="salary-receipt-title">Salary Receipt</div>
          <div class="salary-receipt-subtitle">${formatMonth(salary.month)}</div>
        </div>
      </div>

      <div class="salary-receipt-employee">
        <div class="salary-receipt-field"><span>Employee</span><strong>${salary.employee_name || employee.name || "-"}</strong></div>
        <div class="salary-receipt-field"><span>Employee ID</span><strong>#${salary.employee_id}</strong></div>
        <div class="salary-receipt-field"><span>Role</span><strong>${salary.employee_role || employee.role || "-"}</strong></div>
        <div class="salary-receipt-field"><span>Salary Type</span><strong>${salary.salary_type || "-"}</strong></div>
        <div class="salary-receipt-field"><span>Phone</span><strong>${employee.phone || "-"}</strong></div>
        <div class="salary-receipt-field"><span>Status</span><strong>${salary.locked ? "Finalized" : "Draft"}</strong></div>
      </div>

      <table class="salary-receipt-table">
        <thead><tr><th>Description</th><th>Amount</th></tr></thead>
        <tbody>
          <tr><td>Base Salary</td><td>${money(salary.base_salary)}</td></tr>
          <tr><td>Overtime Pay</td><td>${money(salary.overtime_pay)}</td></tr>
          <tr><td>Salary Deduction</td><td>- ${money(deductions)}</td></tr>
        </tbody>
      </table>

      <div class="salary-receipt-total">
        <span>NET SALARY</span>
        <span>${money(salary.total_salary)}</span>
      </div>

      <table class="salary-receipt-table">
        <tbody>
          <tr><td>Working Days</td><td>${salary.working_days ?? "-"}</td></tr>
          <tr><td>Worked Time</td><td>${formatDuration(salary.actual_worked_minutes)}</td></tr>
          <tr><td>Deducted Holidays</td><td>${Number(salary.deducted_holidays || 0).toFixed(2)}</td></tr>
          <tr><td>Grace Holidays Used</td><td>${Number(salary.grace_holidays_used || 0).toFixed(2)}</td></tr>
        </tbody>
      </table>

      <div class="salary-receipt-note">
        This receipt is generated from the stored salary calculation for ${formatMonth(salary.month)}.
        Overtime is shown for record purposes and does not increase salary under the current payroll rules.
        Generated ${generatedAt}.
      </div>
    </div>
  `;

  document.body.classList.add("printing-receipt");
  window.setTimeout(() => window.print(), 100);
  window.addEventListener(
    "afterprint",
    () => {
      document.body.classList.remove("printing-receipt");
    },
    { once: true },
  );
}
