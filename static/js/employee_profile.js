let CURRENT_EMPLOYEE_ID = null;
let PREVIOUS_SECTION = null;
let PROFILE_RETURN_SECTION = null;
let PROFILE_RETURN_TO_LIST = false;

/* =========================
   OPEN PROFILE FROM EMPLOYEE TABLE
========================= */
function openEmployeeProfile(employeeId, event) {
  if (event) event.stopPropagation();

  const activeSection = document.querySelector(".section.active");
  const activeSectionId = activeSection ? activeSection.id : "overview";

  // If we are already inside Employee Details, this profile was opened
  // from its employee list. Otherwise remember the real originating section.
  if (activeSectionId === "employee-profile") {
    PROFILE_RETURN_SECTION = "employee-profile";
    PROFILE_RETURN_TO_LIST = true;
  } else {
    PROFILE_RETURN_SECTION = activeSectionId;
    PROFILE_RETURN_TO_LIST = false;
  }

  PREVIOUS_SECTION = PROFILE_RETURN_SECTION;
  CURRENT_EMPLOYEE_ID = employeeId;

  switchSection("employee-profile");

  document.getElementById("profile-list-view").style.display = "none";
  document.getElementById("profile-detail-view").style.display = "block";

  const content = document.getElementById("profile-content-area");
  content.innerHTML = `
    <div id="profile-basic-info">
      <div class="profile-loading">Loading employee details...</div>
    </div>
  `;

  loadEmployeeProfile(employeeId);
  loadEmployeeDocuments(employeeId);
  loadEmployeeAttendance(employeeId);
  loadEmployeeSalaryHistory(employeeId);
}

/* =========================
   LOAD PROFILE DATA
========================= */
function loadEmployeeProfile(employeeId) {
  fetch(`${API_BASE}/employee/${employeeId}`)
    .then((res) => {
      if (!res.ok) throw new Error("Profile fetch failed");
      return res.json();
    })
    .then((emp) => {
      const content = document.getElementById("profile-basic-info");
      if (!content) return;

      const money = (value) =>
        `₹${Number(value || 0).toLocaleString("en-IN", {
          minimumFractionDigits: 2,
          maximumFractionDigits: 2,
        })}`;
      const yesNo = (value) => (Number(value) ? "Enabled" : "Disabled");
      const time = (value) => value || "Not configured";

      content.innerHTML = `
        <div class="employee-profile-header">
          <div>
            <div class="employee-profile-eyebrow">EMPLOYEE PROFILE</div>
            <h2>${emp.name || "-"}</h2>
            <p>${emp.role || "No role assigned"} · Employee #${emp.id}</p>
          </div>
          <span class="employee-profile-status ${emp.status === "active" ? "active" : "inactive"}">${emp.status || "unknown"}</span>
        </div>

        <div class="employee-profile-grid">
          <section class="profile-info-panel">
            <div class="profile-panel-title">Personal & Contact</div>
            <div class="profile-field-grid">
              <div class="profile-field"><span>Employee ID</span><strong>#${emp.id}</strong></div>
              <div class="profile-field"><span>Full Name</span><strong>${emp.name || "-"}</strong></div>
              <div class="profile-field"><span>Phone</span><strong>${emp.phone || "-"}</strong></div>
              <div class="profile-field profile-field-wide"><span>Address</span><strong>${emp.address || "-"}</strong></div>
            </div>
          </section>

          <section class="profile-info-panel">
            <div class="profile-panel-title">Employment & Payroll</div>
            <div class="profile-field-grid">
              <div class="profile-field"><span>Salary Type</span><strong>${emp.salary_type || "-"}</strong></div>
              <div class="profile-field"><span>Monthly Salary</span><strong>${money(emp.monthly_salary)}</strong></div>
              <div class="profile-field"><span>Hourly Rate</span><strong>${money(emp.hourly_rate)}</strong></div>
              <div class="profile-field"><span>Working Days</span><strong>${emp.working_days ?? "-"}</strong></div>
            </div>
          </section>

          <section class="profile-info-panel">
            <div class="profile-panel-title">Attendance Configuration</div>
            <div class="profile-field-grid">
              <div class="profile-field"><span>Daily Hours</span><strong>${Number(emp.daily_hours || 0).toFixed(2)} h</strong></div>
              <div class="profile-field"><span>Check In</span><strong>${time(emp.expected_check_in)}</strong></div>
              <div class="profile-field"><span>Check Out</span><strong>${time(emp.expected_check_out)}</strong></div>
              <div class="profile-field"><span>Late Grace</span><strong>${emp.late_grace_minutes ?? 0} min</strong></div>
            </div>
          </section>

          <section class="profile-info-panel">
            <div class="profile-panel-title">Overtime & Grace Holidays</div>
            <div class="profile-field-grid">
              <div class="profile-field"><span>Overtime</span><strong>${yesNo(emp.overtime_enabled)}</strong></div>
              <div class="profile-field"><span>Overtime Rate</span><strong>${Number(emp.overtime_rate || 0).toFixed(2)}×</strong></div>
              <div class="profile-field"><span>Grace Holidays</span><strong>${Number(emp.grace_holidays || 0).toFixed(2)}</strong></div>
              <div class="profile-field"><span>Account Status</span><strong>${emp.status || "-"}</strong></div>
            </div>
          </section>
        </div>

        <section class="profile-info-panel profile-full-panel">
          <div class="profile-panel-title">Attendance Snapshot</div>
          <div id="profile-attendance-summary" class="profile-inline-loading">Loading attendance...</div>
        </section>

        <section class="profile-info-panel profile-full-panel">
          <div class="profile-panel-title">Salary History</div>
          <div id="profile-salary-history" class="profile-inline-loading">Loading salary history...</div>
        </section>
      `;
    })
    .catch((err) => {
      console.error(err);
      const content = document.getElementById("profile-basic-info");
      if (content)
        content.innerHTML = `<div class="profile-error">Failed to load employee details.</div>`;
      if (window.showToast) showToast("Failed to load profile", "error");
    });
}

