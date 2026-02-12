import { BACKEND_BASE } from './config.js';
import { PAYSTACK_PUBLIC_KEY } from './config.js';

const API_URL = BACKEND_BASE;
const shortId = window.location.pathname.split('/').pop();
const invoiceId = shortId.startsWith('inv_') ? shortId : `inv_${shortId}`;

// Elements
const loadingState = document.getElementById('loadingState');
const loadingSignature = document.getElementById('loadingSignature');
const errorState = document.getElementById('errorState');
const paidState = document.getElementById('paidState');
const invoiceContent = document.getElementById('invoiceContent');
const paystackModal = document.getElementById('paystackModal');
const successModal = document.getElementById('successModal');
const modalClose = document.getElementById('modalClose');
const processPayment = document.getElementById('processPayment');
const payBtn = document.getElementById('payBtn');
const payerEmailInput = document.getElementById('payerEmail');
const modalAmount = document.getElementById('modalAmount');
const modalRecipient = document.getElementById('modalRecipient');
const modalDescription = document.getElementById('modalDescription');
const downloadReceipt = document.getElementById('downloadReceipt');
const downloadSuccessReceipt = document.getElementById('downloadSuccessReceipt');
const closeSuccessModal = document.getElementById('closeSuccessModal');

const fallbackUsername = shortId.startsWith('inv_') ? shortId.slice(4) : shortId;
loadingSignature.textContent = fallbackUsername;

let currentInvoice = null;
let paystackHandler = null;

// --- Helper Functions ---

function hideAll() {
    [loadingState, errorState, paidState, invoiceContent].forEach(el => el.classList.add('hidden'));
    paystackModal.classList.remove('open', 'hidden');
    successModal.classList.remove('open', 'hidden');
    // Default modals to hidden
    paystackModal.classList.add('hidden');
    successModal.classList.add('hidden');
}

function showLoading() { hideAll(); loadingState.classList.remove('hidden'); }
function showError() { hideAll(); errorState.classList.remove('hidden'); }
function showPaid() { hideAll(); paidState.classList.remove('hidden'); }
function showInvoice() { hideAll(); invoiceContent.classList.remove('hidden'); }

function openModal(modalId) {
    const modal = document.getElementById(modalId);
    modal.classList.remove('hidden');
    setTimeout(() => modal.classList.add('open'), 10);
}

function closeModal(modalId) {
    const modal = document.getElementById(modalId);
    modal.classList.remove('open');
    setTimeout(() => modal.classList.add('hidden'), 300);
}

function formatCurrency(amount, currency) {
    const symbol = currency === 'NGN' ? '₦' : '$';
    return `${symbol}${Number(amount).toLocaleString(undefined, {minimumFractionDigits: 2})}`;
}

