import { BACKEND_BASE } from './config.js';
import { showUpgradeRequired } from './upgrade-handler.js';

const BACKEND_URL = BACKEND_BASE;

// ── DOM Elements ──

const fullNameInput = document.getElementById('fullName');
const businessNameInput = document.getElementById('businessName');
const whatsappNumberInput = document.getElementById('whatsappNumber');
const emailInput = document.getElementById('email');
const usernameInput = document.getElementById('username');
const taglineInput = document.getElementById('businessTagline');

const logoUploadInput = document.getElementById('logoUpload');
const logoPreview = document.getElementById('logoPreview');
const logoInitials = document.getElementById('logoInitials');

const saveFab = document.getElementById('saveFab');
const profileForm = document.getElementById('profileForm');
const copyPaylinkBtn = document.getElementById('copyPaylink');

const toast = document.getElementById('toast');
const toastMessage = document.getElementById('toastMessage');
const planCard = document.querySelector('.plan-card');

const usernameHint = document.getElementById('usernameHint');

const defaultInvoiceFeePayerInput =
    document.getElementById('defaultInvoiceFeePayer');

const businessNameCount = document.getElementById('businessNameCount');
const taglineCount = document.getElementById('taglineCount');
const domainSelector = document.getElementById('domainSelector');
const domainUpsell = document.getElementById('domainUpsell');
const domainNg = document.getElementById('domainNg');
const domainVip = document.getElementById('domainVip');
const paylinkPrefix = document.getElementById('paylinkPrefix');
const handleNg = document.getElementById('handleNg');
const handleVip = document.getElementById('handleVip');

// ── State ──

let hasChanges = false;
let isSaving = false;
let currentUserPlan = 'free';
let hasSilverAccess = false;
let originalUsername = null;
let lastUsernameChange = null;
let originalInitials = 'P';
let originalLogoUrl = null;
let usernameCheckToken = 0;
let currentPreferredDomain = 'ng';
let canUseVip = false;

// ── Helpers ──

function getToken() {
    return localStorage.getItem('idToken');
}

function showToast(message, type = 'info') {
    let text = message;

    if (typeof message === 'object' && message !== null) {
        text =
            message.message ||
            message.detail?.message ||
            message.detail ||
            JSON.stringify(message);
    }

    toastMessage.textContent = String(text);
    toast.classList.remove('show', 'info', 'success', 'warning', 'error');
    toast.classList.add('show', type);

    window.setTimeout(() => {
        toast.classList.remove('show', type);
    }, 4000);
}

function setHasChanges(changed = true) {
    hasChanges = changed;

    if (saveFab) {
        saveFab.classList.toggle('visible', hasChanges);
    }
}

function getErrorMessage(data, fallback) {
    if (typeof data?.detail === 'string') {
        return data.detail;
    }

    if (typeof data?.detail?.message === 'string') {
        return data.detail.message;
    }

    if (typeof data?.message === 'string') {
        return data.message;
    }

    return fallback;
}

function handleAuthenticationError() {
    showToast('Unauthorized. Please log in again.', 'error');
    window.location.href = '/entry';
}

/**
 * Detect a subscription-required 403 and route it through the
 * upgrade handler. Returns true if the response was handled.
 */
function checkUpgradeRequired(response, data, feature) {
    if (response.status === 403) {
        const detail = data?.detail;

        if (
            typeof detail === 'object' &&
            detail !== null &&
            detail.error === 'subscription_required'
        ) {
            showUpgradeRequired({ feature: feature || null, source: 'server' });
            return true;
        }
    }

    if (response.status === 401) {
        handleAuthenticationError();
        return true;
    }

    return false;
}

async function readResponse(response) {
    try {
        return await response.json();
    } catch {
        return {};
    }
}

function formatPhoneNumber(phone) {
    if (!phone) return '';

    const cleaned = phone.replace(/\D/g, '');

    if (cleaned.length === 11 && cleaned.startsWith('0')) {
        return '+234 ' + cleaned.slice(1).replace(
            /(\d{3})(\d{3})(\d{4})/,
            '$1 $2 $3'
        );
    }

    if (cleaned.length === 13 && cleaned.startsWith('234')) {
        return '+234 ' + cleaned.slice(3).replace(
            /(\d{3})(\d{3})(\d{4})/,
            '$1 $2 $3'
        );
    }

    if (cleaned.length === 10) {
        return '+234 ' + cleaned.replace(
            /(\d{3})(\d{3})(\d{4})/,
            '$1 $2 $3'
        );
    }

    return phone;
}

