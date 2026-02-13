// ---------------------------
// Configuration
// ---------------------------
import { BACKEND_BASE } from './config.js';

// Import analytics
import { 
  trackOnboardingPageView,
  trackStepViewed,
  trackStepCompleted,
  trackNextClicked,
  trackBackClicked,
  trackUsernameCheck,
  trackBusinessNameEntered,
  trackBankSelected,
  trackAccountVerified,
  trackPlanSelected,
  trackOnboardingStarted,
  trackOnboardingCompleted,
  trackOnboardingFailed,
  trackPreviewViewed
} from "./onboarding_analytics.js";

if (!localStorage.getItem('idToken')) {
    window.location.replace('/entry');
}
const BACKEND_URL = BACKEND_BASE;
const ONBOARDING_STATE = {
    currentStep: 1,
    totalSteps: 5,
    baseUrl: BACKEND_BASE,
    userData: null,
    formData: {
        username: '',
        businessName: '',
        payoutBank: '',
        payoutAccount: '',
        plan: ''
    },
    validation: {
        username: { isValid: false, isChecking: false },
        payoutAccount: {
            isFormatValid: false,   // 10-digit check only
            isVerified: false,      // Paystack confirmed
            accountName: null
        }
    }
};

// Step names for analytics
const STEP_NAMES = {
    1: 'username',
    2: 'business',
    3: 'payout',
    4: 'plan',
    5: 'preview'
};

async function guardOnboardingAccess() {
    const token = ensureAuthenticated();
    if (!token) return false;

    const res = await authFetch(`${BACKEND_URL}/api/onboarding/me`);
    if (!res || !res.ok) {
        window.location.href = '/entry';
        return false;
    }

    const user = await res.json();

    if (user.onboarding_complete) {
        window.location.replace('/entry'); // replace = no back button
        return false;
    }

    return true;
}


// ---------------------------
// Authentication Guard
// ---------------------------
function ensureAuthenticated() {
    const token = localStorage.getItem('idToken');
    if (!token) {
        window.location.href = '/entry';
        return false;
    }
    return token;
}


async function authFetch(url, options = {}) {
    const token = ensureAuthenticated();
    if (!token) return; // Already redirected

    options.headers = {
        ...(options.headers || {}),
        'Authorization': `Bearer ${token}`
    };

    const res = await fetch(url, options);

    // Unauthorized → redirect
    if (res.status === 401 || res.status === 403) {
        localStorage.removeItem('idToken');
        window.location.href = '/entry';
        return;
    }

    return res;
}

// ---------------------------
// DOM Elements
// ---------------------------
const stepElements = document.querySelectorAll('.step');
const stepContentElements = document.querySelectorAll('.step-content');
const backBtn = document.getElementById('back-btn');
const nextBtn = document.getElementById('next-btn');
//const fabContinue = document.getElementById('fab-continue');
const successModal = document.getElementById('success-modal');
const paylinkPrefix = document.getElementById('paylink-prefix');
const usernameInput = document.getElementById('username');
const businessNameInput = document.getElementById('business-name');
const payoutBankSelect = document.getElementById('payout-bank');
const payoutAccountInput = document.getElementById('payout-account');
const planCards = document.querySelectorAll('.plan-card');

const previewLink = document.getElementById('preview-link');
const previewBrand = document.getElementById('preview-brand');
const previewLogo = document.getElementById('preview-logo');
const finalPreviewLink = document.getElementById('final-preview-link');
const finalPreviewBrand = document.getElementById('final-preview-brand');
const finalPreviewLogo = document.getElementById('final-preview-logo');
const finalPlanName = document.getElementById('final-plan-name');
const finalPlanDetails = document.getElementById('final-plan-details');

const usernameStatus = document.getElementById('username-status');
const usernameError = document.getElementById('username-error');
const payoutStatus = document.getElementById('payout-status');

