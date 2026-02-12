import { BACKEND_BASE } from './config.js';
import { authFetch, showUpgradeToast, showUpgradeModal } from './upgrade-handler.js';
// ── Backend URL ──
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
const previewLogo = document.getElementById('previewLogo');
const previewLogoInitials = document.getElementById('previewLogoInitials');
const previewName = document.getElementById('previewName');
const previewHandle = document.getElementById('previewHandle');
const previewEmail = document.getElementById('previewEmail');
const previewWhatsapp = document.getElementById('previewWhatsapp');
const previewPowered = document.getElementById('previewPowered');
const previewTagline = document.getElementById('previewTagline');
const previewPlanName = document.getElementById('previewPlanName');
const previewSecuredBy = document.querySelector('.secured-by');
const saveFab = document.getElementById('saveFab');
const profileForm = document.getElementById('profileForm');
const copyPaylinkBtn = document.getElementById('copyPaylink');
const toast = document.getElementById('toast');
const toastMessage = document.getElementById('toastMessage');
const planCard = document.querySelector('.plan-card');
const verifiedBadge = document.getElementById('verifiedBadge');
const usernameHint = document.getElementById('usernameHint');

let hasChanges = false;
let currentUserPlan = 'free';
let originalUsername = null;
let lastUsernameChange = null;

// ── Helpers ──
function showToast(message, type = 'info') {
    let text = message;

    if (typeof message === 'object' && message !== null) {
        text =
            message.message ||
            message.detail?.message ||
            JSON.stringify(message);
    }

    toastMessage.textContent = String(text);
    toast.classList.add('show', type);

    setTimeout(() => toast.classList.remove('show', type), 4000);

    console.log('[TOAST]', text);
}

function formatPhoneNumber(phone) {
    if (!phone) return '';
    const cleaned = phone.replace(/\D/g, '');
    if (cleaned.length === 11 && cleaned.startsWith('0')) return '+234 ' + cleaned.slice(1).replace(/(\d{3})(\d{3})(\d{4})/, '$1 $2 $3');
    if (cleaned.length === 13 && cleaned.startsWith('234')) return '+234 ' + cleaned.slice(3).replace(/(\d{3})(\d{3})(\d{4})/, '$1 $2 $3');
    if (cleaned.length === 10) return '+234 ' + cleaned.replace(/(\d{3})(\d{3})(\d{4})/, '$1 $2 $3');
    return phone;
}

function checkUpgradeRequired(response, data) {
    if (
        response.status === 403 &&
        data?.detail?.code?.startsWith('require_')
    ) {
        const { message, required_plan } = data.detail;

        showToast(message || 'This feature requires a paid plan', 'warning');

        // 🔥 THIS is the missing part
        showUpgradeModal(required_plan || 'silver');

        console.warn('[UPGRADE_REQUIRED]', data.detail);
        return true;
    }

    if (response.status === 401) {
        showToast('Unauthorized — please log in again', 'error');
        window.location.href = '/entry';
        return true;
    }

    return false;
}


// Character limit counters
const businessNameLimit = 30;
const taglineLimit = 45;

const businessNameCount = document.getElementById('businessNameCount');
const taglineCount = document.getElementById('taglineCount');

// ---- Business Name Limit ----
businessNameInput.addEventListener('input', () => {
    let val = businessNameInput.value;

    if (val.length > businessNameLimit) {
        businessNameInput.value = val.substring(0, businessNameLimit);
        val = businessNameInput.value;
    }

    const remaining = businessNameLimit - val.length;
    businessNameCount.textContent = `${remaining} characters left`;
});

// ---- Tagline Limit ----
taglineInput.addEventListener('input', () => {
    let val = taglineInput.value;

    if (val.length > taglineLimit) {
        taglineInput.value = val.substring(0, taglineLimit);
        val = taglineInput.value;
    }

    const remaining = taglineLimit - val.length;
    taglineCount.textContent = `${remaining} characters left`;
});

function canChangeUsername() {
    if (!lastUsernameChange) return true;
    const oneYearInMs = 365 * 24 * 60 * 60 * 1000;
    const now = new Date();
    return (now - lastUsernameChange) > oneYearInMs;
}

