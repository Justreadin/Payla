import { BACKEND_BASE } from './config.js';

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
} from './onboarding_analytics.js';


/* --------------------------------------------------
   Configuration and state
-------------------------------------------------- */

const BACKEND_URL = BACKEND_BASE;
const FREE_PLAN = 'free';

const ONBOARDING_STATE = {
    currentStep: 1,
    totalSteps: 5,
    baseUrl: BACKEND_BASE.replace(/\/+$/, ''),
    userData: null,

    formData: {
        username: '',
        businessName: '',
        payoutBank: '',
        payoutAccount: '',
        plan: FREE_PLAN
    },

    validation: {
        username: { isValid: false, isChecking: false },
        payoutAccount: {
            isFormatValid: false,
            isVerified: false,
            accountName: null
        }
    }
};

const STEP_NAMES = {
    1: 'username',
    2: 'business',
    3: 'payout',
    4: 'plan',
    5: 'preview'
};

let usernameTimeout;
let usernameRequestId = 0;
let payoutTimeout;
let payoutVerificationRequestId = 0;


/* --------------------------------------------------
   DOM
-------------------------------------------------- */

const stepElements = document.querySelectorAll('.step');
const stepContentElements = document.querySelectorAll('.step-content');

const backBtn = document.getElementById('back-btn');
const nextBtn = document.getElementById('next-btn');

const successModal = document.getElementById('success-modal');
const paylinkPrefix = document.getElementById('paylink-prefix');

const usernameInput = document.getElementById('username');
const businessNameInput = document.getElementById('business-name');
const payoutBankSelect = document.getElementById('payout-bank');
const payoutAccountInput = document.getElementById('payout-account');

const usernameStatus = document.getElementById('username-status');
const usernameError = document.getElementById('username-error');
const payoutStatus = document.getElementById('payout-status');

// Step 5 preview
const previewBrand = document.getElementById('preview-brand');
const previewTagline = document.getElementById('preview-tagline');
const previewLink = document.getElementById('preview-link');
const previewLogoInitials = document.getElementById('preview-logo-initials');
const previewTrust = document.getElementById('preview-trust');

// Side panel preview
const sidePreviewBrand = document.getElementById('side-preview-brand');
const sidePreviewTagline = document.getElementById('side-preview-tagline');
const sidePreviewLink = document.getElementById('side-preview-link');
const sidePreviewLogoInitials = document.getElementById('side-preview-logo-initials');
const sidePreviewTrust = document.getElementById('side-preview-trust');

if (paylinkPrefix) {
    paylinkPrefix.textContent = `${ONBOARDING_STATE.baseUrl}/`;
}


/* --------------------------------------------------
   Authentication
-------------------------------------------------- */

function ensureAuthenticated() {
    const token = localStorage.getItem('idToken');

    if (!token) {
        window.location.replace('/entry');
        return null;
    }

    return token;
}

async function authFetch(url, options = {}) {
    const token = ensureAuthenticated();
    if (!token) return null;

    const headers = new Headers(options.headers || {});
    headers.set('Authorization', `Bearer ${token}`);

    const response = await fetch(url, { ...options, headers });

    if (response.status === 401 || response.status === 403) {
        localStorage.removeItem('idToken');
        window.location.replace('/entry');
        return null;
    }

    return response;
}

async function guardOnboardingAccess() {
    const token = ensureAuthenticated();
    if (!token) return false;

    try {
        const response = await authFetch(`${BACKEND_URL}/api/onboarding/me`);

        if (!response || !response.ok) {
            if (response) window.location.replace('/entry');
            return false;
        }

        const user = await response.json();

        if (user.onboarding_complete) {
            window.location.replace('/entry');
            return false;
        }

        return true;
    } catch (error) {
        console.error('Unable to check onboarding access:', error);
        return false;
    }
}


/* --------------------------------------------------
   Initialization
-------------------------------------------------- */

