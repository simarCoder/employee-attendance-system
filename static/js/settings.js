/**
 * settings.js
 * Handles the Settings page interactions.
 */

// function loadSettings() {
//   // 1. Load Hours (Admin + Head)
//   // fetch(`${API_BASE}/settings/hours`)
//   //   .then((res) => res.json())
//   //   .then((data) => {
//   //     const input = document.getElementById("setting-hours");
//   //     if (input) input.value = data.hours;
//   //   })
//   //   .catch((err) => console.error(err));

//   loadWorkingDays();

//   // 2. Load System Users & Renewal Date (Head Only)
//   const role = sessionStorage.getItem("role");
//   if (role === "head") {
//     loadSystemUsers();
//     loadRenewalDate();
//     loadDemoMode(); // NEW: Load toggle state
//   }
// }

function loadSettings() {
  loadWorkingDays();

  const role = sessionStorage.getItem("role");

  if (role === "head") {
    loadSystemUsers();
    loadRenewalDate();
    loadDemoMode();
    loadSecureyeConfig();
  }
}

async function loadWorkingDays() {
  try {
    const response = await fetch(`${API_BASE}/settings/working-days`);

    const data = await response.json();

    if (!response.ok || !data.success) {
      throw new Error(data.message || "Failed to load working days");
    }

    const checkboxes = document.querySelectorAll(".working-day-checkbox");

    checkboxes.forEach((checkbox) => {
      checkbox.checked = data.days.includes(Number(checkbox.value));
    });
  } catch (error) {
    console.error("Working days load failed:", error);
  }
}

async function saveWorkingDays(event) {
  event.preventDefault();

  const checkboxes = document.querySelectorAll(".working-day-checkbox");

  const days = [];

  checkboxes.forEach((checkbox) => {
    if (checkbox.checked) {
      days.push(Number(checkbox.value));
    }
  });

  if (days.length === 0) {
    showToast("Select at least one working day.", "error");

    return;
  }

  try {
    const response = await fetch(`${API_BASE}/settings/working-days`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        days: days,
      }),
    });

    const data = await response.json();

    if (!response.ok || !data.success) {
      throw new Error(data.message || "Failed to save working days");
    }

    showToast("Working days saved successfully.", "success");
  } catch (error) {
    console.error("Working days save failed:", error);

    showToast(error.message || "Server error.", "error");
  }
}

async function triggerDatabaseBackup() {
  try {
    const btn = document.querySelector(
      'button[onclick="triggerDatabaseBackup()"]',
    );
    const origText = btn.innerText;
    btn.innerText = "Backing up...";
    btn.disabled = true;

    const res = await fetch(`${API_BASE}/settings/backup`, { method: "POST" });
    const data = await res.json();

    if (res.ok) {
      if (window.showToast) showToast("Backup Successful!", "success");
    } else {
      if (window.showToast) showToast(data.message, "error");
    }

    btn.innerText = origText;
    btn.disabled = false;
  } catch (err) {
    console.error(err);
    if (window.showToast) showToast("Backup failed (server error)", "error");
  }
}

// --- RENEWAL LOGIC ---
function loadRenewalDate() {
  fetch(`${API_BASE}/settings/renewal`)
    .then((res) => res.json())
    .then((data) => {
      const input = document.getElementById("setting-renewal-date");
      if (input && data.date) {
        input.value = data.date;
      }
    })
    .catch((err) => console.error(err));
}

async function saveRenewalDate(event) {
  event.preventDefault();
  const dateStr = document.getElementById("setting-renewal-date").value;

  try {
    const res = await fetch(`${API_BASE}/settings/renewal`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ date: dateStr }),
    });

    const data = await res.json();
    if (res.ok) {
      if (window.showToast) showToast(data.message, "success");
    } else {
      if (window.showToast) showToast(data.message, "error");
    }
  } catch (err) {
    if (window.showToast) showToast("Server error", "error");
  }
}

// --- DEMO MODE LOGIC (NEW) ---
function loadDemoMode() {
  fetch(`${API_BASE}/settings/demo`)
    .then((res) => res.json())
    .then((data) => {
      const toggle = document.getElementById("setting-demo-toggle");
      if (toggle) toggle.checked = data.enabled;
    })
    .catch((err) => console.error("Error loading demo mode:", err));
}