finalPreviewLink.textContent = ONBOARDING_STATE.baseUrl;
paylinkPrefix.textContent = ONBOARDING_STATE.baseUrl;

// ---------------------------
// Initialize onboarding
// ---------------------------
async function initializeOnboarding() {
    const allowed = await guardOnboardingAccess();
    if (!allowed) return; // 🚫 STOP EVERYTHING

    setupEventListeners();
    await loadBanks();
    await loadUserData();
    updateUI();
    
    // Track onboarding start
    trackOnboardingStarted();
    trackOnboardingPageView();
    trackStepViewed(1, STEP_NAMES[1]);
}


// ---------------------------
// Setup event listeners
// ---------------------------
function setupEventListeners() {
    backBtn.addEventListener('click', goToPreviousStep);
    nextBtn.addEventListener('click', goToNextStep);
    //fabContinue.addEventListener('click', completeOnboarding);

    usernameInput.addEventListener('input', handleUsernameInput);
    businessNameInput.addEventListener('input', handleBusinessNameInput);
    payoutBankSelect.addEventListener('change', handlePayoutBankChange);
    payoutAccountInput.addEventListener('input', handlePayoutAccountInput);

    planCards.forEach(card => {
        card.addEventListener('click', () => selectPlan(card.dataset.plan));
    });

    document.getElementById('go-to-dashboard').addEventListener('click', () => {
        window.location.href = '/dashboard';
    });
}

// ---------------------------
// Load banks from backend
// ---------------------------
async function loadBanks() {
    try {
        const res = await authFetch(`${BACKEND_URL}/api/payout/banks`);

        if (!res || !res.ok) throw new Error('Failed to load banks');

        const data = await res.json();
        payoutBankSelect.innerHTML = '<option value="">Select your bank</option>';
        data.banks.forEach(bank => {
            const option = document.createElement('option');
            option.value = bank.code;
            option.textContent = bank.name;
            payoutBankSelect.appendChild(option);
        });
    } catch (err) {
        console.error('Failed to load banks', err);
        payoutBankSelect.innerHTML = '<option value="">Failed to load banks</option>';
    }
}

// ---------------------------
// Load current user data from backend
// ---------------------------
// ---------------------------
// Load current user data from backend
// ---------------------------
async function loadUserData() {
    const token = ensureAuthenticated();
    if (!token) return;

    try {
        const res = await authFetch(`${BACKEND_URL}/api/onboarding/me`);
        if (!res || !res.ok) {
            // Not allowed → redirect
            window.location.href = '/entry';
            return;
        }
        const user = await res.json();
        
        // Store user data in state for later use
        ONBOARDING_STATE.userData = user;

        if (user.plan === 'presell') {
            ONBOARDING_STATE.formData.plan = 'presell';
            // Optional: Update the UI card for Silver to say "Presell Applied"
            const silverCard = document.querySelector('.plan-card[data-plan="silver"]');
            if (silverCard) {
                silverCard.querySelector('.price').textContent = "FREE";
                silverCard.querySelector('.period').textContent = "for 1 year";
                silverCard.querySelector('.badge').textContent = "PRESELL ACTIVE";
            }
        } else {
            ONBOARDING_STATE.formData.plan = 'silver';
        }

        if (user.onboarding_complete) {
            window.location.href = '/entry'; // Prevent re-access
            return;
        }


        ONBOARDING_STATE.formData.username = user.username || '';
        ONBOARDING_STATE.formData.businessName = user.business_name || '';
        ONBOARDING_STATE.formData.payoutBank = user.payout_bank || '';
        ONBOARDING_STATE.formData.payoutAccount = user.payout_account_number || '';
        ONBOARDING_STATE.formData.plan = user.plan || 'silver';

        usernameInput.value = ONBOARDING_STATE.formData.username;
        businessNameInput.value = ONBOARDING_STATE.formData.businessName;
        payoutBankSelect.value = ONBOARDING_STATE.formData.payoutBank;
        payoutAccountInput.value = ONBOARDING_STATE.formData.payoutAccount;

        ONBOARDING_STATE.validation.username.isValid = !!user.username;
        ONBOARDING_STATE.validation.payoutAccount.isVerified = false;

        selectPlan(ONBOARDING_STATE.formData.plan);

        if (ONBOARDING_STATE.formData.payoutBank && ONBOARDING_STATE.formData.payoutAccount) {
            verifyPayoutAccount(
                ONBOARDING_STATE.formData.payoutBank,
                ONBOARDING_STATE.formData.payoutAccount
            );
        }

        updatePreview();
        updateFinalPreview();
        updateUI();
    } catch (err) {
        console.error('Failed to load onboarding user', err);
        window.location.href = '/entry'; // fallback redirect
    }
}