async function initializeOnboarding() {
    const allowed = await guardOnboardingAccess();
    if (!allowed) return;

    setupEventListeners();

    // Static stamped seal in both previews.
    renderStaticSeal();

    await loadBanks();
    await loadUserData();

    updateUI();

    trackOnboardingStarted();
    trackOnboardingPageView();
    trackStepViewed(1, STEP_NAMES[1]);
}

function setupEventListeners() {
    backBtn.addEventListener('click', goToPreviousStep);
    nextBtn.addEventListener('click', goToNextStep);

    usernameInput.addEventListener('input', handleUsernameInput);
    businessNameInput.addEventListener('input', handleBusinessNameInput);

    payoutBankSelect.addEventListener('change', handlePayoutBankChange);
    payoutAccountInput.addEventListener('input', handlePayoutAccountInput);

    document
        .getElementById('go-to-dashboard')
        .addEventListener('click', () => {
            window.location.href = '/dashboard';
        });
}


/* --------------------------------------------------
   The static stamped seal used in the preview
-------------------------------------------------- */

function renderStaticSeal() {
    const svg = `
        <div class="payla-stamp">
            <svg class="payla-stamp__svg" viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
                <defs>
                    <path id="onboarding-stamp-arc-top" d="M 50,50 m -29,0 a 29,29 0 1,1 58,0" />
                </defs>
                <circle class="payla-stamp__ring-outer" cx="50" cy="50" r="46" />
                <circle class="payla-stamp__ring-dashed" cx="50" cy="50" r="42.5" />
                <circle class="payla-stamp__ring-inner" cx="50" cy="50" r="34" />
                <text class="payla-stamp__arc-text" text-anchor="middle">
                    <textPath href="#onboarding-stamp-arc-top" startOffset="50%">
                        NAME MATCHED
                    </textPath>
                </text>
                <text class="payla-stamp__center-text" x="50" y="54" text-anchor="middle">
                    SEALED
                </text>
                <rect class="payla-stamp__banner-bg" x="10" y="78" width="80" height="13" rx="2.5" />
                <text class="payla-stamp__banner-text" x="50" y="86.5" text-anchor="middle">
                    NEW
                </text>
            </svg>
        </div>
    `;

    if (previewTrust) previewTrust.innerHTML = svg;
    if (sidePreviewTrust) sidePreviewTrust.innerHTML = svg;
}


/* --------------------------------------------------
   Load banks
-------------------------------------------------- */

async function loadBanks() {
    try {
        const response = await authFetch(`${BACKEND_URL}/api/payout/banks`);
        if (!response) return;

        if (!response.ok) {
            throw new Error(`Bank list request failed: ${response.status}`);
        }

        const data = await response.json();

        payoutBankSelect.innerHTML = '<option value="">Select your bank</option>';

        for (const bank of data.banks || []) {
            const option = document.createElement('option');
            option.value = String(bank.code);
            option.textContent = bank.name;
            payoutBankSelect.appendChild(option);
        }
    } catch (error) {
        console.error('Failed to load banks:', error);
        payoutBankSelect.innerHTML = '<option value="">Unable to load banks</option>';
    }
}


/* --------------------------------------------------
   Load saved onboarding data
-------------------------------------------------- */

