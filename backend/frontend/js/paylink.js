// ====================================================
// PAYLA PAYLINK PAGE – FINAL FIXED & WORKING 100%
// Client Pays Fee • Full Sync • No Errors • Layla Approved
// ====================================================
import { BACKEND_BASE } from './config.js';
import { PAYSTACK_PUBLIC_KEY } from './config.js';
document.addEventListener('DOMContentLoaded', function () {
    const BACKEND_URL = BACKEND_BASE;

    // ================= DOM ELEMENTS =================
    const loadingState        = document.getElementById('loadingState');
    const errorState          = document.getElementById('errorState');
    const paylinkContent      = document.getElementById('paylinkContent');

    const previewLogo         = document.getElementById('previewLogo');
    const previewLogoInitials = document.getElementById('previewLogoInitials');

    const previewName         = document.getElementById('previewName');
    const previewTagline      = document.getElementById('previewTagline');
    const previewHandle       = document.getElementById('previewHandle');
    const previewEmail        = document.getElementById('previewEmail');
    const previewWhatsapp     = document.getElementById('previewWhatsapp');
    const previewPowered      = document.getElementById('previewPowered');

    const silverBadge         = document.getElementById('previewPlanName'); // Verified badge
    const loadingSignature    = document.getElementById('loadingSignature'); // @username

    // Modals
    const paystackModal  = document.getElementById('paystackModal');
    const successModal   = document.getElementById('successModal');
    const transferBtn    = document.getElementById('transferBtn');
    const modalClose     = document.getElementById('modalClose');
    const successClose   = document.getElementById('successClose');
    const closeSuccess   = document.getElementById('closeSuccess');
    const printReceipt   = document.getElementById('printReceipt');
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
        showErrorState();
        return;
    }
    document.title = `@${username} • Payla`;
    if (loadingSignature) loadingSignature.textContent = `@${username}`;

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
        const initials = name.split(' ').map(w => w[0] || '').join('').toUpperCase().slice(0, 2) || 'P';
        previewLogoInitials.textContent = initials;
        previewLogo.style.backgroundImage = 'none';
        previewLogoInitials.style.display = 'block';
    }

    // Page view analytics
    fetch(`${BACKEND_URL}/api/paylinks/${username}/analytics/view`, { method: 'POST' });

    // Transfer button click
    transferBtn.addEventListener('click', () => {
        fetch(`${BACKEND_URL}/api/paylinks/${username}/analytics/transfer`, { method: 'POST' });
        openPaystackModal();
    });

    // ================= LOAD PAYLINK + PROFILE =================
    async function initPaylinkPage() {
        try {
            // 1. Get Paylink
            const paylinkRes = await fetch(`${BACKEND_URL}/api/paylinks/${username}`);
            if (!paylinkRes.ok) throw new Error('Paylink not found');
            const paylink = await paylinkRes.json();

            // 2. Get Owner Profile
            let owner = {};
            try {
                const ownerRes = await fetch(`${BACKEND_URL}/api/users/${paylink.user_id}`);
                if (ownerRes.ok) owner = await ownerRes.json();
            } catch (e) {
                console.warn('Could not load owner profile');
            }

            const displayName = paylink.display_name || owner.business_name || owner.full_name || `@${username}`;

            // Determine if user has Silver+ subscription
            const currentPlan = (owner?.plan || 'free').toLowerCase();
            const isPremium = ['silver', 'gold', 'opal'].includes(currentPlan);

            // Explicitly hide elements if NOT premium
            if (silverBadge) {
                silverBadge.parentElement.style.display = isPremium ? 'flex' : 'none';
            }

            // ================= Logo with preload =================
            if (owner.logo_url) {
                const logoUrl = owner.logo_url.startsWith('http') ? owner.logo_url : `${BACKEND_URL}${owner.logo_url}`;
                const img = new Image();
                img.onload = () => {
                    previewLogo.style.backgroundImage = `url(${logoUrl})`;
                    previewLogoInitials.style.display = 'none';
                };
                img.onerror = () => showInitials(displayName);
                img.src = logoUrl;
            } else {
                showInitials(displayName);
            }

            // ================= Fill Content =================
            previewName.textContent     = displayName;
            previewTagline.textContent  = paylink.description;
            previewHandle.textContent   = `@${paylink.username}`;
            previewEmail.textContent    = owner.email || '—';
            previewWhatsapp.textContent = formatPhoneNumber(owner.phone_number || owner.whatsapp_number || '');
            previewPowered.textContent  = displayName;

            // ================= CONDITIONAL PREMIUM ELEMENTS =================
            if (silverBadge) silverBadge.parentElement.style.display = isPremium ? 'block' : 'none';
            if (previewPowered) previewPowered.parentElement.style.display = isPremium ? 'block' : 'none';
            if (loadingSignature) loadingSignature.style.display = isPremium ? 'block' : 'none';

            // ================= Show page =================
            loadingState.classList.add('hidden');
            paylinkContent.classList.remove('hidden');

        } catch (err) {
            console.error('Failed to load paylink:', err);
            showErrorState();
        }
    }

    function showErrorState() {
        loadingState?.classList.add('hidden');
        errorState?.classList.remove('hidden');
    }

    // ================= MODALS =================
    function openPaystackModal() {
        paystackModal.classList.remove('hidden');
        setTimeout(() => paystackModal.classList.add('open'), 10);
        paymentAmount.focus();
    }

    function closePaystackModal() {
        paystackModal.classList.remove('open');
        setTimeout(() => paystackModal.classList.add('hidden'), 300);
    }

    function closeSuccessModal() {
        successModal.classList.remove('open');
        setTimeout(() => successModal.classList.add('hidden'), 300);
    }

    transferBtn?.addEventListener('click', openPaystackModal);
    modalClose?.addEventListener('click', closePaystackModal);
    successClose?.addEventListener('click', closeSuccessModal);
    closeSuccess?.addEventListener('click', closeSuccessModal);
    printReceipt?.addEventListener('click', () => window.print());

    paystackModal?.addEventListener('click', e => e.target === paystackModal && closePaystackModal());
    successModal?.addEventListener('click', e => e.target === successModal && closeSuccessModal());

