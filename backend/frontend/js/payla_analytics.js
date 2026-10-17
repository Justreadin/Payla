// js/payla_analytics.js
import { track } from "./web_analytics.js";

/* ──────────────────────────────
   PAGE & SESSION
────────────────────────────── */

export function trackLandingView() {
  track("landing_view", {
    page: "home",
    source: document.referrer || "direct",
  });
}

/* ──────────────────────────────
   NAV
────────────────────────────── */

export function trackNavOpened(source) {
  track("nav_opened", { source });
}

export function trackNavClosed(source) {
  track("nav_closed", { source });
}

/* ──────────────────────────────
   HERO USERNAME FIELD
────────────────────────────── */

export function trackUsernameCheckStarted(username) {
  track("username_check_started", {
    length: username.length,
  });
}

export function trackUsernameCheckResult(username, available) {
  track("username_check_result", {
    length: username.length,
    available,
  });
}

export function trackUsernameCheckFailed(reason) {
  track("username_check_failed", { reason });
}

/* ──────────────────────────────
   CTA EVENTS
────────────────────────────── */

export function trackContinueClick(location) {
  track("cta_continue_clicked", { location });
}

export function trackLockYearClick(location) {
  track("cta_lock_year_clicked", { location });
}

/* Claim triggers — hero, nav, product, pricing, final CTA */
export function trackClaimOpen(source, { hasUsername = false, usernameLength = 0 } = {}) {
  track("claim_open", {
    source,
    has_username: hasUsername,
    username_length: usernameLength,
  });
}

/* ──────────────────────────────
   MODAL
────────────────────────────── */

export function trackLockModalOpened({ source = "unknown", prefilled = false } = {}) {
  track("lock_modal_opened", { source, prefilled });
}

export function trackLockModalClosed() {
  track("lock_modal_closed");
}

export function trackModalSuccessView(username) {
  track("modal_success_view", {
    username_length: username.length,
  });
}

export function trackModalEmailAppOpened() {
  track("modal_email_app_opened");
}

export function trackModalVerificationResent() {
  track("modal_verification_resent");
}

export function trackModalVerificationConfirmed() {
  track("modal_verification_confirmed");
}

/* ──────────────────────────────
   PRICING
────────────────────────────── */

export function trackPricingToggle(mode) {
  track("pricing_toggle", { mode });
}

/* ──────────────────────────────
   FAQ
────────────────────────────── */

export function trackFaqOpen(question) {
  track("faq_open", { question });
}

/* ──────────────────────────────
   PAYMENT FUNNEL
────────────────────────────── */

export function trackPresellFormSubmitted(email) {
  track("presell_form_submitted", {
    email_domain: email.split("@")[1],
  });
}

export function trackPaymentIntent(reference) {
  track("payment_intent", { reference });
}

export function trackPaymentSuccess(reference, amount) {
  track("purchase", {
    transaction_id: reference,
    value: amount / 100,
    currency: "NGN",
  });
}

export function trackPaymentFailed(reason) {
  track("payment_failed", { reason });
}