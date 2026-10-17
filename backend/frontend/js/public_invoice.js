import { BACKEND_BASE } from './config.js';

import {
  trackInvoicePageView,
  trackInvoiceLoadSuccess,
  trackInvoiceLoadFailed,
  trackPayButtonClicked,
  trackPaymentModalOpened,
  trackPaymentModalClosed,
  trackPaymentAttempt,
  trackPaymentSuccess,
  trackPaymentFailed,
  trackReceiptDownloaded,
  trackPaidInvoiceView,
  trackPayerEmailEntered
} from './invoice_analytics.js';

const API_URL = BACKEND_BASE.replace(/\/+$/, '');

const pathParts = window.location.pathname.split('/').filter(Boolean);
const shortId = pathParts[pathParts.length - 1] || '';
const invoiceId = shortId.startsWith('inv_')
  ? shortId
  : `inv_${shortId}`;

const pageLoadStart = performance.now();

const elements = {
  loadingState: document.getElementById('loadingState'),
  loadingSignature: document.getElementById('loadingSignature'),
  errorState: document.getElementById('errorState'),
  invoiceContent: document.getElementById('invoiceContent'),

  paystackModal: document.getElementById('paystackModal'),
  modalClose: document.getElementById('modalClose'),
  processPayment: document.getElementById('processPayment'),
  payBtn: document.getElementById('payBtn'),
  payerEmailInput: document.getElementById('payerEmail'),

  modalAmount: document.getElementById('modalAmount'),
  modalRecipient: document.getElementById('modalRecipient'),
  modalDescription: document.getElementById('modalDescription'),
};

const fallbackUsername = shortId.startsWith('inv_')
  ? shortId.slice(4)
  : shortId;

elements.loadingSignature.textContent = fallbackUsername;

let currentInvoice = null;
let checkoutInProgress = false;
let invoicePageViewTracked = false;
let recipientFetched = false;

const paymentReturnParams = new URLSearchParams(window.location.search);
const returnedReference =
  paymentReturnParams.get('reference') ||
  paymentReturnParams.get('trxref') ||
  '';

const isPaymentReturn = Boolean(returnedReference);

// --------------------------------------------------
// Analytics helpers
// --------------------------------------------------

function safelyTrack(callback, ...args) {
  try {
    callback?.(...args);
  } catch (error) {
    console.warn('Invoice analytics event failed:', error);
  }
}

elements.payerEmailInput?.addEventListener('blur', event => {
  const email = event.target.value.trim();
  const emailParts = email.split('@');

  if (emailParts.length === 2 && emailParts[1]) {
    safelyTrack(trackPayerEmailEntered, invoiceId, emailParts[1]);
  }
});

// --------------------------------------------------
// Page states
// --------------------------------------------------

function hideAll() {
  [elements.loadingState, elements.errorState, elements.invoiceContent]
    .forEach(element => element?.classList.add('hidden'));
}

function showLoading() {
  hideAll();
  elements.loadingState?.classList.remove('hidden');
}

function showError() {
  hideAll();
  elements.errorState?.classList.remove('hidden');
}

function showInvoice() {
  hideAll();
  elements.invoiceContent?.classList.remove('hidden');
}

function openModal(modalId) {
  const modal = document.getElementById(modalId);
  if (!modal) return;

  modal.classList.remove('hidden');
  window.requestAnimationFrame(() => modal.classList.add('open'));

  if (modalId === 'paystackModal') {
    safelyTrack(trackPaymentModalOpened, invoiceId);
  }
}

function closeModal(modalId, method = 'close_button') {
  const modal = document.getElementById(modalId);
  if (!modal) return;

  modal.classList.remove('open');
  window.setTimeout(() => modal.classList.add('hidden'), 300);

  if (modalId === 'paystackModal') {
    safelyTrack(trackPaymentModalClosed, invoiceId, method);
  }
}

// --------------------------------------------------
// Formatting helpers
// --------------------------------------------------

function formatCurrency(amount, currency = 'NGN') {
  const code = String(currency || 'NGN').toUpperCase();
  const value = Number(amount);

  if (!Number.isFinite(value)) {
    return `${code} 0.00`;
  }

  try {
    return new Intl.NumberFormat('en-NG', {
      style: 'currency',
      currency: code,
      minimumFractionDigits: 2,
      maximumFractionDigits: 2
    }).format(value);
  } catch {
    return `${code} ${value.toLocaleString('en-NG', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2
    })}`;
  }
}

function formatDate(dateString) {
  if (!dateString) return 'N/A';
  const date = new Date(dateString);
  if (Number.isNaN(date.getTime())) return 'N/A';

  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric'
  });
}