// ── Load Profile ──
async function loadProfile() {
    const token = localStorage.getItem('idToken');
    if (!token) return showToast('User not authenticated', 'error');

    try {
        const res = await fetch(`${BACKEND_URL}/api/profile/`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });

        if (res.status === 401) {
            showToast('Unauthorized — please log in again', 'error');
            return window.location.href = '/entry'; // redirect on 401
        }

        const data = await res.json();

        // Populate fields
        fullNameInput.value = data.full_name || '';
        businessNameInput.value = data.business_name || '';
        // backend stores phone as phone_number
        whatsappNumberInput.value = data.phone_number || '';
        usernameInput.value = data.username || '';
        originalUsername = data.username || null;
        emailInput.value = data.email || '';
        taglineInput.value = data.tagline || '';
        currentUserPlan = (data.plan || 'free').toLowerCase();
        lastUsernameChange = data.last_username_change ? new Date(data.last_username_change) : null;
        // Logo
        if (logoPreview && data.logo_url) {
            const fullUrl = data.logo_url.startsWith('http') ? data.logo_url : `${BACKEND_URL}${data.logo_url}`;
            logoPreview.style.backgroundImage = `url(${fullUrl})`;
            logoInitials.style.display = 'none';
        }else {
            // ensure gradient shows
            logoPreview.style.backgroundImage = ''; // allow CSS gradient
            logoInitials.style.display = 'flex';
        }

        // Update plan card
        const PLAN_INFO = {
            silver: { desc: 'Active • Premium features enabled', badge: 'SILVER' },
            gold: { desc: 'Active • Extra features unlocked', badge: 'GOLD' },
            opal: { desc: 'Active • All features unlocked', badge: 'OPAL' },
            free: { desc: 'Free • Upgrade for premium features', badge: 'FREE' }
        };

        planCard.className = `plan-card ${currentUserPlan}`;
        planCard.querySelector('strong').textContent = `Payla ${currentUserPlan.charAt(0).toUpperCase() + currentUserPlan.slice(1)}`;
        planCard.querySelector('p').textContent = (PLAN_INFO[currentUserPlan] || PLAN_INFO.free).desc;
        const planBadge = planCard.querySelector('.plan-badge span');
        if (planBadge) planBadge.textContent = (PLAN_INFO[currentUserPlan] || PLAN_INFO.free).badge;

        if (previewPlanName) {
            previewPlanName.textContent = `Payla ${currentUserPlan.charAt(0).toUpperCase() + currentUserPlan.slice(1)}`;
        }

        // Verified badge logic: show verified only for paid plans/trial
        if (['silver', 'gold', 'opal'].includes(currentUserPlan)) {
            verifiedBadge.textContent = 'Verified';
            verifiedBadge.classList.add('on');
        } else {
            verifiedBadge.textContent = 'Unverified';
            verifiedBadge.classList.remove('on');
        }

        ;
    } catch (err) {
        console.error(err);
        showToast('Failed to load profile', 'error');
    }
}

// ── Check username availability (calls /paylinks/check-username) ──
let usernameCheckToken = null;
async function checkUsernameAvailability(username) {
    usernameHint.textContent = '';
    if (!username) return;

    const usernameRegex = /^[a-z0-9_-]{3,20}$/;
    if (!usernameRegex.test(username)) {
        usernameHint.textContent = 'Invalid username format — use 3-20 letters/numbers/_/-';
        usernameHint.style.color = '#ef4444';
        return { available: false, message: 'Invalid format' };
    }

    try {
        const res = await fetch(`${BACKEND_URL}/api/paylinks/check-username`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ username })
        });
        const data = await res.json();

        if (res.status >= 400) {
            usernameHint.textContent = data.message || data.detail || 'Not available';
            usernameHint.style.color = '#ef4444';
            showToast(data.message || data.detail || 'Username check failed', 'error');
            return { available: false, message: data.message || data.detail || 'Unavailable' };
        }

        if (data.available) {
            usernameHint.textContent = data.message;
            usernameHint.style.color = '#16a34a';
            return { available: true, message: data.message };
        } else {
            usernameHint.textContent = data.message || 'Unavailable';
            usernameHint.style.color = '#ef4444';
            return { available: false, message: data.message || 'Unavailable' };
        }
    } catch (err) {
        console.error('Username check failed', err);
        showToast('Failed to check username', 'error');
        return { available: false, message: 'Check failed' };
    }
}

