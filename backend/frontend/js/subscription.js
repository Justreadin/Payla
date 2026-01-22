// Payla Subscription - Complete Integration with FastAPI Backend
import { API_BASE } from './config.js';
class SubscriptionManager {
    constructor() {
        this.API_BASE = API_BASE;
        this.currentUser = null;
        this.subscriptionStatus = null;
        this.plans = null;
        this.selectedPlan = null;
        
        this.init();
    }

    async init() {
        try {
            // Check authentication
            if (!this.getAuthToken()) {
                window.location.href = '/entry';
                return;
            }

            // Load all data
            await this.loadSubscriptionStatus();
            await this.loadPlans();
            
            // Initialize UI components
            this.initEventListeners();
            this.updateUI();
            // If trial/sub is expired, automatically pop the plan selection
            if (this.subscriptionStatus && this.subscriptionStatus.is_active === false) {
                // Small delay to ensure the background UI has rendered first
                setTimeout(() => {
                    this.showPlanSelectionModal();
                    this.showToast("Your Silver access has expired. Please choose a plan to continue.", "error");
                }, 500);
            }
        } catch (error) {
            console.error('Failed to initialize subscription manager:', error);
            this.showError('Failed to load subscription data. Please refresh the page.');
        }
    }

    getAuthToken() {
        return localStorage.getItem('idToken') || '';
    }

    async loadSubscriptionStatus() {
        try {
            const response = await fetch(`${this.API_BASE}/subscription/status`, {
                headers: {
                    'Authorization': `Bearer ${this.getAuthToken()}`,
                    'Content-Type': 'application/json'
                }
            });
            
            if (response.ok) {
                this.subscriptionStatus = await response.json();
            } else if (response.status === 401) {
                window.location.href = '/entry';
                return;
            } else {
                throw new Error('Failed to fetch subscription status');
            }
        } catch (error) {
            console.error('Error loading subscription status:', error);
            throw error;
        }
    }

    async loadPlans() {
        try {
            const response = await fetch(`${this.API_BASE}/subscription/plans`, {
                headers: {
                    'Authorization': `Bearer ${this.getAuthToken()}`,
                    'Content-Type': 'application/json'
                }
            });
            
            if (response.ok) {
                const data = await response.json();
                this.plans = data.plans;
            } else {
                throw new Error('Failed to fetch plans');
            }
        } catch (error) {
            console.error('Error loading plans:', error);
            throw error;
        }
    }