function getDaysLeft(dueDate) {
  if (!dueDate) return null;

  const due = new Date(dueDate);
  if (Number.isNaN(due.getTime())) return null;

  const today = new Date();
  today.setHours(0, 0, 0, 0);
  due.setHours(0, 0, 0, 0);

  return Math.ceil((due - today) / (1000 * 60 * 60 * 24));
}

function getInvoiceDisplayId(invoice) {
  return invoice.invoice_number ||
    `INV-${String(invoice._id || invoiceId).replace(/^inv_/, '').slice(0, 8).toUpperCase()}`;
}

// --------------------------------------------------
// Merchant logo
// --------------------------------------------------

async function loadMerchantLogo(invoice) {
  const logoContainer = document.getElementById('previewLogo');
  const logoInitials = document.getElementById('previewLogoInitials');

  if (!logoContainer || !logoInitials) return;

  const displayName = invoice.sender_business_name || 'Business';

  let owner = {};

  if (invoice.sender_id) {
    try {
      const response = await fetch(
        `${API_URL}/api/users/${encodeURIComponent(invoice.sender_id)}`
      );
      if (response.ok) owner = await response.json();
    } catch (error) {
      console.warn('Could not load merchant profile:', error);
    }
  }

  const logoPath = invoice.sender_logo || owner.logo_url || owner.logo || '';
  const finalDisplayName =
    invoice.sender_business_name || owner.business_name || displayName;

  logoInitials.textContent = finalDisplayName.substring(0, 2).toUpperCase();

  if (!logoPath) {
    logoContainer.style.backgroundImage = 'none';
    logoInitials.style.display = 'flex';
    return;
  }

  let logoUrl;
  try {
    logoUrl = new URL(logoPath, `${API_URL}/`).href;
  } catch {
    logoInitials.style.display = 'flex';
    return;
  }

  if (
    logoUrl.includes('res.cloudinary.com') &&
    logoUrl.includes('/upload/') &&
    !logoUrl.includes('/upload/f_auto')
  ) {
    logoUrl = logoUrl.replace('/upload/', '/upload/f_auto,q_auto/');
  }

  const image = new Image();

  image.onload = () => {
    logoContainer.style.backgroundImage = `url("${logoUrl.replace(/"/g, '%22')}")`;
    logoContainer.style.backgroundSize = 'cover';
    logoContainer.style.backgroundPosition = 'center';
    logoContainer.style.filter = 'none';
    logoInitials.style.display = 'none';
  };

  image.onerror = () => {
    logoContainer.style.backgroundImage = 'none';
    logoInitials.style.display = 'flex';
  };

  logoInitials.style.display = 'flex';
  logoContainer.style.filter = 'blur(2px)';
  image.src = logoUrl;
}

// --------------------------------------------------
// Bank-confirmed recipient (for the modal)
// --------------------------------------------------

async function fetchRecipientOnce(invoice) {
  if (recipientFetched) return;
  recipientFetched = true;

  const recipientEl = elements.modalRecipient;
  if (!recipientEl) return;

  // The modal shows the bank-confirmed legal name. We call the same
  // endpoint the paylink page uses — the invoice carries the sender's
  // username, so we can reuse that route.
  const username = invoice.sender_username;
  if (!username) return;

  try {
    const response = await fetch(
      `${API_URL}/api/paylinks/${encodeURIComponent(username)}/recipient`
    );

    if (!response.ok) {
      console.warn('Recipient details unavailable:', response.status);
      return;
    }

    const data = await response.json();

    if (data && data.name) {
      recipientEl.textContent = data.name;
    }
  } catch (error) {
    console.warn('Could not fetch recipient details:', error);
  }
}

// --------------------------------------------------
// Invoice rendering
// --------------------------------------------------

