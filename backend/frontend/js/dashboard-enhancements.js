// Payla Dashboard - Enhancement Features
// Additional features: notifications, analytics, paylinks, and UI enhancements

import { API_BASE } from './config.js';
import { authFetch, showUpgradeRequired } from './upgrade-handler.js';

class DashboardEnhancements {
    constructor() {
        if (window.enhancementsInstance) {
            return window.enhancementsInstance;
        }
        window.enhancementsInstance = this;

        this.API_BASE = API_BASE;
        this.isProcessingToggle = false;
        this.initialized = false;
        this.analyticsLoaded = false;

        this.init();
    }

    init() {
        if (this.initialized) return;

        // Enhancement DOM Elements
        this.copyLinkBtn = document.getElementById('copy-link-btn');
        this.notificationsBtn = document.getElementById('notifications-btn');
        this.notificationsModal = document.getElementById('notifications-modal');
        this.notificationsClose = document.getElementById('notifications-close');
        this.notificationsList = document.getElementById('notificationsList');
        this.notificationBadge = document.getElementById('notification-badge');
        this.analyticsBtn = document.getElementById('analytics-btn');
        this.analyticsModal = document.getElementById('analytics-modal');
        this.analyticsClose = document.getElementById('analytics-close');
        this.analyticsContent = document.getElementById('analyticsContent');

        // Paylink toggle elements
        this.paylinkToggle = document.getElementById('paylink-toggle');
        this.statusBadge = document.getElementById('status-badge');

        // Enhancement state
        this.notifications = [];
        this.analyticsData = null;
        this.isProcessingToggle = false;

        this.setupEnhancementListeners();
        this.initEnhancements();
        this.initialized = true;
    }