function getInitials(name) {
    const words = String(name || '').trim().split(/\s+/).filter(Boolean);

    if (!words.length) return 'P';

    return words
        .slice(0, 2)
        .map(word => word.charAt(0).toUpperCase())
        .join('');
}

function updateCharacterCounter(input, counter, limit) {
    if (!input || !counter) return;

    counter.textContent = `${Math.max(0, limit - input.value.length)} characters left`;
}

function canChangeUsername() {
    if (!lastUsernameChange) return true;

    const changedAt = new Date(lastUsernameChange).getTime();

    if (Number.isNaN(changedAt)) return true;

    return Date.now() - changedAt >= 365 * 24 * 60 * 60 * 1000;
}

/**
 * The plan card reflects the user's entitlement, not their raw
 * plan string. An expired Silver user has plan === "silver" but
 * has_silver === false, and the card should read as Free.
 */
function updatePlanCard() {
    if (!planCard) return;

    const planInfo = {
        silver: {
            desc: 'Active • Premium features enabled',
            badge: 'SILVER'
        },
        gold: {
            desc: 'Active • Extra features unlocked',
            badge: 'GOLD'
        },
        opal: {
            desc: 'Active • All features unlocked',
            badge: 'OPAL'
        },
        free: {
            desc: 'Free • Upgrade for premium features',
            badge: 'FREE'
        }
    };

    // The displayed plan follows entitlement, not the raw string.
    const displayPlan = hasSilverAccess
        ? (currentUserPlan === 'free' ? 'silver' : currentUserPlan)
        : 'free';

    const plan = planInfo[displayPlan] || planInfo.free;
    const formattedPlan =
        displayPlan.charAt(0).toUpperCase() +
        displayPlan.slice(1);

    planCard.className = `plan-card ${displayPlan}`;

    const heading = planCard.querySelector('strong');
    const description = planCard.querySelector('p');
    const badge = planCard.querySelector('.plan-badge span');

    if (heading) heading.textContent = `Payla ${formattedPlan}`;
    if (description) description.textContent = plan.desc;
    if (badge) badge.textContent = plan.badge;

}

function updateLogoPreview(url) {
    if (!logoPreview) return;

    if (url) {
        const fullUrl = url.startsWith('http') || url.startsWith('data:') || url.startsWith('/')
            ? url
            : `${BACKEND_URL}${url}`;

        logoPreview.style.backgroundImage = `url("${fullUrl}")`;
        logoPreview.classList.remove('initials-medallion');
        logoPreview.innerHTML = '';
    } else {
        logoPreview.style.backgroundImage = '';
        logoPreview.classList.add('initials-medallion');

        const text = document.createElement('span');
        text.className = 'initials-medallion__text';
        text.textContent = originalInitials;

        logoPreview.innerHTML = '';
        logoPreview.appendChild(text);
    }

    logoPreview.style.filter = 'none';
}

// ── Bank Confirmation Card ──

const BANK_STATUS_CONFIG = {
    matched: {
        label: 'Confirmed',
        message:
            'Your Payla name matches the name on your bank account. ' +
            'Your paylink shows the verified stamp.',
        tone: 'success',
    },
    mismatch: {
        label: 'Action needed',
        message:
            'The name on your bank account doesn\u2019t match the name on ' +
            'your Payla profile. Contact support so we can help you ' +
            'confirm the account.',
        tone: 'warn',
    },
    pending: {
        label: 'In progress',
        message:
            'We\u2019re confirming your bank account. This usually ' +
            'completes within a few minutes.',
        tone: 'info',
    },
    failed: {
        label: 'Temporarily unavailable',
        message:
            'We couldn\u2019t reach the bank to confirm your account. ' +
            'We\u2019ll try again automatically \u2014 you don\u2019t need ' +
            'to do anything.',
        tone: 'error',
    },
};

