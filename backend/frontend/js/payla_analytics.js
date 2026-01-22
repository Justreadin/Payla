// payla.analytics.js
import { track } from "./web_analytics.js";

/* ──────────────────────────────
   PAGE & SESSION
────────────────────────────── */

export function trackLandingView() {
  track("landing_view", {
    page: "home",
    source: document.referrer || "direct"
  });
}

/* ──────────────────────────────
   CTA EVENTS
────────────────────────────── */

export function trackContinueClick(location) {
  track("cta_continue_clicked", {
    location
  });
}

export function trackLockYearClick(location) {
  track("cta_lock_year_clicked", {
    location
  });
}

/* ──────────────────────────────
   MODAL
────────────────────────────── */

export function trackLockModalOpened() {
  track("lock_modal_opened");
}

export function trackLockModalClosed() {
  track("lock_modal_closed");
}

/* ──────────────────────────────
   PAYMENT FUNNEL
────────────────────────────── */

export function trackPresellFormSubmitted(email) {
  track("presell_form_submitted", {
    email_domain: email.split("@")[1]
  });
}

export function trackPaymentIntent(reference) {
  track("payment_intent", {
    reference
  });
}

export function trackPaymentSuccess(reference, amount) {
  track("purchase", {
    transaction_id: reference,
    value: amount / 100,
    currency: "NGN"
  });
}

export function trackPaymentFailed(reason) {
  track("payment_failed", { reason });
}