// ── Save Profile ──
// ── Save Profile ──
async function saveProfile() {
    const token = localStorage.getItem('idToken');
    if (!token) return showToast('User not authenticated', 'error');

    const newUsername = usernameInput.value.trim().toLowerCase();
    const isUsernameChanging = originalUsername !== newUsername;
    let usernameChangedSuccess = false;

    // --- Part A: Handle Username Change (with Gatekeeper) ---
    if (isUsernameChanging) {
        // 1. LOCAL GATEKEEPER: Check 1-year cooldown before calling API
        if (!canChangeUsername()) {
            showToast('Username is locked for 1 year. Other profile changes will be saved.', 'warning');
            // We skip Part A entirely, but continue to Part B so other fields save.
        } else {
            // 2. Availability Check
            const check = await checkUsernameAvailability(newUsername);
            if (!check.available) {
                showToast(check.message || 'Username unavailable', 'error');
                return; // Stop the entire save process if username is taken
            }

            // 3. Call Paylink API (Required for backend logic/Paystack page)
            try {
                const resPaylink = await fetch(`${BACKEND_URL}/api/paylinks/`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${token}`
                    },
                    body: JSON.stringify({
                        username: newUsername,
                        display_name: businessNameInput.value,
                        description: taglineInput.value,
                        currency: "NGN"
                    })
                });
                const paylinkData = await resPaylink.json();

                if (checkUpgradeRequired(resPaylink, paylinkData)) return;

                if (resPaylink.status >= 400) {
                    showToast(paylinkData.detail || 'Failed to update paylink', 'error');
                    return;
                }
                usernameChangedSuccess = true;
            } catch (err) {
                console.error(err);
                showToast('Failed to save paylink', 'error');
                return;
            }
        }
    }

    // --- Part B: Handle Profile Update (Syncing data to main User record) ---
    // If username changed successfully, we use newUsername. 
    // If cooldown was active or call failed, we revert to originalUsername for the profile record.
    const payload = {
        full_name: fullNameInput.value,
        business_name: businessNameInput.value,
        username: usernameChangedSuccess ? newUsername : originalUsername,
        phone_number: whatsappNumberInput.value,
        tagline: taglineInput?.value || ""
    };

    try {
        const res = await fetch(`${BACKEND_URL}/api/profile/update`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify(payload)
        });

        const data = await res.json();

        if (checkUpgradeRequired(res, data)) return;
        
        // Final catch for profile update errors
        if (res.status >= 400) {
            showToast(data.detail || 'Failed to save profile', 'error');
            return;
        }

        // --- Part C: FINAL SUCCESS ---
        showToast('Profile updated successfully', 'success');
        
        // Sync local state ONLY if the change actually happened
        if (usernameChangedSuccess) {
            originalUsername = newUsername;
            lastUsernameChange = new Date(); 
        }
        
        hasChanges = false;
        saveFab.classList.remove('visible');
    } catch (err) {
        console.error(err);
        showToast('Failed to save profile', 'error');
    }
}
// ── Upload Logo ──
logoUploadInput.addEventListener('change', async function(e) {
    const file = e.target.files[0];
    if (!file) return;

    // 1. Validation
    if (file.size > 2 * 1024 * 1024) return showToast('File too large! Max 2MB', 'error');

    // 2. Immediate "Elite" Loading State
    // We show a local preview immediately so the user isn't staring at a blank screen
    const reader = new FileReader();
    reader.onload = (event) => {
        logoPreview.style.backgroundImage = `url(${event.target.result})`;
        logoPreview.style.filter = 'blur(4px) brightness(0.7)'; // "Processing" look
        logoInitials.innerHTML = '<i class="fas fa-circle-notch fa-spin"></i>';
        logoInitials.style.display = 'flex';
        logoInitials.style.color = 'var(--rose-gold)';
    };
    reader.readAsDataURL(file);

    const formData = new FormData();
    formData.append('file', file);

    const token = localStorage.getItem('idToken');
    if (!token) return showToast('User not authenticated', 'error');

    try {
        const res = await fetch(`${BACKEND_URL}/api/profile/upload-logo`, {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${token}` },
            body: formData
        });

        const data = await res.json();

        if (checkUpgradeRequired(res, data)) {
            resetLogoUI(); // Helper to clear loading if upgrade needed
            return;
        }

        if (res.status >= 400) {
            showToast(data.detail || data.message || 'Upload failed', 'error');
            resetLogoUI();
            return;
        }

        if (data.logo_url) {
            const fullUrl = data.logo_url.startsWith('http') ? data.logo_url : `${BACKEND_URL}${data.logo_url}`;
            
            // 3. Smooth Transition to Final Cloud Image
            const img = new Image();
            img.onload = () => {
                logoPreview.style.backgroundImage = `url(${fullUrl})`;
                logoPreview.style.filter = 'none'; // Clear the blur
                logoInitials.style.display = 'none';
                showToast('Logo updated on the cloud', 'success');
            };
            img.src = fullUrl;
        } else {
            resetLogoUI();
        }
    } catch (err) {
        console.error(err);
        showToast('Failed to upload logo', 'error');
        resetLogoUI();
    }
});

