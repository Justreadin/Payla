// onboarding_analytics.js
import { track } from "./web_analytics.js";

/* ──────────────────────────────
   PAGE VIEW
────────────────────────────── */
export function trackOnboardingPageView() {
  track("onboarding_page_view", {
    page: "onboarding",
    step: getCurrentStep()
  });
}

function getCurrentStep() {
  // Get current step from the DOM or state
  const activeStep = document.querySelector('.step-content.active');
  if (activeStep) {
    return activeStep.id || "unknown";
  }
  return "unknown";
}

/* ──────────────────────────────
   STEP NAVIGATION
────────────────────────────── */
export function trackStepViewed(stepNumber, stepName) {
  track("onboarding_step_view", {
    step_number: stepNumber,
    step_name: stepName
  });
}

export function trackStepCompleted(stepNumber, stepName) {
  track("onboarding_step_completed", {
    step_number: stepNumber,
    step_name: stepName
  });
}

export function trackNextClicked(fromStep, toStep) {
  track("onboarding_next_clicked", {
    from_step: fromStep,
    to_step: toStep
  });
}

export function trackBackClicked(fromStep, toStep) {
  track("onboarding_back_clicked", {
    from_step: fromStep,
    to_step: toStep
  });
}

/* ──────────────────────────────
   FORM INTERACTIONS
────────────────────────────── */
export function trackUsernameCheck(username, available) {
  track("username_check", {
    username_length: username.length,
    available: available ? "true" : "false"
  });
}

export function trackBusinessNameEntered(length) {
  track("business_name_entered", {
    character_count: length
  });
}

export function trackBankSelected(bankCode) {
  track("bank_selected", {
    bank_code: bankCode
  });
}

export function trackAccountVerified(verified, bankCode) {
  track("account_verified", {
    verified: verified ? "true" : "false",
    bank_code: bankCode
  });
}

/* ──────────────────────────────
   PLAN SELECTION
────────────────────────────── */
export function trackPlanSelected(plan) {
  track("plan_selected", {
    plan_type: plan
  });
}

/* ──────────────────────────────
   COMPLETION
────────────────────────────── */
export function trackOnboardingStarted() {
  track("onboarding_started");
}

export function trackOnboardingCompleted(username, plan) {
  track("onboarding_completed", {
    username_length: username.length,
    plan: plan
  });
}

export function trackOnboardingFailed(reason) {
  track("onboarding_failed", { reason });
}

/* ──────────────────────────────
   PREVIEW INTERACTIONS
────────────────────────────── */
export function trackPreviewViewed() {
  track("preview_viewed");
}