function loadEmployeeAttendance(employeeId) {
  fetch(`${API_BASE}/attendance/${employeeId}`)
    .then((res) => res.json())
    .then((records) => {
      const target = document.getElementById("profile-attendance-summary");
      if (!target) return;
      const rows = Array.isArray(records) ? records : [];
      const totalMinutes = rows.reduce((sum, row) => {
        if (row.worked_minutes !== null && row.worked_minutes !== undefined) {
          return sum + Math.max(0, Math.round(Number(row.worked_minutes) || 0));
        }

        return (
          sum + Math.max(0, Math.round(Number(row.worked_hours || 0) * 60))
        );
      }, 0);
      const totalHours = (totalMinutes / 60).toFixed(1);
      const completed = rows.filter(
        (row) => row.check_in && row.check_out,
      ).length;
      target.innerHTML = `
        <div class="profile-stat-grid">
          <div><span>Attendance Records</span><strong>${rows.length}</strong></div>
          <div><span>Completed Days</span><strong>${completed}</strong></div>
          <div><span>Worked Hours</span><strong>${totalHours} h</strong></div>
        </div>
      `;
    })
    .catch((err) => {
      console.error("Attendance profile load error", err);
      const target = document.getElementById("profile-attendance-summary");
      if (target) target.textContent = "Attendance data unavailable.";
    });
}