async function loadUserData() {
    try {
        const response = await authFetch(`${BACKEND_URL}/api/onboarding/me`);
        if (!response) return;

        if (!response.ok) {
            throw new Error(`Unable to load onboarding data: ${response.status}`);
        }

        const user = await response.json();

        if (user.onboarding_complete) {
            window.location.replace('/entry');
            return;
        }

        ONBOARDING_STATE.userData = user;

        ONBOARDING_STATE.formData.username = user.username || '';
        ONBOARDING_STATE.formData.businessName = user.business_name || '';
        ONBOARDING_STATE.formData.payoutBank = user.payout_bank || '';
        ONBOARDING_STATE.formData.payoutAccount = user.payout_account_number || '';
        ONBOARDING_STATE.formData.plan = FREE_PLAN;

        usernameInput.value = ONBOARDING_STATE.formData.username;
        businessNameInput.value = ONBOARDING_STATE.formData.businessName;
        payoutBankSelect.value = ONBOARDING_STATE.formData.payoutBank;
        payoutAccountInput.value = ONBOARDING_STATE.formData.payoutAccount;

        ONBOARDING_STATE.validation.username.isValid = Boolean(user.username);
        ONBOARDING_STATE.validation.username.isChecking = false;

        ONBOARDING_STATE.validation.payoutAccount.isFormatValid =
            /^\d{10}$/.test(ONBOARDING_STATE.formData.payoutAccount);

        ONBOARDING_STATE.validation.payoutAccount.isVerified = false;
        ONBOARDING_STATE.validation.payoutAccount.accountName = null;

        updatePreview();

        if (
            ONBOARDING_STATE.validation.payoutAccount.isFormatValid &&
            ONBOARDING_STATE.formData.payoutBank
        ) {
            schedulePayoutVerification(
                ONBOARDING_STATE.formData.payoutBank,
                ONBOARDING_STATE.formData.payoutAccount,
                0
            );
        }

        updateUI();
    } catch (error) {
        console.error('Failed to load onboarding user:', error);
        alert('Unable to load your setup details. Please refresh and try again.');
    }
}


/* --------------------------------------------------
   Step validation
-------------------------------------------------- */

function validateCurrentStep() {
    switch (ONBOARDING_STATE.currentStep) {
        case 1:
            return (
                ONBOARDING_STATE.validation.username.isValid &&
                !ONBOARDING_STATE.validation.username.isChecking
            );
        case 2:
            return true;
        case 3:
            return Boolean(
                ONBOARDING_STATE.formData.payoutBank &&
                ONBOARDING_STATE.validation.payoutAccount.isFormatValid &&
                ONBOARDING_STATE.validation.payoutAccount.isVerified
            );
        case 4:
            return ONBOARDING_STATE.formData.plan === FREE_PLAN;
        case 5:
            return true;
        default:
            return false;
    }
}


/* --------------------------------------------------
   Username
-------------------------------------------------- */

function handleUsernameInput(event) {
    const username = event.target.value.trim().toLowerCase();
    ONBOARDING_STATE.formData.username = username;

    clearTimeout(usernameTimeout);
    usernameRequestId++;

    ONBOARDING_STATE.validation.username.isValid = false;
    ONBOARDING_STATE.validation.username.isChecking = false;

    const validFormat = /^[a-zA-Z0-9_-]{3,20}$/.test(username);

    if (!validFormat) {
        showUsernameStatus('error', 'Use 3–20 letters, numbers, hyphens or underscores.');
        updatePreview();
        updateUI();
        return;
    }

    showUsernameStatus('loading', 'Checking availability...');

    usernameTimeout = setTimeout(() => {
        checkUsernameAvailability(username);
    }, 500);

    updatePreview();
    updateUI();
}

async function checkUsernameAvailability(username) {
    const requestId = ++usernameRequestId;
    ONBOARDING_STATE.validation.username.isChecking = true;

    showUsernameStatus('loading', 'Checking availability...');
    updateUI();

    try {
        const params = new URLSearchParams({ username });
        const userId = ONBOARDING_STATE.userData?.id;
        if (userId) params.set('current_user_id', userId);

        const response = await authFetch(
            `${BACKEND_URL}/api/onboarding/validate-username?${params}`
        );

        if (!response || requestId !== usernameRequestId) return;
        if (!response.ok) throw new Error(`Username check failed: ${response.status}`);

        const data = await response.json();

        if (requestId !== usernameRequestId) return;
        if (username !== ONBOARDING_STATE.formData.username) return;

        ONBOARDING_STATE.validation.username.isValid = data.available === true;

        showUsernameStatus(
            data.available ? 'success' : 'error',
            data.message || (data.available ? 'Username is available.' : 'Username is unavailable.')
        );

        trackUsernameCheck(username, data.available === true);
    } catch (error) {
        if (requestId !== usernameRequestId) return;

        console.error('Username check failed:', error);
        ONBOARDING_STATE.validation.username.isValid = false;
        showUsernameStatus('error', 'Could not check availability. Please try again.');
    } finally {
        if (requestId === usernameRequestId) {
            ONBOARDING_STATE.validation.username.isChecking = false;
            updateUI();
        }
    }
}

