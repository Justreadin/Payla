// invoice_analytics.js
import { track } from "./web_analytics.js";

/* ──────────────────────────────
   PAGE VIEW
────────────────────────────── */
export function trackInvoicePageView(invoiceId, status, referrer = document.referrer || "direct") {
  track("invoice_page_view", {
    page: "invoice",
    invoice_id: invoiceId,
    status: status,
    referrer: referrer,
    timestamp: new Date().toISOString()
  });
}

/* ──────────────────────────────
   LOADING & ERROR STATES
────────────────────────────── */
export function trackInvoiceLoadSuccess(invoiceId, load_time_ms, status) {
  track("invoice_load_success", {
    invoice_id: invoiceId,
    load_time_ms: load_time_ms,
    status: status
  });
}

export function trackInvoiceLoadFailed(invoiceId, reason) {
  track("invoice_load_failed", {
    invoice_id: invoiceId,
    reason: reason
  });
}

/* ──────────────────────────────
   PAYMENT FUNNEL
────────────────────────────── */
export function trackPayButtonClicked(invoiceId, amount, currency) {
  track("pay_button_clicked", {
    invoice_id: invoiceId,
    amount: amount,
    currency: currency,
    action: "open_payment_modal"
  });
}

export function trackPaymentModalOpened(invoiceId) {
  track("payment_modal_opened", {
    invoice_id: invoiceId
  });
}

export function trackPaymentModalClosed(invoiceId, method = 'close_button') {
  track("payment_modal_closed", {
    invoice_id: invoiceId,
    close_method: method
  });
}

/* ──────────────────────────────
   PAYMENT ATTEMPT
────────────────────────────── */
export function trackPaymentAttempt(invoiceId, amount, currency, email_domain) {
  track("payment_attempt", {
    invoice_id: invoiceId,
    amount: amount,
    currency: currency,
    email_domain: email_domain
  });
}

export function trackPaymentSuccess(invoiceId, amount, currency, reference, transaction_id) {
  track("payment_success", {
    invoice_id: invoiceId,
    amount: amount,
    currency: currency,
    reference: reference,
    transaction_id: transaction_id
  });
  
  // Also track as purchase for e-commerce analytics
  track("purchase", {
    transaction_id: reference,
    value: amount,
    currency: currency,
    items: [{
      item_name: `Invoice ${invoiceId}`,
      item_category: "invoice",
      quantity: 1,
      price: amount
    }]
  });
}

export function trackPaymentFailed(invoiceId, amount, currency, reason) {
  track("payment_failed", {
    invoice_id: invoiceId,
    amount: amount,
    currency: currency,
    reason: reason
  });
}

/* ──────────────────────────────
   RECEIPT ACTIONS
────────────────────────────── */
export function trackReceiptDownloaded(invoiceId, source = 'payment_success') {
  track("receipt_downloaded", {
    invoice_id: invoiceId,
    source: source
  });
}

/* ──────────────────────────────
   INVOICE STATUS CHECKS
────────────────────────────── */
export function trackPaidInvoiceView(invoiceId) {
  track("paid_invoice_view", {
    invoice_id: invoiceId
  });
}

/* ──────────────────────────────
   EMAIL INTERACTIONS
────────────────────────────── */
export function trackPayerEmailEntered(invoiceId, email_domain) {
  track("payer_email_entered", {
    invoice_id: invoiceId,
    email_domain: email_domain
  });
}