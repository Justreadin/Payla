// js/payla_modal.js
import { BACKEND_BASE } from "./config.js";
import {
  trackLockModalOpened,
  trackLockModalClosed,
  trackModalSuccessView,
  trackModalEmailAppOpened,
  trackModalVerificationResent,
  trackModalVerificationConfirmed,
  trackUsernameCheckStarted,
  trackUsernameCheckResult,
  trackUsernameCheckFailed,
} from "./payla_analytics.js";

class PaylaClaimModal {
  constructor() {
    this.modal = null;
    this.overlay = null;
    this.currentStage = "claim"; // 'claim' | 'success'
    this.usernameCheckTimeout = null;
    this.isUsernameAvailable = false;
    this.usernameValue = "";
    this.userEmail = "";
    this.verificationPolling = null;
    this.openedFrom = "unknown";

    this.init();
  }

  /* ============================================================
     INIT
     ============================================================ */

  init() {
    this.createModal();
    this.bindEvents();
  }

  createModal() {
    this.overlay = document.createElement("div");
    this.overlay.className = "opal-modal-overlay";
    this.overlay.id = "paylaClaimModal";

    this.overlay.innerHTML = `
      <div class="opal-modal" role="dialog" aria-modal="true" aria-labelledby="opalTitle">
        <button class="opal-modal-close" id="opalModalClose" aria-label="Close">
          <i class="fas fa-times"></i>
        </button>

        <!-- Stage 1: Claim -->
        <div class="opal-modal-stage opal-claim-stage" id="opalClaimStage">
          <div class="opal-header">
            <h2 class="opal-title" id="opalTitle">Claim your Payla username</h2>
            <p class="opal-subtitle">
              Join the first 200. Lock in the founding price.
            </p>
          </div>

          <form class="opal-form" id="opalClaimForm" novalidate>
            <div class="opal-form-group">
              <label for="opalUsername">Your Payla username</label>
              <div class="opal-username-container">
                <div class="opal-username-input" id="opalUsernameField">
                  <span class="opal-username-prefix">payla.ng/</span>
                  <input
                    type="text"
                    id="opalUsername"
                    placeholder="yourname"
                    maxlength="20"
                    pattern="[a-zA-Z0-9_-]+"
                    autocomplete="off"
                    autocapitalize="none"
                    spellcheck="false"
                    required
                  />
                  <div class="opal-validation-status" id="opalUsernameStatus">
                    <div class="opal-loading-spinner"></div>
                    <div class="opal-success-check"></div>
                  </div>
                </div>
                <div class="opal-feedback-text" id="opalFeedback"></div>
              </div>
            </div>

            <div class="opal-form-group floating">
              <input type="email" id="opalEmail" class="opal-input" placeholder=" " required />
              <label for="opalEmail">Email</label>
            </div>

            <div class="opal-form-group floating">
              <input
                type="password"
                id="opalPassword"
                class="opal-input"
                placeholder=" "
                minlength="8"
                required
              />
              <label for="opalPassword">Create a password</label>
            </div>

            <button type="submit" class="opal-claim-btn" id="opalClaimBtn">
              <span class="opal-btn-text">Create my account</span>
              <span class="opal-btn-loader"></span>
            </button>

            <div class="opal-trust-zone">
              <div class="opal-trust-badges">
                <span class="opal-badge">
                  <i class="fas fa-lock"></i> No bank login required
                </span>
                <span class="opal-badge">
                  <i class="fas fa-shield-halved"></i> Secured by Paystack
                </span>
                <span class="opal-price-badge">Free to start</span>
              </div>
            </div>
          </form>
        </div>

        <!-- Stage 2: Success -->
        <div class="opal-modal-stage opal-success-stage hidden" id="opalSuccessStage">
          <div class="opal-success-icon">
            <div class="opal-success-check-large"></div>
          </div>

          <h2 class="opal-success-title">
            <span class="opal-success-username" id="successUsername">@yourname</span> is reserved.
          </h2>

          <div class="opal-link-card">
            <span class="opal-preview-domain">payla.ng/</span>
            <span class="opal-preview-username" id="successLink"></span>
          </div>

          <p class="opal-success-message" id="successMessage">
            We've sent an activation link to <strong id="successEmailDisplay"></strong>.
            <br>Confirm it to activate your account.
          </p>

          <div class="opal-success-actions">
            <button class="opal-resend-link" id="opalResendBtn">
              Resend activation link
            </button>
          </div>

          <div class="opal-verification-status hidden" id="verificationStatus">
            <div class="opal-status-spinner"></div>
            <span>Waiting for verification…</span>
          </div>
        </div>
      </div>
    `;

    document.body.appendChild(this.overlay);
    this.modal = this.overlay.querySelector(".opal-modal");
  }