function loadEmployeeSalaryHistory(employeeId) {
  fetch(`${API_BASE}/salary/records?employee_id=${employeeId}`)
    .then((res) => res.json())
    .then((payload) => {
      const target = document.getElementById("profile-salary-history");
      if (!target) return;
      const records = payload.records || [];
      if (!records.length) {
        target.innerHTML = `<div class="profile-empty">No salary records generated yet.</div>`;
        return;
      }

      target.innerHTML = `
        <div class="table-container profile-history-table">
          <table class="table">
            <thead><tr><th>Month</th><th>Base Salary</th><th>Deductions</th><th>Total</th><th>Status</th><th></th></tr></thead>
            <tbody>
              ${records
                .slice(0, 12)
                .map((record) => {
                  const deductions = Math.max(
                    0,
                    Number(record.base_salary || 0) -
                      Number(record.total_salary || 0),
                  );
                  return `<tr>
                  <td>${record.month}</td>
                  <td>₹${Number(record.base_salary || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}</td>
                  <td>₹${deductions.toLocaleString("en-IN", { minimumFractionDigits: 2 })}</td>
                  <td><strong>₹${Number(record.total_salary || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}</strong></td>
                  <td><span class="status-badge">${record.locked ? "Locked" : "Draft"}</span></td>
                  <td><button class="btn profile-receipt-btn" onclick="viewSalaryReceipt(${employeeId}, '${record.month}')">Receipt</button></td>
                </tr>`;
                })
                .join("")}
            </tbody>
          </table>
        </div>
      `;
    })
    .catch((err) => {
      console.error("Salary history load error", err);
      const target = document.getElementById("profile-salary-history");
      if (target) target.textContent = "Salary history unavailable.";
    });
}

/* =========================
   LOAD SALARY DATA
========================= */
function loadEmployeeSalary(employeeId) {
  fetch(`${API_BASE}/employee/${employeeId}`)
    .then((res) => res.json())
    .then((emp) => {
      const salarySection = document.getElementById("profile-salary-section");
      if (salarySection) {
        // FIX: Use responsive grid here too
        salarySection.innerHTML = `
                <h4 style="margin-bottom: 0.5rem; color: var(--primary);">Financial Details</h4>
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 1rem;">
                    <div>
                        <label class="form-label" style="font-size: 0.8rem;">Monthly Base Salary</label>
                        <div style="font-size: 1.2rem; font-weight: bold; color: var(--text-main);">
                            ₹${emp.monthly_salary ? emp.monthly_salary.toLocaleString() : "0"}
                        </div>
                    </div>
                </div>
            `;
      }
    })
    .catch((err) => console.error("Salary load error", err));
}

/* =========================
   LOAD DOCUMENTS
========================= */
function loadEmployeeDocuments(employeeId) {
  fetch(`${API_BASE}/employee/${employeeId}/documents`)
    .then((res) => {
      if (!res.ok) throw new Error("Docs fetch failed");
      return res.json();
    })
    .then((docs) => {
      const tbody = document.getElementById("employee-docs-body");
      tbody.innerHTML = "";

      if (!docs || docs.length === 0) {
        tbody.innerHTML = `
          <tr>
            <td colspan="5" style="text-align:center;">
              No documents uploaded.
            </td>
          </tr>
        `;
        return;
      }

      // Check privileges for VIEW/DELETE
      const role = sessionStorage.getItem("role");
      const hasPrivilege = ["admin", "head"].includes(role);

      docs.forEach((doc) => {
        const tr = document.createElement("tr");
        const fileName = doc.file_path.split("\\").pop().split("/").pop();

        let formattedDate = doc.uploaded_at;
        if (typeof formatDateTime12Hour === "function") {
          formattedDate = formatDateTime12Hour(doc.uploaded_at);
        }

        // Construct Actions
        let actions = "-";
        if (hasPrivilege) {
          // Ensure API_BASE doesn't have trailing slash if doc.file_path starts with one, or handle logic
          // Assuming API_BASE is e.g. http://localhost:5000 and doc.file_path is UPLOADS/employee_1/file.png
          const relativePath = doc.file_path.replace(/\\/g, "/");
          const viewBtn = `<a href="${API_BASE}/${relativePath}" target="_blank" class="btn btn-primary" style="padding:4px 8px; font-size:0.8rem; text-decoration:none; margin-right: 5px;">View</a>`;
          const deleteBtn = `<button onclick="deleteDocument(${doc.doc_id})" class="btn" style="background:var(--danger); color:white; padding:4px 8px; font-size:0.8rem;">Delete</button>`;
          actions = viewBtn + deleteBtn;
        }

        tr.innerHTML = `
          <td>${doc.doc_type}</td>
          <td>${doc.adhaar_no || "-"}</td>
          <td>${fileName}</td>
          <td>${formattedDate}</td>
          <td>${actions}</td>
        `;

        tbody.appendChild(tr);
      });
    })
    .catch((err) => {
      console.error(err);
      if (window.showToast) showToast("Failed to load documents", "error");
    });
}

// DELETE DOCUMENT FUNCTION
function deleteDocument(docId) {
  if (window.showConfirmModal) {
    showConfirmModal("Are you sure you want to delete this document?", () => {
      executeDelete(docId);
    });
  } else {
    if (confirm("Delete this document?")) executeDelete(docId);
  }
}

function executeDelete(docId) {
  fetch(`${API_BASE}/documents/delete`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ doc_id: docId }),
  })
    .then((res) => res.json())
    .then((data) => {
      if (window.showToast) showToast(data.message, "success");
      // Reload list to see changes
      loadEmployeeDocuments(CURRENT_EMPLOYEE_ID);
    })
    .catch((err) => {
      console.error(err);
      if (window.showToast) showToast("Error deleting document", "error");
    });
}

/* =========================
   LOAD EMPLOYEE LIST (DETAILS SECTION)
========================= */
function loadProfileEmployeeList() {
  fetch(`${API_BASE}/employees`)
    .then((res) => res.json())
    .then((employees) => {
      const tbody = document.getElementById("profile-employee-list-body");
      tbody.innerHTML = "";

      if (!employees || employees.length === 0) {
        tbody.innerHTML = `
          <tr>
            <td colspan="4" style="text-align:center;">
              No employees found
            </td>
          </tr>
        `;
        return;
      }

      employees.forEach((emp) => {
        const tr = document.createElement("tr");

        tr.innerHTML = `
          <td>#${emp.id}</td>
          <td>${emp.name}</td>
          <td>${emp.role}</td>
          <td>
            <button class="btn btn-primary" style="padding:4px 8px;">
              View Profile
            </button>
          </td>
        `;

        tr.querySelector("button").addEventListener("click", () => {
          openEmployeeProfile(emp.id);
        });

        tbody.appendChild(tr);
      });
    });
}

/* =========================
   SIDEBAR CLICK
========================= */
function openEmployeeDetailsSection(navElement) {
  switchSection("employee-profile", navElement);

  document.getElementById("profile-list-view").style.display = "block";
  document.getElementById("profile-detail-view").style.display = "none";

  loadProfileEmployeeList();
}