function toggleDemoMode() {
  const toggle = document.getElementById("setting-demo-toggle");
  if (!toggle) return;

  fetch(`${API_BASE}/settings/demo`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled: toggle.checked }),
  })
    .then((res) => res.json())
    .then((data) => {
      if (window.showToast) showToast(data.message, "success");
      // Reload to apply banner layout changes
      setTimeout(() => location.reload(), 1000);
    })
    .catch((err) => {
      console.error(err);
      if (window.showToast) showToast("Failed to update demo mode", "error");
      // Revert toggle if failed
      toggle.checked = !toggle.checked;
    });
}

// --- SYSTEM USERS LOGIC ---
function loadSystemUsers() {
  const tbody = document.getElementById("system-users-table-body");
  if (!tbody) return;

  fetch(`${API_BASE}/users`)
    .then((res) => res.json())
    .then((users) => {
      tbody.innerHTML = "";
      if (users.length === 0) {
        tbody.innerHTML = `<tr><td colspan="5" style="text-align:center;">No users found.</td></tr>`;
        return;
      }

      users.forEach((u) => {
        const tr = document.createElement("tr");
        tr.innerHTML = `
                <td>${u.id}</td>
                <td>${u.username}</td>
                <td>${u.role.toUpperCase()}</td>
                <td>
                    <div style="display:flex; gap:0.5rem;">
                        <input type="password" value="${u.password}" id="pass-${u.id}" class="form-control" style="padding:0.25rem 0.5rem; font-size:0.8rem; width:100px;">
                        <button onclick="updateUserPassword(${u.id})" class="btn btn-primary" style="padding:0.25rem 0.5rem; font-size:0.8rem;">Save</button>
                    </div>
                </td>
                <td>
                    <button onclick="deleteSystemUser(${u.id})" class="btn btn-warning" style="padding:0.25rem 0.5rem; font-size:0.8rem; background:var(--danger); color:white;">Delete</button>
                </td>
            `;
        tbody.appendChild(tr);
      });
    })
    .catch((err) => {
      console.error(err);
      tbody.innerHTML = `<tr><td colspan="5" style="text-align:center; color:red;">Error loading users.</td></tr>`;
    });
}

async function saveWorkingHours(event) {
  event.preventDefault();
  const hours = document.getElementById("setting-hours").value;

  try {
    const res = await fetch(`${API_BASE}/settings/hours`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ hours: parseFloat(hours) }),
    });

    const data = await res.json();
    if (res.ok) {
      if (window.showToast) showToast(data.message, "success");
    } else {
      if (window.showToast) showToast(data.message, "error");
    }
  } catch (err) {
    if (window.showToast) showToast("Server error", "error");
  }
}

async function addSystemUser(event) {
  event.preventDefault();

  // Only HEAD
  const role = sessionStorage.getItem("role");
  if (role !== "head") {
    if (window.showToast) showToast("Only HEAD can add users", "error");
    return;
  }

  const u = document.getElementById("new-user-name").value;
  const p = document.getElementById("new-user-pass").value;
  const r = document.getElementById("new-user-role").value;

  try {
    const res = await fetch(`${API_BASE}/users/add`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: u, password: p, role: r }),
    });

    const data = await res.json();
    if (res.ok) {
      if (window.showToast) showToast(data.message, "success");
      document.getElementById("add-user-form").reset();
      loadSystemUsers();
    } else {
      if (window.showToast) showToast(data.message, "error");
    }
  } catch (err) {
    if (window.showToast) showToast("Server error", "error");
  }
}

async function updateUserPassword(userId) {
  const newPass = document.getElementById(`pass-${userId}`).value;
  if (!newPass) return;

  try {
    const res = await fetch(`${API_BASE}/users/password`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: userId, password: newPass }),
    });

    const data = await res.json();
    if (res.ok) {
      if (window.showToast) showToast("Password updated", "success");
    } else {
      if (window.showToast) showToast(data.message, "error");
    }
  } catch (err) {
    if (window.showToast) showToast("Server error", "error");
  }
}

async function deleteSystemUser(userId) {
  const currentUserId = sessionStorage.getItem("user_id");

  showConfirmModal(
    "Delete this system user? This cannot be undone.",
    async () => {
      try {
        const res = await fetch(`${API_BASE}/users/delete`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            user_id: userId,
            current_user_id: currentUserId,
          }),
        });

        const data = await res.json();
        if (res.ok) {
          if (window.showToast) showToast(data.message, "success");
          loadSystemUsers();
        } else {
          if (window.showToast) showToast(data.message, "error");
        }
      } catch (err) {
        if (window.showToast) showToast("Server error", "error");
      }
    },
  );
}

// ============================================================
// SECUREYE DEVICE CONFIGURATION
// ============================================================

