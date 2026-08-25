/**
 * employees.js
 * Handles fetching, displaying, and adding employees.
 */

async function loadEmployees() {
  try {
    const response = await fetch(`${API_BASE}/employees`);

    if (!response.ok) {
      throw new Error("Failed to fetch employees");
    }

    // ALL employees from backend
    const employees = await response.json();

    // -------------------------------------------------
    // EMPLOYEE DIRECTORY
    // Show ALL employees here
    // -------------------------------------------------
    renderEmployeeTable(employees);

    // -------------------------------------------------
    // ACTIVE EMPLOYEES
    // Operational sections should only receive these
    // -------------------------------------------------
    const activeEmployees = employees.filter((emp) => emp.status === "active");

    // Dashboard = active employee count only
    updateDashboardStats(activeEmployees.length);

    // -------------------------------------------------
    // Notify operational modules
    // Attendance / Salary dropdowns receive ACTIVE only
    // -------------------------------------------------
    const event = new CustomEvent("employeesLoaded", {
      detail: activeEmployees,
    });

    window.dispatchEvent(event);
  } catch (error) {
    console.error("Error loading employees:", error);

    renderEmptyState("employee-table-body", "No connection to backend.");
  }
}

function deactivateEmployee(id, event) {
  if (event) event.stopPropagation();

  // Role check handled by server mainly, but also UI check
  const role = sessionStorage.getItem("role");
  if (!["admin", "head"].includes(role)) {
    showToast("Access Denied", "error");
    return;
  }

  showConfirmModal("Deactivate this employee account?", async () => {
    const response = await fetch(`${API_BASE}/employee/deactivate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ employee_id: id }),
    });

    if (response.ok) {
      showToast("Employee Deactivated", "success");
      loadEmployees();
    } else {
      showToast("Failed to deactivate", "error");
    }
  });
}

async function activateEmployee(id, event) {
  if (event) event.stopPropagation();

  // Only Admin or Head can activate
  const role = sessionStorage.getItem("role");
  if (!["admin", "head"].includes(role)) {
    showToast("Access Denied. Only Admin/Head can activate.", "error");
    return;
  }

  const response = await fetch(`${API_BASE}/employee/activate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ employee_id: id }),
  });

  if (response.ok) {
    showToast("Employee Activated", "success");
    loadEmployees();
  } else {
    showToast("Failed to activate", "error");
  }
}

async function deleteEmployee(id, event) {
  if (event) event.stopPropagation();

  // Only Admin or Head can delete
  const role = sessionStorage.getItem("role");
  if (!["admin", "head"].includes(role)) {
    showToast("Access Denied.", "error");
    return;
  }

  showConfirmModal(
    "PERMANENTLY DELETE this employee? All data will be lost.",
    async () => {
      const response = await fetch(`${API_BASE}/employee/delete`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ employee_id: id }),
      });

      const data = await response.json();
      if (response.ok) {
        showToast(data.message, "success");
        loadEmployees();
      } else {
        showToast("Error: " + data.message, "error");
      }
    },
  );
}

