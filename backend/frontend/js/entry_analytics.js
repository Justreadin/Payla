// entry_analytics.js
import { track } from "./web_analytics.js";

/* ──────────────────────────────
   PAGE VIEW
────────────────────────────── */
export function trackEntryPageView() {
  track("entry_page_view", {
    page: "entry",
    referrer: document.referrer || "direct"
  });
}

/* ──────────────────────────────
   EMAIL STEP EVENTS
────────────────────────────── */
export function trackEmailSubmitted(email) {
  track("email_submitted", {
    email_domain: email.split("@")[1],
    action: "continue"
  });
}

export function trackEmailCheckResult(exists) {
  track("email_check_result", {
    exists: exists ? "true" : "false"
  });
}

/* ──────────────────────────────
   LOGIN STEP EVENTS
────────────────────────────── */
export function trackLoginAttempt(email) {
  track("login_attempt", {
    email_domain: email.split("@")[1]
  });
}

export function trackLoginSuccess(email, userId) {
  track("login_success", {
    email_domain: email.split("@")[1],
    user_id: userId
  });
}

export function trackLoginFailed(reason) {
  track("login_failed", { reason });
}

/* ──────────────────────────────
   SIGNUP STEP EVENTS
────────────────────────────── */
export function trackSignupAttempt(email) {
  track("signup_attempt", {
    email_domain: email.split("@")[1]
  });
}

export function trackSignupSuccess(email, userId) {
  track("signup_success", {
    email_domain: email.split("@")[1],
    user_id: userId
  });
}

export function trackSignupFailed(reason) {
  track("signup_failed", { reason });
}

/* ──────────────────────────────
   VERIFICATION EVENTS
────────────────────────────── */
export function trackVerificationSent(email) {
  track("verification_sent", {
    email_domain: email.split("@")[1]
  });
}

export function trackVerificationResent(email) {
  track("verification_resent", {
    email_domain: email.split("@")[1]
  });
}

export function trackVerificationCompleted(email) {
  track("verification_completed", {
    email_domain: email.split("@")[1]
  });
}

/* ──────────────────────────────
   NAVIGATION EVENTS
────────────────────────────── */
export function trackBackToEmail() {
  track("back_to_email_clicked");
}

export function trackGoToOnboarding() {
  track("goto_onboarding_clicked");
}

export function trackPasswordToggle(action) {
  track("password_toggle", { action });
}