function getDeveloperHeaders() {
  const userId = sessionStorage.getItem("user_id");

  return {
    "Content-Type": "application/json",
    "X-User-ID": userId || "",
  };
}

async function loadSecureyeConfig() {
  try {
    const response = await fetch(`${API_BASE}/settings/secureye`, {
      method: "GET",
      headers: getDeveloperHeaders(),
    });

    const data = await response.json();

    if (!response.ok || !data.success) {
      throw new Error(data.error || "Failed to load Secureye configuration");
    }

    const ipInput = document.getElementById("secureye-ip");
    const portInput = document.getElementById("secureye-port");
    const timeoutInput = document.getElementById("secureye-timeout");

    if (ipInput) {
      ipInput.value = data.ip || "";
    }

    if (portInput) {
      portInput.value = data.port ?? 5005;
    }

    if (timeoutInput) {
      timeoutInput.value = data.timeout ?? 10;
    }
  } catch (error) {
    console.error("Secureye configuration load failed:", error);
  }
}

async function saveSecureyeConfig(event) {
  event.preventDefault();

  const ip = document.getElementById("secureye-ip").value.trim();

  const port = Number(document.getElementById("secureye-port").value);

  const timeout = Number(document.getElementById("secureye-timeout").value);

  if (!ip) {
    showToast("Enter the Secureye IP address.", "error");
    return;
  }

  if (!Number.isInteger(port) || port < 1 || port > 65535) {
    showToast("Invalid port number.", "error");
    return;
  }

  if (!Number.isInteger(timeout) || timeout <= 0) {
    showToast("Invalid timeout.", "error");
    return;
  }

  try {
    const response = await fetch(`${API_BASE}/settings/secureye`, {
      method: "POST",
      headers: getDeveloperHeaders(),
      body: JSON.stringify({
        ip: ip,
        port: port,
        timeout: timeout,
      }),
    });

    const data = await response.json();

    if (!response.ok || !data.success) {
      throw new Error(data.error || "Failed to save configuration");
    }

    showToast("Secureye configuration saved successfully.", "success");
  } catch (error) {
    console.error("Secureye configuration save failed:", error);

    showToast(error.message || "Server error.", "error");
  }
}

async function testSecureyeConnection() {
  const button = document.getElementById("secureye-test-btn");

  const resultBox = document.getElementById("secureye-test-result");

  const outputBox = document.getElementById("secureye-test-output");

  if (!button || !resultBox || !outputBox) {
    return;
  }

  const originalText = button.innerText;

  button.disabled = true;
  button.innerText = "Testing...";

  resultBox.style.display = "block";

  outputBox.innerHTML = `
    <div style="color: var(--text-muted)">
      Connecting to Secureye...
    </div>
  `;

  try {
    const response = await fetch(`${API_BASE}/settings/secureye/test`, {
      method: "POST",
      headers: getDeveloperHeaders(),
    });

    const data = await response.json();

    if (!response.ok || !data.success) {
      throw new Error(data.error || "Secureye connection failed.");
    }

    let responseHtml = "";

    if (data.responses) {
      responseHtml = Object.entries(data.responses)
        .map(
          ([name, value]) => `
            <div style="margin-top: 0.5rem;">
              <strong>${name}</strong>
              <div
                style="
                  font-family: monospace;
                  font-size: 0.75rem;
                  word-break: break-all;
                  color: var(--text-muted);
                  margin-top: 0.2rem;
                "
              >
                ${value}
              </div>
            </div>
          `,
        )
        .join("");
    }

    outputBox.innerHTML = `
      <div style="color: var(--success); font-weight: 700;">
        ✓ Device Connected
      </div>

      <div style="margin-top: 0.75rem;">
        <strong>IP:</strong> ${data.ip}
      </div>

      <div>
        <strong>Port:</strong> ${data.port}
      </div>

      <div>
        <strong>Timeout:</strong> ${data.timeout}s
      </div>

      <div>
        <strong>Record Count:</strong> ${data.record_count}
      </div>

      <div style="margin-top: 1rem;">
        <strong>Protocol Responses</strong>
        ${responseHtml}
      </div>
    `;

    showToast("Secureye connection successful.", "success");
  } catch (error) {
    console.error("Secureye connection test failed:", error);

    outputBox.innerHTML = `
      <div style="color: var(--danger); font-weight: 700;">
        ✗ Connection Failed
      </div>

      <div style="margin-top: 0.5rem;">
        ${error.message || "Unable to connect to Secureye."}
      </div>
    `;

    showToast(error.message || "Secureye connection failed.", "error");
  } finally {
    button.disabled = false;
    button.innerText = originalText;
  }
}