async function updateInvoiceUI(invoice) {
  document.getElementById('previewName').textContent =
    invoice.sender_business_name || 'Business';

  document.getElementById('previewHandle').textContent =
    `payla.ng/@${invoice.sender_username || 'username'}`;

  await loadMerchantLogo(invoice);

  const daysLeft = getDaysLeft(invoice.due_date);
  const dueStatus = document.getElementById('dueStatus');
  const dueText = document.getElementById('dueText');
  const statusText = document.getElementById('statusText');

  if (invoice.status === 'paid') {
    statusText.textContent = 'Paid';
    dueText.textContent = 'Paid';
    dueStatus.dataset.status = 'paid';
  } else if (daysLeft === null) {
    statusText.textContent = 'Unpaid';
    dueText.textContent = 'Payment due';
    dueStatus.dataset.status = 'far';
  } else if (daysLeft < 0) {
    const daysLate = Math.abs(daysLeft);
    statusText.textContent = 'Overdue';
    dueText.textContent = daysLate === 1
      ? 'Overdue by 1 day'
      : `Overdue by ${daysLate} days`;
    dueStatus.dataset.status = 'overdue';
  } else if (daysLeft === 0) {
    statusText.textContent = 'Due today';
    dueText.textContent = 'Due today';
    dueStatus.dataset.status = 'today';
  } else if (daysLeft === 1) {
    statusText.textContent = 'Due soon';
    dueText.textContent = 'Due tomorrow';
    dueStatus.dataset.status = 'imminent';
  } else if (daysLeft <= 3) {
    statusText.textContent = 'Due soon';
    dueText.textContent = `Due in ${daysLeft} days`;
    dueStatus.dataset.status = 'close';
  } else if (daysLeft <= 7) {
    statusText.textContent = 'Unpaid';
    dueText.textContent = `Due in ${daysLeft} days`;
    dueStatus.dataset.status = 'soon';
  } else {
    statusText.textContent = 'Unpaid';
    dueText.textContent = `Due in ${daysLeft} days`;
    dueStatus.dataset.status = 'far';
  }

  document.getElementById('invoiceAmount').textContent =
    formatCurrency(invoice.amount, invoice.currency);

  document.getElementById('invoiceCurrency').textContent =
    String(invoice.currency || 'NGN').toUpperCase();

  document.getElementById('invoiceNumber').textContent =
    getInvoiceDisplayId(invoice);

  document.getElementById('invoiceDescription').textContent =
    invoice.description || 'No description provided';

  document.getElementById('invoiceDueDate').textContent =
    formatDate(invoice.due_date);

  document.getElementById('createdDate').textContent =
    formatDate(invoice.created_at);

  document.getElementById('senderEmail').textContent =
    invoice.sender_email || 'Not provided';

  document.getElementById('poweredBy').textContent =
    invoice.sender_business_name || 'Payla';

  const notesBox = document.getElementById('notesBox');
  const notes = document.getElementById('invoiceNotes');

  if (invoice.notes?.trim()) {
    notes.textContent = invoice.notes;
    notesBox.classList.remove('hidden');
  } else {
    notesBox.classList.add('hidden');
  }

  elements.modalAmount.textContent =
    formatCurrency(invoice.amount, invoice.currency);

  // Temporary recipient — bank-confirmed name is fetched lazily when
  // the modal opens. Until then we show the business name as fallback.
  elements.modalRecipient.textContent =
    invoice.sender_business_name || 'Recipient';

  elements.modalDescription.textContent =
    invoice.description || 'Invoice payment';

  if (invoice.customer_email && !elements.payerEmailInput.value.trim()) {
    elements.payerEmailInput.value = invoice.customer_email;
  }

  const isPaid = invoice.status === 'paid';
  elements.payBtn.disabled = isPaid;

  const payBtnText = elements.payBtn.querySelector('.btn-text');
  if (payBtnText) {
    payBtnText.textContent = isPaid ? 'Already paid' : 'Pay now';
  }
}

// --------------------------------------------------
// Backend invoice status
// --------------------------------------------------

async function fetchInvoice() {
  const response = await fetch(
    `${API_URL}/api/invoices/${encodeURIComponent(invoiceId)}`,
    { cache: 'no-store' }
  );

  if (!response.ok) {
    const error = new Error(
      response.status === 404
        ? 'Invoice not found.'
        : 'Unable to load invoice.'
    );
    error.status = response.status;
    throw error;
  }

  return response.json();
}

function showConfirmedPayment(invoice) {
  currentInvoice = invoice;

  const params = new URLSearchParams({
    invoice_id: shortId,
    reference: returnedReference || invoice.transaction_reference || ''
  });

  window.location.replace(`/invoice_receipt.html?${params.toString()}`);
}