function showUsernameStatus(type, message) {
    usernameStatus.style.display = 'none';
    usernameError.style.display = 'none';

    if (type === 'success') {
        usernameStatus.className = 'status success';
        usernameStatus.style.display = 'flex';
        const span = usernameStatus.querySelector('span');
        if (span) span.textContent = message;
    } else if (type === 'error') {
        usernameError.className = 'status error';
        usernameError.style.display = 'flex';
        const span = usernameError.querySelector('span');
        if (span) span.textContent = message;
    } else if (type === 'loading') {
        usernameStatus.className = 'status';
        usernameStatus.style.display = 'flex';
        const icon = document.createElement('i');
        icon.className = 'fas fa-spinner fa-spin';
        const span = document.createElement('span');
        span.textContent = message;
        usernameStatus.replaceChildren(icon, span);
    }
}


/* --------------------------------------------------
   Payout verification
-------------------------------------------------- */

function invalidatePayoutVerification() {
    clearTimeout(payoutTimeout);
    payoutVerificationRequestId++;
    ONBOARDING_STATE.validation.payoutAccount.isVerified = false;
    ONBOARDING_STATE.validation.payoutAccount.accountName = null;
}

function handlePayoutBankChange(event) {
    const bankCode = event.target.value;
    ONBOARDING_STATE.formData.payoutBank = bankCode;

    invalidatePayoutVerification();

    ONBOARDING_STATE.validation.payoutAccount.isFormatValid =
        /^\d{10}$/.test(ONBOARDING_STATE.formData.payoutAccount);

    if (bankCode) trackBankSelected(bankCode);

    if (bankCode && ONBOARDING_STATE.validation.payoutAccount.isFormatValid) {
        schedulePayoutVerification(bankCode, ONBOARDING_STATE.formData.payoutAccount);
    } else {
        payoutStatus.style.display = 'none';
    }

    updateUI();
}

function handlePayoutAccountInput(event) {
    const accountNumber = event.target.value.replace(/\D/g, '').slice(0, 10);
    event.target.value = accountNumber;
    ONBOARDING_STATE.formData.payoutAccount = accountNumber;

    invalidatePayoutVerification();

    ONBOARDING_STATE.validation.payoutAccount.isFormatValid =
        /^\d{10}$/.test(accountNumber);

    if (
        ONBOARDING_STATE.validation.payoutAccount.isFormatValid &&
        ONBOARDING_STATE.formData.payoutBank
    ) {
        schedulePayoutVerification(ONBOARDING_STATE.formData.payoutBank, accountNumber);
    } else {
        payoutStatus.style.display = 'none';
    }

    updateUI();
}

function schedulePayoutVerification(bankCode, accountNumber, delay = 500) {
    clearTimeout(payoutTimeout);

    payoutTimeout = setTimeout(() => {
        if (
            bankCode !== ONBOARDING_STATE.formData.payoutBank ||
            accountNumber !== ONBOARDING_STATE.formData.payoutAccount
        ) return;

        verifyPayoutAccount(bankCode, accountNumber);
    }, delay);
}

