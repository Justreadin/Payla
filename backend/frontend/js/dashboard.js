// Payla Dashboard - Core Luxury Fintech Experience
// Core dashboard functionality: invoices, stats, auth, and basic data management
import { API_BASE } from './config.js';
import { authFetch, showUpgradeRequired } from './upgrade-handler.js';
import {
  trackDashboardPageView,
  trackDashboardSession,
  trackDashboardHeartbeat,
  trackDashboardEngagement
} from "./dashboard_analytics.js";

class PaylaDashboard {
    constructor() {
        if (window.paylaInstance) {
            console.warn('Prevented double instantiation of Dashboard');
            return window.paylaInstance;
        }
        window.paylaInstance = this;
        this.API_BASE = API_BASE;
        this.refreshInterval = null;
        this.isRefreshing = false;
        this.init();
    }

    init() {
        if (this.initialized) return;
        this.initialized = true;
        this.trackRetention();

        // Core DOM Elements
        this.avatarBtn = document.getElementById('avatar-btn');
        this.dropdown = document.getElementById('dropdown');
        this.filterBtns = document.querySelectorAll('.filter-btn');
        this.invoiceCards = document.getElementById('invoiceCards');
        this.viewMoreBtn = document.getElementById('viewMoreBtn');
        this.viewMoreSection = document.getElementById('viewMoreSection');
        this.allInvoicesModal = document.getElementById('all-invoices-modal');
        this.allInvoicesClose = document.getElementById('all-invoices-close');
        this.invoicesGrid = document.getElementById('invoicesGrid');
        this.invoiceDetailModal = document.getElementById('invoice-detail-modal');
        this.invoiceDetailClose = document.getElementById('invoice-detail-close');
        this.invoiceDetailContent = document.getElementById('invoiceDetailContent');
        this.toast = document.getElementById('toast');
        this.toastMessage = document.getElementById('toast-message');
        this.subscriptionBanner = document.getElementById('subscriptionBanner');
        // Core State
        this.activeFilter = null;
        this.dropdownOpen = false;
        this.maxVisibleCards = 4;
        this.allInvoices = [];
        this.dashboardData = null;
        this.entitlement = { has_silver: false, plan: 'free' };

        // Core Event Listeners
        this.setupCoreEventListeners();
        this.initDashboard();

        this.startAutoRefresh(30000);
    }

    trackRetention() {
        if (!this.pageViewTracked) {
            trackDashboardPageView();
            this.pageViewTracked = true;
        }

        this.sessionId = generateSessionId();
        this.sessionStartTime = Date.now();
        trackDashboardSession();

        this.startHeartbeat();
        this.setupEngagementTracking();
    }

    setupEngagementTracking() {
        window.addEventListener('beforeunload', () => {
            if (this.sessionStartTime) {
                const duration = Math.floor((Date.now() - this.sessionStartTime) / 1000);
                trackDashboardEngagement(duration);
            }
            if (this.heartbeatInterval) {
                clearInterval(this.heartbeatInterval);
            }
        });

        document.addEventListener('visibilitychange', () => {
            if (document.hidden) {
                if (this.heartbeatInterval) {
                    clearInterval(this.heartbeatInterval);
                    this.heartbeatInterval = null;
                }
            } else {
                if (!this.heartbeatInterval && this.sessionId) {
                    this.startHeartbeat();
                }
            }
        });
    }

    startHeartbeat() {
        let activeTime = 0;
        this.heartbeatInterval = setInterval(() => {
            activeTime += 30;
            trackDashboardHeartbeat(this.sessionId, activeTime);
        }, 30000);
    }

    startAutoRefresh(ms) {
        if (this.refreshInterval) clearInterval(this.refreshInterval);
        this.refreshInterval = setInterval(() => {
            this.refreshDashboard();
        }, ms);
    }

    async refreshDashboard() {
        if (this.isRefreshing) return;
        try {
            this.isRefreshing = true;
            await this.loadDashboardData();
            this.updateStats();
            this.renderInvoiceCards();
            this.updateFilterCounts();
            this.updateSubscriptionLink();
            this.renderSubscriptionBanner();
        } catch (error) {
            console.error('Auto-refresh failed:', error);
        } finally {
            this.isRefreshing = false;
        }
    }

    setupResponsiveBehavior() {
        document.addEventListener('visibilitychange', () => {
            if (document.hidden) {
                clearInterval(this.refreshInterval);
            } else {
                this.startAutoRefresh(30000);
                this.refreshDashboard();
            }
        });

        window.addEventListener('resize', () => {
            this.adjustLayoutForMobile();
        });

        this.adjustLayoutForMobile();
    }

