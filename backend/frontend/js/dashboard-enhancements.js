// Payla Dashboard - Enhancement Features
// Additional features: notifications, analytics, paylinks, and UI enhancements

import { dashboard } from './dashboard.js';
import { API_BASE } from './config.js';

document.addEventListener('DOMContentLoaded', async () => {
    if (!dashboard) {
        console.error('Dashboard not loaded yet');
        return;
    }

    await dashboard.loadDashboardData();

    window.enhancements = new DashboardEnhancements();
});


class DashboardEnhancements {
    constructor() {
        this.API_BASE = API_BASE;
        this.init();
    }

    init() {
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

        // Paylink Toggle Elements
        this.paylinkToggle = document.getElementById('paylink-toggle');
        this.statusBadge = document.getElementById('status-badge');

        // Enhancement State
        this.notifications = [];
        this.analyticsData = null;
        this.isProcessingToggle = false;

        // Setup Enhancement Event Listeners
        this.setupEnhancementListeners();

        // Initialize Enhancements
        this.initEnhancements();
    }

    setupEnhancementListeners() {
        // Copy link button
        if (this.copyLinkBtn) {
            this.copyLinkBtn.addEventListener('click', () => {
                this.copyPaylink();
            });
        }

        // Notifications button
        if (this.notificationsBtn) {
            this.notificationsBtn.addEventListener('click', () => {
                this.openNotificationsModal();
            });
        }

        // Analytics button
        if (this.analyticsBtn) {
            this.analyticsBtn.addEventListener('click', () => {
                this.openAnalyticsModal();
            });
        }

        // Paylink toggle (FIXED — use click instead of change)
        if (this.paylinkToggle) {
            this.paylinkToggle.addEventListener('click', (e) => {
                // The checkbox state will already reflect new state on click
                const isActive = e.target.checked;
                console.log("Toggle clicked:", isActive);
                this.handlePaylinkToggle(isActive);
            });
        }

        // Modal close buttons
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

        // Close enhancement modals with Escape key
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                this.closeNotificationsModal();
                this.closeAnalyticsModal();
            }
        });
    }

    async initEnhancements() {
        try {
            await this.loadEnhancementData();
            this.updatePaylinkInfo();
            this.updateNotificationBadge();
            this.initializePaylinkToggle();
            this.setupAutoRefresh();
            this.setupUIEnhancements();
        } catch (error) {
            console.error('Failed to initialize enhancements:', error);
        }
    }

    async loadEnhancementData() {
        try {
            const token = this.getAuthToken();
            if (!token) {
                console.error('No authentication token found');
                return;
            }

            // Load notifications
            const notificationsResponse = await fetch(`${this.API_BASE}/dashboard/notifications`, {
                headers: {
                    'Authorization': `Bearer ${token}`
                }
            });
            
            if (notificationsResponse.ok) {
                this.notifications = await notificationsResponse.json();
                console.log('Loaded notifications:', this.notifications.length);
            } else {
                console.error('Failed to load notifications:', notificationsResponse.status);
            }

            // Load analytics
            const analyticsResponse = await fetch(`${this.API_BASE}/dashboard/analytics/`, {
                headers: {
                    'Authorization': `Bearer ${token}`
                }
            });
            
            if (analyticsResponse.ok) {
                this.analyticsData = await analyticsResponse.json();
                console.log('Loaded analytics data');
            } else {
                console.error('Failed to load analytics:', analyticsResponse.status);
            }

        } catch (error) {
            console.error('Error loading enhancement data:', error);
        }
    }

    getAuthToken() {
        return localStorage.getItem('idToken') || '';
    }

    // Initialize paylink toggle state
    initializePaylinkToggle() {
        const paylink = dashboard?.dashboardData?.paylink;
        if (!paylink) {
            console.log('No paylink data found for toggle initialization');
            return;
        }

        const isActive = paylink.active !== false;
        console.log('Initializing toggle with active state:', isActive);
        
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

    // Handle toggle state changes
    async handlePaylinkToggle(isActive) {
        if (this.isProcessingToggle) {
            console.log('Toggle operation already in progress, skipping');
            return;
        }

        this.isProcessingToggle = true;
        console.log('Processing toggle change to:', isActive);

        try {
            if (isActive) {
                await this.activatePaylink();
            } else {
                await this.deactivatePaylink();
            }
        } catch (error) {
            console.error('Toggle operation failed:', error);
            // Revert toggle state on error
            if (this.paylinkToggle) {
                this.paylinkToggle.checked = !isActive;
            }
            this.showToggleErrorModal(isActive, error);
        } finally {
            this.isProcessingToggle = false;
        }
    }

    async activatePaylink() {
        const token = this.getAuthToken();
        if (!token) {
            throw new Error('No authentication token found');
        }

        console.log('Activating paylink...');

        const response = await fetch(`${this.API_BASE}/paylinks/me/activate`, {
            method: 'PATCH',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            }
        });

        console.log('Activation response status:', response.status);

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
            throw new Error(errorData.detail || 'Failed to activate paylink');
        }

        // Update UI
        if (this.statusBadge) {
            this.statusBadge.textContent = 'Active';
            this.statusBadge.classList.remove('inactive');
            this.statusBadge.classList.add('active');
        }

        // Update local data
        if (dashboard?.dashboardData?.paylink) {
            dashboard.dashboardData.paylink.active = true;
        }

        if (dashboard) {
            dashboard.showToast('Paylink activated successfully!', 'success');
        }

        console.log('Paylink activated successfully');
    }

    async deactivatePaylink() {
        const token = this.getAuthToken();
        if (!token) {
            throw new Error('No authentication token found');
        }

        console.log('Starting deactivation process...');

        // Show confirmation modal
        const confirmed = await this.showDeactivationConfirmation();
        if (!confirmed) {
            console.log('Deactivation cancelled by user');
            if (this.paylinkToggle) {
                this.paylinkToggle.checked = true; // Revert to active
            }
            return;
        }

        console.log('User confirmed deactivation, making API call...');

        const response = await fetch(`${this.API_BASE}/paylinks/me/deactivate`, {
            method: 'PATCH',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            }
        });

        console.log('Deactivation response status:', response.status);

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
            throw new Error(errorData.detail || 'Failed to deactivate paylink');
        }

        // Update UI
        if (this.statusBadge) {
            this.statusBadge.textContent = 'Inactive';
            this.statusBadge.classList.remove('active');
            this.statusBadge.classList.add('inactive');
        }

        // Update local data
        if (dashboard?.dashboardData?.paylink) {
            dashboard.dashboardData.paylink.active = false;
        }

        if (dashboard) {
            dashboard.showToast('Paylink deactivated', 'info');
        }

        console.log('Paylink deactivated successfully');
    }

    // Show deactivation confirmation modal
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

            // Close on overlay click
            modal.addEventListener('click', (e) => {
                if (e.target === modal) {
                    cleanup();
                    resolve(false);
                }
            });

            // Close on Escape key
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

    // Show error modal when toggle operation fails
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


    updatePaylinkInfo() {
        const paylink = dashboard?.dashboardData?.paylink;
        // Get the fresh analytics data we loaded in loadEnhancementData()
        const analytics = this.analyticsData; 

        if (!paylink) return;

        // 1. Update Paylink URL Display
        const urlEl = document.getElementById('paylink-url');
        if (urlEl) {
            const fullUrl = paylink.url || `https://payla.ng/@${dashboard.dashboardData.user.username}`;
            urlEl.textContent = fullUrl.replace(/^https?:\/\//, '');
            urlEl.dataset.fullUrl = fullUrl;
        }
        const userEl = document.getElementById('user-paylink');
        if (userEl) {
            const userUrl = paylink.url || `https://payla.ng/@${dashboard.dashboardData.user.username}`;
            userEl.textContent = userUrl.replace(/^https?:\/\//, '');
            userEl.dataset.userUrl = userUrl;
        }

        // 2. DATA SOURCE FIX: Use Analytics first, fallback to Paylink object
        const totalReceived = analytics?.total_received ?? paylink.total_received ?? 0;
        const totalTransactions = analytics?.total_transactions ?? paylink.total_transactions ?? 0;
        
        // Success Rate Logic Fix:
        // If backend provides a string like "85%", use it. Otherwise calculate based on attempts.
        let successRate = "0%";
        if (analytics?.success_rate) {
            successRate = analytics.success_rate;
        } else if (paylink.total_requested > 0) {
            successRate = `${Math.round((totalReceived / paylink.total_requested) * 100)}%`;
        }

        // 3. Update the UI Elements
        const receivedEl = document.getElementById('paylink-received');
        const transactionsEl = document.getElementById('paylink-transactions');
        const successRateEl = document.getElementById('paylink-success-rate');

        if (receivedEl) {
            // Formats 1229 into 1,229
            receivedEl.textContent = `₦${totalReceived.toLocaleString()}`;
        }
        if (transactionsEl) {
            transactionsEl.textContent = totalTransactions;
        }
        if (successRateEl) {
            successRateEl.textContent = successRate;
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
                    <p>You're all caught up!</p>
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
                <button class="mark-read-btn" onclick="enhancements.markNotificationRead('${notification.id}')">
                    <i class="fas fa-check"></i>
                </button>
                ` : ''}
            </div>
        `).join('');
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
                // Update local state
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

    async openAnalyticsModal() {
        await this.renderAnalytics();
        this.analyticsModal.classList.add('open');
        document.body.style.overflow = 'hidden';
    }

    closeAnalyticsModal() {
        this.analyticsModal.classList.remove('open');
        document.body.style.overflow = 'auto';
    }

async renderAnalytics() {
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

        // Metrics Calculation
        const totalReceived = analytics.total_received ?? 0;
        const totalTransactions = analytics.total_transactions ?? 0;
        const totalRequested = analytics.total_requested ?? 0;
        // FIX: Compare transaction count to requested attempts
        const successRate = totalRequested > 0 ? Math.round((totalTransactions / totalRequested) * 100) : 0;    
        
        const pageViews = analytics.page_views ?? 0;
        const transferClicks = analytics.transfer_clicks ?? 0;
        const conversionRate = pageViews > 0 ? Math.round((transferClicks / pageViews) * 100) : 0;

        const dailyViews = analytics.daily_page_views ?? {};
        const dailyClicks = analytics.daily_transfer_clicks ?? {};

        this.analyticsContent.innerHTML = `
            <div class="analytics-overview">
                <div class="analytics-stat">
                    <div class="analytics-value">₦${totalReceived.toLocaleString()}</div>
                    <div class="analytics-label">Total Received</div>
                </div>
                <div class="analytics-stat">
                    <div class="analytics-value">${totalTransactions}</div>
                    <div class="analytics-label">Total Transactions</div>
                </div>
                <div class="analytics-stat">
                    <div class="analytics-value">${successRate}%</div>
                    <div class="analytics-label">Success Rate</div>
                </div>
                <div class="analytics-stat">
                    <div class="analytics-value">${pageViews}</div>
                    <div class="analytics-label">Page Views</div>
                </div>
                <div class="analytics-stat">
                    <div class="analytics-value">${conversionRate}%</div>
                    <div class="analytics-label">Conversion Rate</div>
                </div>
            </div>

            <div class="analytics-trends">
                <h4>7-Day Performance</h4>
                <div class="trend-chart-container">
                    ${this.generateTrendChart(dailyViews, dailyClicks)}
                </div>
            </div>

            <div class="analytics-chart-placeholder">
                <i class="fas fa-chart-bar"></i>
                <p>Advanced analytics and revenue charts coming soon</p>
                <small>Real-time tracking and detailed insights</small>
            </div>
        `;
    }

    generateTrendChart(dailyViews, dailyClicks) {
        // Get last 7 days keys
        const dates = Object.keys(dailyViews).sort().slice(-7);
        if (dates.length === 0) return '<p class="no-data">No trend data available yet</p>';

        // Find max value to scale the bars relative to the highest peak
        const maxViews = Math.max(...Object.values(dailyViews), 1); 
        const maxClicks = Math.max(...Object.values(dailyClicks), 1);
        const overallMax = Math.max(maxViews, maxClicks);

        return `
            <div class="trend-bars">
                ${dates.map(date => {
                    const views = dailyViews[date] || 0;
                    const clicks = dailyClicks[date] || 0;
                    // Calculate heights
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
                if (dashboard) dashboard.showToast('Paylink copied ♡');
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
                await this.loadEnhancementData();
                this.updatePaylinkInfo();
                this.updateNotificationBadge();
                console.log("Dashboard enhancements auto-refreshed");
            } catch (error) {
                console.error("Enhancements auto-refresh failed:", error);
            }
        }, interval);
    }

    setupUIEnhancements() {
        this.animateNewInvoices();
        this.highlightOverdueInvoices();
        this.setupSmoothAnimations();
    }

    animateNewInvoices() {
        const cards = document.querySelectorAll('.invoice-card');
        cards.forEach((card, index) => {
            card.style.animation = `cardAppear 0.5s ease-out ${index * 0.1}s forwards`;
        });
    }

    highlightOverdueInvoices() {
        const overdueCards = document.querySelectorAll('.invoice-card[data-status="overdue"]');
        overdueCards.forEach(card => {
            card.style.border = '2px solid #e74c3c';
            card.style.boxShadow = '0 0 10px rgba(231, 76, 60, 0.3)';
        });
    }

    setupSmoothAnimations() {
        // Add smooth transitions for filter buttons
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

// Initialize enhancements when DOM is loaded
let enhancements;
document.addEventListener('DOMContentLoaded', () => {
    if (typeof dashboard !== 'undefined') {
        enhancements = new DashboardEnhancements();
    } else {
        console.error('Dashboard core not initialized. Enhancements disabled.');
    }
});

// Export for potential module usage
export { DashboardEnhancements, enhancements };