function renderEmployeeTable(employees) {
  const tbody = document.getElementById("employee-table-body");
  tbody.innerHTML = "";

  const currentUserRole = sessionStorage.getItem("role");
  const canModify = ["admin", "head"].includes(currentUserRole);

  employees.forEach((emp) => {
    const tr = document.createElement("tr");

    // Action Buttons Logic
    let actionButtons = "";

    // 1. Activate/Deactivate (Only Admin/Head)
    if (canModify) {
      if (emp.status === "active") {
        actionButtons += `<button class="btn btn-warning" style="padding:4px 8px; margin-right:5px;" onclick="deactivateEmployee(${emp.id}, event)">Deactivate</button>`;
      } else {
        actionButtons += `<button class="btn btn-primary" style="padding:4px 8px; margin-right:5px;" onclick="activateEmployee(${emp.id}, event)">Activate</button>`;
      }

      // 2. Edit (Only Admin/Head)
      actionButtons += `
  <button
    class="btn btn-primary"
    style="padding:4px 8px; margin-right:5px;"
    onclick="editEmployee(${emp.id}, event)"
  >
    Edit
  </button>
`;

      // 3. Delete (Only Admin/Head)
      actionButtons += `
  <button
    class="btn"
    style="background:#ef4444; color:white; padding:4px 8px;"
    onclick="deleteEmployee(${emp.id}, event)"
  >
    Delete
  </button>
`;
    } else {
      actionButtons = `<span style="color:var(--text-muted); font-size:0.8rem;">Read Only</span>`;
    }

    tr.innerHTML = `
      <td>#${emp.id}</td>
      <td>${emp.name}</td>
      <td>${emp.role}</td>
      <td>${emp.phone || "-"}</td>
      <td>${emp.address || "-"}</td>
      <td>₹${emp.monthly_salary}</td>
      <td>
        <span class="status-badge"
              style="
                background: ${emp.status === "active" ? "#16a34a" : "#fa6515c4"};
                color: black;
                padding: 4px 8px;
                border-radius: 6px;
              ">
          ${emp.status}
        </span>
      </td>
      <td>${actionButtons}</td>
    `;

    tr.addEventListener("click", () => {
      openEmployeeProfile(emp.id);
    });

    tbody.appendChild(tr);
  });
}

// async function addEmployee(event) {
//   event.preventDefault();

//   const name = document.getElementById("emp-name").value;
//   const role = document.getElementById("emp-role").value;
//   const phone = document.getElementById("emp-contact").value;
//   const address = document.getElementById("emp-address").value;
//   const salary = document.getElementById("emp-salary").value;

//   const payload = {
//     name: name,
//     role: role,
//     phone: phone,
//     address: address,
//     monthly_salary: parseFloat(salary),
//   };

//   try {
//     const response = await fetch(`${API_BASE}/employee/add`, {
//       method: "POST",
//       headers: { "Content-Type": "application/json" },
//       body: JSON.stringify(payload),
//     });

//     if (response.ok) {
//       showToast("Employee added successfully", "success");
//       document.getElementById("add-employee-form").reset();
//       loadEmployees();
//     } else {
//       const err = await response.json();
//       showToast(err.message || "Error adding employee", "error");
//     }
//   } catch (error) {
//     console.error("Add employee failed:", error);
//     showToast("Failed to connect to server", "error");
//   }
// }

async function addEmployee(event) {
  event.preventDefault();

  const name = document.getElementById("emp-name").value.trim();

  const role = document.getElementById("emp-role").value.trim();

  const phone = document.getElementById("emp-contact").value.trim();

  const address = document.getElementById("emp-address").value.trim();

  const salaryType = document.getElementById("emp-salary-type").value;

  const salary = parseFloat(document.getElementById("emp-salary").value);

  const dailyHours = parseFloat(
    document.getElementById("emp-daily-hours").value,
  );

  const expectedCheckIn = document.getElementById("emp-check-in").value || null;

  const expectedCheckOut =
    document.getElementById("emp-check-out").value || null;

  const lateGrace =
    parseInt(document.getElementById("emp-late-grace").value) || 0;

  const overtimeEnabled = document.getElementById("emp-overtime-enabled")
    .checked
    ? 1
    : 0;

  const workingDays = parseFloat(
    document.getElementById("emp-working-days").value,
  );
  const overtimeRate =
    parseFloat(document.getElementById("emp-overtime-rate").value) || 1.5;

  const payload = {
    name: name,
    role: role,
    phone: phone,
    address: address,

    monthly_salary: salary,

    salary_type: salaryType,
    daily_hours: dailyHours,
    expected_check_in: expectedCheckIn,
    expected_check_out: expectedCheckOut,
    late_grace_minutes: lateGrace,
    overtime_enabled: overtimeEnabled,
    overtime_rate: overtimeRate,
    working_days: workingDays,
  };

  console.log("Adding employee:", payload);

  try {
    const response = await fetch(`${API_BASE}/employee/add`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });

    const result = await response.json();

    if (response.ok) {
      showToast("Employee added successfully", "success");

      document.getElementById("add-employee-form").reset();

      loadEmployees();
    } else {
      showToast(
        result.message || result.error || "Error adding employee",
        "error",
      );
    }
  } catch (error) {
    console.error("Add employee failed:", error);

    showToast("Failed to connect to server", "error");
  }
}

