/**
 * settings.js
 * Handles the Settings page interactions.
 */

function loadSettings() {
  // loadWorkingDays();

  const role = sessionStorage.getItem("role");

  if (role === "head") {
    loadRenewalDate();
    loadDemoMode();
    loadSecureyeConfig();
  }

  if (role === "admin" || role === "head") {
    loadSystemUsers();
  }
}

// async function loadWorkingDays() {
//   try {
//     const response = await fetch(`${API_BASE}/settings/working-days`);

//     const data = await response.json();

//     if (!response.ok || !data.success) {
//       throw new Error(data.message || "Failed to load working days");
//     }

//     const checkboxes = document.querySelectorAll(".working-day-checkbox");

//     checkboxes.forEach((checkbox) => {
//       checkbox.checked = data.days.includes(Number(checkbox.value));
//     });
//   } catch (error) {
//     console.error("Working days load failed:", error);
//   }
// }

// async function saveWorkingDays(event) {
//   event.preventDefault();

//   const checkboxes = document.querySelectorAll(".working-day-checkbox");

//   const days = [];

//   checkboxes.forEach((checkbox) => {
//     if (checkbox.checked) {
//       days.push(Number(checkbox.value));
//     }
//   });

//   if (days.length === 0) {
//     showToast("Select at least one working day.", "error");

//     return;
//   }

//   try {
//     const response = await fetch(`${API_BASE}/settings/working-days`, {
//       method: "POST",
//       headers: {
//         "Content-Type": "application/json",
//       },
//       body: JSON.stringify({
//         days: days,
//       }),
//     });

//     const data = await response.json();

//     if (!response.ok || !data.success) {
//       throw new Error(data.message || "Failed to save working days");
//     }

//     showToast("Working days saved successfully.", "success");
//   } catch (error) {
//     console.error("Working days save failed:", error);

//     showToast(error.message || "Server error.", "error");
//   }
// }

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
async function loadSystemUsers() {
  const tableBody = document.getElementById("system-users-table-body");
  const role = sessionStorage.getItem("role");

  if (!tableBody) {
    console.error("System users table body not found.");
    return;
  }

  // Only Admin and Developer can view system users.
  if (role !== "admin" && role !== "head") {
    tableBody.innerHTML = "";
    return;
  }

  try {
    const response = await fetch(`${API_BASE}/users`, {
      method: "GET",
      headers: {
        "Content-Type": "application/json",
      },
    });

    const data = await response.json();

    if (!response.ok) {
      throw new Error(
        data.message || data.error || "Failed to load system users.",
      );
    }

    /*
     * Backend may return either:
     * [
     *   { id, username, password, role }
     * ]
     *
     * or:
     * {
     *   users: [...]
     * }
     */
    const users = Array.isArray(data)
      ? data
      : Array.isArray(data.users)
        ? data.users
        : [];

    /*
     * Permission visibility:
     *
     * Developer:
     *   sees everybody
     *
     * Admin:
     *   sees Admin + User
     *   does NOT see Developer
     *
     * User:
     *   sees nobody
     */
    const visibleUsers =
      role === "head"
        ? users
        : users.filter((user) => user.role === "admin" || user.role === "user");

    if (visibleUsers.length === 0) {
      tableBody.innerHTML = `
        <tr>
          <td colspan="5" style="text-align: center;">
            No system users found.
          </td>
        </tr>
      `;
      return;
    }

    tableBody.innerHTML = "";

    visibleUsers.forEach((user) => {
      const row = document.createElement("tr");

      const idCell = document.createElement("td");
      idCell.textContent = user.id ?? user.user_id ?? "";

      const usernameCell = document.createElement("td");
      usernameCell.textContent = user.username ?? "";

      const roleCell = document.createElement("td");
      roleCell.textContent = user.role ?? "";

      // Password field with show/hide button
      const passwordCell = document.createElement("td");

      const passwordWrapper = document.createElement("div");
      passwordWrapper.style.display = "flex";
      passwordWrapper.style.alignItems = "center";
      passwordWrapper.style.gap = "6px";

      const passwordInput = document.createElement("input");
      passwordInput.type = "password";
      passwordInput.value = user.password ?? "";
      passwordInput.readOnly = true;
      passwordInput.className = "form-control";
      passwordInput.style.maxWidth = "220px";

      const eyeButton = document.createElement("button");
      eyeButton.type = "button";
      eyeButton.className = "btn btn-sm";
      eyeButton.textContent = "👁";
      eyeButton.title = "Show password";

      eyeButton.addEventListener("click", () => {
        if (passwordInput.type === "password") {
          passwordInput.type = "text";
          eyeButton.textContent = "⌣";
          eyeButton.title = "Hide password";
        } else {
          passwordInput.type = "password";
          eyeButton.textContent = "👁";
          eyeButton.title = "Show password";
        }
      });

      passwordWrapper.appendChild(passwordInput);
      passwordWrapper.appendChild(eyeButton);
      passwordCell.appendChild(passwordWrapper);

      const actionCell = document.createElement("td");

      const changeButton = document.createElement("button");
      changeButton.type = "button";
      changeButton.className = "btn btn-sm btn-primary";
      changeButton.textContent = "Change Password";

      changeButton.addEventListener("click", () => {
        changeUserPassword(user.id ?? user.user_id, user.username ?? "");
      });

      actionCell.appendChild(changeButton);

      row.appendChild(idCell);
      row.appendChild(usernameCell);
      row.appendChild(roleCell);
      row.appendChild(passwordCell);
      row.appendChild(actionCell);

      tableBody.appendChild(row);
    });
  } catch (error) {
    console.error("System users loading failed:", error);

    tableBody.innerHTML = `
      <tr>
        <td
          colspan="5"
          style="
            text-align: center;
            color: var(--danger);
          "
        >
          ${error.message || "Failed to load system users."}
        </td>
      </tr>
    `;
  }
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

  const form = document.getElementById("add-user-form");
  const submitButton = form?.querySelector('button[type="submit"]');

  if (submitButton?.disabled) {
    return;
  }

  const currentRole = sessionStorage.getItem("role");

  if (currentRole !== "head" && currentRole !== "admin") {
    showToast("You do not have permission to create users.", "error");
    return;
  }

  const u = document.getElementById("new-user-name").value.trim();
  const p = document.getElementById("new-user-pass").value;
  const r = document.getElementById("new-user-role").value;

  if (!u || !p) {
    showToast("Username and password are required.", "error");
    return;
  }

  if (currentRole === "admin" && r !== "user") {
    showToast("Admins can only create User accounts.", "error");
    return;
  }

  if (submitButton) {
    submitButton.disabled = true;
    submitButton.innerText = "Creating...";
  }

  try {
    const res = await fetch(`${API_BASE}/users/add`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        username: u,
        password: p,
        role: r,
      }),
    });

    const data = await res.json();

    if (!res.ok || !data.success) {
      throw new Error(data.message || "Failed to create user.");
    }

    showToast(data.message || "User created successfully.", "success");

    form.reset();

    await loadSystemUsers();
  } catch (error) {
    console.error("Create user failed:", error);

    showToast(error.message || "Server error while creating user.", "error");
  } finally {
    if (submitButton) {
      submitButton.disabled = false;
      submitButton.innerText = "Create User";
    }
  }
}