async function verifyPayoutAccount(bankCode, accountNumber) {
    const requestId = ++payoutVerificationRequestId;

    ONBOARDING_STATE.validation.payoutAccount.isVerified = false;
    ONBOARDING_STATE.validation.payoutAccount.accountName = null;

    payoutStatus.style.display = 'flex';
    payoutStatus.className = 'status';

    const spinner = document.createElement('i');
    spinner.className = 'fas fa-spinner fa-spin';
    payoutStatus.replaceChildren(spinner, document.createTextNode(' Verifying account...'));

    updateUI();

    try {
        const params = new URLSearchParams({ bank: bankCode, account: accountNumber });
        const response = await authFetch(`${BACKEND_URL}/api/payout/resolve?${params}`);

        if (!response || requestId !== payoutVerificationRequestId) return;

        let data = {};
        try { data = await response.json(); } catch {}

        if (requestId !== payoutVerificationRequestId) return;

        if (
            bankCode !== ONBOARDING_STATE.formData.payoutBank ||
            accountNumber !== ONBOARDING_STATE.formData.payoutAccount
        ) return;

        if (response.ok && data.account_name) {
            payoutStatus.className = 'status success';

            const icon = document.createElement('i');
            icon.className = 'fas fa-check-circle';
            const name = document.createElement('span');
            name.textContent = data.account_name;

            payoutStatus.replaceChildren(icon, name);

            ONBOARDING_STATE.validation.payoutAccount.isVerified = true;
            ONBOARDING_STATE.validation.payoutAccount.accountName = data.account_name;

            trackAccountVerified(true, bankCode);
        } else {
            ONBOARDING_STATE.validation.payoutAccount.isVerified = false;
            ONBOARDING_STATE.validation.payoutAccount.accountName = null;

            payoutStatus.className = 'status error';

            const icon = document.createElement('i');
            const message = document.createElement('span');

            if (response.status === 429 || response.status === 503) {
                icon.className = 'fas fa-clock';
                message.textContent = 'Bank verification is temporarily unavailable. Please try again shortly.';
            } else if (response.status === 400) {
                icon.className = 'fas fa-times-circle';
                message.textContent = data.detail || data.message || 'Unable to verify these bank details. Please check them.';
                trackAccountVerified(false, bankCode);
            } else {
                icon.className = 'fas fa-exclamation-circle';
                message.textContent = 'We could not verify this account right now. Please try again.';
            }

            payoutStatus.replaceChildren(icon, message);
        }
    } catch (error) {
        if (requestId !== payoutVerificationRequestId) return;

        console.error('Payout verification failed:', error);

        ONBOARDING_STATE.validation.payoutAccount.isVerified = false;
        ONBOARDING_STATE.validation.payoutAccount.accountName = null;

        payoutStatus.className = 'status error';

        const icon = document.createElement('i');
        icon.className = 'fas fa-exclamation-circle';
        const message = document.createElement('span');
        message.textContent = 'Verification failed. Check your connection and try again.';

        payoutStatus.replaceChildren(icon, message);
    } finally {
        if (requestId === payoutVerificationRequestId) updateUI();
    }
}


/* --------------------------------------------------
   Business name
-------------------------------------------------- */

function handleBusinessNameInput(event) {
    const businessName = event.target.value.trim();
    ONBOARDING_STATE.formData.businessName = businessName;

    if (businessName.length > 0) trackBusinessNameEntered(businessName.length);

    updatePreview();
    updateUI();
}


/* --------------------------------------------------
   Plan
-------------------------------------------------- */

function selectPlan() {
    ONBOARDING_STATE.formData.plan = FREE_PLAN;
    trackPlanSelected(FREE_PLAN);
    updateUI();
}


/* --------------------------------------------------
   Preview
-------------------------------------------------- */

function getInitials(name) {
    if (!name) return 'P';

    const initials = String(name)
        .trim()
        .split(/\s+/)
        .filter(Boolean)
        .map(word => word[0])
        .join('')
        .toUpperCase()
        .slice(0, 2);

    return initials || 'P';
}

function updatePreview() {
    const username = ONBOARDING_STATE.formData.username;
    const brand = ONBOARDING_STATE.formData.businessName || 'Your Name';
    const handle = username ? `@${username}` : '@yourusername';
    const initials = getInitials(ONBOARDING_STATE.formData.businessName || 'Payla');

    // Side panel
    if (sidePreviewBrand) sidePreviewBrand.textContent = brand;
    if (sidePreviewLink) sidePreviewLink.textContent = handle;
    if (sidePreviewLogoInitials) sidePreviewLogoInitials.textContent = initials;

    // Step 5
    if (previewBrand) previewBrand.textContent = brand;
    if (previewLink) previewLink.textContent = handle;
    if (previewLogoInitials) previewLogoInitials.textContent = initials;
}


/* --------------------------------------------------
   Complete
-------------------------------------------------- */

