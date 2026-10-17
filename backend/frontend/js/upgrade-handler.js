// utils/upgrade-handler.js
// Centralized upgrade detection and UI handling.
//
// Three exports:
//   authFetch(url, options)                       — token + 401/403 handling
//   showUpgradeRequired({ feature, source, silverHistory })
//   showUpgradeToast(message, type)
//
// No cooldown: every modal is user-initiated (a click on a Silver action).


/* ──────────────────────────────────────────────
   FEATURE SPEC
────────────────────────────────────────────── */

const FEATURE_MAP = {
  receipts: {
    label: 'receipts',
    title: "Receipts are part of Silver",
    description: "Generate a formal PDF receipt for every payment.",
    benefits: [
      "PDF receipts generated automatically after payment",
      "Your logo and brand colours on every receipt",
      "A permanent record of every transaction"
    ]
  },
  invoices: {
    label: 'invoices',
    title: "Invoices are part of Silver",
    description: "Send branded invoices clients can pay directly.",
    benefits: [
      "Professional invoices clients can pay directly",
      "Set up payment reminders for every invoice",
      "Invoices close automatically when payment arrives"
    ]
  },
  reminders: {
    label: 'reminders',
    title: "Reminders are part of Silver",
    description: "Let Layla follow up so you don't have to.",
    benefits: [
      "Automated follow-ups via WhatsApp, SMS, and email",
      "Customise reminder messages to suit your business",
      "Layla follows up, so you don't have to"
    ]
  },
  analytics: {
    label: 'analytics',
    title: "Analytics are part of Silver",
    description: "See how your payments and your link are performing.",
    benefits: [
      "Track payments and Paylink performance",
      "See page views, transfer clicks, and payment success rates",
      "Review your performance over the last 7 days"
    ]
  },
  branding: {
    label: 'custom branding',
    title: "Custom branding is part of Silver",
    description: "Give clients a consistent, branded payment experience.",
    benefits: [
      "Add your logo and brand colours to your documents",
      "Customise the look of your invoices and receipts",
      "Give clients a consistent, branded payment experience"
    ]
  }
};

const DEFAULT_FEATURE = {
  label: 'Silver',
  title: "Payla Silver",
  description: "Everything you need to run your payments end to end.",
  benefits: [
    "Professional invoices clients can pay directly",
    "Automated reminders from Layla",
    "Payment tracking and paylink analytics",
    "PDF receipts and custom branding",
    "Invoices close automatically when payment arrives"
  ]
};


/* ──────────────────────────────────────────────
   HELPERS
────────────────────────────────────────────── */

function resolveFeature(key) {
  if (!key) return DEFAULT_FEATURE;
  return FEATURE_MAP[key] || DEFAULT_FEATURE;
}

function inferFeatureFromUrl(url) {
  const value = String(url || "").toLowerCase();

  if (value.includes("/receipt")) return "receipts";
  if (value.includes("/reminders") || value.includes("/reminder")) return "reminders";
  if (value.includes("/dashboard/analytics") || value.includes("/analytics")) return "analytics";
  if (value.includes("/invoices") || value.includes("/invoice")) return "invoices";
  if (value.includes("/branding") || value.includes("/invoice-colors")) return "branding";

  return null;
}

/**
 * Adapt the modal's title and CTA when the user has a Silver history
 * that isn't "never". The benefit list and description stay the same —
 * a lapsed user doesn't need to be re-sold, just reminded.
 */
function personalizeForHistory(spec, silverHistory) {
  const featureLabel = spec.label || 'Silver';

  if (silverHistory === 'expired') {
    return {
      ...spec,
      title: `Renew Silver to keep ${featureLabel}`,
      ctaLabel: 'Renew Silver'
    };
  }

  if (silverHistory === 'in_grace') {
    return {
      ...spec,
      title: `Update billing to keep ${featureLabel}`,
      ctaLabel: 'Update billing'
    };
  }

  // 'cancelled', 'active', 'never', undefined → default copy.
  return {
    ...spec,
    ctaLabel: "See what's included"
  };
}


/* ──────────────────────────────────────────────
   TOAST
────────────────────────────────────────────── */

function normalizeMessage(input, fallback) {
  if (!input) return fallback;
  if (typeof input === "string") return input;
  if (typeof input === "object") {
    return input.message || input.detail || fallback;
  }
  return fallback;
}