async function loadBankConfirmation() {
    const card = document.getElementById('bankConfirmation');
    if (!card) return;

    const statusEl = document.getElementById('bankConfirmStatus');
    const statusLabel = statusEl?.querySelector('.bank-confirmation__status-label');
    const enteredNameEl = document.getElementById('enteredName');
    const bankNameEl = document.getElementById('bankName');
    const messageEl = document.getElementById('bankConfirmMessage');
    const actionsEl = document.getElementById('bankConfirmActions');

    const token = getToken();
    if (!token) return;

    try {
        const response = await fetch(
            `${BACKEND_URL}/api/profile/bank-confirmation`,
            {
                headers: {
                    Authorization: `Bearer ${token}`,
                },
            }
        );

        if (response.status === 401) {
            handleAuthenticationError();
            return;
        }

        if (!response.ok) return;

        const data = await readResponse(response);
        const status = data.status || 'pending';
        const config = BANK_STATUS_CONFIG[status] || BANK_STATUS_CONFIG.pending;

        if (enteredNameEl) {
            enteredNameEl.textContent = data.entered_full_name || '—';
        }

        if (bankNameEl) {
            bankNameEl.textContent = data.bank_confirmed_name || '—';
        }

        if (statusEl && statusLabel) {
            statusEl.dataset.status = config.tone;
            statusLabel.textContent = config.label;
        }

        if (messageEl) {
            messageEl.textContent = config.message;
        }

        if (actionsEl) {
            actionsEl.hidden = status !== 'mismatch';
        }

        card.hidden = false;
    } catch (error) {
        console.warn('Could not load bank confirmation:', error);
    }
}

// ── Character Counters ──

businessNameInput?.addEventListener('input', () => {
    if (businessNameInput.value.length > 30) {
        businessNameInput.value = businessNameInput.value.slice(0, 30);
    }

    updateCharacterCounter(businessNameInput, businessNameCount, 30);
    setHasChanges();
});

taglineInput?.addEventListener('input', () => {
    if (taglineInput.value.length > 45) {
        taglineInput.value = taglineInput.value.slice(0, 45);
    }

    updateCharacterCounter(taglineInput, taglineCount, 45);
    setHasChanges();
});

function renderDomainSelector() {
    if (!domainSelector || !domainUpsell) return;

    const username = usernameInput?.value.trim() || 'yourusername';
    const handle = `/@${username}`;

    if (handleNg) handleNg.textContent = handle;
    if (handleVip) handleVip.textContent = handle;

    // Only Silver users can change the domain.
    if (canUseVip) {
        domainSelector.hidden = false;
        domainUpsell.hidden = true;
    } else {
        domainSelector.hidden = true;
        domainUpsell.hidden = false;
    }

    if (domainNg) {
        domainNg.checked = currentPreferredDomain === 'ng';
    }
    if (domainVip) {
        domainVip.checked = currentPreferredDomain === 'vip';
    }

    if (paylinkPrefix) {
        paylinkPrefix.textContent =
            currentPreferredDomain === 'vip' ? 'payla.vip/' : 'payla.ng/';
    }
}

function setPreferredDomain(domain) {
    if (domain !== 'ng' && domain !== 'vip') return;
    if (domain === currentPreferredDomain) return;

    currentPreferredDomain = domain;
    renderDomainSelector();
    setHasChanges();
}

domainNg?.addEventListener('change', () => {
    if (domainNg.checked) setPreferredDomain('ng');
});

domainVip?.addEventListener('change', () => {
    if (domainVip.checked) setPreferredDomain('vip');
});

usernameInput?.addEventListener('input', () => {
    renderDomainSelector();
});

// ── Load Profile ──