async function completeOnboarding() {
    if (!validateCurrentStep()) return;

    nextBtn.disabled = true;

    try {
        const payload = {
            username: ONBOARDING_STATE.formData.username,
            business_name: ONBOARDING_STATE.formData.businessName,
            payout_bank: ONBOARDING_STATE.formData.payoutBank,
            payout_account_number: ONBOARDING_STATE.formData.payoutAccount,
            plan: FREE_PLAN
        };

        const response = await authFetch(`${BACKEND_URL}/api/onboarding`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (!response) return;

        if (!response.ok) {
            let errorData = {};
            try { errorData = await response.json(); } catch {}

            const message = errorData.detail || 'Unable to complete onboarding.';
            trackOnboardingFailed(message);
            alert(message);
            return;
        }

        trackOnboardingCompleted(ONBOARDING_STATE.formData.username, FREE_PLAN);
        showSuccessModal();
    } catch (error) {
        console.error('Onboarding failed:', error);
        trackOnboardingFailed(error.message || 'Onboarding failed');
        alert('Failed to complete onboarding. Please try again.');
    } finally {
        nextBtn.disabled = false;
        updateUI();
    }
}

function showSuccessModal() {
    successModal.classList.add('open');

    const paylink = `${ONBOARDING_STATE.baseUrl}/@${ONBOARDING_STATE.formData.username}`;

    if (navigator.clipboard?.writeText) {
        navigator.clipboard.writeText(paylink).catch(error => {
            console.warn('Could not copy Paylink:', error);
        });
    }

    if (typeof window.twq === 'function') {
        window.twq('event', 'tw-r4oqa-r4p9b', { status: 'completed' });
    }
}


/* --------------------------------------------------
   Navigation
-------------------------------------------------- */

function goToNextStep() {
    if (!validateCurrentStep()) return;

    const fromStep = ONBOARDING_STATE.currentStep;
    const fromStepName = STEP_NAMES[fromStep];

    if (fromStep < ONBOARDING_STATE.totalSteps) {
        trackStepCompleted(fromStep, fromStepName);
        ONBOARDING_STATE.currentStep++;

        const toStep = ONBOARDING_STATE.currentStep;
        const toStepName = STEP_NAMES[toStep];

        trackNextClicked(fromStepName, toStepName);
        trackStepViewed(toStep, toStepName);

        window.scrollTo({ top: 0, behavior: 'smooth' });
        updateUI();

        if (toStep === 5) {
            trackPreviewViewed();
        }
    } else {
        completeOnboarding();
    }
}

function goToPreviousStep() {
    const fromStep = ONBOARDING_STATE.currentStep;
    if (fromStep <= 1) return;

    const fromStepName = STEP_NAMES[fromStep];
    ONBOARDING_STATE.currentStep--;

    const toStep = ONBOARDING_STATE.currentStep;
    const toStepName = STEP_NAMES[toStep];

    trackBackClicked(fromStepName, toStepName);
    trackStepViewed(toStep, toStepName);

    updateUI();
}


/* --------------------------------------------------
   UI
-------------------------------------------------- */

function updateUI() {
    stepElements.forEach(step => {
        const number = Number.parseInt(step.dataset.step, 10);
        step.classList.toggle('active', number === ONBOARDING_STATE.currentStep);
        step.classList.toggle('completed', number < ONBOARDING_STATE.currentStep);
    });

    stepContentElements.forEach((content, index) => {
        content.classList.toggle('active', index + 1 === ONBOARDING_STATE.currentStep);
    });

    backBtn.style.visibility =
        ONBOARDING_STATE.currentStep === 1 ? 'hidden' : 'visible';

    nextBtn.textContent =
        ONBOARDING_STATE.currentStep === 4
            ? 'Preview'
            : ONBOARDING_STATE.currentStep === 5
                ? 'Complete Setup'
                : 'Continue';

    nextBtn.disabled = !validateCurrentStep();

    // Refresh preview whenever the current step changes.
    updatePreview();
}


/* --------------------------------------------------
   Start
-------------------------------------------------- */

document.addEventListener('DOMContentLoaded', initializeOnboarding);