function showUpgradeToast(message, type = "info") {
  const safeMessage = normalizeMessage(message, "Something went wrong");

  const toast =
    document.getElementById("toast") ||
    document.getElementById("draft-toast");

  if (!toast) {
    console.warn("[toast fallback]", safeMessage);
    return;
  }

  const messageEl =
    toast.querySelector("#toastMessage") ||
    toast.querySelector("#toast-message") ||
    toast.querySelector(".toast-message") ||
    toast.querySelector("span");

  if (messageEl) {
    messageEl.textContent = safeMessage;
  } else {
    toast.textContent = safeMessage;
  }

  toast.classList.remove("error", "warning", "success");
  toast.classList.add("show");
  if (type !== "info") toast.classList.add(type);

  const duration = type === "error" ? 5000 : 4000;

  window.clearTimeout(toast._hideTimer);
  toast._hideTimer = window.setTimeout(() => {
    toast.classList.remove("show", "error", "warning", "success");
  }, duration);
}


/* ──────────────────────────────────────────────
   UPGRADE MODAL
────────────────────────────────────────────── */

function buildUpgradeModal(spec) {
  const modal = document.createElement("div");
  modal.id = "upgrade-required-modal";
  modal.className = "modal-overlay upgrade-modal";

  const benefitsHtml = spec.benefits
    .map(
      (item) => `
        <li>
          <i class="fas fa-check" aria-hidden="true"></i>
          <span>${item}</span>
        </li>`
    )
    .join("");

  modal.innerHTML = `
    <div class="upgrade-card" role="dialog" aria-modal="true" aria-labelledby="upgrade-title">
      <button class="upgrade-close" type="button" aria-label="Close" id="upgrade-modal-close">
        <i class="fas fa-times" aria-hidden="true"></i>
      </button>

      <div class="upgrade-icon" aria-hidden="true">
        <i class="fas fa-crown"></i>
      </div>

      <h2 class="upgrade-title" id="upgrade-title">${spec.title}</h2>
      <p class="upgrade-description">${spec.description}</p>

      <ul class="upgrade-benefits">
        ${benefitsHtml}
      </ul>

      <div class="upgrade-actions">
        <button class="upgrade-primary" type="button" id="upgrade-modal-cta">
          ${spec.ctaLabel || "See what's included"}
        </button>
        <button class="upgrade-secondary" type="button" id="upgrade-modal-cancel">
          Not now
        </button>
      </div>
    </div>
  `;

  return modal;
}

function showUpgradeRequired({ feature, source, silverHistory } = {}) {
  const baseSpec = resolveFeature(feature);
  const spec = personalizeForHistory(baseSpec, silverHistory);

  const existing = document.getElementById("upgrade-required-modal");
  if (existing) existing.remove();

  const modal = buildUpgradeModal(spec);
  document.body.appendChild(modal);

  const close = () => {
    modal.classList.remove("open");
    window.setTimeout(() => modal.remove(), 260);
  };

  const goToSubscription = () => {
    window.location.href = "/subscription";
  };

  modal.querySelector("#upgrade-modal-close").addEventListener("click", close);
  modal.querySelector("#upgrade-modal-cancel").addEventListener("click", close);
  modal.querySelector("#upgrade-modal-cta").addEventListener("click", goToSubscription);

  modal.addEventListener("click", (event) => {
    if (event.target === modal) close();
  });

  const onKey = (event) => {
    if (event.key === "Escape") {
      close();
      document.removeEventListener("keydown", onKey);
    }
  };
  document.addEventListener("keydown", onKey);

  requestAnimationFrame(() => modal.classList.add("open"));
}


/* ──────────────────────────────────────────────
   AUTH FETCH
────────────────────────────────────────────── */

export async function authFetch(url, options = {}) {
  const token = localStorage.getItem("idToken");

  if (!token) {
    showUpgradeToast("Please log in to continue", "error");
    window.location.href = "/entry";
    throw new Error("Unauthorized");
  }

  const { feature: featureHint, silverHistory: historyHint, ...fetchOptions } = options;

  const headers = {
    Authorization: `Bearer ${token}`,
    ...(fetchOptions.headers || {})
  };

  const res = await fetch(url, { ...fetchOptions, headers });

  if (res.status === 401) {
    showUpgradeToast("Session expired. Please log in again", "error");
    window.location.href = "/entry";
    throw new Error("Unauthorized");
  }

  if (res.status === 403) {
    let payload = null;
    try {
      payload = await res.clone().json();
    } catch {
      // Non-JSON 403 — treat as generic forbidden.
    }

    const detail =
      payload && typeof payload === "object" && payload.detail
        ? payload.detail
        : null;

    if (detail && detail.error === "subscription_required") {
      const feature =
        featureHint ||
        inferFeatureFromUrl(url) ||
        null;

      showUpgradeRequired({
        feature,
        source: "server",
        silverHistory: historyHint
      });
      throw new Error("Upgrade Required");
    }

    showUpgradeToast(
      normalizeMessage(detail, "This feature is not available on your plan"),
      "warning"
    );
    throw new Error("Forbidden");
  }

  return res;
}


/* ──────────────────────────────────────────────
   EXPORTS
────────────────────────────────────────────── */

export { showUpgradeToast, showUpgradeRequired, FEATURE_MAP };