async function loadInvoice() {
  showLoading();

  try {
    let invoice = await fetchInvoice();

    if (isPaymentReturn && invoice.status !== 'paid') {
      for (let attempt = 0; attempt < 6; attempt += 1) {
        await new Promise(resolve => window.setTimeout(resolve, 2000));
        invoice = await fetchInvoice();
        if (invoice.status === 'paid') break;
      }
    }

    currentInvoice = invoice;

    if (!invoicePageViewTracked) {
      safelyTrack(trackInvoicePageView, invoiceId, invoice.status);
      invoicePageViewTracked = true;
    }

    const loadTime = Math.round(performance.now() - pageLoadStart);

    if (invoice.status === 'paid') {
      showConfirmedPayment(invoice);
      safelyTrack(trackInvoiceLoadSuccess, invoiceId, loadTime, 'paid');
      return;
    }

    await updateInvoiceUI(invoice);
    initializePaystack(invoice);
    showInvoice();

    safelyTrack(
      trackInvoiceLoadSuccess,
      invoiceId,
      loadTime,
      invoice.status || 'unpaid'
    );

    if (isPaymentReturn) {
      const dueText = document.getElementById('dueText');
      if (dueText) {
        dueText.textContent = 'Payment processing — check back shortly';
      }
    }
  } catch (error) {
    console.error('Invoice loading failed:', error);

    safelyTrack(
      trackInvoiceLoadFailed,
      invoiceId,
      error.message || 'unknown_error'
    );

    showError();
  }
}

// --------------------------------------------------
// Checkout
// --------------------------------------------------

function setCheckoutLoading(isLoading) {
  const button = elements.processPayment;
  const buttonText = button.querySelector('.btn-text');
  const buttonLoader = button.querySelector('.btn-loader');

  button.disabled = isLoading;

  if (buttonText) buttonText.style.opacity = isLoading ? '0' : '1';
  if (buttonLoader) buttonLoader.style.display = isLoading ? 'flex' : 'none';
}

function initializePaystack(invoice) {
  elements.payBtn.onclick = () => {
    if (checkoutInProgress) return;
    if (!currentInvoice || currentInvoice.status === 'paid') return;

    safelyTrack(
      trackPayButtonClicked,
      invoiceId,
      invoice.amount,
      invoice.currency
    );

    openModal('paystackModal');

    // Populate the bank-confirmed recipient lazily — once only.
    fetchRecipientOnce(currentInvoice);
  };

  elements.processPayment.onclick = async () => {
    if (checkoutInProgress) return;
    if (!currentInvoice || currentInvoice.status === 'paid') return;

    const email = elements.payerEmailInput.value.trim();
    const emailInput = elements.payerEmailInput;

    if (!email || !emailInput.checkValidity() || !email.includes('@')) {
      alert('Enter a valid email address.');
      emailInput.focus();
      return;
    }

    const emailDomain = email.split('@')[1];

    safelyTrack(
      trackPaymentAttempt,
      invoiceId,
      invoice.amount,
      invoice.currency,
      emailDomain
    );

    checkoutInProgress = true;
    setCheckoutLoading(true);

    try {
      const response = await fetch(
        `${API_URL}/api/invoices/${encodeURIComponent(invoiceId)}/initialize-payment`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ payer_email: email })
        }
      );

      let result = {};
      try {
        result = await response.json();
      } catch {
        // Non-JSON server error handled below.
      }

      if (!response.ok) {
        throw new Error(
          result.detail ||
          result.message ||
          'Unable to start payment. Please try again.'
        );
      }

      const authorizationUrl = result.authorization_url;
      if (!authorizationUrl) {
        throw new Error('The payment service did not return a checkout URL.');
      }

      let checkoutUrl;
      try {
        checkoutUrl = new URL(authorizationUrl);
      } catch {
        throw new Error('The payment service returned an invalid URL.');
      }

      const isPaystackHost =
        checkoutUrl.hostname === 'paystack.com' ||
        checkoutUrl.hostname.endsWith('.paystack.com');

      if (checkoutUrl.protocol !== 'https:' || !isPaystackHost) {
        throw new Error('The payment service returned an invalid checkout URL.');
      }

      window.location.assign(checkoutUrl.href);
    } catch (error) {
      console.error('Checkout initialization failed:', error);

      safelyTrack(
        trackPaymentFailed,
        invoiceId,
        invoice.amount,
        invoice.currency,
        error.message || 'checkout_initialization_failed'
      );

      alert(
        error.message ||
        'We could not start your payment. Please try again.'
      );

      checkoutInProgress = false;
      setCheckoutLoading(false);
    }
  };
}

// --------------------------------------------------
// Event listeners
// --------------------------------------------------

elements.modalClose.onclick = () => {
  if (checkoutInProgress) return;
  closeModal('paystackModal', 'close_button');
};

elements.paystackModal?.addEventListener('click', event => {
  if (event.target === elements.paystackModal && !checkoutInProgress) {
    closeModal('paystackModal', 'overlay_click');
  }
});

// --------------------------------------------------
// Initialize
// --------------------------------------------------

document.addEventListener('DOMContentLoaded', () => {
  loadInvoice();
});