// ================= PAYMENT – SUBACCOUNT COMPATIBLE =================
    processPayment?.addEventListener('click', async (e) => { 
        const rawAmount = paymentAmount.value.trim();
        const email = payerEmail.value.trim();

        if (!rawAmount || rawAmount < 1000) return showToast('Minimum amount is ₦1,000', 'error');
        if (!email.includes('@')) return showToast('Enter a valid email', 'error');

        let amount = parseFloat(rawAmount);
        if (isNaN(amount)) return showToast('Invalid amount', 'error');

        // ================= ADD FEES SO CREATOR GETS FULL AMOUNT =================
        // Because 'bearer' = 'subaccount', Paystack deducts fees from the creator.
        // We add them here so the customer covers that deduction.
        function addPaystackFee(baseAmount) {
            // 1. If amount is 0 or less, return 0
            if (baseAmount <= 0) return 0;

            let total;
            const paystackPercent = 0.015; // 1.5%
            const flatFee = 100;

            // 2. Paystack Reverse Formula
            // This calculates what to charge the customer so the merchant gets baseAmount
            if (baseAmount < 2500) {
                // No flat fee for transactions under 2500
                total = baseAmount / (1 - paystackPercent);
            } else {
                total = (baseAmount + flatFee) / (1 - paystackPercent);
            }

            // 3. Add Payout/Settlement Fee (Paystack bank transfer charge)
            // We add this so the user's bank settlement is exactly the baseAmount
            let payoutFee = 10;
            if (baseAmount > 5000) payoutFee = 25;
            if (baseAmount > 50000) payoutFee = 50;
            
            total += payoutFee;

            // 4. Cap the total fee at ₦2000 (Paystack's maximum fee cap)
            // If the difference is > 2000, Paystack only takes 2000
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
                    amount: totalAmount,           // This is the gross amount (e.g., 1229)
                    amount_requested: amount,      // 🔥 ADD THIS: This is the base amount (e.g., 1200)
                    payer_email: email,
                    payer_name: email.split('@')[0],
                })
            });

            if (!initRes.ok) {
                const err = await initRes.json().catch(() => ({}));
                throw new Error(err.detail || 'Payment failed to start');
            }

            const data = await initRes.json();

            // ================= CRITICAL SUBACCOUNT MAPPING =================
            PaystackPop.setup({
                key: data.public_key || PAYSTACK_PUBLIC_KEY,
                email: data.email,
                amount: data.amount_kobo,
                ref: data.reference,
                subaccount: data.subaccount, // <--- NEW: Tells Paystack which creator gets the money
                bearer: 'subaccount',        // <--- NEW: Creator pays the fee (which we added above)
                metadata: data.metadata,
                callback: (response) => {
                    closePaystackModal();
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
                    processPayment.innerHTML = '<i class="fas fa-lock"></i> Pay with Paystack';
                }
            }).openIframe();

        } catch (err) {
            console.error(err);
            showToast(err.message || 'Payment failed.', 'error');
            processPayment.disabled = false;
            processPayment.innerHTML = '<i class="fas fa-lock"></i> Pay with Paystack';
        }
    });


    function showSuccessScreen(data) {
        paidAmount.textContent      = `₦${data.amount.toLocaleString()}`;
        recipientInfo.textContent   = data.recipient;
        transactionId.textContent   = data.reference;
        transactionDate.textContent = data.date;

        const actionsDiv = document.querySelector('.success-actions');
        let receiptBtn = document.getElementById('downloadReceipt');
        if (!receiptBtn) {
            receiptBtn = document.createElement('button');
            receiptBtn.id = 'downloadReceipt';
            receiptBtn.className = 'btn-secondary';
            receiptBtn.innerHTML = '<i class="fas fa-download"></i> Download Receipt';
            receiptBtn.onclick = () => {
                const url = `${BACKEND_URL}/api/receipt/paylink/${data.reference}.pdf`;
                window.open(url, '_blank');
            };
            actionsDiv.insertBefore(receiptBtn, actionsDiv.firstChild);
        }

        successModal.classList.remove('hidden');
        setTimeout(() => successModal.classList.add('open'), 10);
    }

    // ================= TOAST =================
    function showToast(message, type = 'success') {
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.innerHTML = `<i class="fas fa-${type === 'success' ? 'check-circle' : 'exclamation-circle'}"></i><span>${message}</span>`;
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
