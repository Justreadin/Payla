// Payla Dashboard - Core Luxury Fintech Experience
// Core dashboard functionality: invoices, stats, auth, and basic data management
import { API_BASE } from './config.js';
class PaylaDashboard {
    constructor() {
        this.API_BASE = API_BASE;
        this.refreshInterval = null;
        this.isRefreshing = false;
        this.init();
    }

    init() {
        // Core DOM Elements
        this.avatarBtn = document.getElementById('avatar-btn');
        this.dropdown = document.getElementById('dropdown');
        this.filterBtns = document.querySelectorAll('.filter-btn');
        this.invoiceCards = document.getElementById('invoiceCards');
        this.viewMoreBtn = document.getElementById('viewMoreBtn');
        this.viewMoreSection = document.getElementById('viewMoreSection');
        this.fab = document.getElementById('fab');
        this.quickInvoiceModal = document.getElementById('quick-invoice-modal');
        this.modalClose = document.getElementById('modal-close');
        this.quickInvoiceForm = document.getElementById('quick-invoice-form');
        this.allInvoicesModal = document.getElementById('all-invoices-modal');
        this.allInvoicesClose = document.getElementById('all-invoices-close');
        this.invoicesGrid = document.getElementById('invoicesGrid');
        this.invoiceDetailModal = document.getElementById('invoice-detail-modal');
        this.invoiceDetailClose = document.getElementById('invoice-detail-close');
        this.invoiceDetailContent = document.getElementById('invoiceDetailContent');
        this.toast = document.getElementById('toast');
        this.toastMessage = document.getElementById('toast-message');

        // Core State
        this.activeFilter = null;
        this.dropdownOpen = false;
        this.maxVisibleCards = 4;
        this.allInvoices = [];
        this.dashboardData = null;

        // Core Event Listeners
        this.setupCoreEventListeners();
        this.initDashboard();
        
        // Start auto-refresh every 30 seconds
        this.startAutoRefresh(30000);
    }

    startAutoRefresh(ms) {
        if (this.refreshInterval) clearInterval(this.refreshInterval);
        this.refreshInterval = setInterval(() => {
            this.refreshDashboard();
        }, ms)   
    }

    async refreshDashboard() {
        if (this.isRefreshing) return;
        
        try {
            this.isRefreshing = true;
            // Fetch fresh data
            await this.loadDashboardData();
            
            // Re-render UI components with new data
            this.updateStats();
            this.renderInvoiceCards();
            this.updateFilterCounts();
            
            console.log('🔄 Dashboard auto-refreshed at:', new Date().toLocaleTimeString());
        } catch (error) {
            console.error('Auto-refresh failed:', error);
        } finally {
            this.isRefreshing = false;
        }
    }

    // Optional: Stop refreshing when the user leaves the tab to save resources
    setupResponsiveBehavior() {
        document.addEventListener('visibilitychange', () => {
            if (document.hidden) {
                clearInterval(this.refreshInterval);
            } else {
                this.startAutoRefresh(30000);
                this.refreshDashboard(); // Refresh immediately when coming back
            }
        });
    }

    async checkAccess() {
        const res = await authFetch(`${BACKEND_URL}/api/onboarding/me`);
        if (!res) return;

        const user = await res.json();

        // 1. If onboarding isn't even done, send them back to onboarding
        if (!user.onboarding_complete) {
            window.location.href = '/onboarding';
            return;
        }

        // 2. Logic to check if trial/subscription is expired
        const now = new Date();
        const trialEnd = user.trial_end_date ? new Date(user.trial_end_date) : null;
        const subEnd = user.subscription_end ? new Date(user.subscription_end) : null;
        const presellEnd = user.presell_end_date ? new Date(user.presell_end_date) : null;

        // Is there any active access?
        const hasAccess = 
            (presellEnd && presellEnd > now) || 
            (user.subscription_id && subEnd > now) || 
            (trialEnd && trialEnd > now);

        if (!hasAccess) {
            // Redirect to billing with a 'reason' parameter
            window.location.href = '/subscription?reason=expired';
        }
    }