// async function updateUserPassword(userId) {
//   const newPass = document.getElementById(`pass-${userId}`).value;
//   if (!newPass) return;

//   try {
//     const res = await fetch(`${API_BASE}/users/password`, {
//       method: "POST",
//       headers: { "Content-Type": "application/json" },
//       body: JSON.stringify({ user_id: userId, password: newPass }),
//     });

//     const data = await res.json();
//     if (res.ok) {
//       if (window.showToast) showToast("Password updated", "success");
//     } else {
//       if (window.showToast) showToast(data.message, "error");
//     }
//   } catch (err) {
//     if (window.showToast) showToast("Server error", "error");
//   }
// }

async function changeUserPassword(userId, username) {
  const newPassword = window.prompt(`Enter new password for ${username}:`);

  if (newPassword === null) {
    return;
  }

  if (!newPassword.trim()) {
    showToast("Password cannot be empty.", "error");
    return;
  }

  if (newPassword.length < 4) {
    showToast("Password must be at least 4 characters.", "error");
    return;
  }

  try {
    const response = await fetch(`${API_BASE}/users/password`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        user_id: userId,
        password: newPassword,
      }),
    });

    const data = await response.json();

    if (!response.ok || !data.success) {
      showToast(data.message || "Password update failed.", "error");
      return;
    }

    showToast(`Password updated for ${username}.`, "success");

    loadSystemUsers();
  } catch (error) {
    console.error(error);
    showToast("Server error while changing password.", "error");
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

async function changeOwnPassword(event) {
  event.preventDefault();

  const newPassword = document.getElementById("own-password").value;
  const confirmPassword = document.getElementById("own-password-confirm").value;

  if (!newPassword || !confirmPassword) {
    showToast("Password fields are required.", "error");
    return;
  }

  if (newPassword.length < 4) {
    showToast("Password must be at least 4 characters.", "error");
    return;
  }

  if (newPassword !== confirmPassword) {
    showToast("Passwords do not match.", "error");
    return;
  }

  const currentUserId = sessionStorage.getItem("user_id");

  if (!currentUserId) {
    showToast("Session expired. Please login again.", "error");
    return;
  }

  try {
    const response = await fetch(`${API_BASE}/users/password`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        user_id: Number(currentUserId),
        password: newPassword,
      }),
    });

    const data = await response.json();

    if (!response.ok) {
      showToast(data.message || "Failed to change password.", "error");
      return;
    }

    showToast("Password changed successfully. Please login again.", "success");

    document.getElementById("own-password").value = "";
    document.getElementById("own-password-confirm").value = "";

    setTimeout(() => {
      fetch(`${API_BASE}/logout`, {
        method: "POST",
      }).finally(() => {
        window.location.href = "/";
      });
    }, 1200);
  } catch (error) {
    console.error(error);
    showToast("Server error while changing password.", "error");
  }
}