// ---------------------------
// Step validation
// ---------------------------
function validateCurrentStep() {
    switch (ONBOARDING_STATE.currentStep) {
        case 1: return ONBOARDING_STATE.validation.username.isValid;
        case 2: return true;
        case 3:
            return (
                ONBOARDING_STATE.formData.payoutBank &&
                ONBOARDING_STATE.validation.payoutAccount.isVerified
            );
        case 4: return !!ONBOARDING_STATE.formData.plan;
        case 5: return true;
        default: return false;
    }
}

// ---------------------------
// Form Handlers
// ---------------------------
let usernameTimeout;
function handleUsernameInput(e) {
    const username = e.target.value.trim().toLowerCase();
    ONBOARDING_STATE.formData.username = username;
    
    clearTimeout(usernameTimeout); // Cancel the previous timer

    const isValidFormat = /^[a-zA-Z0-9_-]{3,20}$/.test(username);
    if (!isValidFormat) {
        showUsernameStatus('error', 'Invalid format...');
        ONBOARDING_STATE.validation.username.isValid = false;
        updateUI();
    } else {
        showUsernameStatus('loading', 'Checking...');
        // Wait 500ms after the user stops typing before calling the API
        usernameTimeout = setTimeout(() => {
            checkUsernameAvailability(username);
        }, 500);
    }
    updatePreview();
}

function handleBusinessNameInput(e) {
    const businessName = e.target.value.trim();
    ONBOARDING_STATE.formData.businessName = businessName;
    
    // Track business name entry (only if not empty)
    if (businessName.length > 0) {
        trackBusinessNameEntered(businessName.length);
    }
    
    updatePreview();
    updateUI();
}

function handlePayoutBankChange(e) {
    const bankCode = e.target.value;
    ONBOARDING_STATE.formData.payoutBank = bankCode;

    // Track bank selection
    if (bankCode) {
        trackBankSelected(bankCode);
    }

    ONBOARDING_STATE.validation.payoutAccount.isVerified = false;
    ONBOARDING_STATE.validation.payoutAccount.accountName = null;

    if (!ONBOARDING_STATE.formData.payoutBank) {
        payoutStatus.style.display = 'none';
        updateUI();
        return;
    }

    if (ONBOARDING_STATE.validation.payoutAccount.isFormatValid) {
        verifyPayoutAccount(
            ONBOARDING_STATE.formData.payoutBank,
            ONBOARDING_STATE.formData.payoutAccount
        );
    }

    updateUI();
}


function handlePayoutAccountInput(e) {
    const account = e.target.value.trim().replace(/\D/g, '');
    ONBOARDING_STATE.formData.payoutAccount = account;
    e.target.value = account;

    ONBOARDING_STATE.validation.payoutAccount.isFormatValid = /^\d{10}$/.test(account);
    ONBOARDING_STATE.validation.payoutAccount.isVerified = false;
    ONBOARDING_STATE.validation.payoutAccount.accountName = null;
    if (
        ONBOARDING_STATE.validation.payoutAccount.isFormatValid &&
        ONBOARDING_STATE.formData.payoutBank
    ) {verifyPayoutAccount(
            ONBOARDING_STATE.formData.payoutBank,
            account
        );
    } else {
        payoutStatus.style.display = 'none';
    }

    updateUI();
}

