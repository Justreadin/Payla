// claim-modal.js - Ultra-Luxury Opal Claim Modal
import { BACKEND_BASE } from './config.js';

class OpalClaimModal {
    constructor() {
        this.modal = null;
        this.overlay = null;
        this.currentStage = 'claim'; // 'claim' or 'success'
        this.usernameCheckTimeout = null;
        this.isUsernameAvailable = false;
        this.usernameValue = '';
        this.userEmail = '';
        this.verificationPolling = null;
        
        this.init();
    }

    init() {
        // Create modal structure
        this.createModal();
        
        // Bind events
        this.bindEvents();
        
        // Track view
        this.trackModalView();
    }

    createModal() {
        // Create overlay
        this.overlay = document.createElement('div');
        this.overlay.className = 'opal-modal-overlay';
        this.overlay.id = 'opalClaimModal';
        
        // Create modal HTML
        this.overlay.innerHTML = `
            <div class="opal-modal">
                <button class="opal-modal-close" id="opalModalClose">
                    <i class="fas fa-times"></i>
                </button>
                
                <!-- Stage 1: Claim Form -->
                <div class="opal-modal-stage opal-claim-stage" id="opalClaimStage">
                    <div class="opal-header">
                        <h2 class="opal-title">Claim your unique @username</h2>
                        <p class="opal-subtitle">Join <strong>153+ creators</strong> getting paid with Steeze.</p>
                    </div>
                    
                    <form class="opal-form" id="opalClaimForm">
                        <!-- Username Field -->
                        <div class="opal-form-group">
                            <label>Pick your handle</label>
                            <div class="opal-username-container">
                                <div class="opal-username-input">
                                    <span class="opal-username-prefix">@</span>
                                    <input type="text" 
                                           id="opalUsername" 
                                           placeholder="yourname" 
                                           maxlength="20"
                                           pattern="[a-zA-Z0-9_-]+"
                                           autocomplete="off"
                                           required>
                                    <div class="opal-validation-status" id="opalUsernameStatus">
                                        <div class="opal-loading-spinner"></div>
                                        <div class="opal-success-check"></div>
                                    </div>
                                </div>
                                <div class="opal-feedback-text" id="opalFeedback">
                                    <i class="fas fa-sparkles"></i>
                                    <span>✨ Brilliant choice! This handle is reserved for you.</span>
                                </div>
                            </div>
                            
                            <!-- Live Preview -->
                            <div class="opal-live-preview" id="opalLivePreview">
                                <i class="fas fa-link"></i>
                                <span>
                                    <span class="opal-preview-domain">payla.ng/</span>
                                    <span class="opal-preview-username" id="opalPreviewUsername">@yourname</span>
                                </span>
                            </div>
                        </div>
                        
                        <!-- Email Field with Floating Label -->
                        <div class="opal-form-group floating">
                            <input type="email" 
                                   id="opalEmail" 
                                   class="opal-input" 
                                   placeholder=" " 
                                   required>
                            <label for="opalEmail">Email</label>
                        </div>
                        
                        <!-- Password Field with Floating Label -->
                        <div class="opal-form-group floating">
                            <input type="password" 
                                   id="opalPassword" 
                                   class="opal-input" 
                                   placeholder=" " 
                                   minlength="8"
                                   required>
                            <label for="opalPassword">Create a password</label>
                        </div>

                         <!-- Claim Button -->
                        <button type="submit" class="opal-claim-btn" id="opalClaimBtn">
                            <span class="opal-btn-text">
                                <i class="fas fa-crown"></i>
                                CLAIM MY FREE YEAR
                            </span>
                            <span class="opal-btn-loader"></span>
                        </button>
                        
                        <!-- Trust Zone -->
                        <div class="opal-trust-zone">
                            <div class="opal-trust-badges">
                                <span class="opal-badge">
                                    <i class="fas fa-lock"></i> No bank login required
                                </span>
                                <span class="opal-badge">
                                    <i class="fas fa-shield-alt"></i> Secured by Paystack
                                </span>
                                <span class="opal-price-badge">₦0.00 today</span>
                            </div>
                            
                            <div class="opal-scarcity-nudge">
                                <span class="opal-live-dot"></span>
                                <span><span class="opal-spots-number" id="opalSpotsLeft">412</span>/500 Founding spots left</span>
                            </div>
                        </div>
                        
                    </form>
                </div>
                
                <!-- Stage 2: Success State -->
                <div class="opal-modal-stage opal-success-stage hidden" id="opalSuccessStage">
                    <div class="opal-success-icon">
                        <div class="opal-success-check-large"></div>
                        <div class="opal-confetti"></div>
                    </div>
                    
                    <h2 class="opal-success-title">
                        <span class="opal-success-username" id="successUsername">@yourname</span> is yours! 🥂
                    </h2>
                    
                    <div class="opal-link-card">
                        <span class="opal-preview-domain">payla.ng/</span>
                        <span class="opal-preview-username" id="successLink"></span>
                    </div>
                    
                    <p class="opal-success-message" id="successMessage">
                        Identity successfully reserved. We've sent an activation link to <strong id="successEmailDisplay"></strong>.
                        <br>Verify it now to activate your 1-year free access.
                    </p>
                    
                    <div class="opal-success-actions">
                        <button class="opal-email-btn" id="opalOpenEmailBtn">
                            <i class="fas fa-envelope"></i>
                            OPEN EMAIL APP
                        </button>
                        <button class="opal-resend-link" id="opalResendBtn">
                            Resend activation link
                        </button>
                    </div>
                    
                    <div class="opal-verification-status hidden" id="verificationStatus">
                        <div class="opal-status-spinner"></div>
                        <span>Waiting for verification...</span>
                    </div>
                </div>
            </div>
        `;
        
        document.body.appendChild(this.overlay);
        this.modal = this.overlay.querySelector('.opal-modal');
    }