async function loadProfile() {
    const token = getToken();

    if (!token) {
        showToast('User not authenticated.', 'error');
        return;
    }

    try {
        const response = await fetch(`${BACKEND_URL}/api/profile/`, {
            headers: {
                Authorization: `Bearer ${token}`
            }
        });

        const data = await readResponse(response);

        if (response.status === 401) {
            handleAuthenticationError();
            return;
        }

        if (!response.ok) {
            showToast(getErrorMessage(data, 'Failed to load profile.'), 'error');
            return;
        }

        // Populate profile fields.
        fullNameInput.value = data.full_name || '';
        businessNameInput.value = data.business_name || '';
        whatsappNumberInput.value = data.phone_number || '';
        usernameInput.value = data.username || '';
        emailInput.value = data.email || '';
        taglineInput.value = data.tagline || '';

        originalUsername = (data.username || '').toLowerCase();
        currentUserPlan = (data.plan || 'free').toLowerCase();

        // Entitlement flag from the backend — this is what the plan
        // card should trust, not the raw plan string.
        hasSilverAccess = Boolean(data.entitlement?.has_silver);

        canUseVip = Boolean(data.entitlement?.can_use_vip);
        currentPreferredDomain = data.preferred_domain === 'vip' ? 'vip' : 'ng';

        renderDomainSelector();

        lastUsernameChange = data.last_username_change
            ? new Date(data.last_username_change)
            : null;

        originalInitials = getInitials(
            data.business_name || data.full_name
        );

        originalLogoUrl = data.logo_url || null;
        updateLogoPreview(originalLogoUrl);

        const savedFeePayer = data.default_invoice_fee_payer;

        if (defaultInvoiceFeePayerInput) {
            defaultInvoiceFeePayerInput.value =
                savedFeePayer === 'client' ? 'client' : 'merchant';
        }

        updatePlanCard();

        updateCharacterCounter(businessNameInput, businessNameCount, 30);
        updateCharacterCounter(taglineInput, taglineCount, 45);

        setHasChanges(false);
    } catch (error) {
        console.error('Failed to load profile:', error);
        showToast('Failed to load profile.', 'error');
    }
}

// ── Username Availability ──

async function checkUsernameAvailability(username) {
    if (!usernameHint) return { available: false, message: 'Username field unavailable.' };

    usernameHint.textContent = '';

    if (!username) {
        return { available: false, message: 'Enter a username.' };
    }

    const normalizedUsername = username.trim().toLowerCase();
    const usernameRegex = /^[a-z0-9_-]{3,20}$/;

    if (!usernameRegex.test(normalizedUsername)) {
        usernameHint.textContent =
            'Invalid format. Use 3–20 letters, numbers, dashes, or underscores.';
        usernameHint.style.color = '#ef4444';

        return { available: false, message: 'Invalid username format.' };
    }

    const checkToken = ++usernameCheckToken;

    try {
        const response = await fetch(
            `${BACKEND_URL}/api/paylinks/check-username`,
            {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    username: normalizedUsername
                })
            }
        );

        const data = await readResponse(response);

        if (checkToken !== usernameCheckToken) {
            return { available: false, message: 'A newer check is running.' };
        }

        if (!response.ok) {
            const message = getErrorMessage(
                data,
                'Username availability check failed.'
            );

            usernameHint.textContent = message;
            usernameHint.style.color = '#ef4444';

            return { available: false, message };
        }

        if (data.available) {
            usernameHint.textContent = data.message || 'Username is available.';
            usernameHint.style.color = '#16a34a';

            return { available: true, message: data.message };
        }

        const message = data.message || 'Username is unavailable.';

        usernameHint.textContent = message;
        usernameHint.style.color = '#ef4444';

        return { available: false, message };
    } catch (error) {
        console.error('Username availability check failed:', error);

        return {
            available: false,
            message: 'Could not check username availability.'
        };
    }
}

// ── Save Profile ──