function selectPlan(plan) {
    ONBOARDING_STATE.formData.plan = plan;

    planCards.forEach(card => {
        card.classList.toggle('active', card.dataset.plan === plan);
    });

    // Track plan selection
    trackPlanSelected(plan);

    updateFinalPreview();
    updateUI();
}

// ---------------------------
// Username availability
// ---------------------------
// ---------------------------
// Username availability
// ---------------------------
async function checkUsernameAvailability(username) {
    ONBOARDING_STATE.validation.username.isChecking = true;
    showUsernameStatus('loading', 'Checking availability...');

    try {
        // Get the current user ID from the token or from the /me endpoint
        // Since we already loaded user data, we can use the stored user ID
        // Let's get it from the user data we loaded
        const token = localStorage.getItem('idToken');
        
        // First, let's decode the token to get the user ID (Firebase UID)
        // Or we can use the user data we already loaded
        let userId = '';
        
        // Option 1: If you have the user data in memory
        if (ONBOARDING_STATE.userData && ONBOARDING_STATE.userData.id) {
            userId = ONBOARDING_STATE.userData.id;
        } else {
            // Option 2: Decode the JWT token (simpler)
            try {
                const payload = JSON.parse(atob(token.split('.')[1]));
                userId = payload.user_id || payload.uid || payload.sub;
            } catch (e) {
                console.warn('Could not decode token', e);
            }
        }
        
        // Build URL with current_user_id parameter
        let url = `${BACKEND_URL}/api/onboarding/validate-username?username=${username}`;
        if (userId) {
            url += `&current_user_id=${userId}`;
        }
        
        const res = await fetch(url);
        const data = await res.json();

        ONBOARDING_STATE.validation.username.isValid = data.available;
        showUsernameStatus(data.available ? 'success' : 'error', data.message);
        
        // Track username check
        trackUsernameCheck(username, data.available);
    } catch (err) {
        console.error('Username check failed:', err);
        ONBOARDING_STATE.validation.username.isValid = false;
        showUsernameStatus('error', 'Error checking username');
    } finally {
        ONBOARDING_STATE.validation.username.isChecking = false;
        updateUI();
    }
}

// ---------------------------
// Verify payout account via backend
// ---------------------------
async function verifyPayoutAccount(bankCode, accountNumber) {
    payoutStatus.style.display = 'flex';
    payoutStatus.className = 'status';
    payoutStatus.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Verifying account...';

    try {
        const res = await authFetch(
            `${BACKEND_URL}/api/payout/resolve?bank=${bankCode}&account=${accountNumber}`
        );
        if (!res) return;

        const data = await res.json();

        if (data.account_name) {
            payoutStatus.className = 'status success';
            payoutStatus.innerHTML =
                `<i class="fas fa-check-circle"></i> ${data.account_name}`;

            ONBOARDING_STATE.validation.payoutAccount.isVerified = true;
            ONBOARDING_STATE.validation.payoutAccount.accountName = data.account_name;
            
            // Track successful account verification
            trackAccountVerified(true, bankCode);
        } else {
            payoutStatus.className = 'status error';
            payoutStatus.innerHTML =
                `<i class="fas fa-times-circle"></i> Invalid account`;

            ONBOARDING_STATE.validation.payoutAccount.isVerified = false;
            ONBOARDING_STATE.validation.payoutAccount.accountName = null;
            
            // Track failed account verification
            trackAccountVerified(false, bankCode);
        }
    } catch (err) {
        console.error('Payout verification failed:', err);
        payoutStatus.className = 'status error';
        payoutStatus.innerHTML = `<i class="fas fa-times-circle"></i> Verification failed`;
        ONBOARDING_STATE.validation.payoutAccount.isVerified = false;
        ONBOARDING_STATE.validation.payoutAccount.accountName = null;
        
        // Track verification error
        trackAccountVerified(false, bankCode);
    }

    updateUI();
}