    async checkAccess() {
        const res = await authFetch(`${this.API_BASE}/api/onboarding/me`);
        if (!res) return;

        const user = await res.json();

        if (!user.onboarding_complete) {
            window.location.href = '/onboarding';
            return;
        }

        const now = new Date();
        const subEnd = user.subscription_end ? new Date(user.subscription_end) : null;
        const presellEnd = user.presell_end_date ? new Date(user.presell_end_date) : null;

        const hasAccess =
            (presellEnd && presellEnd > now) ||
            (user.subscription_id && subEnd > now);

        if (!hasAccess) {
            window.location.href = '/subscription?reason=expired';
        }
    }

    setupCoreEventListeners() {
        this.avatarBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            this.toggleDropdown();
        });

        document.addEventListener('click', () => {
            if (this.dropdownOpen) {
                this.closeDropdown();
            }
        });

        this.filterBtns.forEach(btn => {
            btn.addEventListener('click', () => {
                const filter = btn.getAttribute('data-filter');
                this.toggleFilter(filter, btn);
            });
        });

        this.viewMoreBtn.addEventListener('click', () => {
            this.openAllInvoicesModal();
        });

        this.allInvoicesClose.addEventListener('click', () => {
            this.closeAllInvoicesModal();
        });

        this.invoiceDetailClose.addEventListener('click', () => {
            this.closeInvoiceDetailModal();
        });

        this.setupModalCloseListeners();
        this.setupCardActions();
        this.setupDetailActions();
        this.setupSilverGate();
    }

    /**
     * Soft gate for the "New Invoice" link in the section header.
     * The link is an <a href="/invoice">, so we intercept the click,
     * check entitlement, and either let it through or show the modal.
     */
    setupSilverGate() {
        document.addEventListener('click', (event) => {
            const link = event.target.closest('.section-action');
            if (!link) return;

            if (this.entitlement?.has_silver) return;

            event.preventDefault();
            showUpgradeRequired({
                feature: 'invoices',
                source: 'soft_gate',
                silverHistory: this.entitlement?.silver_history
            });
        });
    }

    /**
     * Wrap a Silver-only action. Runs the action if entitled,
     * shows the upgrade modal if not. All Silver actions route
     * through this so the pattern stays consistent.
     */
    requireSilver(feature, actionFn) {
        if (this.entitlement?.has_silver) {
            return actionFn();
        }
        showUpgradeRequired({
            feature,
            source: 'soft_gate',
            silverHistory: this.entitlement?.silver_history
        });
    }

    setupModalCloseListeners() {
        document.querySelectorAll('.modal-overlay').forEach(overlay => {
            overlay.addEventListener('click', (e) => {
                if (e.target === overlay) {
                    overlay.classList.remove('open');
                    document.body.style.overflow = 'auto';
                }
            });
        });

        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                this.closeAllInvoicesModal();
                this.closeInvoiceDetailModal();
            }
        });
    }

    setupCardActions() {
        document.addEventListener('click', async (e) => {
            const actionBtn = e.target.closest('.action-btn');
            if (!actionBtn) return;

            const card = actionBtn.closest('.invoice-card');
            const title = actionBtn.getAttribute('title');
            const invoiceId = card.getAttribute('data-id');

            switch (title) {
                case 'Edit Draft':
                    this.editDraft(card);
                    break;
                case 'Copy Link':
                    this.copyInvoiceLink(card);
                    break;
                case 'View Invoice':
                    this.viewInvoice(card);
                    break;
                case 'Remind':
                    this.remindClient(card);
                    break;
                case 'Delete Invoice':
                    await this.deleteInvoice(card, invoiceId);
                    break;
            }
        });
    }

    setupDetailActions() {
        this.invoiceDetailContent.addEventListener('click', (e) => {
            const btn = e.target.closest('[data-action]');
            if (!btn) return;

            const invoiceId = btn.getAttribute('data-invoice-id');
            const action = btn.getAttribute('data-action');

            switch (action) {
                case 'edit':
                    this.editInvoice(invoiceId);
                    break;
                case 'copy':
                    this.copyInvoiceLink(invoiceId);
                    break;
                case 'download':
                    this.downloadInvoice(invoiceId);
                    break;
            }
        });
    }

    async deleteInvoice(card, invoiceId) {
        if (!confirm('Are you sure you want to delete this invoice?')) return;

        try {
            const response = await fetch(`${this.API_BASE}/invoices/${invoiceId}`, {
                method: 'DELETE',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${this.getAuthToken()}`
                }
            });

            if (!response.ok) throw new Error(`Failed to delete invoice: ${response.status}`);

            card.remove();
            this.showToast('Invoice deleted successfully');
            this.allInvoices = this.allInvoices.filter(inv => inv.id !== invoiceId);
            this.updateFilterCounts();
        } catch (error) {
            console.error(error);
            this.showToast('Failed to delete invoice. Please try again.', true);
        }
    }

    async initDashboard() {
        try {
            await this.loadDashboardData();
            this.renderInvoiceCards();
            this.updateStats();
            this.updateFilterCounts();
            this.updateSubscriptionLink();
            this.renderSubscriptionBanner();
            this.setupResponsiveBehavior();
        } catch (error) {
            console.error('Failed to initialize dashboard:', error);
            this.showToast('Failed to load dashboard data. Please refresh.', true);
        }
    }

    async loadDashboardData() {
        try {
            const response = await authFetch(`${this.API_BASE}/dashboard/`, {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${this.getAuthToken()}`
                }
            });

            if (!response.ok) {
                const text = await response.text();
                console.error('API returned non-JSON:', text);
                if (response.status === 401) {
                    window.location.href = '/';
                    return;
                }
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            this.dashboardData = await response.json();

            // Entitlement flag drives every soft gate on the page.
            this.entitlement = this.dashboardData.entitlement || {
                has_silver: false,
                plan: 'free'
            };

            this.allInvoices = this.dashboardData.invoices.map(inv => {
                let cleanId = inv._id || inv.id;
                let rawLink = inv.link || inv.invoice_url || `/i/${cleanId}`;

                if (rawLink.includes('https://payla.nghttps://payla.ng')) {
                    rawLink = rawLink.replace('https://payla.nghttps://payla.ng', 'https://payla.ng');
                }

                return {
                    ...inv,
                    id: cleanId,
                    link: rawLink
                };
            });
        } catch (error) {
            if (error.message === 'Upgrade Required') {
                return;
            }
            console.error('Error loading dashboard data:', error);
            throw error;
        }
    }

    getAuthToken() {
        return localStorage.getItem('idToken') || '';
    }

    updateSubscriptionLink() {
        const label = document.getElementById('subscription-label');
        if (!label) return;

        const hasSilver = this.entitlement?.has_silver;
        label.textContent = hasSilver ? 'Subscription' : 'Upgrade to Silver';
    }

        /**
     * Render the renewal banner. States mirror the backend's
     * `silver_history` values. Only lapsed, in-grace, and cancelled
     * states produce a banner; active and never-subscribed stay silent.
     */
    renderSubscriptionBanner() {
        const banner = this.subscriptionBanner;
        if (!banner) return;

        const entitlement = this.entitlement || {};
        const history = entitlement.silver_history || 'never';

        // Non-banner states.
        if (history === 'active' || history === 'never') {
            banner.hidden = true;
            banner.innerHTML = '';
            return;
        }

        // Dismissal is per-session for non-urgent states.
        if (history !== 'in_grace') {
            const dismissed = sessionStorage.getItem(
                `payla_banner_dismissed_${history}`
            );
            if (dismissed === '1') {
                banner.hidden = true;
                return;
            }
        }

        const copy = this.bannerCopyFor(history, entitlement);
        if (!copy) {
            banner.hidden = true;
            return;
        }

        banner.className = `subscription-banner subscription-banner--${copy.tone}`;
        banner.hidden = false;
        banner.innerHTML = `
            <div class="subscription-banner__icon">
                <i class="fas ${copy.icon}" aria-hidden="true"></i>
            </div>
            <div class="subscription-banner__body">
                <p class="subscription-banner__title">${copy.title}</p>
                <p class="subscription-banner__message">${copy.message}</p>
            </div>
            <div class="subscription-banner__actions">
                <a href="/subscription" class="subscription-banner__cta">
                    ${copy.cta}
                </a>
                ${history !== 'in_grace' ? `
                <button type="button"
                        class="subscription-banner__dismiss"
                        data-banner-dismiss="${history}"
                        aria-label="Dismiss">
                    <i class="fas fa-times" aria-hidden="true"></i>
                </button>` : ''}
            </div>
        `;

        // Wire dismissal.
        const dismissBtn = banner.querySelector('[data-banner-dismiss]');
        if (dismissBtn) {
            dismissBtn.addEventListener('click', () => {
                sessionStorage.setItem(
                    `payla_banner_dismissed_${history}`,
                    '1'
                );
                banner.hidden = true;
            });
        }
    }

    bannerCopyFor(history, entitlement) {
        const endDate = this.formatBannerDate(entitlement.subscription_end);

        if (history === 'in_grace') {
            const days = Number(entitlement.days_left_in_grace || 0);
            return {
                tone: 'urgent',
                icon: 'fa-triangle-exclamation',
                title: 'Your Silver renewal needs attention',
                message: days > 0
                    ? `Access continues for ${days} more ${days === 1 ? 'day' : 'days'}. Update billing to keep your Silver features.`
                    : 'Update billing to keep your Silver features.',
                cta: 'Update billing'
            };
        }

        if (history === 'cancelled') {
            return {
                tone: 'info',
                icon: 'fa-circle-info',
                title: 'Your Silver renewals are off',
                message: endDate
                    ? `Silver continues until ${endDate}. Renew to keep access.`
                    : 'Silver continues through the paid period.',
                cta: 'Review Silver'
            };
        }

        if (history === 'expired') {
            return {
                tone: 'neutral',
                icon: 'fa-clock-rotate-left',
                title: 'Your Silver subscription has ended',
                message: endDate
                    ? `Silver ended ${endDate}. Renew to bring back invoices, receipts, reminders, and analytics.`
                    : 'Renew to bring back invoices, receipts, reminders, and analytics.',
                cta: 'Renew Silver'
            };
        }

        return null;
    }

    formatBannerDate(value) {
        if (!value) return null;

        let date;
        if (typeof value === 'number') {
            date = new Date(value * 1000);
        } else if (typeof value === 'object' && value.seconds) {
            date = new Date(value.seconds * 1000);
        } else {
            date = new Date(value);
        }

        if (Number.isNaN(date.getTime())) return null;

        return date.toLocaleDateString('en-NG', {
            day: 'numeric',
            month: 'short',
            year: 'numeric'
        });
    }

    updateStats() {
        if (!this.dashboardData || !this.dashboardData.stats) return;

        const stats = this.dashboardData.stats;

        // Collected
        const totalEarnedEl = document.getElementById('total-earned');
        if (stats.has_earnings) {
            totalEarnedEl.textContent = `₦${stats.total_earned?.toLocaleString() || '0'}`;
            totalEarnedEl.style.fontSize = '';
        } else {
            totalEarnedEl.textContent = 'First Payment Pending';
            totalEarnedEl.style.fontSize = '1.1rem';
        }

        // Breakdown sub-line — All time prefix
        const breakdownEl = document.getElementById('collected-breakdown');
        if (breakdownEl) {
            const invoiceRev = Number(stats.invoice_revenue || 0);
            const paylinkRev = Number(stats.paylink_revenue || 0);

            if (invoiceRev > 0 || paylinkRev > 0) {
                const fmt = (n) => `₦${n.toLocaleString('en-NG', { maximumFractionDigits: 0 })}`;
                breakdownEl.textContent =
                    `All time · ${fmt(invoiceRev)} invoices · ${fmt(paylinkRev)} link`;
                breakdownEl.style.display = '';
            } else {
                breakdownEl.textContent = '';
                breakdownEl.style.display = 'none';
            }
        }

        // Outstanding
        document.getElementById('pending-amount').textContent =
            `₦${stats.pending_amount?.toLocaleString() || '0'}`;

        const overdueCountEl = document.getElementById('overdue-count');
        if (stats.overdue_count > 0) {
            overdueCountEl.textContent =
                `₦${stats.overdue_amount?.toLocaleString() || '0'} (${stats.overdue_count}) Overdue`;
            overdueCountEl.style.color = '#ff4757';
        } else {
            overdueCountEl.textContent = '0 Overdue';
            overdueCountEl.style.color = '';
        }

        // Invoices Sent
        document.getElementById('total-invoices').textContent = stats.total_invoices || '0';

        // Settlement strip
        this.updateSettlement(stats);
    }

    updateSettlement(stats) {
        const strip = document.getElementById('settlement-strip');
        const textEl = document.getElementById('settlement-text');

        if (!strip || !textEl) return;

        if (!stats.is_subaccount_linked || !stats.has_earnings || !stats.next_settlement_estimate) {
            strip.hidden = true;
            return;
        }

        let formatted = stats.next_settlement_estimate;

        try {
            const d = new Date(stats.next_settlement_estimate + 'T00:00:00Z');
            if (!Number.isNaN(d.getTime())) {
                formatted = d.toLocaleDateString('en-NG', {
                    weekday: 'short',
                    month: 'short',
                    day: 'numeric',
                    timeZone: 'UTC'
                });
            }
        } catch {
            // fall through to raw value
        }

        textEl.textContent = `Next settlement: ${formatted} · T+1, weekdays only`;
        strip.hidden = false;
    }

    renderInvoiceCards() {
        let displayInvoices = this.allInvoices;

        if (this.activeFilter) {
            displayInvoices = this.allInvoices.filter(inv => inv.status === this.activeFilter);
        }

        const visibleInvoices = displayInvoices.slice(0, this.maxVisibleCards);
        this.invoiceCards.innerHTML = '';

        if (visibleInvoices.length === 0) {
            if (this.allInvoices.length > 0 && this.activeFilter) {
                this.invoiceCards.innerHTML = `
                    <div class="empty-state">
                        <i class="fas fa-filter"></i>
                        <h3>No ${this.activeFilter} invoices</h3>
                        <p>Try removing the filter to see all invoices</p>
                    </div>
                `;
            } else {
                this.invoiceCards.innerHTML = `
                    <div class="empty-state">
                        <i class="fas fa-file-invoice"></i>
                        <h3>No invoices yet</h3>
                        <p>Create your first invoice to get started</p>
                    </div>
                `;
            }
            this.viewMoreSection.classList.add('hidden');
            return;
        }

        visibleInvoices.forEach(invoice => {
            const card = this.createInvoiceCard(invoice);
            this.invoiceCards.appendChild(card);
        });

        if (displayInvoices.length > this.maxVisibleCards) {
            this.viewMoreSection.classList.remove('hidden');
        } else {
            this.viewMoreSection.classList.add('hidden');
        }
    }

    createInvoiceCard(invoice) {
        const card = document.createElement('div');
        card.className = 'invoice-card';
        card.setAttribute('data-status', invoice.status);
        card.setAttribute('data-id', invoice.id);

        const statusConfig = {
            draft: { icon: 'fas fa-pencil-alt', class: 'status-draft' },
            paid: { icon: 'fas fa-check-circle', class: 'status-paid' },
            pending: { icon: 'fas fa-hourglass-half', class: 'status-pending' },
            overdue: { icon: 'fas fa-clock', class: 'status-overdue' },
            failed: { icon: 'fas fa-times-circle', class: 'status-failed' }
        };

        const config = statusConfig[invoice.status] || statusConfig.pending;
        const dueDate = invoice.due_date ? new Date(invoice.due_date).toLocaleDateString('en-US', {
            month: 'short',
            day: 'numeric',
            year: 'numeric'
        }) : 'Not set';

        card.innerHTML = `
            <div class="card-header">
                <div class="card-description">${invoice.description || 'No description'}</div>
            </div>
            <div class="card-amount">${this.formatCurrency(invoice.amount, invoice.currency)}</div>
            <div class="card-details">
                <div class="due-date">
                    <i class="fas fa-${invoice.status === 'draft' ? 'pencil-alt' : 'calendar-check'}"></i>
                    <span>${dueDate}</span>
                </div>
                <div class="status-badge ${config.class}">
                    <i class="${config.icon} status-icon"></i>
                    ${this.capitalizeFirst(invoice.status)}
                </div>
            </div>
            <div class="card-footer">
                <div class="card-actions">
                    ${this.getCardActions(invoice.status, invoice.id)}
                </div>
            </div>
        `;

        return card;
    }

    formatCurrency(amount, currency = 'NGN') {
        const formatter = new Intl.NumberFormat('en-NG', {
            style: 'currency',
            currency: currency,
            minimumFractionDigits: 0,
            maximumFractionDigits: 0
        });
        return formatter.format(amount || 0);
    }

    getCardActions(status, invoiceId) {
        const deleteButton = `
            <button class="action-btn delete" title="Delete Invoice" data-id="${invoiceId}">
                <i class="fas fa-trash"></i>
            </button>
        `;

        const actions = {
            draft: `
                <button class="action-btn primary" title="Edit Draft" data-id="${invoiceId}">
                    <i class="fas fa-edit"></i>
                </button>
                ${deleteButton}
            `,
            paid: `
                <button class="action-btn" title="Copy Link" data-id="${invoiceId}">
                    <i class="fas fa-copy"></i>
                </button>
                <button class="action-btn" title="View Invoice" data-id="${invoiceId}">
                    <i class="fas fa-eye"></i>
                </button>
                ${deleteButton}
            `,
            pending: `
                <button class="action-btn" title="Copy Link" data-id="${invoiceId}">
                    <i class="fas fa-copy"></i>
                </button>
                <button class="action-btn" title="View Invoice" data-id="${invoiceId}">
                    <i class="fas fa-eye"></i>
                </button>
                ${deleteButton}
            `,
            overdue: `
                <button class="action-btn" title="Copy Link" data-id="${invoiceId}">
                    <i class="fas fa-copy"></i>
                </button>
                <button class="action-btn" title="View Invoice" data-id="${invoiceId}">
                    <i class="fas fa-eye"></i>
                </button>
                ${deleteButton}
            `,
            failed: `
                <button class="action-btn" title="View Invoice" data-id="${invoiceId}">
                    <i class="fas fa-eye"></i>
                </button>
                ${deleteButton}
            `
        };

        return actions[status] || actions.pending;
    }

    updateFilterCounts() {
        if (!this.allInvoices) return;

        const counts = {
            draft: this.allInvoices.filter(inv => inv.status === 'draft').length,
            paid: this.allInvoices.filter(inv => inv.status === 'paid').length,
            overdue: this.allInvoices.filter(inv => inv.status === 'overdue').length,
            pending: this.allInvoices.filter(inv => inv.status === 'pending').length,
            failed: this.allInvoices.filter(inv => inv.status === 'failed').length
        };

        this.filterBtns.forEach(btn => {
            const filter = btn.getAttribute('data-filter');
            const countElement = btn.querySelector('.filter-count');
            if (countElement) {
                countElement.textContent = counts[filter] || '0';
                countElement.style.opacity = counts[filter] > 0 ? '1' : '0.5';
            }
        });
    }

    toggleDropdown() {
        if (this.dropdownOpen) {
            this.closeDropdown();
        } else {
            this.openDropdown();
        }
    }

    openDropdown() {
        this.dropdown.classList.add('show');
        this.dropdownOpen = true;
        this.avatarBtn.style.animation = 'pulse 2s infinite';
    }

    closeDropdown() {
        this.dropdown.classList.remove('show');
        this.dropdownOpen = false;
        this.avatarBtn.style.animation = '';
    }

    toggleFilter(filter, button) {
        const span = button.querySelector('span:first-child');
        const isActive = button.classList.contains('active');

        if (isActive) {
            button.classList.remove('active');
            span.textContent = `Show ${this.capitalizeFirst(filter)}`;
            this.activeFilter = null;
        } else {
            this.filterBtns.forEach(btn => {
                btn.classList.remove('active');
                const btnSpan = btn.querySelector('span:first-child');
                const btnFilter = btn.getAttribute('data-filter');
                btnSpan.textContent = `Show ${this.capitalizeFirst(btnFilter)}`;
            });

            button.classList.add('active');
            span.textContent = `Hide ${this.capitalizeFirst(filter)}`;
            this.activeFilter = filter;
        }

        this.renderInvoiceCards();

        button.style.transform = 'scale(0.95)';
        setTimeout(() => {
            button.style.transform = 'scale(1)';
        }, 150);
    }

    openAllInvoicesModal() {
        this.renderAllInvoicesGrid();
        this.allInvoicesModal.classList.add('open');
        document.body.style.overflow = 'hidden';

        this.viewMoreBtn.style.transform = 'scale(0.95)';
        setTimeout(() => {
            this.viewMoreBtn.style.transform = 'scale(1)';
        }, 150);
    }

    closeAllInvoicesModal() {
        this.allInvoicesModal.classList.remove('open');
        document.body.style.overflow = 'auto';
    }

    renderAllInvoicesGrid() {
        this.invoicesGrid.innerHTML = '';

        if (this.allInvoices.length === 0) {
            this.invoicesGrid.innerHTML = `
                <div class="empty-state">
                    <i class="fas fa-file-invoice"></i>
                    <h3>No invoices found</h3>
                    <p>Create your first invoice to get started</p>
                </div>
            `;
            return;
        }

        this.allInvoices.forEach(invoice => {
            const card = this.createInvoiceCard(invoice);
            this.invoicesGrid.appendChild(card);
        });
    }

    openInvoiceDetailModal(invoiceId) {
        const invoice = this.allInvoices.find(inv => inv.id === invoiceId);
        if (!invoice) {
            this.showToast('Invoice not found', true);
            return;
        }

        this.renderInvoiceDetail(invoice);
        this.invoiceDetailModal.classList.add('open');
        document.body.style.overflow = 'hidden';
    }

    closeInvoiceDetailModal() {
        this.invoiceDetailModal.classList.remove('open');
        document.body.style.overflow = 'auto';
    }

    renderInvoiceDetail(invoice) {
        const statusConfig = {
            draft: { class: 'status-draft', label: 'Draft' },
            paid: { class: 'status-paid', label: 'Paid' },
            pending: { class: 'status-pending', label: 'Pending' },
            overdue: { class: 'status-overdue', label: 'Overdue' },
            failed: { class: 'status-failed', label: 'Failed' }
        };

        const config = statusConfig[invoice.status] || statusConfig.pending;

        const dueDate = invoice.due_date ? new Date(invoice.due_date).toLocaleDateString('en-US', {
            year: 'numeric',
            month: 'long',
            day: 'numeric'
        }) : 'Not set';

        const createdAt = invoice.created_at ? new Date(invoice.created_at).toLocaleDateString('en-US', {
            year: 'numeric',
            month: 'long',
            day: 'numeric'
        }) : 'Unknown';

        const paidAt = invoice.paid_date ? new Date(invoice.paid_date).toLocaleDateString('en-US', {
            year: 'numeric',
            month: 'long',
            day: 'numeric'
        }) : null;

        const invoiceNumber = `INV-${String(invoice.id || '').replace(/^inv_/, '').toUpperCase()}`;

        const paymentRow = invoice.status === 'paid' && paidAt ? `
            <div class="info-group info-group--payment">
                <div class="info-label">Payment</div>
                <div class="info-value">Paid on ${paidAt} · via Paystack</div>
            </div>
        ` : '';

        const dueDateNote = invoice.status === 'paid' ? '' : this.getDueDateNote(invoice);

        this.invoiceDetailContent.innerHTML = `
            <div class="invoice-detail-header">
                <div class="invoice-detail-id">${invoiceNumber}</div>
                <div class="invoice-detail-header-row">
                    <div>
                        <h2 class="invoice-detail-title">${invoice.description || 'No description'}</h2>
                        <div class="invoice-detail-amount">${this.formatCurrency(invoice.amount, invoice.currency)}</div>
                    </div>
                    <div class="invoice-detail-status ${config.class}">
                        <i class="${this.getStatusIcon(invoice.status)}"></i>
                        ${config.label}
                    </div>
                </div>
            </div>

            <div class="invoice-detail-info">
                <div class="info-group">
                    <div class="info-label">Client Information</div>
                    ${invoice.client_phone ? `<div class="info-note">Phone: ${invoice.client_phone}</div>` : ''}
                    ${invoice.client_email ? `<div class="info-note">Email: ${invoice.client_email}</div>` : ''}
                    ${!invoice.client_phone && !invoice.client_email ? `<div class="info-note">No client contact on file</div>` : ''}
                </div>

                <div class="info-group">
                    <div class="info-label">Due Date</div>
                    <div class="info-value">${dueDate}</div>
                    ${dueDateNote ? `<div class="info-note">${dueDateNote}</div>` : ''}
                </div>

                ${paymentRow}

                <div class="info-group">
                    <div class="info-label">Created Date</div>
                    <div class="info-value">${createdAt}</div>
                </div>
            </div>

            ${invoice.notes ? `
            <div class="info-group">
                <div class="info-label">Description & Notes</div>
                <div class="info-note">${invoice.notes}</div>
            </div>
            ` : ''}

            <div class="invoice-detail-actions">
                ${this.getDetailActions(invoice)}
            </div>
        `;
    }

    getStatusIcon(status) {
        const icons = {
            draft: 'fas fa-pencil-alt',
            paid: 'fas fa-check-circle',
            pending: 'fas fa-hourglass-half',
            overdue: 'fas fa-clock',
            failed: 'fas fa-times-circle'
        };
        return icons[status] || 'fas fa-file-invoice';
    }

    getDueDateNote(invoice) {
        if (invoice.status === 'draft') return 'This invoice has not been sent to the client yet.';
        if (invoice.status === 'overdue') return 'This invoice is past due. Consider sending a reminder.';
        if (invoice.status === 'failed') return 'Payment failed. You may want to resend this invoice.';
        return 'Awaiting payment from client.';
    }

    getDetailActions(invoice) {
        if (invoice.status === 'draft') {
            return `
                <button class="btn-primary" data-action="edit" data-invoice-id="${invoice.id}">
                    <i class="fas fa-edit"></i>
                    Edit Draft
                </button>
            `;
        }

        if (invoice.status === 'paid') {
            return `
                <button class="btn-secondary" data-action="copy" data-invoice-id="${invoice.id}">
                    <i class="fas fa-copy"></i>
                    Copy Link
                </button>
                <button class="btn-primary" data-action="download" data-invoice-id="${invoice.id}">
                    <i class="fas fa-download"></i>
                    Download receipt
                </button>
            `;
        }

        return '';
    }

    editDraft(card) {
        const invoiceId = card.getAttribute('data-id');
        this.openInvoiceDetailModal(invoiceId);
    }

    viewInvoice(card) {
        const invoiceId = typeof card === 'string' ? card : card.getAttribute('data-id');
        this.openInvoiceDetailModal(invoiceId);
    }

    copyInvoiceLink(card) {
        const invoiceId = typeof card === 'string' ? card : card.getAttribute('data-id');
        const invoice = this.allInvoices.find(inv => inv.id === invoiceId);

        if (invoice && invoice.invoice_url) {
            let cleanUrl = invoice.invoice_url;

            if (cleanUrl.includes('payla.nghttps://payla.ng')) {
                cleanUrl = cleanUrl.replace('https://payla.nghttps://payla.ng', 'https://payla.ng');
            }

            navigator.clipboard.writeText(cleanUrl).then(() => {
                this.showToast('Invoice link copied');
            });
        } else {
            this.showToast('No invoice link available', true);
        }

        const btn = typeof card === 'string'
            ? document.querySelector(`[data-id="${invoiceId}"] [title="Copy Link"]`)
            : card.querySelector('[title="Copy Link"]');

        if (btn) {
            btn.classList.add('success');
            setTimeout(() => btn.classList.remove('success'), 1000);
        }
    }

    remindClient(card) {
        const invoiceId = typeof card === 'string' ? card : card.getAttribute('data-id');
        this.showToast('Reminder sent');

        const btn = typeof card === 'string' ?
            document.querySelector(`[data-id="${invoiceId}"] [title="Remind"]`) :
            card.querySelector('[title="Remind"]');

        if (btn) {
            btn.classList.add('success');
            setTimeout(() => {
                btn.classList.remove('success');
            }, 1000);
        }
    }

    capitalizeFirst(string) {
        return string.charAt(0).toUpperCase() + string.slice(1);
    }

    showToast(message, isError = false, duration = 3000) {
        this.toastMessage.textContent = message;
        this.toast.className = 'toast';

        if (isError) {
            this.toast.classList.add('error');
        } else if (typeof isError === 'string') {
            this.toast.classList.add(isError);
        }

        this.toast.classList.add('show');

        setTimeout(() => {
            this.toast.classList.remove('show', 'error', 'warning', 'success');
        }, duration);
    }

    adjustLayoutForMobile() {
        const isMobile = window.innerWidth <= 768;
        document.body.style.overflowX = isMobile ? 'hidden' : 'auto';
    }

    // Detail modal actions
    editInvoice(invoiceId) {
        window.location.href = `/invoice?edit=${invoiceId}`;
    }

    downloadInvoice(invoiceId) {
        this.requireSilver('receipts', () => {
            const invoice = this.allInvoices.find(inv => inv.id === invoiceId);

            if (!invoice) {
                this.showToast('Invoice not found', true);
                return;
            }

            const paymentReference =
                invoice.transaction_reference ||
                invoice.paystack_reference;

            if (!paymentReference) {
                this.showToast('Payment reference unavailable', true);
                return;
            }

            const url =
                `${this.API_BASE}/receipt/invoice/${encodeURIComponent(invoiceId)}.pdf` +
                `?token=${encodeURIComponent(paymentReference)}`;

            window.open(url, '_blank', 'noopener');
            this.showToast('Receipt downloading');
        });
    }
}

function generateSessionId() {
    return 'session_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
}

let dashboard;

document.addEventListener('DOMContentLoaded', () => {
    dashboard = new PaylaDashboard();
    window.dashboard = dashboard;
});

export { PaylaDashboard }