async function editEmployee(id, event) {
  if (event) {
    event.stopPropagation();
  }

  const role = sessionStorage.getItem("role");

  if (!["admin", "head"].includes(role)) {
    showToast("Access Denied. Only Admin/Head can edit employees.", "error");
    return;
  }

  try {
    const response = await fetch(`${API_BASE}/employee/${id}`);

    if (!response.ok) {
      throw new Error("Failed to load employee");
    }

    const emp = await response.json();

    const existingModal = document.getElementById("edit-employee-modal");

    if (existingModal) {
      existingModal.remove();
    }

    const modal = document.createElement("div");

    modal.id = "edit-employee-modal";

    modal.className = "modal-overlay";

    modal.style.display = "flex";

    modal.innerHTML = `
      <div
      class="modal-card"
      style="
        width: min(820px, 92vw);
        max-width: 820px;
        max-height: 90vh;
        overflow-y: auto;
      "
      >

        <h3 style="margin-bottom: 1rem;">
          Edit Employee
        </h3>

        <form id="edit-employee-form">

          <div
            style="
              display:grid;
              grid-template-columns:1fr 1fr;
              gap:0.75rem;
            "
          >

            <div>
              <label class="form-label">Full Name</label>
              <input
                id="edit-emp-name"
                class="form-control"
                type="text"
                value="${escapeHtml(emp.name || "")}"
                required
              >
            </div>

            <div>
              <label class="form-label">Role / Designation</label>
              <input
                id="edit-emp-role"
                class="form-control"
                type="text"
                value="${escapeHtml(emp.role || "")}"
                required
              >
            </div>

            <div>
              <label class="form-label">Phone Number</label>
              <input
                id="edit-emp-phone"
                class="form-control"
                type="text"
                value="${escapeHtml(emp.phone || "")}"
                required
              >
            </div>

            <div>
              <label class="form-label">Address</label>
              <input
                id="edit-emp-address"
                class="form-control"
                type="text"
                value="${escapeHtml(emp.address || "")}"
                required
              >
            </div>

          </div>

          <div
            style="
              display:grid;
              grid-template-columns:1.2fr 1fr 1fr 1fr;
              gap:1rem;
              margin-top:1rem;
            "
          >

            <div>
              <label class="form-label">Salary Type</label>

              <select
                id="edit-emp-salary-type"
                class="form-control"
              >
                <option value="monthly" ${emp.salary_type === "monthly" ? "selected" : ""}>
                  Monthly Salary
                </option>

                <option value="hourly" ${emp.salary_type === "hourly" ? "selected" : ""}>
                  Hourly Salary
                </option>
              </select>
            </div>

            <div>
              <label class="form-label">Salary</label>

              <input
                id="edit-emp-salary"
                class="form-control"
                type="number"
                min="0"
                step="0.01"
                value="${emp.monthly_salary ?? 0}"
                required
              >
            </div>

            <div>
              <label class="form-label">Daily Hours</label>

              <input
                id="edit-emp-daily-hours"
                class="form-control"
                type="number"
                min="1"
                max="24"
                step="1"
                value="${emp.daily_hours ?? 8}"
                required
              >
            </div>
            <div>
                  <label class="form-label">Working Days</label>

                  <input
                      id="edit-emp-working-days"
                      class="form-control"
                      type="number"
                      min="1"
                      max="31"
                      step="1"
                      value="${emp.working_days ?? 26}"
                      required
                  >
              </div>

          </div>

          <div
            style="
              display:grid;
              grid-template-columns:1fr 1fr 1fr;
              gap:1rem;
              margin-top:1rem;
            "
          >

            <div>
              <label class="form-label">
                Expected Check-In
              </label>

              <input
                id="edit-emp-check-in"
                class="form-control"
                type="time"
                value="${emp.expected_check_in || ""}"
              >
            </div>

            <div>
              <label class="form-label">
                Expected Check-Out
              </label>

              <input
                id="edit-emp-check-out"
                class="form-control"
                type="time"
                value="${emp.expected_check_out || ""}"
              >
            </div>

            <div>
              <label class="form-label">
                Late Grace (minutes)
              </label>

              <input
                id="edit-emp-late-grace"
                class="form-control"
                type="number"
                min="0"
                step="1"
                value="${emp.late_grace_minutes ?? 0}"
              >
            </div>

          </div>

          <div
            style="
              display:flex;
              align-items:center;
              justify-content:flex-start;
              gap:1.5rem;
              margin-top:1.25rem;
              padding-top:1rem;
              border-top:1px solid var(--border);
            "
          >

            <label
              style="
                display:flex;
                align-items:center;
                gap:0.5rem;
              "
            >
              <input
                type="checkbox"
                id="edit-emp-overtime-enabled"
                ${emp.overtime_enabled ? "checked" : ""}
              >

              Enable Overtime
            </label>

            <input
              id="edit-emp-overtime-rate"
              class="form-control"
              type="number"
              min="0.1"
              step="0.1"
              value="${emp.overtime_rate ?? 1}"
              style="max-width:220px"
              placeholder="OT Multiplier"
            >

          </div>

          <div
            style="
              display:flex;
              justify-content:flex-end;
              gap:0.75rem;
              margin-top:1.5rem;
            "
          >

            <button
              type="button"
              class="btn"
              id="cancel-edit-employee"
              style="
                background:var(--bg-input);
                color:var(--text-main);
              "
            >
              Cancel
            </button>

            <button
              type="submit"
              class="btn btn-primary"
            >
              Save Changes
            </button>

          </div>

        </form>

      </div>
    `;

    document.body.appendChild(modal);

    document
      .getElementById("cancel-edit-employee")
      .addEventListener("click", () => {
        modal.remove();
      });

    document
      .getElementById("edit-employee-form")
      .addEventListener("submit", async (e) => {
        e.preventDefault();

        const payload = {
          employee_id: id,

          name: document.getElementById("edit-emp-name").value.trim(),

          role: document.getElementById("edit-emp-role").value.trim(),

          phone: document.getElementById("edit-emp-phone").value.trim(),

          address: document.getElementById("edit-emp-address").value.trim(),

          salary_type: document.getElementById("edit-emp-salary-type").value,

          monthly_salary: parseFloat(
            document.getElementById("edit-emp-salary").value,
          ),

          daily_hours: parseFloat(
            document.getElementById("edit-emp-daily-hours").value,
          ),

          expected_check_in:
            document.getElementById("edit-emp-check-in").value || null,

          expected_check_out:
            document.getElementById("edit-emp-check-out").value || null,

          late_grace_minutes:
            parseInt(document.getElementById("edit-emp-late-grace").value) || 0,

          overtime_enabled: document.getElementById("edit-emp-overtime-enabled")
            .checked
            ? 1
            : 0,

          overtime_rate:
            parseFloat(
              document.getElementById("edit-emp-overtime-rate").value,
            ) || 1,
        };

        try {
          const response = await fetch(`${API_BASE}/employee/update`, {
            method: "POST",

            headers: {
              "Content-Type": "application/json",
            },

            body: JSON.stringify(payload),
          });

          const result = await response.json();

          if (!response.ok) {
            throw new Error(
              result.message || result.error || "Failed to update employee",
            );
          }

          modal.remove();

          showToast("Employee updated successfully", "success");

          loadEmployees();
        } catch (error) {
          console.error("Employee update failed:", error);

          showToast(error.message || "Failed to update employee", "error");
        }
      });
  } catch (error) {
    console.error("Failed to load employee for editing:", error);

    showToast("Failed to load employee details", "error");
  }
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
