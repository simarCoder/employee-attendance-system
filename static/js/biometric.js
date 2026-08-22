async function loadBiometricMappings() {
  const tbody = document.getElementById("biometric-mapping-body");

  try {
    const response = await fetch("/biometric/mappings");

    const data = await response.json();

    if (!response.ok || !data.success) {
      throw new Error(data.error || "Failed to load mappings");
    }

    tbody.innerHTML = "";

    if (data.mappings.length === 0) {
      tbody.innerHTML = `
                <tr>
                    <td colspan="5"
                        style="text-align:center;">
                        No biometric mappings found.
                    </td>
                </tr>
            `;

      return;
    }

    data.mappings.forEach((mapping) => {
      const row = document.createElement("tr");

      row.innerHTML = `
                <td>${mapping.name}</td>
                <td>${mapping.role || "-"}</td>
                <td>#${mapping.employee_id}</td>
                <td>${mapping.device_card_id}</td>

                <td>
                    <button
                        type="button"
                        class="btn btn-danger"
                        onclick="removeBiometricMapping(${mapping.device_card_id})"
                    >
                        Unmap
                    </button>
                </td>
            `;

      tbody.appendChild(row);
    });
  } catch (error) {
    console.error("Biometric mappings failed:", error);

    tbody.innerHTML = `
            <tr>
                <td colspan="5"
                    style="text-align:center; color:var(--danger);">
                    Failed to load biometric mappings.
                </td>
            </tr>
        `;
  }
}

async function loadBiometricEmployees() {
  const select = document.getElementById("biometric-employee-select");

  try {
    const response = await fetch("/employees");

    const employees = await response.json();

    select.innerHTML = `
            <option value="">
                Select Employee
            </option>
        `;

    employees.forEach((employee) => {
      const option = document.createElement("option");

      option.value = employee.id;

      option.textContent = `#${employee.id} - ${employee.name}`;

      select.appendChild(option);
    });
  } catch (error) {
    console.error("Failed to load employees:", error);
  }
}

async function assignBiometricMapping() {
  const employeeId = document.getElementById("biometric-employee-select").value;

  const cardId = document.getElementById("biometric-card-id").value;

  if (!employeeId) {
    alert("Select an employee.");
    return;
  }

  if (!cardId) {
    alert("Enter the Secureye Card ID.");
    return;
  }

  try {
    const response = await fetch("/biometric/mapping", {
      method: "POST",

      headers: {
        "Content-Type": "application/json",
      },

      body: JSON.stringify({
        employee_id: Number(employeeId),

        device_card_id: Number(cardId),
      }),
    });

    const data = await response.json();

    if (!response.ok || !data.success) {
      throw new Error(data.error || data.message || "Mapping failed");
    }

    alert("Biometric device assigned successfully.");

    document.getElementById("biometric-card-id").value = "";

    await loadBiometricMappings();
  } catch (error) {
    console.error("Biometric assignment failed:", error);

    alert(error.message);
  }
}
async function removeBiometricMapping(deviceCardId) {
  if (!confirm(`Remove Secureye ID ${deviceCardId} from its employee?`)) {
    return;
  }

  try {
    const response = await fetch("/biometric/mapping", {
      method: "DELETE",

      headers: {
        "Content-Type": "application/json",
      },

      body: JSON.stringify({
        device_card_id: deviceCardId,
      }),
    });

    const data = await response.json();

    if (!response.ok || !data.success) {
      throw new Error(data.error || data.message || "Unmapping failed");
    }

    await loadBiometricMappings();
  } catch (error) {
    console.error("Biometric unmapping failed:", error);

    alert(error.message);
  }
}