// Helper to reset UI state on failure/cancel
function resetLogoUI() {
    logoPreview.style.filter = 'none';
    // Logic to restore initials or previous state if needed
    if (!logoPreview.style.backgroundImage || logoPreview.style.backgroundImage === 'none') {
        logoInitials.style.display = 'flex';
        logoInitials.innerHTML = originalInitials || 'P'; // Use a stored value or default
    } else {
        logoInitials.style.display = 'none';
    }
}

[fullNameInput, businessNameInput, whatsappNumberInput, taglineInput].forEach(input => {
    input.addEventListener('input', () => {
        hasChanges = true;
        saveFab.classList.add('visible');
    });
});


// username blur triggers availability check
usernameInput.addEventListener('blur', function() {
    const val = this.value.trim().toLowerCase();
    checkUsernameAvailability(val);
});

// save
saveFab.addEventListener('click', saveProfile);

copyPaylinkBtn.addEventListener('click', () => {
    const paylink = `payla.ng/${usernameInput.value || 'username'}`;
    navigator.clipboard.writeText(paylink).then(() => showToast('Paylink copied to clipboard!', 'success'));
});

// ── Validation ──
usernameInput.addEventListener('input', function() {
    const val = this.value.trim().toLowerCase();
    const usernameRegex = /^[a-z0-9_-]{3,20}$/;
    
    usernameHint.textContent = '';
    this.style.borderColor = '';

    const isChanging = val !== originalUsername;

    // Rule: Format Validation
    if (!usernameRegex.test(val)) {
        this.style.borderColor = '#ef4444'; 
        usernameHint.textContent = 'Use 3-20 letters, numbers, dashes, or underscores.';
        usernameHint.style.color = '#ef4444';
        saveFab.classList.remove('visible'); // Block saving invalid format
        return;
    }

    // Rule: Once-per-year Cooldown
    if (isChanging && lastUsernameChange) {
        const oneYearInMs = 365 * 24 * 60 * 60 * 1000;
        const now = new Date();
        const timeSinceChange = now - new Date(lastUsernameChange);

        if (timeSinceChange < oneYearInMs) {
            const daysLeft = Math.ceil((oneYearInMs - timeSinceChange) / (1000 * 60 * 60 * 24));
            this.style.borderColor = '#f59e0b'; // Amber
            usernameHint.textContent = `Username locked. Available in ${daysLeft} days.`;
            usernameHint.style.color = '#f59e0b';
            saveFab.classList.remove('visible'); // Block saving during cooldown
            return;
        }
    }

    // Rule: If it's valid and different from original, allow saving
    if (isChanging) {
        hasChanges = true; // Mark that we have a valid change
        saveFab.classList.add('visible');
    } else {
        // If they typed back to their original name, and no other fields changed, hide fab
        // Note: This logic assumes no other fields are dirty. 
        // For a simpler life, you can just keep hasChanges as true.
    }
});

whatsappNumberInput.addEventListener('blur', function() {
    const phone = this.value.replace(/\D/g, '');
    if (phone.length < 10) {
        showToast('Please enter a valid phone number', 'error');
        this.style.borderColor = '#ef4444';
    } else {
        this.style.borderColor = '';
        this.value = formatPhoneNumber(this.value);
    }
});


// Prevent default form submission
profileForm.addEventListener('submit', e => e.preventDefault());

// ── Initialize
document.addEventListener('DOMContentLoaded', loadProfile);