function formatDate(dateString) {
    if (!dateString) return 'N/A';
    return new Date(dateString).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

function formatDateTime(dateString) {
    if (!dateString) return 'N/A';
    return new Date(dateString).toLocaleDateString('en-US', { 
        month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit' 
    });
}

function getDaysLeft(dueDate) {
    const diff = new Date(dueDate) - new Date();
    return Math.ceil(diff / (1000 * 60 * 60 * 24));
}

// --- Core Logic ---

async function updateInvoiceUI(invoice) {
    // 1. Business Info
    document.getElementById('previewName').textContent = invoice.sender_business_name || 'Business';
    document.getElementById('previewHandle').textContent = `payla.ng/@${invoice.sender_username || 'username'}`;

    // 2. Fetch the LIVE Owner Profile
    let owner = {};
    try {
        const ownerRes = await fetch(`${API_URL}/api/users/${invoice.sender_id}`);
        if (ownerRes.ok) owner = await ownerRes.json();
    } catch (e) {
        console.warn('Could not load owner profile for logo sync');
    }

    // 3. Optimized Logo Logic
    const logoImg = document.getElementById('previewLogo');
    const logoInitials = document.getElementById('previewLogoInitials');
    
    // Priority: Invoice record -> Live Owner Profile
    let logoPath = invoice.sender_logo || owner.logo_url || owner.logo;
    const displayName = invoice.sender_business_name || owner.business_name || 'Business';

    if (logoPath) {
        let fullUrl = logoPath.startsWith('http') ? logoPath : `${API_URL}${logoPath}`;
        
        // 🔥 CLOUDINARY OPTIMIZATION: Inject auto-format and auto-quality
        if (fullUrl.includes('cloudinary.com')) {
            fullUrl = fullUrl.replace('/upload/', '/upload/f_auto,q_auto/');
        }

        // Image Preloader logic
        const img = new Image();
        img.onload = () => {
            logoImg.style.backgroundImage = `url('${fullUrl}')`;
            logoImg.style.backgroundSize = 'cover';
            logoImg.style.backgroundPosition = 'center';
            logoImg.style.filter = 'none'; // Ensure no leftover filters
            logoInitials.style.display = 'none';
        };
        img.onerror = () => {
            logoInitials.textContent = displayName.substring(0, 2).toUpperCase();
            logoInitials.style.display = 'flex';
        };
        
        // Show a slight blur/loading state while the cloud image fetches
        logoImg.style.filter = 'blur(2px)';
        img.src = fullUrl;
    } else {
        logoInitials.textContent = displayName.substring(0, 2).toUpperCase();
        logoInitials.style.display = 'flex';
        logoImg.style.backgroundImage = 'none';
    }
    
    // 3. Status logic
    const daysLeft = getDaysLeft(invoice.due_date);
    const dueStatus = document.getElementById('dueStatus');
    const dueText = document.getElementById('dueText');
    const statusElement = document.getElementById('statusText');

    if (invoice.status === "paid") {
        statusElement.textContent = "PAID";
        dueStatus.className = 'status-display paid'; // Ensure you have this CSS class
    } else if (daysLeft < 0) {
        dueText.textContent = statusElement.textContent = 'OVERDUE';
        dueStatus.className = 'status-display overdue';
    } else if (daysLeft === 0) {
        dueText.textContent = statusElement.textContent = 'DUE TODAY';
        dueStatus.className = 'status-display due-today';
    } else {
        dueText.textContent = statusElement.textContent = `DUE IN ${daysLeft} DAYS`;
        dueStatus.className = 'status-display due-future';
    }

    // 4. Details
    document.getElementById('invoiceAmount').textContent = formatCurrency(invoice.amount, invoice.currency);
    document.getElementById('invoiceCurrency').textContent = invoice.currency;
    document.getElementById('invoiceNumber').textContent = invoice.invoice_number || `INV-${invoice._id.substring(0, 8).toUpperCase()}`;
    document.getElementById('invoiceDescription').textContent = invoice.description || 'No description provided';
    document.getElementById('invoiceDueDate').textContent = formatDate(invoice.due_date);
    document.getElementById('createdDate').textContent = formatDate(invoice.created_at);
    document.getElementById('senderEmail').textContent = invoice.sender_email || 'Not provided';
    document.getElementById('senderName').textContent = invoice.sender_business_name || invoice.sender_name || 'Not provided';
    document.getElementById('poweredBy').textContent = invoice.sender_business_name || 'Payla';

    // 5. Notes
    const notesBox = document.getElementById('notesBox');
    if (invoice.notes?.trim()) {
        document.getElementById('invoiceNotes').textContent = invoice.notes;
        notesBox.classList.remove('hidden');
    } else {
        notesBox.classList.add('hidden');
    }

    // 6. Modal Prep
    modalAmount.textContent = formatCurrency(invoice.amount, invoice.currency);
    modalRecipient.textContent = invoice.sender_business_name || 'Recipient';
    modalDescription.textContent = invoice.description || 'Invoice payment';
    if (invoice.customer_email) payerEmailInput.value = invoice.customer_email;
}

function updatePaidUI(invoice) {
    document.getElementById('paidDate').textContent = `Paid on ${formatDateTime(invoice.paid_at)}`;
    document.getElementById('paidAmount').textContent = formatCurrency(invoice.amount, invoice.currency);
    document.getElementById('invoiceId').textContent = invoice.invoice_number || 'Invoice';
    document.getElementById('paidTo').textContent = invoice.sender_business_name || 'Recipient';
}

async function loadInvoice() {
    showLoading();
    try {
        const res = await fetch(`${API_URL}/api/invoices/${invoiceId}`);
        if (!res.ok) throw new Error("Not found");
        const inv = await res.json();
        currentInvoice = inv;

        if (inv.status === "paid") {
            updatePaidUI(inv);
            showPaid();
        } else {
            updateInvoiceUI(inv);
            initializePaystack(inv);
            showInvoice();
        }
    } catch (err) {
        console.error(err);
        showError();
    }
}


function calculateTotalWithFees(amount) {
    // 1. Add the Payout Fee (so merchant gets clean 1000)
    let payoutFee = amount <= 5000 ? 10 : (amount <= 50000 ? 25 : 50);
    let targetAmount = amount + payoutFee;

    // 2. Use the "Net" formula to cover Collection Fees
    let total;
    if (targetAmount < 2500) {
        total = targetAmount / 0.985;
    } else {
        total = (targetAmount + 100) / 0.985;
    }

    // 3. Apply Paystack Fee Cap (₦2,000)
    if ((total - amount) > 2000) {
        total = amount + 2000;
    }
    return Math.ceil(total);
}
function initializePaystack(invoice) {
    payBtn.onclick = () => {
        if (!invoice.sender_subaccount_code) {
            alert("Merchant payout account not configured.");
            return;
        }
        openModal('paystackModal');
    };

    processPayment.onclick = () => {
        const email = payerEmailInput.value.trim();
        if (!email || !email.includes('@')) {
            alert('Enter a valid email address.');
            return;
        }

        const btnText = processPayment.querySelector('.btn-text');
        const btnLoader = processPayment.querySelector('.btn-loader');
        btnText.style.opacity = '0';
        btnLoader.style.display = 'flex';
        processPayment.disabled = true;

        let finalAmount = invoice.amount;
        if (invoice.currency === 'NGN') {
            finalAmount = calculateTotalWithFees(invoice.amount);
        }

        const handler = PaystackPop.setup({
            key: PAYSTACK_PUBLIC_KEY,
            email,
            amount: Math.round(finalAmount * 100),
            currency: (invoice.currency || 'NGN').toUpperCase(),
            ref: `inv_${invoice._id}_${Date.now()}`,

            subaccount: invoice.sender_subaccount_code.trim(),
            bearer: 'subaccount',

            metadata: {
                invoice_id: invoice._id,
                type: 'invoice_payment'
            },

            callback: function (response) {
                closeModal('paystackModal');
                currentInvoice.status = 'paid'; 
                currentInvoice.paid_at = new Date().toISOString();
                
                updatePaidUI(currentInvoice); // Update the "Paid" screen data
                showPaid(); // Switch the background to the green "Paid" state
                
                openModal('successModal');

                fetch(`${API_URL}/api/invoices/${invoice._id}/status`, {
                    method: 'PATCH',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        status: 'paid',
                        transaction_reference: response.reference,
                        payer_email: email
                    })
                }).catch(console.error);
            },

            onClose: function () {
                btnText.style.opacity = '1';
                btnLoader.style.display = 'none';
                processPayment.disabled = false;
            }
        });

        handler.openIframe();
    };
}


function setupReceiptDownload() {
    const downloadAction = () => {
        if (currentInvoice) window.open(`${API_URL}/api/receipt/invoice/${currentInvoice._id}.pdf`, '_blank');
    };
    downloadReceipt.onclick = downloadAction;
    downloadSuccessReceipt.onclick = downloadAction;
}

// --- Event Listeners ---
modalClose.onclick = () => closeModal('paystackModal');
closeSuccessModal.onclick = () => {
    closeModal('successModal');
    location.reload();
};

document.addEventListener('DOMContentLoaded', () => {
    loadInvoice();
    setupReceiptDownload();
});