    setupCoreEventListeners() {
        // Avatar dropdown
        this.avatarBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            this.toggleDropdown();
        });

        // Close dropdown when clicking outside
        document.addEventListener('click', () => {
            if (this.dropdownOpen) {
                this.closeDropdown();
            }
        });

        // Filter buttons
        this.filterBtns.forEach(btn => {
            btn.addEventListener('click', () => {
                const filter = btn.getAttribute('data-filter');
                this.toggleFilter(filter, btn);
            });
        });

        // View More button
        this.viewMoreBtn.addEventListener('click', () => {
            this.openAllInvoicesModal();
        });

        // FAB - Quick Invoice
        this.fab.addEventListener('click', () => {
            this.openQuickInvoice();
        });

        // Modal close buttons
        this.modalClose.addEventListener('click', () => {
            this.closeQuickInvoice();
        });

        this.allInvoicesClose.addEventListener('click', () => {
            this.closeAllInvoicesModal();
        });

        this.invoiceDetailClose.addEventListener('click', () => {
            this.closeInvoiceDetailModal();
        });

        // Quick invoice form
        this.quickInvoiceForm.addEventListener('submit', (e) => {
            e.preventDefault();
            this.submitQuickInvoice();
        });

        // Close modals when clicking outside
        this.setupModalCloseListeners();

        // Card actions delegation
        this.setupCardActions();
    }

    setupModalCloseListeners() {
        // Close modals when clicking on overlay
        document.querySelectorAll('.modal-overlay').forEach(overlay => {
            overlay.addEventListener('click', (e) => {
                if (e.target === overlay) {
                    overlay.classList.remove('open');
                    document.body.style.overflow = 'auto';
                }
            });
        });

        // Close modals with Escape key
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                this.closeQuickInvoice();
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
                case 'Resend':
                    this.resendInvoice(card);
                    break;
                case 'Delete Invoice':
                    await this.deleteInvoice(card, invoiceId);
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

            // Remove card from DOM
            card.remove();
            this.showToast('Invoice deleted successfully ♡');

            // Update local state
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
            this.setupResponsiveBehavior();
        } catch (error) {
            console.error('Failed to initialize dashboard:', error);
            this.showToast('Failed to load dashboard data. Please refresh.', true);
        }
    }

    async loadDashboardData() {
        try {
            const response = await fetch(`${this.API_BASE}/dashboard/`, {
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

            console.log('📊 Dashboard Data Loaded:', this.dashboardData);
            console.log('📈 Stats:', this.dashboardData.stats);
            console.log('📋 Invoices:', this.dashboardData.invoices.length);

            // Map invoices with proper ID handling
            this.allInvoices = this.dashboardData.invoices.map(inv => ({
                ...inv,
                id: inv._id || inv.id // Use _id from backend, fallback to id
            }));

            // Debug: Log invoice statuses
            const statusBreakdown = this.allInvoices.reduce((acc, inv) => {
                acc[inv.status] = (acc[inv.status] || 0) + 1;
                return acc;
            }, {});
            
            console.log('📊 Invoice Status Breakdown:', statusBreakdown);

            // Debug: Log overdue invoices
            const overdueInvoices = this.allInvoices.filter(inv => inv.status === 'overdue');
            console.log('⏰ Overdue Invoices:', overdueInvoices.length, overdueInvoices);

        } catch (error) {
            console.error('Error loading dashboard data:', error);
            throw error;
        }
    }
    getAuthToken() {
        // This should be implemented based on your auth system
        return localStorage.getItem('idToken') || '';
    }

    updateStats() {
        if (!this.dashboardData || !this.dashboardData.stats) return;

        const stats = this.dashboardData.stats;

        // Update Total Earned with "First Payment Pending" message
        const totalEarnedEl = document.getElementById('total-earned');
        if (stats.has_earnings) {
            totalEarnedEl.textContent = `₦${stats.total_earned?.toLocaleString() || '0'}`;
            totalEarnedEl.style.fontSize = ''; // Reset font size
        } else {
            totalEarnedEl.textContent = 'First Payment Pending';
            totalEarnedEl.style.fontSize = '1.1rem'; // Smaller font for longer text
        }

        // Update Pending Amount
        document.getElementById('pending-amount').textContent = `₦${stats.pending_amount?.toLocaleString() || '0'}`;
        
        // Update Total Invoices
        document.getElementById('total-invoices').textContent = stats.total_invoices || '0';
        
        // Update Overdue Count with Amount and Count
        const overdueCountEl = document.getElementById('overdue-count');
        if (stats.overdue_count > 0) {
            overdueCountEl.textContent = `₦${stats.overdue_amount?.toLocaleString() || '0'} (${stats.overdue_count}) Overdue`;
            overdueCountEl.style.color = '#ff4757'; // Red color for overdue
        } else {
            overdueCountEl.textContent = '0 Overdue';
            overdueCountEl.style.color = ''; // Reset color
        }
        
        // Update Growth Trend
        document.getElementById('growth-trend').innerHTML = `<i class="fas fa-arrow-up"></i> ${stats.growth_trend || '0%'} from last month`;
    }

    renderInvoiceCards() {
        // Apply filter if active
        let displayInvoices = this.allInvoices;
        
        if (this.activeFilter) {
            displayInvoices = this.allInvoices.filter(inv => inv.status === this.activeFilter);
        }
        
        const visibleInvoices = displayInvoices.slice(0, this.maxVisibleCards);
        this.invoiceCards.innerHTML = '';

        if (visibleInvoices.length === 0) {
            // Check if we have invoices but they're filtered out
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

        // Show/hide view more button based on filtered invoices
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

    getClientInitials(clientName) {
        if (!clientName) return 'NC';
        return clientName
            .split(' ')
            .map(word => word.charAt(0))
            .join('')
            .toUpperCase()
            .slice(0, 2);
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
                <button class="action-btn" title="Resend" data-id="${invoiceId}">
                    <i class="fas fa-redo"></i>
                </button>
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

        console.log('Filter counts:', counts); // Debug log

        this.filterBtns.forEach(btn => {
            const filter = btn.getAttribute('data-filter');
            const countElement = btn.querySelector('.filter-count');
            if (countElement) {
                countElement.textContent = counts[filter] || '0';
                
                // Highlight filters with items
                if (counts[filter] > 0) {
                    countElement.style.opacity = '1';
                } else {
                    countElement.style.opacity = '0.5';
                }
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
            // Deactivate filter
            button.classList.remove('active');
            span.textContent = `Show ${this.capitalizeFirst(filter)}`;
            this.activeFilter = null;
        } else {
            // Deactivate all other filters
            this.filterBtns.forEach(btn => {
                btn.classList.remove('active');
                const btnSpan = btn.querySelector('span:first-child');
                const btnFilter = btn.getAttribute('data-filter');
                btnSpan.textContent = `Show ${this.capitalizeFirst(btnFilter)}`;
            });
            
            // Activate this filter
            button.classList.add('active');
            span.textContent = `Hide ${this.capitalizeFirst(filter)}`;
            this.activeFilter = filter;
        }

        // Re-render cards with filter
        this.renderInvoiceCards();

        // Animation
        button.style.transform = 'scale(0.95)';
        setTimeout(() => {
            button.style.transform = 'scale(1)';
        }, 150);
    }
    filterCards(status) {
        const allCards = document.querySelectorAll('.invoice-card');
        
        allCards.forEach(card => {
            const cardStatus = card.getAttribute('data-status');
            
            if (cardStatus === status) {
                card.style.display = 'block';
                card.style.animation = 'cardAppear 0.5s ease-out';
            } else {
                card.style.animation = 'fadeOut 0.3s ease-out';
                setTimeout(() => {
                    card.style.display = 'none';
                }, 300);
            }
        });

        // Update view more section visibility
        const visibleCards = Array.from(allCards).filter(card => card.style.display !== 'none');
        if (visibleCards.length > 0) {
            this.viewMoreSection.classList.remove('hidden');
        } else {
            this.viewMoreSection.classList.add('hidden');
        }
    }

    showAllCards() {
        const allCards = document.querySelectorAll('.invoice-card');
        
        allCards.forEach(card => {
            card.style.display = 'block';
            card.style.animation = 'cardAppear 0.5s ease-out';
        });

        if (this.allInvoices.length > this.maxVisibleCards) {
            this.viewMoreSection.classList.remove('hidden');
        } else {
            this.viewMoreSection.classList.add('hidden');
        }
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

        this.invoiceDetailContent.innerHTML = `
            <div class="invoice-detail-header">
                <div>
                    <h2 class="invoice-detail-title">${invoice.description || 'No description'}</h2>
                    <div class="invoice-detail-amount">${this.formatCurrency(invoice.amount, invoice.currency)}</div>
                </div>
                <div class="invoice-detail-status ${config.class}">
                    <i class="${this.getStatusIcon(invoice.status)}"></i>
                    ${config.label}
                </div>
            </div>

            <div class="invoice-detail-info">
                <div class="info-group">
                    <div class="info-label">Client Information</div>
                    ${invoice.client_phone ? `<div class="info-note">Phone: ${invoice.client_phone}</div>` : ''}
                    ${invoice.client_email ? `<div class="info-note">Email: ${invoice.client_email}</div>` : ''}
                </div>

                <div class="info-group">
                    <div class="info-label">Due Date</div>
                    <div class="info-value">${dueDate}</div>
                    <div class="info-note">${this.getDueDateNote(invoice)}</div>
                </div>

                <div class="info-group">
                    <div class="info-label">Created Date</div>
                    <div class="info-value">${createdAt}</div>
                </div>

                ${invoice.paid_date ? `
                <div class="info-group">
                    <div class="info-label">Paid Date</div>
                    <div class="info-value">${new Date(invoice.paid_date).toLocaleDateString('en-US', { 
                        year: 'numeric', 
                        month: 'long', 
                        day: 'numeric' 
                    })}</div>
                </div>
                ` : ''}
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
        if (invoice.status === 'paid') return 'Payment completed successfully.';
        if (invoice.status === 'overdue') return 'This invoice is past due. Consider sending a reminder.';
        if (invoice.status === 'failed') return 'Payment failed. You may want to resend this invoice.';
        return 'Awaiting payment from client.';
    }

    getDetailActions(invoice) {
        if (invoice.status === 'draft') {
            return `
                <button class="btn-primary" onclick="dashboard.editInvoice('${invoice.id}')">
                    <i class="fas fa-edit"></i>
                    Edit Draft
                </button>
                <button class="btn-secondary" onclick="dashboard.sendInvoice('${invoice.id}')">
                    <i class="fas fa-paper-plane"></i>
                    Send Now
                </button>
            `;
        }

        if (invoice.status === 'paid') {
            return `
                <button class="btn-secondary" onclick="dashboard.copyInvoiceLink('${invoice.id}')">
                    <i class="fas fa-copy"></i>
                    Copy Link
                </button>
                <button class="btn-primary" onclick="dashboard.downloadInvoice('${invoice.id}')">
                    <i class="fas fa-download"></i>
                    Download receipt
                </button>
            `;
        }

        if (invoice.status === 'overdue') {
            return `
            `;
        }

        if (invoice.status === 'failed') {
            return `
                <button class="btn-secondary" onclick="dashboard.resendInvoice('${invoice.id}')">
                    <i class="fas fa-redo"></i>
                    Resend Invoice
                </button>
            `;
        }

        return '';
    }

    openQuickInvoice() {
        this.quickInvoiceModal.classList.add('open');
        document.body.style.overflow = 'hidden';
        this.fab.style.transform = 'scale(0.9)';
        setTimeout(() => {
            this.fab.style.transform = 'scale(1)';
        }, 150);
    }

    closeQuickInvoice() {
        this.quickInvoiceModal.classList.remove('open');
        document.body.style.overflow = 'auto';
    }

    async submitQuickInvoice() {
        const description = document.getElementById('invoice-description').value;
        const amount = parseFloat(document.getElementById('invoice-amount').value);
        const currency = document.getElementById('invoice-currency').value;
        const dueDate = document.getElementById('due-date').value; // Changed from clientPhone

        const amountValue = parseFloat(document.getElementById('invoice-amount').value);
            if (isNaN(amountValue) || amountValue <= 0) {
                this.showToast('Amount must be a valid number', true);
                return;
            }

        if (!description.trim() || !dueDate.trim()) {
            this.showToast('Please fill in all required fields', true);
            return;
        }
        if (this.isSubmitting) return;

        this.showLoadingState();

        try {
            this.isSubmitting = true; // Set flag
            const submitBtn = this.quickInvoiceForm.querySelector('button[type="submit"]');
            if (submitBtn) submitBtn.disabled = true; // Disable button UI

            this.showLoadingState();
            const response = await fetch(`${this.API_BASE}/dashboard/quick-invoice`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${this.getAuthToken()}`
                },
                body: JSON.stringify({ 
                    description, 
                    amount, 
                    currency, 
                    due_date: dueDate, // Changed from client_phone
                })
            });

            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

            const result = await response.json();

            this.hideLoadingState();
            this.closeQuickInvoice();

            // Show success toast
            this.showToast('Invoice sent successfully ♡');

            if (result.invoice_url) {
                this.showInvoiceLinkModal(result.invoice_url, result.invoice_id);
            }

            this.quickInvoiceForm.reset();

            // Reload dashboard data
            await this.loadDashboardData();
            this.renderInvoiceCards();
            this.updateStats();
            this.updateFilterCounts();

        } catch (error) {
            console.error('Error creating quick invoice:', error);
            this.hideLoadingState();
            this.showToast('Failed to send invoice. Please try again.', true);
        } finally {
            this.isSubmitting = false; // Reset flag
            const submitBtn = this.quickInvoiceForm.querySelector('button[type="submit"]');
            if (submitBtn) submitBtn.disabled = false; // Re-enable button
            this.hideLoadingState();
        }
    }

    showInvoiceLinkModal(invoiceUrl, invoiceId) {
        let modal = document.getElementById('invoice-link-modal');

        // 1. SANITIZER: Fix double domain issue from backend
        // This looks for "payla.nghttps" and removes the "payla.ng" prefix
        let sanitizedUrl = invoiceUrl;
        if (sanitizedUrl.includes('payla.nghttp')) {
            sanitizedUrl = sanitizedUrl.replace('payla.nghttp', 'http');
        }

        // 2. Formatting for display
        const fullUrl = sanitizedUrl;
        const displayUrl = fullUrl.replace(/^https?:\/\//, '');

        if (!modal) {
            modal = document.createElement('div');
            modal.id = 'invoice-link-modal';
            modal.className = 'modal-overlay';
            modal.innerHTML = `
                <div class="modal compact-modal">
                    <button class="modal-close" id="invoice-link-close">
                        <i class="fas fa-times"></i>
                    </button>
                    <h2 class="modal-title">Invoice Created</h2>
                    <p class="modal-subtitle">Share this link with your client</p>
                    
                    <div class="link-container" style="margin: 20px 0;">
                        <div class="link-display" title="Click to preview invoice">
                            <i class="fas fa-link"></i>
                            <span class="link" id="invoice-link-url" style="cursor: pointer; text-decoration: underline;"></span>
                        </div>
                        <button class="copy-link-btn" id="copy-invoice-link-btn">
                            <i class="fas fa-copy"></i>
                            Copy Link
                        </button>
                    </div>
                    
                    <div class="modal-actions" style="display: flex; gap: 10px; justify-content: center;">
                        <button class="btn-primary" id="share-whatsapp-btn" style="display: flex; align-items: center; gap: 8px;">
                            Share on WhatsApp
                        </button>
                    </div>
                </div>
            `;
            document.body.appendChild(modal);

            // --- Event Listeners (Initialized once) ---

            // Close button
            modal.querySelector('#invoice-link-close').addEventListener('click', () => {
                modal.classList.remove('open');
                document.body.style.overflow = 'auto';
            });

            // Copy full URL (with https)
            modal.querySelector('#copy-invoice-link-btn').addEventListener('click', () => {
                const fullLink = modal.querySelector('#invoice-link-url').dataset.fullUrl;
                navigator.clipboard.writeText(fullLink).then(() => {
                    this.showToast('Invoice link copied!');
                });
            });

            // Share WhatsApp (with https)
            modal.querySelector('#share-whatsapp-btn').addEventListener('click', () => {
                const fullLink = modal.querySelector('#invoice-link-url').dataset.fullUrl;
                const message = `Hello! Here's your invoice: ${fullLink}`;
                const whatsappUrl = `https://wa.me/?text=${encodeURIComponent(message)}`;
                window.open(whatsappUrl, '_blank');
            });

            // Close on overlay click
            modal.addEventListener('click', (e) => {
                if (e.target === modal) {
                    modal.classList.remove('open');
                    document.body.style.overflow = 'auto';
                }
            });

            // Close on Escape
            document.addEventListener('keydown', (e) => {
                if (e.key === 'Escape' && modal.classList.contains('open')) {
                    modal.classList.remove('open');
                    document.body.style.overflow = 'auto';
                }
            });
        }

        // --- Update Content for current invoice ---
        const linkEl = modal.querySelector('#invoice-link-url');

        if (linkEl) {
            linkEl.textContent = '';
            // Clear previous content and set clean display text
            linkEl.textContent = displayUrl; 
            
            // Store the full URL in a data attribute for the copy/share buttons
            linkEl.dataset.fullUrl = fullUrl;

            linkEl.style.textDecoration = 'none';
            
            // Preview on click
            linkEl.onclick = () => {
                window.open(fullUrl, '_blank', 'noopener');
            };
        }

        // Show modal
        modal.classList.add('open');
        document.body.style.overflow = 'hidden';
    }


    showLoadingState() {
        const submitBtn = this.quickInvoiceForm.querySelector('.submit-btn');
        submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>Sending...';
        submitBtn.disabled = true;
        submitBtn.classList.add('loading');
    }

    hideLoadingState() {
        const submitBtn = this.quickInvoiceForm.querySelector('.submit-btn');
        submitBtn.innerHTML = '<i class="fas fa-paper-plane"></i>Send Invoice Now<div class="btn-glow"></div>';
        submitBtn.disabled = false;
        submitBtn.classList.remove('loading');
    }

    // Card action handlers
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
            navigator.clipboard.writeText(invoice.invoice_url).then(() => {
                this.showToast('Invoice link copied ♡');
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

    };

    remindClient(card) {
        const invoiceId = typeof card === 'string' ? card : card.getAttribute('data-id');
        this.showToast('Reminder sent ♡');
        
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

    resendInvoice(card) {
        const invoiceId = typeof card === 'string' ? card : card.getAttribute('data-id');
        this.showToast('Invoice resent ♡');
    }

    capitalizeFirst(string) {
        return string.charAt(0).toUpperCase() + string.slice(1);
    }

    showToast(message, isError = false, duration = 3000) {
        this.toastMessage.textContent = message;
        this.toast.className = 'toast';
        if (isError) this.toast.classList.add('error');
        this.toast.classList.add('show');

        setTimeout(() => {
            this.toast.classList.remove('show');
        }, duration);
    }


    setupResponsiveBehavior() {
        window.addEventListener('resize', () => {
            this.adjustLayoutForMobile();
        });
        
        this.adjustLayoutForMobile();
    }

    adjustLayoutForMobile() {
        const isMobile = window.innerWidth <= 768;
        
        if (isMobile) {
            document.body.style.overflowX = 'hidden';
        } else {
            document.body.style.overflowX = 'auto';
        }
    }

    // Additional methods for detail modal actions
    editInvoice(invoiceId) {
        window.location.href = `/invoice?edit=${invoiceId}`;
    }

    sendInvoice(invoiceId) {
        this.showToast('Invoice sent successfully ♡');
        this.closeInvoiceDetailModal();
    }

    downloadInvoice(invoiceId) {
        const url = `${window.location.origin}/api/receipt/invoice/${invoiceId}.pdf`;
        window.open(url, '_blank');
        this.showToast('Invoice PDF downloaded ♡');
    }
}

// Initialize dashboard when DOM is loaded
let dashboard;
document.addEventListener('DOMContentLoaded', () => {
    dashboard = new PaylaDashboard();
});

// Global functions for HTML onclick handlers
function editInvoice(invoiceId) {
    if (dashboard) dashboard.editInvoice(invoiceId);
}

function sendInvoice(invoiceId) {
    if (dashboard) dashboard.sendInvoice(invoiceId);
}

function copyInvoiceLink(invoiceId) {
    if (dashboard) dashboard.copyInvoiceLink(invoiceId);
}

function downloadInvoice(invoiceId) {
    if (dashboard) dashboard.downloadInvoice(invoiceId);
}

function remindClient(invoiceId) {
    if (dashboard) dashboard.remindClient(invoiceId);
}

function resendInvoice(invoiceId) {
    if (dashboard) dashboard.resendInvoice(invoiceId);
}

function viewInvoice(invoiceId) {
    if (dashboard) dashboard.viewInvoice(invoiceId);
}

export {PaylaDashboard, dashboard };
window.dashboard = dashboard;