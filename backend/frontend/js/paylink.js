// ====================================================
// PAYLA PAYLINK PAGE
// ====================================================
import { BACKEND_BASE, PAYSTACK_PUBLIC_KEY } from './config.js';

import {
  trackPaylinkPageView,
  trackTransferButtonClicked,
  trackPaymentModalOpened,
  trackPaymentModalClosed,
  trackPaymentAttempt,
  trackPaymentSuccess,
  trackPaymentFailed,
  trackReceiptDownloaded,
  trackPaylinkLoadSuccess,
  trackPaylinkLoadFailed,
  trackEmailClicked,
  trackWhatsAppClicked,
  trackAmountEntered,
  trackAmountFocus
} from "./paylink_analytics.js";


/* ============================================================
   HELPERS
   ============================================================ */
function escapeHtml(str) {
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function normalizePhoneForTel(phone) {
    if (!phone) return null;
    const digits = phone.replace(/\D/g, '');
    if (!digits) return null;
    if (digits.length === 11 && digits.startsWith('0')) return '234' + digits.slice(1);
    if (digits.length === 13 && digits.startsWith('234')) return digits;
    if (digits.length === 10) return '234' + digits;
    return digits;
}


/* ============================================================
   TRUST MARK — states and builders
   ============================================================ */
const TRUST_STATE = {
    VERIFIED: 'verified',
    UNVERIFIED: 'unverified',
};

// Silver state — drives receipt button visibility in the success modal.
let merchantHasSilver = false;

const MONTH_NAMES_SHORT = ['JAN','FEB','MAR','APR','MAY','JUN','JUL','AUG','SEP','OCT','NOV','DEC'];
const MONTH_NAMES_LONG  = ['January','February','March','April','May','June','July','August','September','October','November','December'];

/**
 * Banner text inside the stamp.
 * Kept very short so it stays legible at render size.
 */
function computeStampBanner(createdAt) {
    if (!createdAt) return 'NEW';

    const created = new Date(createdAt);
    if (Number.isNaN(created.getTime())) return 'NEW';

    const daysSince = (Date.now() - created.getTime()) / (1000 * 60 * 60 * 24);

    if (daysSince < 30) return 'NEW';

    return `${MONTH_NAMES_SHORT[created.getMonth()]} ${created.getFullYear()}`;
}

/**
 * Tenure label for the unverified (plain mark) state.
 */
function computeTenureLabel(createdAt) {
    if (!createdAt) return 'recently';

    const created = new Date(createdAt);
    if (Number.isNaN(created.getTime())) return 'recently';

    return `since ${MONTH_NAMES_LONG[created.getMonth()]} ${created.getFullYear()}`;
}

function buildStampSVG(bannerText) {
    const safe = escapeHtml(String(bannerText || '').toUpperCase());

    return `
        <div class="payla-stamp">
            <svg class="payla-stamp__svg" viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
                <defs>
                    <path id="stamp-arc-top" d="M 50,50 m -29,0 a 29,29 0 1,1 58,0" />
                </defs>

                <circle class="payla-stamp__ring-outer" cx="50" cy="50" r="46" />
                <circle class="payla-stamp__ring-dashed" cx="50" cy="50" r="42.5" />
                <circle class="payla-stamp__ring-inner" cx="50" cy="50" r="34" />

                <text class="payla-stamp__arc-text" text-anchor="middle">
                    <textPath href="#stamp-arc-top" startOffset="50%">
                        NAME MATCHED
                    </textPath>
                </text>

                <text class="payla-stamp__center-text" x="50" y="54" text-anchor="middle">
                    SEALED
                </text>

                <rect class="payla-stamp__banner-bg"
                      x="10" y="78" width="80" height="13" rx="2.5" />
                <text class="payla-stamp__banner-text" x="50" y="86.5" text-anchor="middle">
                    ${safe}
                </text>
            </svg>
        </div>
    `;
}

function buildTenureMark(tenureText) {
    const safe = escapeHtml(tenureText);
    return `
        <div class="payla-tenure-mark" aria-label="On Payla ${safe}">
            <span class="payla-tenure-mark__line">On Payla</span>
            <span class="payla-tenure-mark__line payla-tenure-mark__line--strong">${safe}</span>
        </div>
    `;
}

function renderTrustMark(state, { createdAt }) {
    const container = document.getElementById('trustMark');
    if (!container) return;

    container.replaceChildren();

    if (state === TRUST_STATE.VERIFIED) {
        container.innerHTML = buildStampSVG(computeStampBanner(createdAt));
    } else {
        container.innerHTML = buildTenureMark(computeTenureLabel(createdAt).replace(/^since /, ''));
    }
}


/* ============================================================
   MAIN
   ============================================================ */
document.addEventListener('DOMContentLoaded', function () {
    const BACKEND_URL = BACKEND_BASE;
    const pageLoadStart = performance.now();

    // ================= DOM ELEMENTS =================
    const loadingState        = document.getElementById('loadingState');
    const errorState          = document.getElementById('errorState');
    const paylinkContent      = document.getElementById('paylinkContent');

    const previewLogo         = document.getElementById('previewLogo');

    const previewName         = document.getElementById('previewName');
    const previewTagline      = document.getElementById('previewTagline');

    const previewEmailAction  = document.getElementById('previewEmailAction');
    const previewPhoneAction  = document.getElementById('previewPhoneAction');

    const previewPowered      = document.getElementById('previewPowered');

    const loadingSignature    = document.getElementById('loadingSignature');

    // Recipient block in the payment modal
    const recipientBlock  = document.getElementById('paymentRecipient');
    const recipientNameEl = document.getElementById('recipientName');

    // Modals
    const paystackModal  = document.getElementById('paystackModal');
    const successModal   = document.getElementById('successModal');
    const transferBtn    = document.getElementById('transferBtn');
    const modalClose     = document.getElementById('modalClose');
    const successClose   = document.getElementById('successClose');
    const closeSuccess   = document.getElementById('closeSuccess');
    const processPayment = document.getElementById('processPayment');

    const paymentAmount  = document.getElementById('paymentAmount');
    const payerEmail     = document.getElementById('payerEmail');

    const paidAmount     = document.getElementById('paidAmount');
    const recipientInfo  = document.getElementById('recipientInfo');
    const transactionId  = document.getElementById('transactionId');
    const transactionDate= document.getElementById('transactionDate');

    // ================= GET USERNAME FROM URL =================
    const path = window.location.pathname;
    const username = path.split('/').pop().replace(/^@/, '').trim();

    if (!username) {
        trackPaylinkLoadFailed('unknown', 'no_username_in_url');
        showErrorState();
        return;
    }

    document.title = `@${username} • Payla`;

    if (loadingSignature) {
        loadingSignature.innerHTML = `@<wbr>${escapeHtml(username)}`;
    }

    trackPaylinkPageView(username);

    // ================= PHONE FORMATTER =================
    function formatPhoneNumber(phone) {
        if (!phone) return '—';
        const num = phone.replace(/\D/g, '');
        if (num.length === 11 && num.startsWith('0'))
            return '+234 ' + num.slice(1).replace(/(\d{3})(\d{3})(\d{4})/, '$1 $2 $3');
        if (num.length === 13 && num.startsWith('234'))
            return '+234 ' + num.slice(3).replace(/(\d{3})(\d{3})(\d{4})/, '$1 $2 $3');
        if (num.length === 10)
            return '+234 ' + num.replace(/(\d{3})(\d{3})(\d{4})/, '$1 $2 $3');
        return phone;
    }

    // ================= INITIALS =================
    function showInitials(name) {
        if (!previewLogo) return;

        const initials = String(name || '')
            .split(/\s+/)
            .filter(Boolean)
            .map(w => w[0] || '')
            .join('')
            .toUpperCase()
            .slice(0, 2) || 'P';

        previewLogo.style.backgroundImage = 'none';
        previewLogo.classList.add('initials-medallion');

        const text = document.createElement('span');
        text.className = 'initials-medallion__text';
        text.textContent = initials;

        previewLogo.innerHTML = '';
        previewLogo.appendChild(text);
    }

    // Page view analytics
    fetch(`${BACKEND_URL}/api/paylinks/${username}/analytics/view`, { method: 'POST' });

    // Transfer button click
    transferBtn.addEventListener('click', () => {
        trackTransferButtonClicked(username);
        fetch(`${BACKEND_URL}/api/paylinks/${username}/analytics/transfer`, { method: 'POST' });
        openPaystackModal();
    });

    // Track contact interactions
    previewEmailAction?.addEventListener('click', () => {
        trackEmailClicked(username);
    });
    previewPhoneAction?.addEventListener('click', () => {
        trackWhatsAppClicked(username);
    });

    // Track amount input interactions
    if (paymentAmount) {
        paymentAmount.addEventListener('focus', () => {
            trackAmountFocus(username);
        });
        paymentAmount.addEventListener('blur', (e) => {
            const amount = parseFloat(e.target.value);
            if (!isNaN(amount) && amount > 0) {
                trackAmountEntered(username, amount);
            }
        });
    }

    // ================= LOAD PAYLINK + PROFILE =================
    async function initPaylinkPage() {
        try {
            const paylinkRes = await fetch(`${BACKEND_URL}/api/paylinks/${username}`);
            if (!paylinkRes.ok) {
                trackPaylinkLoadFailed(username, 'paylink_not_found');
                throw new Error('Paylink not found');
            }
            const paylink = await paylinkRes.json();
            merchantHasSilver = Boolean(paylink.silver_verified);

            let owner = {};
            try {
                const ownerRes = await fetch(`${BACKEND_URL}/api/users/${paylink.user_id}`);
                if (ownerRes.ok) owner = await ownerRes.json();
            } catch (e) {
                console.warn('Could not load owner profile');
            }

            const displayName =
                paylink.display_name ||
                owner.business_name ||
                owner.full_name ||
                `@${username}`;

            // Logo with Cloudinary optimization
                        // Logo with Cloudinary optimization
            if (owner.logo_url) {
                let logoUrl = owner.logo_url;
                if (logoUrl.includes('cloudinary.com')) {
                    logoUrl = logoUrl.replace('/upload/', '/upload/f_auto,q_auto/');
                } else if (!logoUrl.startsWith('http') && !logoUrl.startsWith('data:')) {
                    logoUrl = `${BACKEND_URL}${owner.logo_url}`;
                }

                const img = new Image();
                img.onload = () => {
                    previewLogo.style.backgroundImage = `url(${logoUrl})`;
                    previewLogo.classList.remove('initials-medallion');
                    previewLogo.innerHTML = '';
                };
                img.onerror = () => showInitials(displayName);
                img.src = logoUrl;
            } else {
                showInitials(displayName);
            }

            // Fill content
            if (previewName) previewName.textContent = displayName;
            if (previewTagline) previewTagline.textContent = paylink.description || '';

            // ---- Contact actions ----
            if (previewEmailAction) {
                if (owner.email) {
                    previewEmailAction.href = `mailto:${owner.email}`;
                    previewEmailAction.style.display = '';
                } else {
                    previewEmailAction.style.display = 'none';
                }
            }

            if (previewPhoneAction) {
                const rawPhone = owner.phone_number || owner.whatsapp_number || '';
                const telValue = normalizePhoneForTel(rawPhone);
                if (telValue) {
                    previewPhoneAction.href = `tel:+${telValue}`;
                    previewPhoneAction.style.display = '';
                } else {
                    previewPhoneAction.style.display = 'none';
                }
            }

            // Footer signature
            if (previewPowered) {
                previewPowered.textContent = `@${paylink.username || username}`;
            }

            // Footer secured line — "Powered by Payla Silver" for Silver merchants.
            if (merchantHasSilver) {
                const securedByText = document.getElementById('securedByText');
                if (securedByText) {
                    securedByText.textContent = 'Powered by Payla Silver';
                }
            }

            // ---- Trust mark ----
            const trustState = (owner.bank_confirmation_status === 'matched')
                ? TRUST_STATE.VERIFIED
                : TRUST_STATE.UNVERIFIED;

            const signupDate =
                owner.created_at ||
                owner.signup_date ||
                paylink.created_at ||
                null;

            renderTrustMark(trustState, { createdAt: signupDate });

            // ---- Show page ----
            loadingState.classList.add('hidden');
            paylinkContent.classList.remove('hidden');

            const loadTime = performance.now() - pageLoadStart;
            trackPaylinkLoadSuccess(username, Math.round(loadTime));

        } catch (err) {
            console.error('Failed to load paylink:', err);
            trackPaylinkLoadFailed(username, err.message || 'unknown_error');
            showErrorState();
        }
    }

    function showErrorState() {
        loadingState?.classList.add('hidden');
        errorState?.classList.remove('hidden');
    }

    // ================= RECIPIENT BLOCK (modal disclosure) =================
    let recipientFetched = false;

    async function fetchRecipientOnce() {
        if (recipientFetched) return;
        recipientFetched = true;

        try {
            const res = await fetch(
                `${BACKEND_URL}/api/paylinks/${encodeURIComponent(username)}/recipient`
            );

            if (!res.ok) {
                console.warn('Recipient details unavailable:', res.status);
                return;
            }

            const data = await res.json();

            if (!data || !data.name) return;
            if (!recipientBlock || !recipientNameEl) return;

            recipientNameEl.textContent = data.name;
            recipientBlock.hidden = false;
        } catch (err) {
            console.warn('Could not fetch recipient details:', err);
        }
    }

    // ================= MODALS =================
    function openPaystackModal() {
        paystackModal.classList.remove('hidden');
        setTimeout(() => paystackModal.classList.add('open'), 10);
        paymentAmount?.focus();
        trackPaymentModalOpened(username);

        // Populate the recipient block in place.
        fetchRecipientOnce();
    }

    function closePaystackModal() {
        paystackModal.classList.remove('open');
        setTimeout(() => paystackModal.classList.add('hidden'), 300);
        trackPaymentModalClosed(username, 'close_button');
    }

    function closeSuccessModal() {
        successModal.classList.remove('open');
        setTimeout(() => successModal.classList.add('hidden'), 300);
    }

    modalClose?.addEventListener('click', closePaystackModal);
    successClose?.addEventListener('click', closeSuccessModal);
    closeSuccess?.addEventListener('click', closeSuccessModal);
    paystackModal?.addEventListener('click', e => {
        if (e.target === paystackModal) {
            trackPaymentModalClosed(username, 'overlay_click');
            closePaystackModal();
        }
    });

    successModal?.addEventListener('click', e => {
        if (e.target === successModal) closeSuccessModal();
    });

    // ================= PAYMENT — SUBACCOUNT COMPATIBLE =================
    processPayment?.addEventListener('click', async (e) => {
        e.preventDefault();

        const rawAmount = paymentAmount.value.trim();
        const email = payerEmail.value.trim();

        if (!rawAmount || rawAmount < 1000) {
            showToast('Minimum amount is ₦1,000', 'error');
            return;
        }
        if (!email.includes('@')) {
            showToast('Enter a valid email', 'error');
            return;
        }

        let amount = parseFloat(rawAmount);
        if (isNaN(amount)) {
            showToast('Invalid amount', 'error');
            return;
        }

        const emailDomain = email.split('@')[1];
        trackPaymentAttempt(username, amount, emailDomain);

        // Calculate gross amount so merchant gets full base amount
        function addPaystackFee(baseAmount) {
            if (baseAmount <= 0) return 0;
            let total;
            const paystackPercent = 0.015;
            const flatFee = 100;

            if (baseAmount < 2500) {
                total = baseAmount / (1 - paystackPercent);
            } else {
                total = (baseAmount + flatFee) / (1 - paystackPercent);
            }

            let payoutFee = 10;
            if (baseAmount > 5000) payoutFee = 25;
            if (baseAmount > 50000) payoutFee = 50;

            total += payoutFee;

            if ((total - baseAmount) > 2000) {
                total = baseAmount + 2000 + payoutFee;
            }

            return Math.ceil(total);
        }

        const totalAmount = addPaystackFee(amount);

        processPayment.disabled = true;
        processPayment.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Preparing...';

        try {
            const initRes = await fetch(`${BACKEND_URL}/api/paylinks/${username}/transaction`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    paylink_username: username,
                    amount: totalAmount,
                    amount_requested: amount,
                    payer_email: email,
                    payer_name: email.split('@')[0],
                })
            });

            if (!initRes.ok) {
                const err = await initRes.json().catch(() => ({}));
                throw new Error(err.detail || 'Payment failed to start');
            }

            const data = await initRes.json();

            PaystackPop.setup({
                key: data.public_key || PAYSTACK_PUBLIC_KEY,
                email: data.email,
                amount: data.amount_kobo,
                ref: data.reference,
                subaccount: data.subaccount,
                bearer: 'subaccount',
                metadata: data.metadata,
                callback: (response) => {
                    closePaystackModal();
                    trackPaymentSuccess(
                        username,
                        amount,
                        response.reference,
                        data.transaction_id || response.reference
                    );
                    showSuccessScreen({
                        amount: amount,
                        recipient: previewName.textContent,
                        reference: response.reference,
                        date: new Date().toLocaleString('en-NG', { timeZone: 'Africa/Lagos' })
                    });
                    showToast('Payment successful!', 'success');
                },
                onClose: () => {
                    processPayment.disabled = false;
                    processPayment.innerHTML = '<i class="fas fa-lock"></i> Continue to Paystack';
                    trackPaymentModalClosed(username, 'payment_cancelled');
                }
            }).openIframe();

        } catch (err) {
            console.error(err);
            trackPaymentFailed(username, amount, err.message || 'unknown_error');
            showToast(err.message || 'Payment failed.', 'error');
            processPayment.disabled = false;
            processPayment.innerHTML = '<i class="fas fa-lock"></i> Continue to Paystack';
        }
    });


    function showSuccessScreen(data) {
        paidAmount.textContent      = `₦${data.amount.toLocaleString()}`;
        recipientInfo.textContent   = data.recipient;
        transactionId.textContent   = data.reference;
        transactionDate.textContent = data.date;

        // Receipt download is a Silver feature. Free merchants' payers
        // rely on the Paystack-issued confirmation email.
        if (merchantHasSilver) {
            const actionsDiv = document.querySelector('.success-actions');
            let receiptBtn = document.getElementById('downloadReceipt');

            if (!receiptBtn && actionsDiv) {
                receiptBtn = document.createElement('button');
                receiptBtn.id = 'downloadReceipt';
                receiptBtn.className = 'btn btn--outline';
                receiptBtn.innerHTML = '<i class="fas fa-download"></i> Receipt';
                receiptBtn.onclick = () => {
                    const url = `${BACKEND_URL}/api/receipt/paylink/${data.reference}.pdf`;
                    window.open(url, '_blank');
                    trackReceiptDownloaded(data.reference, username);
                };
                actionsDiv.insertBefore(receiptBtn, actionsDiv.firstChild);
            }
        }

        successModal.classList.remove('hidden');
        setTimeout(() => successModal.classList.add('open'), 10);
    }

    // ================= TOAST =================
    function showToast(message, type = 'success') {
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.innerHTML = `<i class="fas fa-${type === 'success' ? 'check-circle' : 'exclamation-circle'}"></i><span>${escapeHtml(message)}</span>`;
        document.body.appendChild(toast);
        setTimeout(() => toast.classList.add('show'), 100);
        setTimeout(() => {
            toast.classList.remove('show');
            setTimeout(() => toast.remove(), 400);
        }, 4000);
    }

    // ================= START =================
    initPaylinkPage();
});