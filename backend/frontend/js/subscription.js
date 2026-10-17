import { API_BASE } from './config.js';

const PLAN_KEYS = {
  monthly: 'silver_monthly',
  yearly: 'silver_yearly',
};

const DEFAULT_PRICES = {
  silver_monthly: 7500,
  silver_yearly: 75000,
};

class SubscriptionManager {
  constructor() {
    this.API_BASE = String(API_BASE || '').replace(/\/$/, '');
    this.status = null;
    this.plans = {};
    this.foundingOffer = {};
    this.cycle = 'monthly';
    this.confirmedPlan = null;
    this.busy = false;
    this.toastTimer = null;

    this.elements = {
      heroTitle: document.getElementById('hero-title'),
      heroSubtitle: document.getElementById('hero-subtitle'),
      heroUpgrade: document.getElementById('hero-upgrade'),
      statusNote: document.getElementById('subscription-status-note'),
      price: document.getElementById('silver-price'),
      period: document.getElementById('silver-period'),
      priceContext: document.getElementById('price-context'),
      foundingBanner: document.getElementById('founding-offer'),
      foundingTitle: document.getElementById('founding-title'),
      foundingDescription: document.getElementById('founding-description'),
      foundingRemaining: document.getElementById('founding-remaining'),
      foundingPriceNote: document.getElementById('founding-price-note'),
      upgrade: document.getElementById('silver-upgrade'),
      planCard: document.getElementById('silver-plan'),
      statusHint: document.getElementById('silver-status-hint'),
      manageSection: document.getElementById('manage-subscription'),
      manageSummary: document.getElementById('manage-summary'),
      toast: document.getElementById('subscription-toast'),
      confirmModal: document.getElementById('subscription-confirm-modal'),
      confirmTitle: document.getElementById('confirm-title'),
      confirmDescription: document.getElementById('confirm-description'),
      confirmCycle: document.getElementById('confirm-cycle'),
      confirmPrice: document.getElementById('confirm-price'),
      confirmPriceNote: document.getElementById('confirm-price-note'),
      confirmFoundingNote: document.getElementById('confirm-founding-note'),
      confirmCheckout: document.getElementById('confirm-checkout'),
      successModal: document.getElementById('subscription-success-modal'),
    };

    this.init();
  }

  async init() {
    if (!this.getAuthToken()) {
      window.location.assign('/entry');
      return;
    }

    this.bindEvents();

    try {
      await Promise.all([
        this.loadStatus(),
        this.loadPlans(),
      ]);

      this.render();
      await this.handleCheckoutReturn();
    } catch (error) {
      console.error('Subscription page initialization failed:', error);

      this.showToast(
        error.message ||
          'Could not load subscription details. Refresh to try again.',
        'error'
      );

      if (this.elements.upgrade) {
        this.elements.upgrade.disabled = true;
      }
    }
  }

  getAuthToken() {
    return localStorage.getItem('idToken') || '';
  }

  authHeaders() {
    return {
      Authorization: `Bearer ${this.getAuthToken()}`,
      'Content-Type': 'application/json',
    };
  }

  async request(path, options = {}) {
    const response = await fetch(`${this.API_BASE}${path}`, {
      ...options,
      headers: {
        ...this.authHeaders(),
        ...(options.headers || {}),
      },
    });

    let data = {};

    try {
      data = await response.json();
    } catch {
      data = {};
    }

    if (response.status === 401) {
      window.location.assign('/entry');
      throw new Error('Your session has expired. Please sign in again.');
    }

    if (!response.ok) {
      throw new Error(
        data.detail ||
        data.message ||
        `Request failed (${response.status})`
      );
    }

    return data;
  }

  async loadStatus() {
    this.status = await this.request('/subscription/status');
  }

  async loadPlans() {
    const response = await this.request('/subscription/plans');

    this.plans = response.plans || {};
    this.foundingOffer = response.founding_offer || {};
  }