/* =========================
   BACK BUTTON
========================= */
function backToEmployeeList() {
  const returnSection =
    PROFILE_RETURN_SECTION || PREVIOUS_SECTION || "overview";

  if (returnSection === "employee-profile") {
    document.getElementById("profile-detail-view").style.display = "none";
    document.getElementById("profile-list-view").style.display = "block";
    loadProfileEmployeeList();
    return;
  }

  document.getElementById("profile-detail-view").style.display = "none";
  document.getElementById("profile-list-view").style.display = "block";
  switchSection(returnSection);
}

/* =========================
   HELPER: 12-HOUR DATE FORMATTER
========================= */
function formatDateTime12Hour(dateTimeStr) {
  if (!dateTimeStr) return "-";
  const parts = dateTimeStr.split(" ");
  const datePart = parts[0];
  const timePart = parts[1];

  if (!timePart) return dateTimeStr;

  const [hoursStr, minutesStr] = timePart.split(":");
  let hours = parseInt(hoursStr, 10);
  const suffix = hours >= 12 ? "PM" : "AM";

  hours = hours % 12 || 12;

  return `${datePart} ${hours}:${minutesStr} ${suffix}`;
}

document.addEventListener("DOMContentLoaded", () => {
  const uploadBtn = document.getElementById("upload-doc-btn");
  const docTypeSelect = document.getElementById("doc-type");
  const docNumberInput = document.getElementById("doc-aadhaar");
  const customTypeInput = document.getElementById("doc-custom-type");

  // Dynamic UI Change Listener
  if (docTypeSelect) {
    docTypeSelect.addEventListener("change", (e) => {
      const type = e.target.value;

      if (type === "Other") {
        if (customTypeInput) customTypeInput.style.display = "block";
        if (docNumberInput) docNumberInput.placeholder = "Document Number";
      } else {
        if (customTypeInput) customTypeInput.style.display = "none";
        if (docNumberInput) docNumberInput.placeholder = `${type} No`;
      }
    });
  }

  if (uploadBtn) {
    uploadBtn.addEventListener("click", () => {
      if (!CURRENT_EMPLOYEE_ID) {
        if (window.showToast) showToast("Select employee first", "error");
        return;
      }

      let docType = document.getElementById("doc-type").value;
      const adhaar = document.getElementById("doc-aadhaar").value;
      const fileInput = document.getElementById("doc-file");

      // Handle "Other" Logic
      if (docType === "Other") {
        const customVal = document
          .getElementById("doc-custom-type")
          .value.trim();
        if (!customVal) {
          if (window.showToast)
            showToast("Please enter the document name", "error");
          return;
        }
        docType = customVal; // Override docType with custom input
      }

      if (!adhaar) {
        if (window.showToast)
          showToast("Please enter document number", "error");
        return;
      }

      if (fileInput.files.length === 0) {
        if (window.showToast) showToast("Select a file", "error");
        return;
      }

      const formData = new FormData();
      formData.append("doc_type", docType);
      formData.append("adhaar_no", adhaar);
      formData.append("file", fileInput.files[0]);

      fetch(`${API_BASE}/employee/${CURRENT_EMPLOYEE_ID}/documents`, {
        method: "POST",
        body: formData,
      })
        .then((res) => res.json())
        .then(() => {
          if (window.showToast) showToast("Uploaded successfully", "success");
          fileInput.value = "";
          document.getElementById("doc-aadhaar").value = "";
          if (customTypeInput) customTypeInput.value = "";
          loadEmployeeDocuments(CURRENT_EMPLOYEE_ID);
        })
        .catch((err) => {
          console.error(err);
          if (window.showToast) showToast("Upload failed", "error");
        });
    });
  }
});

function loadDashboardEmployeeList() {
  fetch(`${API_BASE}/employees`)
    .then((res) => res.json())
    .then((employees) => {
      const tbody = document.getElementById("dashboard-employee-list-body");

      if (!tbody) return;

      tbody.innerHTML = "";

      if (!employees || employees.length === 0) {
        tbody.innerHTML = `
          <tr>
            <td colspan="4" style="text-align:center;">
              No employees found
            </td>
          </tr>
        `;
        return;
      }

      employees.forEach((emp) => {
        const tr = document.createElement("tr");

        tr.innerHTML = `
          <td>#${emp.id}</td>
          <td>${emp.name}</td>
          <td>${emp.role}</td>
          <td>
            <button class="btn btn-primary" style="padding:4px 8px;">
              View Profile
            </button>
          </td>
        `;

        tr.querySelector("button").addEventListener("click", () => {
          openEmployeeProfile(emp.id);
        });

        tbody.appendChild(tr);
      });
    });
}