    bindEvents() {
        // Close button
        const closeBtn = document.getElementById('opalModalClose');
        closeBtn.addEventListener('click', () => this.close());
        
        // Click outside to close
        this.overlay.addEventListener('click', (e) => {
            if (e.target === this.overlay) this.close();
        });
        
        // Username input with debounced check
        const usernameInput = document.getElementById('opalUsername');
        usernameInput.addEventListener('input', (e) => this.handleUsernameInput(e));
        
        // Live preview update
        usernameInput.addEventListener('keyup', (e) => this.updateLivePreview(e));
        
        // Form submission
        const form = document.getElementById('opalClaimForm');
        form.addEventListener('submit', (e) => this.handleSubmit(e));
        
        // Email button
        const emailBtn = document.getElementById('opalOpenEmailBtn');
        if (emailBtn) {
            emailBtn.addEventListener('click', () => this.openEmailApp());
        }
        
        // Resend link
        const resendBtn = document.getElementById('opalResendBtn');
        if (resendBtn) {
            resendBtn.addEventListener('click', () => this.resendActivation());
        }
        
        // Escape key
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && this.overlay.classList.contains('open')) {
                this.close();
            }
        });
        
        // Track button clicks
        const claimBtn = document.getElementById('opalClaimBtn');
        claimBtn.addEventListener('click', () => this.trackClaimClick());
    }

    async handleUsernameInput(e) {
        const input = e.target;
        const username = input.value.trim().toLowerCase();
        const statusDiv = document.getElementById('opalUsernameStatus');
        const feedback = document.getElementById('opalFeedback');
        
        // Clear previous timeout
        if (this.usernameCheckTimeout) {
            clearTimeout(this.usernameCheckTimeout);
        }
        
        // Reset states
        statusDiv.classList.remove('success', 'loading', 'error');
        feedback.classList.remove('show', 'error');
        input.style.borderColor = '';
        this.isUsernameAvailable = false;
        
        // Don't check if username is too short
        if (username.length < 3) {
            if (username.length > 0) {
                feedback.innerHTML = '<i class="fas fa-info-circle"></i><span>Username must be at least 3 characters</span>';
                feedback.classList.add('show', 'error');
            }
            return;
        }
        
        // Validate characters
        const validPattern = /^[a-zA-Z0-9_-]+$/;
        if (!validPattern.test(username)) {
            feedback.innerHTML = '<i class="fas fa-exclamation-circle"></i><span>Only letters, numbers, - and _ allowed</span>';
            feedback.classList.add('show', 'error');
            input.style.borderColor = '#ff4757';
            return;
        }
        
        // Show loading spinner
        statusDiv.classList.add('loading');
        
        // Debounce API call
        this.usernameCheckTimeout = setTimeout(async () => {
            try {
                const response = await fetch(`${BACKEND_BASE}/api/onboarding/validate-username?username=${username}`);
                const data = await response.json();
                
                statusDiv.classList.remove('loading');
                
                if (data.available) {
                    // Username is available
                    statusDiv.classList.add('success');
                    feedback.innerHTML = `
                        <i class="fas fa-sparkles"></i>
                        <span>✨ Brilliant choice! This handle is reserved for you.</span>
                    `;
                    feedback.classList.add('show');
                    feedback.classList.remove('error');
                    input.style.borderColor = '';
                    this.isUsernameAvailable = true;
                    this.usernameValue = username;
                } else {
                    // Username is taken
                    statusDiv.classList.add('error');
                    feedback.innerHTML = `
                        <i class="fas fa-exclamation-circle"></i>
                        <span>Sorry, @${username} is already taken</span>
                    `;
                    feedback.classList.add('show', 'error');
                    input.style.borderColor = '#ff4757';
                    this.isUsernameAvailable = false;
                }
            } catch (error) {
                console.error('Username check failed:', error);
                statusDiv.classList.remove('loading');
                statusDiv.classList.add('error');
                feedback.innerHTML = `
                    <i class="fas fa-exclamation-triangle"></i>
                    <span>Couldn't check availability. Please try again.</span>
                `;
                feedback.classList.add('show', 'error');
            }
        }, 500);
    }

    updateLivePreview(e) {
        const username = e.target.value.trim().toLowerCase();
        const previewSpan = document.getElementById('opalPreviewUsername');
        const successUsername = document.getElementById('successUsername');
        const successLink = document.getElementById('successLink');
        
        const displayUsername = username ? `@${username}` : '@yourname';
        previewSpan.textContent = displayUsername;
        
        if (successUsername) successUsername.textContent = displayUsername;
        if (successLink) successLink.textContent = displayUsername;
    }

    async handleSubmit(e) {
        e.preventDefault();
        
        const username = document.getElementById('opalUsername').value.trim().toLowerCase();
        const email = document.getElementById('opalEmail').value.trim();
        const password = document.getElementById('opalPassword').value;
        const claimBtn = document.getElementById('opalClaimBtn');
        
        // Validation
        if (!this.isUsernameAvailable) {
            this.showToast('Please choose an available username', 'error');
            return;
        }
        
        if (!this.validateEmail(email)) {
            this.showToast('Please enter a valid email', 'error');
            return;
        }
        
        if (password.length < 8) {
            this.showToast('Password must be at least 8 characters', 'error');
            return;
        }
        
        // Show loading state
        claimBtn.classList.add('loading');
        claimBtn.disabled = true;
        
        try {
            const response = await fetch(`${BACKEND_BASE}/api/founding/signup`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    username,
                    email,
                    password
                })
            });
            
            const data = await response.json();
            
            if (response.ok) {
                // Success - transition to stage 2
                this.userEmail = email;
                this.usernameValue = username;
                document.getElementById('successEmailDisplay').textContent = email;
                document.getElementById('successUsername').textContent = `@${username}`;
                document.getElementById('successLink').textContent = `@${username}`;
                
                // Store in localStorage for session
                localStorage.setItem('pendingFoundingUser', JSON.stringify({
                    username,
                    email,
                    timestamp: new Date().toISOString()
                }));
                
                // Track successful signup
                this.trackSuccessfulSignup(username);
                
                // Start polling for email verification
                this.startVerificationPolling(email);
                
                // Animate transition
                this.transitionToSuccess();
            } else {
                // Handle error responses properly
                let errorMessage = 'Signup failed. Please try again.';
                
                if (data.detail) {
                    // If detail is an object with a message property
                    if (typeof data.detail === 'object' && data.detail.message) {
                        errorMessage = data.detail.message;
                    } 
                    // If detail is a string
                    else if (typeof data.detail === 'string') {
                        errorMessage = data.detail;
                    }
                    // If detail is an object with an error property
                    else if (data.detail.error) {
                        errorMessage = data.detail.error;
                    }
                } else if (data.message) {
                    errorMessage = data.message;
                } else if (data.error) {
                    errorMessage = data.error;
                }
                
                // Specific error messages
                if (errorMessage.includes('username_taken') || errorMessage.includes('already taken')) {
                    errorMessage = `@${username} is already taken. Please try another username.`;
                } else if (errorMessage.includes('email_exists') || errorMessage.includes('already registered')) {
                    errorMessage = 'This email is already registered. Please log in instead.';
                }
                
                this.showToast(errorMessage, 'error');
                throw new Error(errorMessage);
            }
        } catch (error) {
            console.error('Signup error:', error);
            // Don't show toast again if we already showed one
            if (!error.message.includes('already taken') && !error.message.includes('already registered')) {
                this.showToast(error.message || 'Something went wrong. Please try again.', 'error');
            }
        } finally {
            claimBtn.classList.remove('loading');
            claimBtn.disabled = false;
        }
    }

    startVerificationPolling(email) {
        // Show verification status
        const statusEl = document.getElementById('verificationStatus');
        if (statusEl) {
            statusEl.classList.remove('hidden');
        }
        
        // Poll every 3 seconds to check if email is verified
        this.verificationPolling = setInterval(async () => {
            try {
                const response = await fetch(`${BACKEND_BASE}/api/founding/status/${encodeURIComponent(email)}`);
                const data = await response.json();
                
                if (data.verified && data.founding_member) {
                    // Clear polling
                    clearInterval(this.verificationPolling);
                    this.verificationPolling = null;
                    
                    // Hide verification status
                    if (statusEl) {
                        statusEl.classList.add('hidden');
                    }
                    
                    // Show success toast
                    this.showToast('🎉 Email verified! Your 1-year free access is now active.', 'success');
                    
                    // Update the success message
                    const successMessage = document.getElementById('successMessage');
                    if (successMessage) {
                        successMessage.innerHTML = `
                            ✅ Email verified! Your 1-year free access is now active.
                            <br>You can now <a href="/onboarding" style="color: #E8B4B8; text-decoration: underline;">complete your onboarding</a> to start using <strong>payla.ng/@${this.usernameValue}</strong>
                        `;
                    }
                    
                    // Change the email button to go to onboarding
                    const emailBtn = document.getElementById('opalOpenEmailBtn');
                    if (emailBtn) {
                        emailBtn.innerHTML = '<i class="fas fa-arrow-right"></i> CONTINUE TO ONBOARDING';
                        emailBtn.onclick = () => {
                            window.location.href = '/entry';
                        };
                    }
                    
                    // Auto-redirect after 3 seconds
                    setTimeout(() => {
                        window.location.href = '/entry';
                    }, 3000);
                }
            } catch (error) {
                console.error('Polling error:', error);
            }
        }, 3000);
    }

    transitionToSuccess() {
        const claimStage = document.getElementById('opalClaimStage');
        const successStage = document.getElementById('opalSuccessStage');
        
        // Animate out claim stage
        claimStage.style.animation = 'slideOutLeft 0.4s cubic-bezier(0.16, 1, 0.3, 1) forwards';
        
        setTimeout(() => {
            claimStage.classList.add('hidden');
            claimStage.style.animation = '';
            
            // Show success stage with animation
            successStage.classList.remove('hidden');
            successStage.style.animation = 'slideInRight 0.4s cubic-bezier(0.16, 1, 0.3, 1) forwards';
            
            this.currentStage = 'success';
            this.trackSuccessView();
        }, 380);
    }

    openEmailApp() {
        const email = this.userEmail;
        const provider = this.getEmailProvider(email);
        
        if (provider) {
            window.open(provider, '_blank');
        } else {
            // Fallback to mailto:
            window.location.href = `mailto:${email}`;
        }
        
        this.trackEmailClick();
    }

    getEmailProvider(email) {
        const domain = email.split('@')[1].toLowerCase();
        const providers = {
            'gmail.com': 'https://mail.google.com',
            'yahoo.com': 'https://mail.yahoo.com',
            'outlook.com': 'https://outlook.live.com',
            'hotmail.com': 'https://outlook.live.com',
            'protonmail.com': 'https://mail.protonmail.com',
            'icloud.com': 'https://www.icloud.com/mail'
        };
        
        return providers[domain] || null;
    }

    async resendActivation() {
        const resendBtn = document.getElementById('opalResendBtn');
        const originalText = resendBtn.textContent;
        
        resendBtn.disabled = true;
        resendBtn.textContent = 'Sending...';
        
        try {
            const pendingUser = JSON.parse(localStorage.getItem('pendingFoundingUser'));
            
            if (!pendingUser) {
                throw new Error('No pending user found');
            }
            
            const response = await fetch(`${BACKEND_BASE}/api/founding/resend-verification`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    email: pendingUser.email
                })
            });
            
            const data = await response.json();
            
            if (response.ok) {
                this.showToast('✅ Verification email resent! Check your inbox.', 'success');
            } else {
                throw new Error(data.detail || 'Failed to resend');
            }
        } catch (error) {
            console.error('Resend error:', error);
            this.showToast('Failed to resend. Please try again.', 'error');
        } finally {
            resendBtn.disabled = false;
            resendBtn.textContent = originalText;
        }
    }

    validateEmail(email) {
        const re = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        return re.test(email);
    }

    showToast(message, type = 'success') {
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.innerHTML = `
            <i class="fas fa-${type === 'success' ? 'check-circle' : 'exclamation-circle'}"></i>
            <span>${message}</span>
        `;
        
        document.body.appendChild(toast);
        
        setTimeout(() => toast.classList.add('show'), 10);
        setTimeout(() => {
            toast.classList.remove('show');
            setTimeout(() => toast.remove(), 400);
        }, 4000);
    }

    // Analytics tracking
    trackModalView() {
        if (typeof window.trackEvent === 'function') {
            window.trackEvent('modal_view', { type: 'claim_modal' });
        }
    }

    trackClaimClick() {
        if (typeof window.trackEvent === 'function') {
            window.trackEvent('claim_click', { 
                username_length: this.usernameValue.length 
            });
        }
    }

    trackSuccessfulSignup(username) {
        if (typeof window.trackEvent === 'function') {
            window.trackEvent('successful_signup', { username });
        }
        
        // Update FOMO counter
        this.updateFomoCounter();
    }

    trackSuccessView() {
        if (typeof window.trackEvent === 'function') {
            window.trackEvent('success_view', {});
        }
    }

    trackEmailClick() {
        if (typeof window.trackEvent === 'function') {
            window.trackEvent('email_click', {});
        }
    }

    async updateFomoCounter() {
        try {
            const response = await fetch(`${BACKEND_BASE}/api/spots-left`);
            const data = await response.json();
            
            const spotsElements = document.querySelectorAll('.opal-spots-number');
            spotsElements.forEach(el => {
                if (el) {
                    el.textContent = data.spotsLeft;
                    el.classList.add('counter-update');
                    setTimeout(() => el.classList.remove('counter-update'), 500);
                }
            });
        } catch (error) {
            console.error('Failed to update FOMO counter:', error);
        }
    }

    // Public methods
    open() {
        this.overlay.classList.add('open');
        document.body.style.overflow = 'hidden';
        
        // Clear any existing polling
        if (this.verificationPolling) {
            clearInterval(this.verificationPolling);
            this.verificationPolling = null;
        }
        
        // Reset to claim stage if coming back
        if (this.currentStage === 'success') {
            const claimStage = document.getElementById('opalClaimStage');
            const successStage = document.getElementById('opalSuccessStage');
            const verificationStatus = document.getElementById('verificationStatus');
            
            claimStage.classList.remove('hidden');
            successStage.classList.add('hidden');
            if (verificationStatus) {
                verificationStatus.classList.add('hidden');
            }
            this.currentStage = 'claim';
            
            // Reset form
            document.getElementById('opalClaimForm').reset();
            document.getElementById('opalUsernameStatus').classList.remove('success', 'loading', 'error');
            document.getElementById('opalFeedback').classList.remove('show', 'error');
            document.getElementById('opalPreviewUsername').textContent = '@yourname';
            
            // Reset success message
            const successMessage = document.getElementById('successMessage');
            if (successMessage) {
                successMessage.innerHTML = `
                    Identity successfully reserved. We've sent an activation link to <strong id="successEmailDisplay"></strong>.
                    <br>Verify it now to activate your 1-year free access.
                `;
            }
            
            // Reset email button
            const emailBtn = document.getElementById('opalOpenEmailBtn');
            if (emailBtn) {
                emailBtn.innerHTML = '<i class="fas fa-envelope"></i> OPEN EMAIL APP';
                emailBtn.onclick = () => this.openEmailApp();
            }
        }
        
        // Focus username input
        setTimeout(() => {
            document.getElementById('opalUsername').focus();
        }, 400);
        
        // Update FOMO counter on open
        this.updateFomoCounter();
    }

    close() {
        this.overlay.classList.remove('open');
        document.body.style.overflow = '';
        
        // Clear polling when modal closes
        if (this.verificationPolling) {
            clearInterval(this.verificationPolling);
            this.verificationPolling = null;
        }
    }
}