    setupEnhancementListeners() {
        if (this.copyLinkBtn) {
            this.copyLinkBtn.addEventListener('click', () => {
                this.copyPaylink();
            });
        }

        if (this.notificationsBtn) {
            this.notificationsBtn.addEventListener('click', () => {
                this.openNotificationsModal();
            });
        }

        if (this.analyticsBtn) {
            this.analyticsBtn.addEventListener('click', () => {
                this.handleAnalyticsClick();
            });
        }

        if (this.paylinkToggle) {
            this.paylinkToggle.addEventListener('click', (e) => {
                const isActive = e.target.checked;
                this.handlePaylinkToggle(isActive);
            });
        }

        if (this.notificationsClose) {
            this.notificationsClose.addEventListener('click', () => {
                this.closeNotificationsModal();
            });
        }

        if (this.analyticsClose) {
            this.analyticsClose.addEventListener('click', () => {
                this.closeAnalyticsModal();
            });
        }

        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                this.closeNotificationsModal();
                this.closeAnalyticsModal();
            }
        });

        const urlEl = document.getElementById('paylink-url');
        if (urlEl) {
            urlEl.style.cursor = 'pointer';
            urlEl.addEventListener('click', () => {
                const fullUrl = urlEl.dataset.fullUrl;
                if (fullUrl) {
                    window.open(fullUrl, '_blank', 'noopener,noreferrer');
                }
            });
        }

        const userEl = document.getElementById('user-paylink');
        if (userEl) {
            userEl.style.cursor = 'pointer';
            userEl.addEventListener('click', () => {
                const userUrl = userEl.dataset.userUrl;
                if (userUrl) {
                    window.open(userUrl, '_blank', 'noopener,noreferrer');
                }
            });
        }
    }

    async initEnhancements() {
        try {
            await this.loadNotifications();
            this.updatePaylinkInfo();
            this.updateNotificationBadge();
            this.initializePaylinkToggle();
            this.setupAutoRefresh();
            this.setupUIEnhancements();
        } catch (error) {
            console.error('Failed to initialize enhancements:', error);
        }
    }

    /**
     * Notifications only. Analytics is fetched lazily when the user
     * clicks View Analytics — it's a Silver endpoint and would 403 on
     * page load for Free users, incorrectly triggering the upgrade modal.
     */
    async loadNotifications() {
        try {
            const token = this.getAuthToken();
            if (!token) {
                console.error('No authentication token found');
                return;
            }

            const response = await fetch(`${this.API_BASE}/dashboard/notifications/`, {
                headers: {
                    'Authorization': `Bearer ${token}`
                }
            });

            if (response.ok) {
                this.notifications = await response.json();
            } else {
                console.error('Failed to load notifications:', response.status);
            }
        } catch (error) {
            console.error('Error loading notifications:', error);
        }
    }

    async loadAnalyticsData() {
        try {
            const token = this.getAuthToken();
            if (!token) return false;

            const response = await authFetch(`${this.API_BASE}/dashboard/analytics/`, {
                headers: {
                    'Authorization': `Bearer ${token}`
                },
                feature: 'analytics',
                silverHistory: window.dashboard?.entitlement?.silver_history
            });

            if (!response.ok) {
                console.error('Failed to load analytics:', response.status);
                return false;
            }

            this.analyticsData = await response.json();
            this.analyticsLoaded = true;

            // Refresh the paylink card with the newly available stats.
            this.updatePaylinkInfo();

            return true;
        } catch (error) {
            if (error.message !== 'Upgrade Required') {
                console.error('Error loading analytics:', error);
            }
            return false;
        }
    }

    getAuthToken() {
        return localStorage.getItem('idToken') || '';
    }

    /**
     * Analytics is a Silver action. For Free users we show the
     * analytics-specific upgrade modal. For Silver users we load
     * the data (once) then open the modal.
     */
    async handleAnalyticsClick() {
        const hasSilver = window.dashboard?.entitlement?.has_silver;

        if (!hasSilver) {
            showUpgradeRequired({
                feature: 'analytics',
                source: 'soft_gate',
                silverHistory: window.dashboard?.entitlement?.silver_history
            });
            return;
        }

        if (!this.analyticsLoaded) {
            const ok = await this.loadAnalyticsData();
            if (!ok) return;
        }

        this.openAnalyticsModal();
    }

    initializePaylinkToggle() {
        const paylink = window.dashboard?.dashboardData?.paylink;
        if (!paylink) return;

        const isActive = paylink.active !== false;

        if (this.paylinkToggle) {
            this.paylinkToggle.checked = isActive;
        }

        if (this.statusBadge) {
            if (isActive) {
                this.statusBadge.textContent = 'Active';
                this.statusBadge.classList.remove('inactive');
                this.statusBadge.classList.add('active');
            } else {
                this.statusBadge.textContent = 'Inactive';
                this.statusBadge.classList.remove('active');
                this.statusBadge.classList.add('inactive');
            }
        }
    }

    async handlePaylinkToggle(isActive) {
        if (this.isProcessingToggle) return;

        try {
            this.isProcessingToggle = true;

            if (this.paylinkToggle) this.paylinkToggle.disabled = true;

            if (isActive) {
                await this.activatePaylink();
            } else {
                await this.deactivatePaylink();
            }
        } catch (error) {
            console.error('Toggle operation failed:', error);
            if (this.paylinkToggle) this.paylinkToggle.checked = !isActive;
            this.showToggleErrorModal(isActive, error);
        } finally {
            this.isProcessingToggle = false;
            if (this.paylinkToggle) this.paylinkToggle.disabled = false;
        }
    }

    async activatePaylink() {
        const token = this.getAuthToken();
        if (!token) throw new Error('No authentication token found');

        const response = await fetch(`${this.API_BASE}/paylinks/me/activate/`, {
            method: 'PATCH',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            }
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
            throw new Error(errorData.detail || 'Failed to activate paylink');
        }

        if (this.statusBadge) {
            this.statusBadge.textContent = 'Active';
            this.statusBadge.classList.remove('inactive');
            this.statusBadge.classList.add('active');
        }

        if (window.dashboard?.dashboardData?.paylink) {
            window.dashboard.dashboardData.paylink.active = true;
        }

        window.dashboard?.showToast?.('Paylink activated successfully', 'success');
    }

    async deactivatePaylink() {
        const token = this.getAuthToken();
        if (!token) throw new Error('No authentication token found');

        const confirmed = await this.showDeactivationConfirmation();
        if (!confirmed) {
            if (this.paylinkToggle) {
                this.paylinkToggle.checked = true;
            }
            return;
        }

        const response = await fetch(`${this.API_BASE}/paylinks/me/deactivate/`, {
            method: 'PATCH',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            }
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
            throw new Error(errorData.detail || 'Failed to deactivate paylink');
        }

        if (this.statusBadge) {
            this.statusBadge.textContent = 'Inactive';
            this.statusBadge.classList.remove('active');
            this.statusBadge.classList.add('inactive');
        }

        if (window.dashboard?.dashboardData?.paylink) {
            window.dashboard.dashboardData.paylink.active = false;
        }

        window.dashboard?.showToast?.('Paylink deactivated', 'info');
    }

    showDeactivationConfirmation() {
        return new Promise((resolve) => {
            const modal = document.createElement('div');
            modal.className = 'confirmation-overlay';
            modal.innerHTML = `
                <div class="confirmation-modal glass">
                    <div class="modal-header">
                        <i class="fas fa-exclamation-triangle warning-icon"></i>
                        <h3>Deactivate Paylink?</h3>
                    </div>
                    <div class="modal-body">
                        <p>When deactivated:</p>
                        <ul class="warning-list">
                            <li><i class="fas fa-times-circle"></i> Your paylink will be inaccessible</li>
                            <li><i class="fas fa-times-circle"></i> No new payments can be received</li>
                            <li><i class="fas fa-times-circle"></i> Existing pending transactions may be affected</li>
                        </ul>
                        <p class="note">You can reactivate anytime.</p>
                    </div>
                    <div class="modal-actions">
                        <button class="btn-cancel" id="cancel-deactivate">
                            <i class="fas fa-times"></i>
                            Cancel
                        </button>
                        <button class="btn-confirm" id="confirm-deactivate">
                            <i class="fas fa-power-off"></i>
                            Deactivate
                        </button>
                    </div>
                </div>
            `;

            document.body.appendChild(modal);

            const cancelBtn = modal.querySelector('#cancel-deactivate');
            const confirmBtn = modal.querySelector('#confirm-deactivate');

            const cleanup = () => {
                document.body.removeChild(modal);
            };

            cancelBtn.addEventListener('click', () => {
                cleanup();
                resolve(false);
            });

            confirmBtn.addEventListener('click', () => {
                cleanup();
                resolve(true);
            });

            modal.addEventListener('click', (e) => {
                if (e.target === modal) {
                    cleanup();
                    resolve(false);
                }
            });

            const handleEscape = (e) => {
                if (e.key === 'Escape') {
                    document.removeEventListener('keydown', handleEscape);
                    cleanup();
                    resolve(false);
                }
            };
            document.addEventListener('keydown', handleEscape);
        });
    }

    showToggleErrorModal(intendedState, error) {
        const modal = document.createElement('div');
        modal.className = 'modal-overlay';
        modal.innerHTML = `
            <div class="error-modal glass">
                <div class="modal-header">
                    <i class="fas fa-exclamation-circle error-icon"></i>
                    <h3>Operation Failed</h3>
                </div>
                <div class="modal-body">
                    <p>Failed to ${intendedState ? 'activate' : 'deactivate'} your paylink:</p>
                    <p class="error-message">${error.message || 'Unknown error occurred'}</p>
                    <p class="note">Please try again or contact support if the issue persists.</p>
                </div>
                <div class="modal-actions">
                    <button class="btn-primary" id="close-error">
                        <i class="fas fa-times"></i>
                        Close
                    </button>
                </div>
            </div>
        `;

        document.body.appendChild(modal);

        const closeBtn = modal.querySelector('#close-error');

        closeBtn.addEventListener('click', () => {
            document.body.removeChild(modal);
        });

        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                document.body.removeChild(modal);
            }
        });
    }

    formatDisplayUrl(url) {
        if (!url) return '';
        return url.replace(/^https?:\/\//, '');
    }

    /**
     * Paylink card content depends on entitlement:
     *   Silver → link, toggle, copy, stats (Received / Payments / Success rate)
     *   Free   → link, toggle, copy, nudge (no stats)
     */
    updatePaylinkInfo() {
        const paylink = window.dashboard?.dashboardData?.paylink;
        if (!paylink) return;

        const hasSilver = Boolean(window.dashboard?.entitlement?.has_silver);

        const urlEl = document.getElementById('paylink-url');
        if (urlEl) {
            const fullUrl = paylink.url || `https://payla.ng/@${window.dashboard?.dashboardData?.user?.username || ''}`;
            urlEl.textContent = fullUrl.replace(/^https?:\/\//, '');
            urlEl.dataset.fullUrl = fullUrl;
        }

        const userEl = document.getElementById('user-paylink');
        if (userEl) {
            const userUrl = paylink.url || `https://payla.ng/@${window.dashboard?.dashboardData?.user?.username || ''}`;
            userEl.textContent = userUrl.replace(/^https?:\/\//, '');
            userEl.dataset.userUrl = userUrl;
        }

        const statsEl = document.querySelector('.paylink-stats');

        if (!hasSilver) {
            if (statsEl) statsEl.hidden = true;
        } else {
            if (statsEl) statsEl.hidden = false;

            const totalReceived = Number(
                this.analyticsData?.total_received
                ?? paylink.total_received
                ?? 0
            );

            const totalTransactions = Number(
                this.analyticsData?.total_transactions
                ?? paylink.total_transactions
                ?? 0
            );

            // Prefer the analytics value once it's been loaded. Fall back
            // to the paylink summary from the dashboard response so the
            // card is complete on first render.
            const successRate = this.analyticsLoaded
                ? (this.analyticsData?.success_rate
                    || paylink.success_rate
                    || "0%")
                : (paylink.success_rate || "0%");

            const receivedEl = document.getElementById('paylink-received');
            const transactionsEl = document.getElementById('paylink-transactions');
            const successRateEl = document.getElementById('paylink-success-rate');

            if (receivedEl) {
                receivedEl.textContent = `₦${totalReceived.toLocaleString()}`;
            }
            if (transactionsEl) {
                transactionsEl.textContent = totalTransactions;
            }
            if (successRateEl) {
                successRateEl.textContent = successRate;
            }
        }

        const nudgeEl = document.getElementById('paylink-nudge');
        if (nudgeEl) {
            const received = Number(paylink.total_received || 0);
            nudgeEl.hidden = received > 0;
        }
    }

    updateNotificationBadge() {
        const unreadCount = this.notifications.filter(n => !n.read).length;
        if (this.notificationBadge) {
            if (unreadCount > 0) {
                this.notificationBadge.textContent = unreadCount;
                this.notificationBadge.classList.remove('hidden');
            } else {
                this.notificationBadge.classList.add('hidden');
            }
        }
    }

    async openNotificationsModal() {
        await this.renderNotifications();
        this.notificationsModal.classList.add('open');
        document.body.style.overflow = 'hidden';
    }

    closeNotificationsModal() {
        this.notificationsModal.classList.remove('open');
        document.body.style.overflow = 'auto';
    }

    async renderNotifications() {
        if (!this.notificationsList) return;

        if (this.notifications.length === 0) {
            this.notificationsList.innerHTML = `
                <div class="empty-state">
                    <i class="fas fa-bell-slash"></i>
                    <h3>No notifications</h3>
                    <p>You're all caught up</p>
                </div>
            `;
            return;
        }

        this.notificationsList.innerHTML = this.notifications.map(notification => `
            <div class="notification-item ${notification.read ? '' : 'unread'}" data-id="${notification.id}">
                <div class="notification-icon">
                    <i class="fas fa-${this.getNotificationIcon(notification.type)}"></i>
                </div>
                <div class="notification-content">
                    <div class="notification-title">${notification.title || 'Notification'}</div>
                    <div class="notification-message">${notification.message || ''}</div>
                    <div class="notification-time">${this.formatTimeAgo(notification.created_at)}</div>
                </div>
                ${!notification.read ? `
                <button class="mark-read-btn" data-notification-id="${notification.id}">
                    <i class="fas fa-check"></i>
                </button>
                ` : ''}
            </div>
        `).join('');

        this.notificationsList.querySelectorAll('[data-notification-id]').forEach(btn => {
            btn.addEventListener('click', () => {
                this.markNotificationRead(btn.getAttribute('data-notification-id'));
            });
        });
    }

    getNotificationIcon(type) {
        const icons = {
            payment: 'credit-card',
            invoice: 'file-invoice',
            reminder: 'bell',
            system: 'info-circle'
        };
        return icons[type] || 'bell';
    }

    formatTimeAgo(dateString) {
        if (!dateString) return 'Just now';
        const date = new Date(dateString);
        if (isNaN(date)) return 'Just now';

        const now = new Date();
        const diffMs = now - date;
        const diffMins = Math.floor(diffMs / 60000);

        if (diffMins < 1) return 'Just now';
        if (diffMins < 60) return `${diffMins}m ago`;

        const diffHours = Math.floor(diffMs / 3600000);
        if (diffHours < 24) return `${diffHours}h ago`;

        const diffDays = Math.floor(diffMs / 86400000);
        if (diffDays < 7) return `${diffDays}d ago`;

        return date.toLocaleDateString();
    }

    async markNotificationRead(notificationId) {
        try {
            const response = await fetch(`${this.API_BASE}/dashboard/notifications/${notificationId}/read`, {
                method: 'PATCH',
                headers: {
                    'Authorization': `Bearer ${this.getAuthToken()}`
                }
            });

            if (response.ok) {
                const notification = this.notifications.find(n => n.id === notificationId);
                if (notification) {
                    notification.read = true;
                }
                this.updateNotificationBadge();
                this.renderNotifications();
            }
        } catch (error) {
            console.error('Error marking notification as read:', error);
        }
    }

    openAnalyticsModal() {
        this.renderAnalytics();
        this.analyticsModal.classList.add('open');
        document.body.style.overflow = 'hidden';
    }

    closeAnalyticsModal() {
        this.analyticsModal.classList.remove('open');
        document.body.style.overflow = 'auto';
    }

    renderAnalytics() {
        if (!this.analyticsContent) return;

        if (!this.analyticsData) {
            this.analyticsContent.innerHTML = `
                <div class="empty-state">
                    <i class="fas fa-chart-line"></i>
                    <h3>No analytics data</h3>
                    <p>Analytics will appear as you receive payments</p>
                </div>
            `;
            return;
        }

        const analytics = this.analyticsData;

        const totalReceived = Number(analytics.total_received ?? 0);
        const totalTransactions = Number(analytics.total_transactions ?? 0);
        const pageViews = Number(analytics.page_views ?? 0);
        const transferClicks = Number(analytics.transfer_clicks ?? 0);

        const successFraction = analytics.success_fraction || 'No attempts yet';

        const averagePayment = Number(analytics.average_payment ?? 0);

        const thisMonth = Number(analytics.this_month_revenue ?? 0);
        const lastMonth = Number(analytics.last_month_revenue ?? 0);
        const monthDelta = this.monthOverMonth(thisMonth, lastMonth);
        const bestWeekday = this.bestWeekday(analytics.weekday_totals);

        const dailyViews = analytics.daily_page_views ?? {};
        const dailyClicks = analytics.daily_transfer_clicks ?? {};

        const revenueSplit = this.revenueSplit(
            analytics.net_invoice_revenue ?? 0,
            analytics.net_paylink_revenue ?? 0
        );

        const funnel = this.buildFunnel(analytics.funnel || {});

        const payments = Array.isArray(analytics.payments)
            ? analytics.payments.slice(0, 20)
            : [];

        this.analyticsContent.innerHTML = `
            <section class="analytics-section">
                <header class="analytics-section__head">
                    <h3 class="analytics-section__title">Your payment link</h3>
                    <p class="analytics-section__sub">
                        Activity on your Payla link and its payment page.
                    </p>
                </header>

                <div class="analytics-overview">
                    <div class="analytics-stat">
                        <div class="analytics-value">₦${totalReceived.toLocaleString()}</div>
                        <div class="analytics-label">Received via your link</div>
                    </div>
                    <div class="analytics-stat">
                        <div class="analytics-value">${totalTransactions}</div>
                        <div class="analytics-label">Link payments</div>
                    </div>
                    <div class="analytics-stat">
                        <div class="analytics-value">${successFraction}</div>
                        <div class="analytics-label">Successful attempts</div>
                    </div>
                    <div class="analytics-stat">
                        <div class="analytics-value">${pageViews.toLocaleString()}</div>
                        <div class="analytics-label">Page views</div>
                    </div>
                    <div class="analytics-stat">
                        <div class="analytics-value">${transferClicks.toLocaleString()}</div>
                        <div class="analytics-label">Transfer taps</div>
                    </div>
                    <div class="analytics-stat">
                        <div class="analytics-value">₦${Math.round(averagePayment).toLocaleString()}</div>
                        <div class="analytics-label">Average payment (all)</div>
                    </div>
                </div>
            </section>

            ${funnel ? `
            <section class="analytics-section">
                <header class="analytics-section__head">
                    <h3 class="analytics-section__title">Where people drop off</h3>
                    <p class="analytics-section__sub">
                        Views, taps, attempts, and payments on your link.
                    </p>
                </header>
                ${funnel}
            </section>
            ` : ''}

            <section class="analytics-section">
                <header class="analytics-section__head">
                    <h3 class="analytics-section__title">All payments</h3>
                    <p class="analytics-section__sub">
                        Money you've received from every source.
                    </p>
                </header>

                ${revenueSplit ? `
                <div class="analytics-panel">
                    <div class="analytics-panel__head">
                        <h4>Where your money comes from</h4>
                    </div>
                    <div class="analytics-split">
                        <div class="analytics-split__bar" aria-hidden="true">
                            <div class="analytics-split__seg analytics-split__seg--invoice"
                                 style="width:${revenueSplit.invoicePct}%"></div>
                            <div class="analytics-split__seg analytics-split__seg--paylink"
                                 style="width:${revenueSplit.paylinkPct}%"></div>
                        </div>
                        <div class="analytics-split__legend">
                            <span class="analytics-split__item">
                                <span class="analytics-split__dot analytics-split__dot--invoice"></span>
                                Invoices ${revenueSplit.invoicePct}% · ₦${revenueSplit.invoice.toLocaleString()}
                            </span>
                            <span class="analytics-split__item">
                                <span class="analytics-split__dot analytics-split__dot--paylink"></span>
                                Paylink ${revenueSplit.paylinkPct}% · ₦${revenueSplit.paylink.toLocaleString()}
                            </span>
                        </div>
                    </div>
                </div>
                ` : ''}

                <div class="analytics-panel">
                    <div class="analytics-panel__head">
                        <h4>This month</h4>
                        <span class="analytics-panel__delta ${monthDelta.tone}">
                            ${monthDelta.label}
                        </span>
                    </div>
                    <p class="analytics-panel__value">₦${thisMonth.toLocaleString()}</p>
                    ${lastMonth > 0 ? `
                    <p class="analytics-panel__sub">vs ₦${lastMonth.toLocaleString()} last month</p>
                    ` : `<p class="analytics-panel__sub">No revenue last month</p>`}
                </div>

                <div class="analytics-panel">
                    <div class="analytics-panel__head">
                        <h4>7-Day Performance</h4>
                    </div>
                    <div class="trend-chart-container">
                        ${this.generateTrendChart(dailyViews, dailyClicks)}
                    </div>
                </div>

                ${bestWeekday ? `
                <div class="analytics-panel">
                    <div class="analytics-panel__head">
                        <h4>When you get paid</h4>
                    </div>
                    <p class="analytics-panel__value analytics-panel__value--accent">
                        ${bestWeekday.label}
                    </p>
                    <p class="analytics-panel__sub">Strongest day by payment volume</p>
                </div>
                ` : ''}

                ${payments.length > 0 ? `
                <div class="analytics-panel analytics-panel--payments">
                    <div class="analytics-panel__head">
                        <h4>Recent payments</h4>
                        <span class="analytics-panel__count">${payments.length}</span>
                    </div>
                    <ul class="analytics-payments">
                        ${payments.map(p => `
                            <li class="analytics-payment">
                                <div class="analytics-payment__main">
                                    <p class="analytics-payment__amount">₦${Number(p.amount || 0).toLocaleString()}</p>
                                    <p class="analytics-payment__meta">
                                        <span class="analytics-payment__tag analytics-payment__tag--${p.source}">
                                            ${p.source === 'invoice' ? 'Invoice' : 'Paylink'}
                                        </span>
                                        <span class="analytics-payment__date">${this.formatPaymentDate(p.paid_at)}</span>
                                    </p>
                                </div>
                                ${p.client_email ? `
                                    <span class="analytics-payment__email">${p.client_email}</span>
                                ` : ''}
                            </li>
                        `).join('')}
                    </ul>
                </div>
                ` : ''}
            </section>
        `;
    }

    /**
     * Build the funnel bars. Returns null if there is nothing to show.
     * Each stage is rendered as a horizontal bar whose width is
     * proportional to the first stage (views).
     */
    buildFunnel(funnel) {
        const views = Number(funnel.views || 0);
        const taps = Number(funnel.taps || 0);
        const attempts = Number(funnel.attempts || 0);
        const paid = Number(funnel.paid || 0);

        if (views <= 0 && taps <= 0 && attempts <= 0 && paid <= 0) {
            return null;
        }

        const base = Math.max(views, taps, attempts, paid, 1);

        const stages = [
            { key: 'views', label: 'Link views', value: views },
            { key: 'taps', label: 'Transfer taps', value: taps },
            { key: 'attempts', label: 'Payment attempts', value: attempts },
            { key: 'paid', label: 'Payments received', value: paid },
        ];

        const total = stages[0].value || 1;

        return `
            <div class="analytics-funnel">
                ${stages.map((stage, index) => {
                    const widthPct = (stage.value / base) * 100;
                    const ofTotal = total > 0
                        ? Math.round((stage.value / total) * 100)
                        : 0;

                    const showPct = index > 0 && total > 0;

                    return `
                        <div class="analytics-funnel__stage">
                            <div class="analytics-funnel__labels">
                                <span class="analytics-funnel__label">${stage.label}</span>
                                <span class="analytics-funnel__value">
                                    ${stage.value.toLocaleString()}${showPct ? ` · ${ofTotal}%` : ''}
                                </span>
                            </div>
                            <div class="analytics-funnel__track">
                                <div class="analytics-funnel__fill" style="width:${widthPct}%"></div>
                            </div>
                        </div>
                    `;
                }).join('')}
            </div>
        `;
    }

    revenueSplit(invoiceAmount, paylinkAmount) {
        const invoice = Number(invoiceAmount || 0);
        const paylink = Number(paylinkAmount || 0);
        const total = invoice + paylink;

        if (total <= 0) return null;

        return {
            invoice,
            paylink,
            invoicePct: Math.round((invoice / total) * 100),
            paylinkPct: Math.round((paylink / total) * 100),
        };
    }

    monthOverMonth(thisMonth, lastMonth) {
        if (lastMonth <= 0 && thisMonth <= 0) {
            return { tone: 'neutral', label: 'No activity yet' };
        }

        if (lastMonth <= 0) {
            return { tone: 'up', label: 'New this month' };
        }

        const delta = ((thisMonth - lastMonth) / lastMonth) * 100;
        const rounded = Math.round(delta);

        if (rounded === 0) {
            return { tone: 'neutral', label: 'No change' };
        }

        if (rounded > 0) {
            return { tone: 'up', label: `+${rounded}% vs last month` };
        }

        return { tone: 'down', label: `${rounded}% vs last month` };
    }

    bestWeekday(totals) {
        if (!totals || typeof totals !== 'object') return null;

        const labels = {
            mon: 'Mondays', tue: 'Tuesdays', wed: 'Wednesdays',
            thu: 'Thursdays', fri: 'Fridays', sat: 'Saturdays', sun: 'Sundays',
        };

        let best = null;
        let bestAmount = 0;

        Object.entries(totals).forEach(([key, value]) => {
            const amount = Number(value || 0);
            if (amount > bestAmount) {
                bestAmount = amount;
                best = key;
            }
        });

        if (!best || bestAmount <= 0) return null;

        return { key: best, amount: bestAmount, label: labels[best] };
    }

    formatPaymentDate(value) {
        if (!value) return '—';

        let date;
        if (typeof value === 'number') {
            date = new Date(value * 1000);
        } else if (typeof value === 'object' && value.seconds) {
            date = new Date(value.seconds * 1000);
        } else {
            date = new Date(value);
        }

        if (Number.isNaN(date.getTime())) return '—';

        return date.toLocaleDateString('en-NG', {
            day: 'numeric', month: 'short',
        });
    }

    generateTrendChart(dailyViews, dailyClicks) {
        const dates = Object.keys(dailyViews).sort().slice(-7);
        if (dates.length === 0) return '<p class="no-data">No trend data available yet</p>';

        const maxViews = Math.max(...Object.values(dailyViews), 1);
        const maxClicks = Math.max(...Object.values(dailyClicks), 1);
        const overallMax = Math.max(maxViews, maxClicks);

        return `
            <div class="trend-bars">
                ${dates.map(date => {
                    const views = dailyViews[date] || 0;
                    const clicks = dailyClicks[date] || 0;
                    const vHeight = (views / overallMax) * 100;
                    const cHeight = (clicks / overallMax) * 100;

                    return `
                        <div class="trend-bar-group">
                            <div class="bar-stack">
                                <div class="bar views" style="height: ${vHeight}%" title="${views} Views"></div>
                                <div class="bar clicks" style="height: ${cHeight}%" title="${clicks} Clicks"></div>
                            </div>
                            <div class="date-label">${new Date(date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}</div>
                        </div>
                    `;
                }).join('')}
            </div>
            <div class="trend-legend">
                <span class="legend-item"><div class="legend-color views"></div> Views</span>
                <span class="legend-item"><div class="legend-color clicks"></div> Clicks</span>
            </div>
        `;
    }

    copyPaylink() {
        const urlEl = document.getElementById('paylink-url');
        const fullUrl = urlEl?.dataset?.fullUrl || urlEl?.textContent;

        if (fullUrl) {
            navigator.clipboard.writeText(fullUrl).then(() => {
                window.dashboard?.showToast?.('Paylink copied');
                this.copyLinkBtn.classList.add('success');
                setTimeout(() => {
                    this.copyLinkBtn.classList.remove('success');
                }, 1000);
            });
        }
    }

    setupAutoRefresh(interval = 300000) {
        setInterval(async () => {
            try {
                await this.loadNotifications();
                this.updatePaylinkInfo();
                this.updateNotificationBadge();
            } catch (error) {
                console.error("Enhancements auto-refresh failed:", error);
            }
        }, interval);
    }

    setupUIEnhancements() {
        this.animateNewInvoices();
        this.setupSmoothAnimations();
    }

    animateNewInvoices() {
        const cards = document.querySelectorAll('.invoice-card');
        cards.forEach((card, index) => {
            card.style.animation = `cardAppear 0.5s ease-out ${index * 0.05}s forwards`;
        });
    }

    setupSmoothAnimations() {
        const filterBtns = document.querySelectorAll('.filter-btn');
        filterBtns.forEach(btn => {
            btn.addEventListener('mouseenter', () => {
                btn.style.transform = 'translateY(-2px)';
            });
            btn.addEventListener('mouseleave', () => {
                btn.style.transform = 'translateY(0)';
            });
        });
    }
}

let enhancements;
document.addEventListener('DOMContentLoaded', async () => {
    if (window.enhancementsInstance) return;

    await new Promise(resolve => setTimeout(resolve, 0));

    if (!window.dashboard) {
        console.error('Dashboard not loaded yet');
        return;
    }

    try {
        if (!window.dashboard.dashboardData) {
            await window.dashboard.loadDashboardData();
        }

        enhancements = new DashboardEnhancements();
        window.enhancements = enhancements;
    } catch (err) {
        console.error("Enhancement Init Error:", err);
    }
});

export { DashboardEnhancements, enhancements };