async function saveProfile() {
    if (isSaving) return;

    const token = getToken();

    if (!token) {
        showToast('User not authenticated.', 'error');
        return;
    }

    const newUsername = usernameInput.value.trim().toLowerCase();
    const usernameRegex = /^[a-z0-9_-]{3,20}$/;

    if (!usernameRegex.test(newUsername)) {
        showToast(
            'Username must contain 3–20 letters, numbers, dashes, or underscores.',
            'error'
        );
        return;
    }

    if (!fullNameInput.value.trim()) {
        showToast('Please enter your full name.', 'error');
        return;
    }

    if (!businessNameInput.value.trim()) {
        showToast('Please enter your business name.', 'error');
        return;
    }

    const phoneDigits = whatsappNumberInput.value.replace(/\D/g, '');

    if (phoneDigits.length < 10) {
        showToast('Please enter a valid WhatsApp number.', 'error');
        whatsappNumberInput.focus();
        return;
    }

    isSaving = true;

    if (saveFab) {
        saveFab.disabled = true;
    }

    try {
        let usernameChangedSuccess = false;
        const isUsernameChanging = newUsername !== (originalUsername || '');

        if (isUsernameChanging) {
            if (!canChangeUsername()) {
                showToast(
                    'Your username is locked for one year. Other profile changes will still be saved.',
                    'warning'
                );
            } else {
                const check = await checkUsernameAvailability(newUsername);

                if (!check.available) {
                    showToast(check.message, 'error');
                    return;
                }

                const paylinkResponse = await fetch(
                    `${BACKEND_URL}/api/paylinks/`,
                    {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            Authorization: `Bearer ${token}`
                        },
                        body: JSON.stringify({
                            username: newUsername,
                            display_name: businessNameInput.value.trim(),
                            description: taglineInput.value.trim(),
                            currency: 'NGN',
                            preferred_domain: canUseVip
                                ? currentPreferredDomain
                                : undefined
                        })
                    }
                );

                const paylinkData = await readResponse(paylinkResponse);

                if (checkUpgradeRequired(paylinkResponse, paylinkData, 'invoices')) {
                    return;
                }

                if (!paylinkResponse.ok) {
                    showToast(
                        getErrorMessage(paylinkData, 'Failed to update Paylink.'),
                        'error'
                    );
                    return;
                }

                usernameChangedSuccess = true;
            }
        }

        const usernameToSave = usernameChangedSuccess
            ? newUsername
            : (originalUsername || '');

        const payload = {
            full_name: fullNameInput.value.trim(),
            business_name: businessNameInput.value.trim(),
            username: usernameToSave,
            phone_number: whatsappNumberInput.value.trim(),
            tagline: taglineInput.value.trim(),
            default_invoice_fee_payer:
                defaultInvoiceFeePayerInput?.value === 'client'
                    ? 'client'
                    : 'merchant'
        };

        if (canUseVip) {
            payload.preferred_domain = currentPreferredDomain;
        }

        const response = await fetch(`${BACKEND_URL}/api/profile/update`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                Authorization: `Bearer ${token}`
            },
            body: JSON.stringify(payload)
        });

        const data = await readResponse(response);

        if (checkUpgradeRequired(response, data)) {
            return;
        }

        if (!response.ok) {
            showToast(
                getErrorMessage(data, 'Failed to save profile.'),
                'error'
            );
            return;
        }

        if (usernameChangedSuccess) {
            originalUsername = newUsername;
            lastUsernameChange = new Date();
        }

        originalInitials = getInitials(
            businessNameInput.value || fullNameInput.value
        );

        showToast('Profile updated successfully.', 'success');
        setHasChanges(false);

        loadBankConfirmation();

        if (data.preferred_domain) {
            currentPreferredDomain =
                data.preferred_domain === 'vip' ? 'vip' : 'ng';
            renderDomainSelector();
        }
    } catch (error) {
        console.error('Failed to save profile:', error);
        showToast('Failed to save profile. Please try again.', 'error');
    } finally {
        isSaving = false;

        if (saveFab) {
            saveFab.disabled = false;
        }
    }
}

// ── Upload Logo ──

function resetLogoUI() {
    updateLogoPreview(originalLogoUrl);
}