// ---------------------------
// Username status UI
// ---------------------------
function showUsernameStatus(type, message) {
    usernameStatus.style.display = 'none';
    usernameError.style.display = 'none';

    if (type === 'success') {
        usernameStatus.style.display = 'flex';
        usernameStatus.querySelector('span').textContent = message;
    } else if (type === 'error') {
        usernameError.style.display = 'flex';
        usernameError.querySelector('span').textContent = message;
    } else if (type === 'loading') {
        usernameStatus.style.display = 'flex';
        usernameStatus.className = 'status';
        usernameStatus.innerHTML = `<i class="fas fa-spinner fa-spin"></i> <span>${message}</span>`;
    }
}

// ---------------------------
// Live preview
// ---------------------------
function updatePreview() {
    if (!ONBOARDING_STATE.formData.username) return;

    previewLink.textContent = `@payla`;
}

function updateFinalPreview() {
    if (!ONBOARDING_STATE.formData.username) return;

    finalPreviewLink.textContent = `@${ONBOARDING_STATE.formData.username}`;
    finalPreviewBrand.textContent =
        ONBOARDING_STATE.formData.businessName || 'Your Name';
    finalPreviewLogo.textContent =
        getInitials(ONBOARDING_STATE.formData.businessName || 'Your Name');

    const planInfo = getPlanInfo(ONBOARDING_STATE.formData.plan);
    finalPlanName.textContent = planInfo.name;
    finalPlanDetails.textContent = planInfo.details;
}

function getPlanInfo(plan) {
    const plans = {
        presell: {
            name: 'Payla Silver (Presell)',
            details: '1 Year Exclusive Access • Founder Member'
        },
        silver: {
            name: 'Payla Silver',
            details: '14 days exclusive access • ₦7,500/month after trial'
        },
        gold: {
            name: 'Payla Gold',
            details: 'Launching January 2026 • ₦20,000/month'
        },
        opal: {
            name: 'Payla Opal',
            details: 'Invite Only • ₦49,999/month'
        }
    };
    return plans[plan] || plans.silver;
}

function getInitials(name) {
    if (!name) return 'YN';
    return name
        .split(' ')
        .map(w => w[0])
        .join('')
        .toUpperCase()
        .slice(0, 2);
}

