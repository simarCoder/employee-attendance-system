/**
 * auth.js
 * Handles server-side authentication/session management.
 *
 * IMPORTANT:
 * The Flask session is the source of truth.
 * sessionStorage is only used as a temporary UI cache.
 */

async function getServerSession() {
  try {
    const res = await fetch("/auth/session", {
      method: "GET",
      credentials: "same-origin",
      cache: "no-store",
    });

    if (!res.ok) {
      return null;
    }

    return await res.json();
  } catch (err) {
    console.error("Session check failed:", err);
    return null;
  }
}

/**
 * Check whether the Flask session is actually valid.
 */
async function checkAuth() {
  const path = window.location.pathname;

  const session = await getServerSession();

  // -------------------------------------------------------
  // Dashboard requires a valid Flask session
  // -------------------------------------------------------
  if (path === "/dashboard") {
    if (!session || session.authenticated !== true) {
      sessionStorage.clear();
      window.location.replace("/");
      return null;
    }

    // Cache ONLY for UI convenience.
    sessionStorage.setItem("role", session.role);
    sessionStorage.setItem("user_id", session.user_id);

    return session;
  }

  // -------------------------------------------------------
  // Login page: if already authenticated, go dashboard
  // -------------------------------------------------------
  if (path === "/") {
    if (session && session.authenticated === true) {
      sessionStorage.setItem("role", session.role);
      sessionStorage.setItem("user_id", session.user_id);

      window.location.replace("/dashboard");
      return session;
    }

    // Make sure stale browser cache doesn't survive.
    sessionStorage.clear();
  }

  return null;
}

/**
 * Login
 */
async function handleLogin(event) {
  event.preventDefault();

  const username = document.getElementById("username").value.trim();
  const password = document.getElementById("password").value;

  try {
    const res = await fetch(`${API_BASE}/login`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      credentials: "same-origin",
      body: JSON.stringify({
        username,
        password,
      }),
    });

    const data = await res.json();

    if (!res.ok) {
      if (window.showToast) {
        showToast(data.error || "Login failed", "error");
      } else {
        alert(data.error || "Login failed");
      }

      return;
    }

    /*
     * Flask has created the real authenticated session.
     *
     * These values are ONLY cached for UI logic.
     */
    sessionStorage.setItem("role", data.role);
    sessionStorage.setItem("user_id", data.user_id);

    window.location.replace("/dashboard");
  } catch (err) {
    console.error("Login error:", err);

    if (window.showToast) {
      showToast("Server error", "error");
    } else {
      alert("Server error");
    }
  }
}

/**
 * Logout
 */
function logout() {
  showConfirmModal("Are you sure you want to logout?", async () => {
    try {
      const res = await fetch("/logout", {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
        },
      });

      if (!res.ok) {
        console.error("Server logout failed.");
      }
    } catch (err) {
      console.error("Logout request failed:", err);
    } finally {
      // Clear only authentication cache.
      sessionStorage.removeItem("role");
      sessionStorage.removeItem("user_id");

      window.location.replace("/");
    }
  });
}

/**
 * Handle expired/revoked Flask sessions.
 *
 * Existing application modules already use fetch().
 * This wrapper catches a 401 returned by the Flask backend
 * and forces the browser back to login.
 */
(function installSessionGuard() {
  const originalFetch = window.fetch;

  window.fetch = async function (...args) {
    const response = await originalFetch.apply(this, args);

    if (response.status === 401 && window.location.pathname === "/dashboard") {
      try {
        const cloned = response.clone();
        const data = await cloned.json();

        if (data.error === "AUTH_REQUIRED") {
          sessionStorage.clear();

          window.location.replace("/");
        }
      } catch (err) {
        console.error("Authentication response handling failed:", err);
      }
    }

    return response;
  };
})();

// Expose functions globally.
window.checkAuth = checkAuth;
window.handleLogin = handleLogin;
window.logout = logout;