logoUploadInput?.addEventListener('change', async event => {
    const file = event.target.files?.[0];

    if (!file) return;

    if (file.size > 2 * 1024 * 1024) {
        showToast('File too large. Maximum size is 2MB.', 'error');
        logoUploadInput.value = '';
        return;
    }

    const allowedTypes = [
        'image/jpeg',
        'image/jpg',
        'image/png',
        'image/webp',
        'image/svg+xml'
    ];

    if (!allowedTypes.includes(file.type)) {
        showToast('Please select a PNG, JPG, WebP, or SVG image.', 'error');
        logoUploadInput.value = '';
        return;
    }

    const token = getToken();

    if (!token) {
        showToast('User not authenticated.', 'error');
        return;
    }

    const reader = new FileReader();

    reader.onload = resultEvent => {
        if (!logoPreview) return;

        logoPreview.style.backgroundImage = `url("${resultEvent.target.result}")`;
        logoPreview.style.filter = 'blur(4px) brightness(0.7)';
        logoPreview.classList.add('initials-medallion');
        logoPreview.innerHTML = '<span class="initials-medallion__spinner"><i class="fas fa-circle-notch fa-spin"></i></span>';
    };

    reader.readAsDataURL(file);

    const formData = new FormData();
    formData.append('file', file);

    try {
        const response = await fetch(
            `${BACKEND_URL}/api/profile/upload-logo`,
            {
                method: 'POST',
                headers: {
                    Authorization: `Bearer ${token}`
                },
                body: formData
            }
        );

        const data = await readResponse(response);

        if (checkUpgradeRequired(response, data, 'branding')) {
            resetLogoUI();
            return;
        }

        if (!response.ok) {
            showToast(
                getErrorMessage(data, 'Logo upload failed.'),
                'error'
            );
            resetLogoUI();
            return;
        }

        if (!data.logo_url) {
            showToast('Upload completed without a logo URL.', 'error');
            resetLogoUI();
            return;
        }

        originalLogoUrl = data.logo_url;
        updateLogoPreview(originalLogoUrl);

        showToast('Logo updated successfully.', 'success');
    } catch (error) {
        console.error('Logo upload failed:', error);
        showToast('Failed to upload logo.', 'error');
        resetLogoUI();
    } finally {
        logoUploadInput.value = '';
    }
});

// ── Dirty State / Change Tracking ──

[
    fullNameInput,
    businessNameInput,
    whatsappNumberInput,
    taglineInput
].forEach(input => {
    input?.addEventListener('input', () => setHasChanges());
});

defaultInvoiceFeePayerInput?.addEventListener('change', () => {
    setHasChanges();
});

// ── Username Validation ──

usernameInput?.addEventListener('input', function () {
    const value = this.value.trim().toLowerCase();
    const usernameRegex = /^[a-z0-9_-]{3,20}$/;

    usernameHint.textContent = '';
    this.style.borderColor = '';

    if (!usernameRegex.test(value)) {
        this.style.borderColor = '#ef4444';
        usernameHint.textContent =
            'Use 3–20 letters, numbers, dashes, or underscores.';
        usernameHint.style.color = '#ef4444';

        setHasChanges();
        return;
    }

    if (value !== (originalUsername || '') && !canChangeUsername()) {
        const nextChange = lastUsernameChange
            ? new Date(lastUsernameChange).getTime() + 365 * 24 * 60 * 60 * 1000
            : Date.now();

        const daysLeft = Math.max(
            1,
            Math.ceil((nextChange - Date.now()) / (24 * 60 * 60 * 1000))
        );

        this.style.borderColor = '#f59e0b';
        usernameHint.textContent =
            `Username locked. Available in ${daysLeft} days.`;
        usernameHint.style.color = '#f59e0b';
    }

    setHasChanges();
});

usernameInput?.addEventListener('blur', async function () {
    const value = this.value.trim().toLowerCase();

    if (!value || value === (originalUsername || '')) {
        usernameHint.textContent = '';
        return;
    }

    await checkUsernameAvailability(value);
});

// ── Phone Validation ──

whatsappNumberInput?.addEventListener('blur', function () {
    const phone = this.value.replace(/\D/g, '');

    if (phone.length < 10) {
        showToast('Please enter a valid WhatsApp number.', 'error');
        this.style.borderColor = '#ef4444';
        return;
    }

    this.style.borderColor = '';
    this.value = formatPhoneNumber(this.value);
});

// ── Buttons ──

saveFab?.addEventListener('click', saveProfile);

copyPaylinkBtn?.addEventListener('click', async () => {
    const username = usernameInput.value.trim();

    if (!username) {
        showToast('Enter a username first.', 'warning');
        return;
    }

    const base = currentPreferredDomain === 'vip'
        ? 'https://payla.vip'
        : 'https://payla.ng';

    const paylink = `${base}/@${username}`;

    try {
        await navigator.clipboard.writeText(paylink);
        showToast('Paylink copied to clipboard!', 'success');
    } catch (error) {
        console.error('Could not copy Paylink:', error);
        showToast('Could not copy the Paylink. Please copy it manually.', 'error');
    }
});

profileForm?.addEventListener('submit', event => {
    event.preventDefault();
});

// ── Initialize ──

document.addEventListener('DOMContentLoaded', () => {
    loadProfile();
    loadBankConfirmation();
});