  bindEvents() {
    document.getElementById('hero-upgrade')
      ?.addEventListener('click', () => {
        document.getElementById('pricing')
          ?.scrollIntoView({ behavior: 'smooth' });
      });

    document.getElementById('silver-upgrade')
      ?.addEventListener('click', () => this.openConfirmation());

    document.querySelectorAll('[data-cycle]').forEach((button) => {
      button.addEventListener('click', () => {
        this.cycle =
          button.dataset.cycle === 'yearly' ? 'yearly' : 'monthly';

        this.renderPrice();
        this.renderBillingToggle();
      });
    });

    document.getElementById('confirm-checkout')
      ?.addEventListener('click', () => this.startCheckout());

    document.getElementById('confirm-back')
      ?.addEventListener('click', () => this.closeConfirmation());

    document.getElementById('confirm-close')
      ?.addEventListener('click', () => this.closeConfirmation());

    this.elements.confirmModal?.addEventListener('click', (event) => {
      if (event.target === this.elements.confirmModal) {
        this.closeConfirmation();
      }
    });

    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') {
        this.closeConfirmation();
      }
    });

    document.getElementById('manage-billing')
      ?.addEventListener('click', () => this.openManageLink());

    document.getElementById('cancel-renewal')
      ?.addEventListener('click', () => this.cancelRenewal());

    document.getElementById('success-dashboard')
      ?.addEventListener('click', () => {
        window.location.assign('/dashboard');
      });
  }

  planKey() {
    return PLAN_KEYS[this.cycle] || PLAN_KEYS.monthly;
  }

  planData(cycle = this.cycle) {
    const key = PLAN_KEYS[cycle] || PLAN_KEYS.monthly;
    return this.plans[key] || {};
  }

  amountFor(cycle = this.cycle) {
    const key = PLAN_KEYS[cycle] || PLAN_KEYS.monthly;
    const plan = this.planData(cycle);

    const founder = this.isFoundingEligible();
    const status = this.status || {};

    if (founder) {
      const locked = cycle === 'yearly'
        ? status.founding_yearly_price_ngn
        : status.founding_monthly_price_ngn;

      if (this.isExistingFounder() && Number(locked) > 0) {
        return Number(locked);
      }

      const founderPrice =
        this.foundingOffer.prices?.[key] ??
        this.foundingOffer[
          cycle === 'yearly'
            ? 'yearly_price_ngn'
            : 'monthly_price_ngn'
        ];

      if (Number(founderPrice) > 0) {
        return Number(founderPrice);
      }
    }

    return Number(plan.amount_ngn ?? DEFAULT_PRICES[key]);
  }

  isExistingFounder() {
    return Boolean(
      this.status?.founding_member_ever ||
      this.status?.founding_price_locked ||
      this.foundingOffer?.is_existing_founder
    );
  }

  isFoundingEligible() {
    if (this.isExistingFounder()) {
      return true;
    }

    return Boolean(
      this.foundingOffer?.available_for_this_account ||
      this.foundingOffer?.reserved_for_this_account
    );
  }

  formatNaira(amount) {
    return `₦${Number(amount || 0).toLocaleString('en-NG', {
      maximumFractionDigits: 0,
    })}`;
  }

  render() {
    this.renderHero();
    this.renderPrice();
    this.renderBillingToggle();
    this.renderFoundingOffer();
    this.renderSubscriptionControls();
  }

  renderHero() {
    const status = this.status || {};

    const active = Boolean(status.active ?? status.is_active);
    const plan = String(status.plan || 'free').toLowerCase();
    const state = String(status.subscription_status || '').toLowerCase();

    // 1. Active Silver (with or without renewal off).
    if (active && plan === 'silver') {
      this.elements.heroTitle.textContent =
        state === 'non_renewing'
          ? 'Your Silver access is still yours.'
          : 'Payla Silver is active.';

      this.elements.heroSubtitle.textContent =
        state === 'non_renewing'
          ? 'Your subscription will not renew, but your paid access continues through the end of your current billing period.'
          : 'Your payment experience is ready. Keep your links, invoices, reminders and analytics working together.';

      this.elements.statusNote.textContent = this.billingEndLabel(status);
      this.elements.heroUpgrade.textContent = 'Manage Silver';

      this.elements.heroUpgrade.onclick = () => {
        this.elements.manageSection?.scrollIntoView({
          behavior: 'smooth',
        });
      };

      return;
    }

    // 2. Past due, still in grace.
    if (state === 'past_due' && status.in_grace_period) {
      this.elements.heroTitle.textContent =
        'Let’s get your Silver access back on track.';

      this.elements.heroSubtitle.textContent =
        'Your latest renewal needs attention. Update your payment to keep your Silver features available.';

      const days = Number(status.days_left_in_grace || 0);

      this.elements.statusNote.textContent = days > 0
        ? `Your access continues for ${days} more ${days === 1 ? 'day' : 'days'}. Update billing to keep Silver.`
        : 'Your renewal is past due. Update billing to keep Silver.';

      this.elements.heroUpgrade.textContent = 'Review Silver';

      this.elements.heroUpgrade.onclick = () => {
        document.getElementById('pricing')
          ?.scrollIntoView({ behavior: 'smooth' });
      };

      return;
    }

    // 3. Was Silver, is not now.
    const wasSilver = Boolean(
      status.last_subscription_payment_at ||
      status.founding_member_ever ||
      status.subscription_id
    );

    if (!active && wasSilver) {
      this.elements.heroTitle.textContent =
        'Your Silver subscription has ended.';

      this.elements.heroSubtitle.textContent =
        'Renew Silver to bring back invoices, receipts, reminders, and analytics. Your paylink and payments keep working on Free.';

      this.elements.statusNote.textContent = status.subscription_end
        ? `Ended ${this.formatDate(status.subscription_end)}.`
        : 'Your Silver access has lapsed.';

      this.elements.heroUpgrade.textContent = 'Renew Silver';

      this.elements.heroUpgrade.onclick = () => {
        document.getElementById('pricing')
          ?.scrollIntoView({ behavior: 'smooth' });
      };

      return;
    }

    // 4. Never subscribed — default marketing copy.
    this.elements.heroTitle.textContent =
      'Your work deserves a better way to get paid.';

    this.elements.heroSubtitle.textContent =
      'A considered payment experience for the people behind the work. Branded paylinks, polished invoices, timely reminders and clear analytics.';

    this.elements.statusNote.textContent = status.message || '';
    this.elements.heroUpgrade.textContent = 'Explore Silver';

    this.elements.heroUpgrade.onclick = () => {
      document.getElementById('pricing')
        ?.scrollIntoView({ behavior: 'smooth' });
    };
  }

  renderPrice() {
    const key = this.planKey();
    const amount = this.amountFor();

    this.elements.price.textContent =
      Number(amount).toLocaleString('en-NG', {
        maximumFractionDigits: 0,
      });

    this.elements.period.textContent =
      this.cycle === 'yearly' ? '/ year' : '/ month';

    if (this.isExistingFounder()) {
      this.elements.priceContext.textContent =
        'Your protected founding price. It remains available to your account on eligible renewals.';

      this.elements.foundingPriceNote.hidden = false;

      this.elements.foundingPriceNote.textContent =
        'Founding price protection applies to your account, including after a cancellation and return.';
    } else if (this.isFoundingEligible()) {
      this.elements.priceContext.textContent =
        'Founding price shown for an eligible account. Your place is secured only after successful payment.';

      this.elements.foundingPriceNote.hidden = false;

      this.elements.foundingPriceNote.textContent =
        'Founding availability is reserved during checkout and confirmed after payment.';
    } else {
      this.elements.priceContext.textContent =
        this.cycle === 'yearly'
          ? 'Billed annually. No trial period.'
          : 'Billed monthly. No trial period.';

      this.elements.foundingPriceNote.hidden = true;
      this.elements.foundingPriceNote.textContent = '';
    }

    const plan = this.plans[key] || {};

    if (plan.name && this.elements.upgrade) {
      this.elements.upgrade.setAttribute(
        'aria-label',
        `Continue with Silver ${this.cycle} for ${this.formatNaira(amount)}`
      );
    }
  }

  renderBillingToggle() {
    document.querySelectorAll('[data-cycle]').forEach((button) => {
      const selected = button.dataset.cycle === this.cycle;

      button.classList.toggle('is-selected', selected);
      button.setAttribute('aria-pressed', String(selected));
    });
  }

  renderFoundingOffer() {
    const offer = this.foundingOffer || {};
    const eligible = this.isFoundingEligible();

    const remaining = Number(
      offer.remaining_spots ??
      offer.remaining ??
      offer.available_spots ??
      NaN
    );

    this.elements.foundingBanner.hidden =
      !eligible && !(Number.isFinite(remaining) && remaining > 0);

    if (this.elements.foundingBanner.hidden) {
      return;
    }

    if (this.isExistingFounder()) {
      this.elements.foundingTitle.textContent =
        'Your founding price is protected';

      this.elements.foundingDescription.textContent =
        'Your founding price protection is attached to your account, including if you cancel and return later.';

      this.elements.foundingRemaining.textContent =
        Number.isFinite(remaining) ? String(remaining) : '✓';

      const capacityLabel = this.elements.foundingRemaining?.parentElement?.querySelector('span');
      if (capacityLabel) capacityLabel.textContent = 'places remaining';
    } else if (offer.reserved_for_this_account) {
      this.elements.foundingTitle.textContent =
        'Your founding checkout is reserved';

      this.elements.foundingDescription.textContent =
        'Complete checkout to confirm your founding membership. A reservation alone does not activate your price protection.';

      this.elements.foundingRemaining.textContent =
        Number.isFinite(remaining) ? String(remaining) : '—';
    } else if (eligible) {
      this.elements.foundingTitle.textContent =
        'Founding member pricing';

      this.elements.foundingDescription.textContent =
        'You are eligible to claim a founding price while a place remains. Price protection begins after successful payment.';

      this.elements.foundingRemaining.textContent =
        Number.isFinite(remaining) ? String(remaining) : '—';
    } else {
      this.elements.foundingTitle.textContent =
        'Founding places are limited';

      this.elements.foundingDescription.textContent =
        'Founding pricing is available to eligible accounts while places remain.';

      this.elements.foundingRemaining.textContent =
        Number.isFinite(remaining) ? String(remaining) : '—';
    }
  }

  renderSubscriptionControls() {
    const status = this.status || {};

    const active = Boolean(status.active ?? status.is_active);
    const plan = String(status.plan || '').toLowerCase();
    const subState = String(status.subscription_status || '').toLowerCase();

    const paidSilver = active && plan === 'silver';

    const wasLapsed = !paidSilver && Boolean(
      status.last_subscription_payment_at ||
      status.founding_member_ever ||
      status.subscription_id
    );

    this.elements.planCard?.classList.toggle(
      'is-active-plan',
      paidSilver
    );

    // Disable the Silver purchase button when Silver is active.
    if (this.elements.upgrade) {
      this.elements.upgrade.disabled = paidSilver || this.busy;
      this.elements.upgrade.setAttribute(
        'aria-disabled',
        String(paidSilver || this.busy)
      );

      this.elements.upgrade.textContent = paidSilver
        ? (
            subState === 'non_renewing'
              ? 'Silver active · Renewal off'
              : 'Current plan'
          )
        : 'Continue to Silver';
    }

    if (paidSilver) {
      this.elements.statusHint.textContent =
        subState === 'non_renewing'
          ? `Access continues until ${this.formatDate(
              status.subscription_end || status.next_billing_date
            )}.`
          : 'Your Silver subscription is active.';

      this.elements.manageSection.hidden = false;

      this.elements.manageSummary.textContent =
        subState === 'non_renewing'
          ? `Renewal is off. Your Silver access is scheduled to end ${this.formatDate(
              status.subscription_end || status.next_billing_date
            )}.`
          : `Silver is active${
              status.next_billing_date
                ? ` until your next billing date on ${this.formatDate(
                    status.next_billing_date
                  )}`
                : ''
            }.`;

      document.getElementById('cancel-renewal').hidden =
        subState === 'non_renewing' ||
        status.cancel_at_period_end === true;

      document.getElementById('manage-billing').hidden =
        !status.subscription_id;

      return;
    }

    this.elements.manageSection.hidden = !status.subscription_id;

    if (subState === 'past_due') {
      this.elements.statusHint.textContent =
        'Your subscription needs renewal attention.';
    } else if (wasLapsed) {
      this.elements.statusHint.textContent =
        'Renew Silver to restore invoices, receipts, reminders, and analytics.';
    } else {
      this.elements.statusHint.textContent =
        'Silver access activates after Paystack confirms your payment.';
    }

    document.getElementById('cancel-renewal').hidden = true;

    document.getElementById('manage-billing').hidden =
      !status.subscription_id;
  }

  
    openConfirmation() {
      const status = this.status || {};
      const active = Boolean(status.active ?? status.is_active);
      const plan = String(status.plan || '').toLowerCase();

      if (this.busy) {
        return;
      }

      if (active && plan === 'silver') {
        this.renderSubscriptionControls();

        this.showToast(
          'Silver is already active on your account.',
          'info'
        );

        return;
      }


    const amount = this.amountFor();

    this.confirmedPlan = this.planKey();

    this.elements.confirmTitle.textContent =
      this.isExistingFounder()
        ? 'Continue with your protected Silver price?'
        : this.isFoundingEligible()
          ? 'Claim your Silver founding price?'
          : 'Continue with Silver?';

    this.elements.confirmDescription.textContent =
      'You will be redirected to Paystack to complete secure recurring billing. Your subscription activates only after payment is verified.';

    this.elements.confirmCycle.textContent =
      this.cycle === 'yearly'
        ? 'Yearly billing'
        : 'Monthly billing';

    this.elements.confirmPrice.textContent =
      this.formatNaira(amount);

    this.elements.confirmPriceNote.textContent =
      this.cycle === 'yearly'
        ? 'Renews annually unless you cancel renewal.'
        : 'Renews monthly unless you cancel renewal.';

    this.elements.confirmFoundingNote.hidden =
      !this.isFoundingEligible();

    this.elements.confirmFoundingNote.textContent =
      this.isExistingFounder()
        ? 'Your protected founding price is linked to your account.'
        : 'Your founding place is only confirmed after successful payment. If checkout is not completed, it is not a permanent reservation.';

    this.elements.confirmModal.hidden = false;

    document.body.classList.add('modal-open');

    this.elements.confirmCheckout.focus();
  }

  closeConfirmation() {
    if (this.elements.confirmModal) {
      this.elements.confirmModal.hidden = true;
    }

    document.body.classList.remove('modal-open');
  }

  async startCheckout() {
    if (this.busy || !this.confirmedPlan) {
      return;
    }

    this.busy = true;

    this.elements.confirmCheckout.disabled = true;
    this.elements.confirmCheckout.textContent =
      'Preparing secure checkout…';

    try {
      const response = await this.request(
        `/subscription/start/${encodeURIComponent(this.confirmedPlan)}`,
        { method: 'POST' }
      );

      if (!response.authorization_url) {
        throw new Error(
          'Checkout URL was not returned. Please try again.'
        );
      }

      // Redirect to the hosted Paystack checkout page.
      window.location.assign(response.authorization_url);

    } catch (error) {
      console.error(
        'Unable to start subscription checkout:',
        error
      );

      this.showToast(
        error.message || 'Could not start checkout. Please try again.',
        'error'
      );

      this.busy = false;
      this.elements.confirmCheckout.disabled = false;

      this.elements.confirmCheckout.textContent =
        'Continue to checkout';
    }
  }

  async handleCheckoutReturn() {
    const url = new URL(window.location.href);

    const reference =
      url.searchParams.get('reference') ||
      url.searchParams.get('trxref');

    const cancelled = url.searchParams.get('cancelled');

    if (cancelled === '1') {
      this.showToast(
        'Checkout was not completed. No subscription has been activated.',
        'info'
      );

      this.cleanCheckoutParams(url);
      return;
    }

    if (!reference) {
      return;
    }

    this.showToast(
      'Confirming your payment with Payla…',
      'info'
    );

    try {
      const result = await this.request(
        `/subscription/verify/${encodeURIComponent(reference)}`
      );

      if (result.success && result.status) {
        this.status = result.status;

        this.render();

        this.elements.successModal.hidden = false;
        document.body.classList.add('modal-open');
      } else {
        throw new Error('Payment has not yet been confirmed.');
      }

    } catch (error) {
      console.error(
        'Checkout return verification failed:',
        error
      );

      this.showToast(
        `${error.message || 'Payment verification is still pending.'} If you were charged, do not pay again; refresh in a moment or contact support with reference ${reference}.`,
        'error',
        9000
      );

    } finally {
      this.cleanCheckoutParams(url);
    }
  }

  cleanCheckoutParams(url) {
    url.searchParams.delete('reference');
    url.searchParams.delete('trxref');
    url.searchParams.delete('cancelled');

    window.history.replaceState(
      {},
      document.title,
      url.pathname + url.search + url.hash
    );
  }

  async openManageLink() {
    try {
      const result = await this.request(
        '/subscription/manage-link'
      );

      const target =
        result.manage_url ||
        result.url ||
        result.authorization_url;

      if (!target) {
        throw new Error(
          'A billing management link is not available for this subscription.'
        );
      }

      window.location.assign(target);

    } catch (error) {
      this.showToast(
        error.message || 'Could not open billing management.',
        'error'
      );
    }
  }

  async cancelRenewal() {
    const confirmed = window.confirm(
      'Cancel future Silver renewals? Your paid access should continue through the end of the current billing period.'
    );

    if (!confirmed) {
      return;
    }

    const button = document.getElementById('cancel-renewal');

    button.disabled = true;

    try {
      const result = await this.request(
        '/subscription/cancel',
        { method: 'POST' }
      );

      this.showToast(
        result.message || 'Future renewal has been cancelled.',
        'success'
      );

      await this.loadStatus();
      this.render();

    } catch (error) {
      this.showToast(
        error.message || 'Could not cancel renewal. Please try again.',
        'error'
      );

    } finally {
      button.disabled = false;
    }
  }

  billingEndLabel(status) {
    const end =
      status.subscription_end ||
      status.next_billing_date;

    if (
      String(status.subscription_status).toLowerCase() ===
      'non_renewing'
    ) {
      return end
        ? `Renewal is off. Your access continues until ${this.formatDate(end)}.`
        : 'Renewal is off. Your paid access remains available through the paid period.';
    }

    return end
      ? `Next billing date: ${this.formatDate(end)}.`
      : 'Your Silver subscription is active.';
  }

  formatDate(value) {
    if (!value) {
      return 'the end of your billing period';
    }

    let date;

    if (typeof value === 'number') {
      date = new Date(value * 1000);
    } else {
      date = new Date(value);
    }

    if (Number.isNaN(date.getTime())) {
      return 'the end of your billing period';
    }

    return date.toLocaleDateString('en-NG', {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
    });
  }

  showToast(message, type = 'info', duration = 4500) {
    const toast = this.elements.toast;

    if (!toast) {
      return;
    }

    window.clearTimeout(this.toastTimer);

    toast.textContent = message;
    toast.dataset.type = type;
    toast.hidden = false;

    this.toastTimer = window.setTimeout(() => {
      toast.hidden = true;
    }, duration);
  }
}

document.addEventListener('DOMContentLoaded', () => {
  new SubscriptionManager();
});