  bindEvents() {
    const closeBtn = document.getElementById("opalModalClose");
    closeBtn?.addEventListener("click", () => this.close());

    this.overlay.addEventListener("click", (e) => {
      if (e.target === this.overlay) this.close();
    });

    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && this.overlay.classList.contains("open")) {
        this.close();
      }
    });

    const usernameInput = document.getElementById("opalUsername");
    usernameInput?.addEventListener("input", (e) => this.handleUsernameInput(e));

    const form = document.getElementById("opalClaimForm");
    form?.addEventListener("submit", (e) => this.handleSubmit(e));

    document.getElementById("opalOpenEmailBtn")?.addEventListener("click", () => this.openEmailApp());
    document.getElementById("opalResendBtn")?.addEventListener("click", () => this.resendActivation());

    /* Landing page can open with a username via event */
    document.addEventListener("payla:open-claim", (e) => {
      this.openedFrom = e.detail?.source || "landing";
      this.open(e.detail?.username || null);
    });
  }

  /* ============================================================
     USERNAME VALIDATION
     ============================================================ */

  async handleUsernameInput(e) {
    const input = e.target;
    const username = input.value.trim().toLowerCase();
    const statusDiv = document.getElementById("opalUsernameStatus");
    const field = document.getElementById("opalUsernameField");
    const feedback = document.getElementById("opalFeedback");

    if (this.usernameCheckTimeout) clearTimeout(this.usernameCheckTimeout);

    statusDiv.classList.remove("success", "loading", "error");
    field.classList.remove("error");
    feedback.classList.remove("show", "error");
    this.isUsernameAvailable = false;

    if (username.length < 3) {
      if (username.length > 0) {
        feedback.innerHTML = `<i class="fas fa-info-circle"></i><span>At least 3 characters.</span>`;
        feedback.classList.add("show", "error");
      }
      return;
    }

    const validPattern = /^[a-zA-Z0-9_-]+$/;
    if (!validPattern.test(username)) {
      feedback.innerHTML = `<i class="fas fa-exclamation-circle"></i><span>Letters, numbers, hyphens and underscores only.</span>`;
      feedback.classList.add("show", "error");
      field.classList.add("error");
      return;
    }

    statusDiv.classList.add("loading");
    trackUsernameCheckStarted(username);

    this.usernameCheckTimeout = setTimeout(async () => {
      try {
        const res = await fetch(
          `${BACKEND_BASE}/api/onboarding/validate-username?username=${encodeURIComponent(username)}`
        );
        const data = await res.json();
        statusDiv.classList.remove("loading");

        if (data.available) {
          statusDiv.classList.add("success");
          feedback.innerHTML = `<span>${username} is available.</span>`;
          feedback.classList.add("show");
          this.isUsernameAvailable = true;
          this.usernameValue = username;
          trackUsernameCheckResult(username, true);
        } else {
          statusDiv.classList.add("error");
          feedback.innerHTML = `<span>@${username} is already taken.</span>`;
          feedback.classList.add("show", "error");
          field.classList.add("error");
          this.isUsernameAvailable = false;
          trackUsernameCheckResult(username, false);
        }
      } catch (err) {
        console.error("Username check failed:", err);
        statusDiv.classList.remove("loading");
        statusDiv.classList.add("error");
        feedback.innerHTML = `<span>Couldn't check availability. Try again.</span>`;
        feedback.classList.add("show", "error");
        trackUsernameCheckFailed("network");
      }
    }, 500);
  }

  /* ============================================================
     SUBMIT
     ============================================================ */

  async handleSubmit(e) {
    e.preventDefault();

    const username = document.getElementById("opalUsername").value.trim().toLowerCase();
    const email = document.getElementById("opalEmail").value.trim();
    const password = document.getElementById("opalPassword").value;
    const claimBtn = document.getElementById("opalClaimBtn");

    if (!this.isUsernameAvailable || username !== this.usernameValue) {
      this.showToast("Please choose an available username first.", "error");
      return;
    }
    if (!this.validateEmail(email)) {
      this.showToast("Please enter a valid email.", "error");
      return;
    }
    if (password.length < 8) {
      this.showToast("Password must be at least 8 characters.", "error");
      return;
    }

    claimBtn.classList.add("loading");
    claimBtn.disabled = true;

    try {
      const res = await fetch(`${BACKEND_BASE}/api/founding/signup`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, email, password }),
      });
      const data = await res.json();

      if (res.ok) {
        this.userEmail = email;
        this.usernameValue = username;

        document.getElementById("successEmailDisplay").textContent = email;
        document.getElementById("successUsername").textContent = `@${username}`;
        document.getElementById("successLink").textContent = `@${username}`;

        localStorage.setItem(
          "pendingFoundingUser",
          JSON.stringify({ username, email, timestamp: new Date().toISOString() })
        );

        this.startVerificationPolling(email);
        this.transitionToSuccess();
      } else {
        let errorMessage = "Signup failed. Please try again.";

        if (typeof data.detail === "object" && data.detail?.message) errorMessage = data.detail.message;
        else if (typeof data.detail === "string") errorMessage = data.detail;
        else if (data.detail?.error) errorMessage = data.detail.error;
        else if (data.message) errorMessage = data.message;
        else if (data.error) errorMessage = data.error;

        if (errorMessage.includes("username_taken") || errorMessage.includes("already taken")) {
          errorMessage = `@${username} is already taken. Please choose another.`;
        } else if (errorMessage.includes("email_exists") || errorMessage.includes("already registered")) {
          errorMessage = "This email is already registered. Please sign in instead.";
        }

        this.showToast(errorMessage, "error");
        throw new Error(errorMessage);
      }
    } catch (err) {
      console.error("Signup error:", err);
      if (
        !err.message.includes("already taken") &&
        !err.message.includes("already registered")
      ) {
        this.showToast(err.message || "Something went wrong. Please try again.", "error");
      }
    } finally {
      claimBtn.classList.remove("loading");
      claimBtn.disabled = false;
    }
  }

  /* ============================================================
     VERIFICATION POLLING
     ============================================================ */

  startVerificationPolling(email) {
    const statusEl = document.getElementById("verificationStatus");
    statusEl?.classList.remove("hidden");

    this.verificationPolling = setInterval(async () => {
      try {
        const res = await fetch(
          `${BACKEND_BASE}/api/founding/status/${encodeURIComponent(email)}`
        );
        const data = await res.json();

        if (data.verified && data.founding_member) {
          clearInterval(this.verificationPolling);
          this.verificationPolling = null;

          statusEl?.classList.add("hidden");
          trackModalVerificationConfirmed();
          this.showToast("Email verified. Your account is active.", "success");

          const successMessage = document.getElementById("successMessage");
          if (successMessage) {
            successMessage.innerHTML = `
              Your email is verified. You can now
              <a href="/entry" style="color: var(--rose-gold); text-decoration: underline;">
                continue to your account
              </a>.
            `;
          }

          const emailBtn = document.getElementById("opalOpenEmailBtn");
          if (emailBtn) {
            emailBtn.innerHTML = `<i class="fas fa-arrow-right"></i> Continue`;
            emailBtn.onclick = () => {
              window.location.href = "/entry";
            };
          }

          setTimeout(() => {
            window.location.href = "/entry";
          }, 3000);
        }
      } catch (err) {
        console.error("Polling error:", err);
      }
    }, 3000);
  }

  /* ============================================================
     TRANSITIONS
     ============================================================ */

  transitionToSuccess() {
    const claimStage = document.getElementById("opalClaimStage");
    const successStage = document.getElementById("opalSuccessStage");

    claimStage.style.animation = "slideOutLeft 0.4s cubic-bezier(0.16, 1, 0.3, 1) forwards";

    setTimeout(() => {
      claimStage.classList.add("hidden");
      claimStage.style.animation = "";

      successStage.classList.remove("hidden");
      successStage.style.animation =
        "slideInRight 0.4s cubic-bezier(0.16, 1, 0.3, 1) forwards";

      this.currentStage = "success";
      trackModalSuccessView(this.usernameValue);
    }, 380);
  }

  /* ============================================================
     EMAIL APP + RESEND
     ============================================================ */

  openEmailApp() {
    const email = this.userEmail;
    const provider = this.getEmailProvider(email);

    if (provider) window.open(provider, "_blank");
    else window.location.href = `mailto:${email}`;

    trackModalEmailAppOpened();
  }

  getEmailProvider(email) {
    const domain = email.split("@")[1]?.toLowerCase();
    const providers = {
      "gmail.com": "https://mail.google.com",
      "yahoo.com": "https://mail.yahoo.com",
      "outlook.com": "https://outlook.live.com",
      "hotmail.com": "https://outlook.live.com",
      "protonmail.com": "https://mail.protonmail.com",
      "icloud.com": "https://www.icloud.com/mail",
    };
    return providers[domain] || null;
  }

  async resendActivation() {
    const resendBtn = document.getElementById("opalResendBtn");
    const originalText = resendBtn.textContent;

    resendBtn.disabled = true;
    resendBtn.textContent = "Sending…";

    try {
      const pendingUser = JSON.parse(localStorage.getItem("pendingFoundingUser"));
      if (!pendingUser) throw new Error("No pending user found");

      const res = await fetch(`${BACKEND_BASE}/api/founding/resend-verification`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: pendingUser.email }),
      });

      if (res.ok) {
        this.showToast("Verification email resent.", "success");
        trackModalVerificationResent();
      } else {
        const data = await res.json();
        throw new Error(data.detail || "Failed to resend");
      }
    } catch (err) {
      console.error("Resend error:", err);
      this.showToast("Failed to resend. Please try again.", "error");
    } finally {
      resendBtn.disabled = false;
      resendBtn.textContent = originalText;
    }
  }

  /* ============================================================
     HELPERS
     ============================================================ */

  validateEmail(email) {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
  }

  showToast(message, type = "success") {
    const toast = document.createElement("div");
    toast.className = `toast ${type}`;
    toast.innerHTML = `
      <i class="fas fa-${type === "success" ? "check-circle" : "exclamation-circle"}"></i>
      <span>${message}</span>
    `;
    document.body.appendChild(toast);

    setTimeout(() => toast.classList.add("show"), 10);
    setTimeout(() => {
      toast.classList.remove("show");
      setTimeout(() => toast.remove(), 400);
    }, 4000);
  }

  /* ============================================================
     OPEN / CLOSE
     ============================================================ */

  open(prefilledUsername = null) {
    this.overlay.classList.add("open");
    document.body.style.overflow = "hidden";

    if (this.verificationPolling) {
      clearInterval(this.verificationPolling);
      this.verificationPolling = null;
    }

    if (this.currentStage === "success") {
      const claimStage = document.getElementById("opalClaimStage");
      const successStage = document.getElementById("opalSuccessStage");
      const statusEl = document.getElementById("verificationStatus");

      claimStage.classList.remove("hidden");
      successStage.classList.add("hidden");
      statusEl?.classList.add("hidden");
      this.currentStage = "claim";

      document.getElementById("opalClaimForm").reset();
      document.getElementById("opalUsernameStatus").classList.remove("success", "loading", "error");
      document.getElementById("opalFeedback").classList.remove("show", "error");
    }

    if (prefilledUsername) {
      const usernameInput = document.getElementById("opalUsername");
      const statusDiv = document.getElementById("opalUsernameStatus");
      const feedback = document.getElementById("opalFeedback");

      usernameInput.value = prefilledUsername;
      usernameInput.dispatchEvent(new Event("input", { bubbles: true }));

      /* Optimistically mark as valid — the hero already validated it */
      setTimeout(() => {
        statusDiv.classList.add("success");
        statusDiv.classList.remove("loading", "error");
        feedback.innerHTML = `<span>${prefilledUsername} is available.</span>`;
        feedback.classList.add("show");
        this.isUsernameAvailable = true;
        this.usernameValue = prefilledUsername;
      }, 50);
    }

    trackLockModalOpened({
      source: this.openedFrom,
      prefilled: Boolean(prefilledUsername),
    });

    setTimeout(() => {
      const target = prefilledUsername
        ? document.getElementById("opalEmail")
        : document.getElementById("opalUsername");
      target?.focus();
    }, 400);
  }

  close() {
    this.overlay.classList.remove("open");
    document.body.style.overflow = "";

    if (this.verificationPolling) {
      clearInterval(this.verificationPolling);
      this.verificationPolling = null;
    }

    trackLockModalClosed();
  }
}

/* ============================================================
   BOOT
   ============================================================ */

document.addEventListener("DOMContentLoaded", () => {
  const modal = new PaylaClaimModal();

  /* Expose for payla.js to call open(username) */
  window.PaylaClaimModal = modal;

  /* Fallback: legacy button ids if any remain in HTML */
  const legacyButtons = document.querySelectorAll("#join-waitlist, #sticky-free");
  legacyButtons.forEach((btn) =>
    btn.addEventListener("click", (e) => {
      e.preventDefault();
      modal.open();
    })
  );
});

export default PaylaClaimModal;