// ---------------------------
// Complete onboarding
// ---------------------------
async function completeOnboarding() {
    if (!validateCurrentStep()) return;

    try {

        let finalPlan = ONBOARDING_STATE.formData.plan;
        
        if (finalPlan === 'silver') {
            finalPlan = 'free'; // Backend logic: 'free' = Silver plan + 14 day trial
        }
        const payload = {
            username: ONBOARDING_STATE.formData.username,
            business_name: ONBOARDING_STATE.formData.businessName,
            payout_bank: ONBOARDING_STATE.formData.payoutBank,
            payout_account_number: ONBOARDING_STATE.formData.payoutAccount,
            plan: finalPlan
        };

        const res = await authFetch(`${BACKEND_URL}/api/onboarding/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        if (!res) return;

        if (!res.ok) {
            const err = await res.json();
            trackOnboardingFailed(err.detail || 'Onboarding failed');
            alert(err.detail || 'Error completing onboarding');
            return;
        }

        // Track successful onboarding completion
        trackOnboardingCompleted(
            ONBOARDING_STATE.formData.username, 
            ONBOARDING_STATE.formData.plan
        );

        showSuccessModal();
    } catch (err) {
        console.error('Onboarding failed:', err);
        trackOnboardingFailed(err.message);
        alert('Failed to complete onboarding. Please try again.');
    }
}

// ---------------------------
// Success modal
// ---------------------------
// ---------------------------
// Success modal
// ---------------------------
function showSuccessModal() {
    // 1. Show the success UI
    successModal.classList.add('open');
    
    // 2. Copy link to clipboard (your existing logic)
    const paylink = `${ONBOARDING_STATE.baseUrl}/@${ONBOARDING_STATE.formData.username}`;
    navigator.clipboard.writeText(paylink);

    // 3. FIRE X ADS PIXEL (The Fix)
    // We check if 'twq' exists first so the app doesn't crash if an ad-blocker is on
    if (typeof twq === 'function') {
        twq('event', 'tw-r4oqa-r4p9b', {
            email_address: null, // Optional: You can pass hashed email if you want later
            status: 'completed'
        });
        console.log("X Pixel Fired: Lead"); 
    }
}

// ---------------------------
// Navigation
// ---------------------------
function goToNextStep() {
    const fromStep = ONBOARDING_STATE.currentStep;
    const fromStepName = STEP_NAMES[fromStep];
    
    if (ONBOARDING_STATE.currentStep < ONBOARDING_STATE.totalSteps) {
        ONBOARDING_STATE.currentStep++;
        const toStep = ONBOARDING_STATE.currentStep;
        const toStepName = STEP_NAMES[toStep];
        
        // Track step navigation
        trackNextClicked(fromStepName, toStepName);
        trackStepViewed(toStep, toStepName);
        
        // Track step completion
        trackStepCompleted(fromStep, fromStepName);
        
        window.scrollTo({ top: 0, behavior: 'smooth' }); // Add this
        updateUI();
        
        // Track preview view when reaching step 5
        if (ONBOARDING_STATE.currentStep === 5) {
            updateFinalPreview();
            trackPreviewViewed();
        }
    } else {
        completeOnboarding();
    }
}

function goToPreviousStep() {
    const fromStep = ONBOARDING_STATE.currentStep;
    const fromStepName = STEP_NAMES[fromStep];
    
    if (ONBOARDING_STATE.currentStep > 1) {
        ONBOARDING_STATE.currentStep--;
        const toStep = ONBOARDING_STATE.currentStep;
        const toStepName = STEP_NAMES[toStep];
        
        // Track back navigation
        trackBackClicked(fromStepName, toStepName);
        trackStepViewed(toStep, toStepName);
        
        updateUI();
    }
}

// ---------------------------
// UI Update
// ---------------------------
function updateUI() {
    stepElements.forEach(step => {
        const stepNumber = parseInt(step.dataset.step);
        step.classList.toggle('active', stepNumber === ONBOARDING_STATE.currentStep);
        step.classList.toggle('completed', stepNumber < ONBOARDING_STATE.currentStep);
    });

    stepContentElements.forEach((content, index) => {
        content.classList.toggle('active', index + 1 === ONBOARDING_STATE.currentStep);
    });

    backBtn.style.visibility = ONBOARDING_STATE.currentStep === 1 ? 'hidden' : 'visible';
    nextBtn.disabled = !validateCurrentStep();

    if (ONBOARDING_STATE.currentStep === 4) {
        nextBtn.textContent = 'Preview';
    } else if (ONBOARDING_STATE.currentStep === ONBOARDING_STATE.totalSteps) {
        nextBtn.textContent = 'Complete Setup';
    } else {
        nextBtn.textContent = 'Continue';
    }

    //const isStepValid = validateCurrentStep();
    //if (isStepValid) {
    //    fabContinue.classList.add('visible');
    //    fabContinue.innerHTML =
    //        ONBOARDING_STATE.currentStep === ONBOARDING_STATE.totalSteps
    //            ? '<i class="fas fa-check"></i>'
    //            : '<i class="fas fa-arrow-right"></i>';
    //} else {
    //    fabContinue.classList.remove('visible');
    //}
}

// ---------------------------
// Initialize
// ---------------------------
document.addEventListener('DOMContentLoaded', initializeOnboarding);