// Initialize modal and attach to buttons
document.addEventListener('DOMContentLoaded', () => {
    const modal = new OpalClaimModal();
    
    // Attach to all claim buttons
    const claimButtons = document.querySelectorAll('#join-waitlist, #sticky-free');
    claimButtons.forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.preventDefault();
            modal.open();
        });
    });
    
    // Add CSS animations for transitions
    const style = document.createElement('style');
    style.textContent = `
        @keyframes slideOutLeft {
            to { 
                opacity: 0;
                transform: translateX(-30px);
            }
        }
        
        @keyframes slideInRight {
            from { 
                opacity: 0;
                transform: translateX(30px);
            }
            to { 
                opacity: 1;
                transform: translateX(0);
            }
        }
        
        .opal-verification-status {
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 12px;
            margin-top: 20px;
            padding: 12px;
            background: rgba(232, 180, 184, 0.05);
            border-radius: 30px;
            border: 1px solid rgba(232, 180, 184, 0.1);
            font-size: 13px;
            color: var(--platinum);
        }
        
        .opal-verification-status.hidden {
            display: none;
        }
        
        .opal-status-spinner {
            width: 16px;
            height: 16px;
            border: 2px solid rgba(232, 180, 184, 0.2);
            border-top-color: var(--rose-gold);
            border-radius: 50%;
            animation: spin 1s linear infinite;
        }
        
        .counter-update {
            animation: counterPulse 0.5s ease-in-out;
        }
        
        @keyframes counterPulse {
            0%, 100% { transform: scale(1); }
            50% { transform: scale(1.1); color: var(--rose-gold); }
        }
    `;
    document.head.appendChild(style);
});