    initEventListeners() {
        // Silver upgrade buttons
        const silverButtons = [
            document.getElementById('silver-upgrade'),
            document.getElementById('sticky-upgrade'),
            document.getElementById('hero-upgrade')
        ];

        silverButtons.forEach(button => {
            if (button) {
                button.addEventListener('click', () => {
                    this.showPlanSelectionModal();
                });
            }
        });

        // Close modal events
        document.addEventListener('click', (e) => {
            if (e.target.classList.contains('modal-overlay') || 
                e.target.classList.contains('modal-close')) {
                this.closePlanSelectionModal();
            }
        });

        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                this.closePlanSelectionModal();
            }
        });

        // Paystack callback handler
        window.handlePaystackCallback = this.handlePaystackCallback.bind(this);
    }

    showPlanSelectionModal() {
        // Check if user already has Silver
        if (this.subscriptionStatus?.plan === 'silver') {
            this.showToast('You already have an active Silver subscription!', 'info');
            return;
        }
        // Inside showPlanSelectionModal()
        const isExpired = this.subscriptionStatus?.is_active === false;
        const title = isExpired ? "Renew Your Silver Access" : "Choose Billing Cycle";
        const subtitle = isExpired ? "Your trial has ended. Pick a plan to reactivate your link." : "Select how you want to pay for Payla Silver";

        // Create modal HTML
        const modalHTML = `
            <div class="modal-overlay" id="plan-selection-modal">
                <div class="modal">
                    <button class="modal-close">
                        <i class="fas fa-times"></i>
                    </button>
                    <h2 class="modal-title">${title}</h2>
                    <p class="modal-subtitle">${subtitle}</p>

                    <div class="billing-options">
                        <div class="billing-option" data-plan="silver_monthly">
                            <div class="billing-header">
                                <h3>Monthly</h3>
                                <div class="badge popular">Flexible</div>
                            </div>
                            <div class="billing-price">
                                <span class="price">₦7,500</span>
                                <span class="period">per month</span>
                            </div>
                            <ul class="billing-features">
                                <li><i class="fas fa-check"></i> Cancel anytime</li>
                                <li><i class="fas fa-check"></i> No long-term commitment</li>
                                <li><i class="fas fa-check"></i> Full access to all features</li>
                            </ul>
                            <button class="btn-primary billing-select">
                                <i class="fas fa-calendar"></i>
                                Choose Monthly
                            </button>
                        </div>

                        <div class="billing-option" data-plan="silver_yearly">
                            <div class="billing-header">
                                <h3>Yearly</h3>
                                <div class="badge gold">Save 17%</div>
                            </div>
                            <div class="billing-price">
                                <span class="price">₦75,000</span>
                                <span class="period">per year</span>
                                <div class="savings">Save ₦15,000</div>
                            </div>
                            <ul class="billing-features">
                                <li><i class="fas fa-check"></i> Best value</li>
                                <li><i class="fas fa-check"></i> One payment per year</li>
                                <li><i class="fas fa-check"></i> Priority feature requests</li>
                            </ul>
                            <button class="btn-gold billing-select">
                                <i class="fas fa-calendar-alt"></i>
                                Choose Yearly
                            </button>
                        </div>
                    </div>

                    <div class="billing-note">
                        <i class="fas fa-shield-alt"></i>
                        <span>14-day free trial included. Cancel before trial ends to avoid charges.</span>
                    </div>
                </div>
            </div>
        `;

        // Remove existing modal if any
        const existingModal = document.getElementById('plan-selection-modal');
        if (existingModal) {
            existingModal.remove();
        }

        document.body.insertAdjacentHTML('beforeend', modalHTML);
        
        // Show modal
        const modal = document.getElementById('plan-selection-modal');
        modal.style.display = 'flex';
        setTimeout(() => modal.classList.add('open'), 10);
        document.body.style.overflow = 'hidden';
        
        // Add event listeners to billing options
        document.querySelectorAll('.billing-select').forEach(button => {
            button.addEventListener('click', (e) => {
                const planOption = e.target.closest('.billing-option');
                const planCode = planOption.dataset.plan;
                this.startSubscription(planCode);
            });
        });

        // Add hover effects
        document.querySelectorAll('.billing-option').forEach(option => {
            option.addEventListener('click', (e) => {
                if (!e.target.classList.contains('billing-select')) {
                    document.querySelectorAll('.billing-option').forEach(opt => {
                        opt.classList.remove('selected');
                    });
                    option.classList.add('selected');
                }
            });
        });
    }

    closePlanSelectionModal() {
        const modal = document.getElementById('plan-selection-modal');
        if (modal) {
            modal.classList.remove('open');
            setTimeout(() => {
                modal.remove();
                document.body.style.overflow = 'auto';
            }, 300);
        }
    }

    async startSubscription(planCode) {
        try {
            this.showToast('Initializing subscription...', 'info');
            this.closePlanSelectionModal();

            const response = await fetch(`${this.API_BASE}/subscription/start/${planCode}`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${this.getAuthToken()}`,
                    'Content-Type': 'application/json'
                }
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || 'Failed to start subscription');
            }

            const subscriptionData = await response.json();
            
            // Initialize Paystack payment
            this.initializePaystackPayment(subscriptionData);

        } catch (error) {
            console.error('Error starting subscription:', error);
            this.showError(error.message || 'Failed to start subscription process');
        }
    }

    initializePaystackPayment(subscriptionData) {
        if (typeof PaystackPop === 'undefined') {
            this.showError('Payment service unavailable. Please try again later.');
            return;
        }

        const handler = PaystackPop.setup({
            key: subscriptionData.public_key,
            email: subscriptionData.email,
            amount: subscriptionData.amount_kobo,
            ref: subscriptionData.reference,
            metadata: subscriptionData.metadata,
            currency: 'NGN',
            
            onClose: () => {
                this.showToast('Payment window closed', 'info');
            },
            
            callback: (response) => {
                this.handlePaystackCallback(response, subscriptionData);
            }
        });

        handler.openIframe();
    }

    async handlePaystackCallback(response, subscriptionData) {
        try {
            if (response.status === 'success') {
                this.showToast('Payment successful! Verifying...', 'success');
                
                // FIX: Pass the reference string, not the whole object
                await this.verifyPaymentWithBackend(subscriptionData.reference);
                
            } else {
                throw new Error('Payment failed');
            }
        } catch (error) {
            console.error('Payment callback error:', error);
            this.showError('Verification failed. Please refresh.');
        }
    }

    async verifyPaymentWithBackend(reference) {
        // This now correctly matches your FastAPI route: /subscription/verify/sub_monthly_...
        const response = await fetch(`${this.API_BASE}/subscription/verify/${reference}`, {
            method: 'GET',
            headers: {
                'Authorization': `Bearer ${this.getAuthToken()}`,
                'Content-Type': 'application/json'
            }
        });

        if (response.ok) {
            const result = await response.json();
            // result.status should contain the updated user object from the backend
            this.subscriptionStatus = result.status; 
            this.updateUI();
            this.showSuccessModal();
        } else {
            this.showError("Verification failed. Please contact support.");
        }
    }
    showSuccessModal() {
        const successHTML = `
            <div class="modal-overlay open" id="success-modal">
                <div class="modal">
                    <div class="modal-icon">
                        <i class="fas fa-crown"></i>
                    </div>
                    <h2 class="modal-title">Welcome to Payla Silver!</h2>
                    <p class="modal-subtitle">Your premium subscription is now active. Start creating beautiful invoices!</p>
                    
                    <div class="modal-actions">
                        <button class="btn btn-primary full" id="go-to-dashboard">
                            <i class="fas fa-rocket"></i>
                            Go to Dashboard
                        </button>
                        <button class="btn btn-secondary" id="explore-features">
                            <i class="fas fa-compass"></i>
                            Explore Features
                        </button>
                    </div>
                </div>
            </div>
        `;

        document.body.insertAdjacentHTML('beforeend', successHTML);

        // Add event listeners
        document.getElementById('go-to-dashboard').addEventListener('click', () => {
            window.location.href = '/dashboard';
        });

        document.getElementById('explore-features').addEventListener('click', () => {
            document.getElementById('success-modal').remove();
            this.scrollToFeatures();
        });

        // Close on overlay click
        document.getElementById('success-modal').addEventListener('click', (e) => {
            if (e.target.id === 'success-modal') {
                e.target.remove();
                window.location.href = '/dashboard';
            }
        });
    }

    scrollToFeatures() {
        const featuresSection = document.querySelector('.pricing-grid');
        if (featuresSection) {
            featuresSection.scrollIntoView({ behavior: 'smooth' });
        }
    }

    updateUI() {
        if (!this.subscriptionStatus) return;

        const { plan, is_active, trial_days_left, message } = this.subscriptionStatus;

        // Update hero section
        this.updateHeroSection(plan, is_active, trial_days_left, message);
        
        // Update plan cards
        this.updatePlanCards(plan);
        
        // Update sticky CTA
        this.updateStickyCTA(plan);
    }

    updateHeroSection(plan, is_active, trial_days_left, message) {
        const heroTitle = document.getElementById('hero-title');
        const heroSubtitle = document.getElementById('hero-subtitle');
        const countdown = document.getElementById('countdown');
        const heroUpgradeButton = document.getElementById('hero-upgrade');

        if (plan === 'silver' && is_active) {
            // User has active Silver subscription
            heroTitle.textContent = 'Payla Silver Active 🎉';
            heroSubtitle.textContent = 'You have full access to all premium features';
            countdown.style.display = 'none';
            
            if (heroUpgradeButton) {
                heroUpgradeButton.innerHTML = '<i class="fas fa-crown"></i> Manage Subscription';
            }
            
        } else if (plan === 'free' && is_active && trial_days_left > 0) {
            // User is in free trial
            heroTitle.textContent = 'Upgrade to Payla Silver';
            heroSubtitle.textContent = `Your free trial ends in ${trial_days_left} days`;
            countdown.textContent = `${trial_days_left} days left in trial`;
            
        } else if (plan === 'free' && !is_active) {
            // Trial expired
            heroTitle.textContent = 'Upgrade to Payla Silver';
            heroSubtitle.textContent = 'Your trial has ended. Upgrade to continue using premium features.';
            countdown.textContent = 'Trial expired — Upgrade to continue';
            countdown.style.background = 'rgba(239, 68, 68, 0.1)';
            countdown.style.borderColor = 'rgba(239, 68, 68, 0.3)';
            countdown.style.color = '#ef4444';
            
        } else {
            // Default state
            heroTitle.textContent = 'Upgrade to Payla Silver';
            heroSubtitle.textContent = 'Get full access to premium features';
            countdown.textContent = 'Start your 14-day free trial';
        }
    }

    updatePlanCards(plan) {
        const silverCard = document.getElementById('silver-plan');
        const silverButton = document.getElementById('silver-upgrade');
        
        if (plan === 'silver') {
            // User already has Silver
            if (silverCard) {
                silverCard.classList.add('activated');
                
                if (silverButton) {
                    silverButton.innerHTML = '<i class="fas fa-crown"></i> Active Subscription';
                    silverButton.disabled = true;
                    silverButton.classList.remove('btn-primary');
                    silverButton.classList.add('btn-secondary');
                }
                
                const statusHint = silverCard.querySelector('.status-hint');
                if (statusHint) {
                    statusHint.textContent = 'You are currently on this plan';
                    statusHint.style.color = 'var(--success)';
                }
            }
        }
    }

    updateStickyCTA(plan) {
        const stickyCTA = document.querySelector('.sticky-cta');
        
        if (plan === 'silver' && stickyCTA) {
            stickyCTA.innerHTML = `
                <div class="sticky-info">
                    <div class="badge popular">Active</div>
                    <div class="sticky-details">
                        <strong>Payla Silver</strong>
                        <span>Subscription Active</span>
                    </div>
                </div>
                <button class="btn-primary" onclick="window.location.href='/dashboard'">
                    Go to Dashboard
                </button>
            `;
        }
    }

    showToast(message, type = 'info') {
        // Remove existing toast
        const existingToast = document.getElementById('subscription-toast');
        if (existingToast) {
            existingToast.remove();
        }

        const toast = document.getElementById('toast');
        const toastMessage = document.getElementById('toast-message');
        
        if (!toast || !toastMessage) return;

        // Update toast content
        toastMessage.textContent = message;
        
        // Update icon and color based on type
        const icon = toast.querySelector('i');
        if (type === 'success') {
            icon.className = 'fas fa-check-circle';
            toast.classList.add('success');
            toast.classList.remove('error');
        } else if (type === 'error') {
            icon.className = 'fas fa-exclamation-circle';
            toast.classList.add('error');
            toast.classList.remove('success');
        } else {
            icon.className = 'fas fa-info-circle';
            toast.classList.remove('success', 'error');
        }

        // Show toast
        toast.classList.add('show');

        // Auto hide
        setTimeout(() => {
            toast.classList.remove('show');
        }, 4000);
    }

    showError(message) {
        this.showToast(message, 'error');
    }
}

// Add button styles for modal
const buttonStyles = `
    .btn {
        padding: 14px 20px;
        border-radius: 10px;
        font-weight: 600;
        cursor: pointer;
        transition: all 0.3s ease;
        border: none;
        font-size: 16px;
        text-align: center;
        text-decoration: none;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        gap: 8px;
    }
    
    .btn.full {
        width: 100%;
    }
`;

// Inject styles
const styleSheet = document.createElement('style');
styleSheet.textContent = buttonStyles;
document.head.appendChild(styleSheet);

// Initialize subscription manager when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    new SubscriptionManager();
});