// utils/upgrade-handler.js
// Centralized upgrade detection, throttling, and UI handling

import { BACKEND_BASE } from './config.js';

const UPGRADE_COOLDOWN_MS = 24 * 60 * 60 * 1000;

/* ──────────────────────────────────────────────
   Throttle helpers (per user, per required plan)
────────────────────────────────────────────── */

function getUserId() {
  return localStorage.getItem('user_id') || 'anon';
}

function getUpgradeKey(requiredPlan) {
  return `upgrade_prompt_${getUserId()}_${requiredPlan}`;
}

function canShowUpgrade(requiredPlan = 'silver') {
  const lastShown = localStorage.getItem(getUpgradeKey(requiredPlan));
  if (!lastShown) return true;

  return Date.now() - new Date(lastShown).getTime() > UPGRADE_COOLDOWN_MS;
}

function markUpgradeShown(requiredPlan = 'silver') {
  localStorage.setItem(
    getUpgradeKey(requiredPlan),
    new Date().toISOString()
  );
}

/* ──────────────────────────────────────────────
   Safe message normalizer (kills [object Object])
────────────────────────────────────────────── */

function normalizeMessage(input, fallback) {
  if (!input) return fallback;
  if (typeof input === 'string') return input;
  if (typeof input === 'object') {
    return input.message || input.detail || fallback;
  }
  return fallback;
}

/* ──────────────────────────────────────────────
   AUTH FETCH (single authority)
────────────────────────────────────────────── */

export async function authFetch(url, options = {}) {
  const token = localStorage.getItem('idToken');

  if (!token) {
    showUpgradeToast('Please log in to continue', 'error');
    window.location.href = '/entry';
    throw new Error('Unauthorized');
  }

  const headers = {
    Authorization: `Bearer ${token}`,
    ...(options.headers || {})
  };

  const res = await fetch(url, { ...options, headers });

  // 🔐 401 — session expired
  if (res.status === 401) {
    showUpgradeToast('Session expired. Please log in again', 'error');
    window.location.href = '/entry';
    throw new Error('Unauthorized');
  }

  // 🚧 403 — upgrade required
  if (res.status === 403) {
    let data = null;
    try {
      data = await res.clone().json();
    } catch {}

    if (data?.detail && typeof data.detail === 'object') {
      handleUpgradeRequired(data.detail);
      throw new Error('Upgrade Required');
    }

    showUpgradeToast('This feature requires a paid plan', 'warning');
    throw new Error('Forbidden');
  }

  return res;
}

/* ──────────────────────────────────────────────
   Upgrade handler (throttled + normalized)
────────────────────────────────────────────── */

function handleUpgradeRequired(detail) {
  const requiredPlan = detail.required_plan || detail.upgrade_to || 'silver';

  if (!canShowUpgrade(requiredPlan)) {
    return; // silently block spam
  }

  const message = normalizeMessage(
    detail.message,
    'This feature requires a paid plan'
  );

  showUpgradeToast(message, 'warning');

  setTimeout(() => {
    showUpgradeModal({
      title: 'Upgrade Required',
      message,
      currentPlan: detail.current_plan || 'free',
      upgradeTo: requiredPlan,
      upgradeUrl: detail.upgrade_url || '/subscription',
      trialExpired: !!detail.trial_expired,
      subscriptionExpired: !!detail.subscription_expired
    });
  }, 400);

  markUpgradeShown(requiredPlan);
}

/* ──────────────────────────────────────────────
   Toast UI (safe + defensive)
────────────────────────────────────────────── */

function showUpgradeToast(message, type = 'info') {
  const safeMessage = normalizeMessage(message, 'Something went wrong');

  const toast =
    document.getElementById('toast') ||
    document.getElementById('draft-toast');

  if (!toast) {
    console.warn('[TOAST FALLBACK]', safeMessage);
    alert(safeMessage);
    return;
  }

  const messageEl =
    toast.querySelector('#toastMessage') ||
    toast.querySelector('#toast-message') ||
    toast.querySelector('.toast-message');

  if (messageEl) {
    messageEl.textContent = safeMessage;
  } else {
    toast.textContent = safeMessage;
  }

  toast.className = 'toast show';
  toast.classList.add(type);

  setTimeout(() => {
    toast.classList.remove('show', 'error', 'warning', 'success');
  }, 4500);
}

/* ──────────────────────────────────────────────
   Upgrade Modal
────────────────────────────────────────────── */

function showUpgradeModal(options) {
  const existing = document.getElementById('upgrade-required-modal');
  if (existing) existing.remove();

  const statusMessage = options.trialExpired
    ? 'Your trial has ended'
    : options.subscriptionExpired
    ? 'Your subscription expired'
    : 'Upgrade to unlock premium features';

  const modal = document.createElement('div');
  modal.id = 'upgrade-required-modal';
  modal.className = 'modal-overlay upgrade-modal';

 modal.innerHTML = `
    <div class="modal glass">
      <button class="modal-close" id="upgrade-modal-close">
        <i class="fas fa-times"></i>
      </button>
      
      <div class="upgrade-content">
        <div class="upgrade-icon">
          <i class="fas fa-crown"></i>
        </div>
        
        <h2 class="upgrade-title">${options.title}</h2>
        <p class="upgrade-message">${options.message}</p>
        
        <p class="upgrade-subtitle">${statusMessage}</p>

        
        <div class="modal-actions">
          <button class="btn-secondary" id="upgrade-modal-cancel">
            Later
          </button>
          <button class="btn-primary upgrade-cta" id="upgrade-modal-cta">
            <i class="fas fa-crown"></i>
            Upgrade Now
          </button>
        </div>
      </div>
    </div>
  `;

  document.body.appendChild(modal);

  const close = () => {
    modal.classList.remove('open');
    setTimeout(() => modal.remove(), 250);
  };

  modal.querySelector('.modal-close').onclick = close;
  modal.querySelector('.btn-secondary').onclick = close;
  modal.querySelector('.btn-primary').onclick = () => {
    window.location.href = options.upgradeUrl;
  };

  modal.onclick = e => {
    if (e.target === modal) close();
  };

  requestAnimationFrame(() => modal.classList.add('open'));
}

/* ──────────────────────────────────────────────
   Exports
────────────────────────────────────────────── */

export { showUpgradeToast, showUpgradeModal };
