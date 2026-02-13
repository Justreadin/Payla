// paylink_analytics.js
import { track } from "./web_analytics.js";

/* ──────────────────────────────
   PAGE VIEW
────────────────────────────── */
export function trackPaylinkPageView(username) {
  track("paylink_page_view", {
    page: "paylink",
    username: username,
    referrer: document.referrer || "direct",
    timestamp: new Date().toISOString()
  });
}

/* ──────────────────────────────
   PAYMENT FUNNEL
────────────────────────────── */
export function trackTransferButtonClicked(username) {
  track("transfer_button_clicked", {
    username: username,
    action: "open_payment_modal"
  });
}

export function trackPaymentModalOpened(username) {
  track("payment_modal_opened", {
    username: username
  });
}

export function trackPaymentModalClosed(username, method = 'close_button') {
  track("payment_modal_closed", {
    username: username,
    close_method: method
  });
}

/* ──────────────────────────────
   PAYMENT ATTEMPT
────────────────────────────── */
export function trackPaymentAttempt(username, amount, email_domain) {
  track("payment_attempt", {
    username: username,
    amount: amount,
    email_domain: email_domain,
    currency: "NGN"
  });
}

export function trackPaymentSuccess(username, amount, reference, transaction_id) {
  track("payment_success", {
    username: username,
    amount: amount,
    reference: reference,
    transaction_id: transaction_id,
    currency: "NGN"
  });
  
  // Also track as purchase for e-commerce analytics
  track("purchase", {
    transaction_id: reference,
    value: amount,
    currency: "NGN",
    items: [{
      item_name: `Payment to @${username}`,
      item_category: "paylink",
      quantity: 1,
      price: amount
    }]
  });
}

export function trackPaymentFailed(username, amount, reason) {
  track("payment_failed", {
    username: username,
    amount: amount,
    reason: reason
  });
}

/* ──────────────────────────────
   RECEIPT ACTIONS
────────────────────────────── */
export function trackReceiptDownloaded(reference, username) {
  track("receipt_downloaded", {
    reference: reference,
    username: username
  });
}

export function trackReceiptPrinted(reference, username) {
  track("receipt_printed", {
    reference: reference,
    username: username
  });
}

/* ──────────────────────────────
   LOADING & ERROR STATES
────────────────────────────── */
export function trackPaylinkLoadSuccess(username, load_time_ms) {
  track("paylink_load_success", {
    username: username,
    load_time_ms: load_time_ms
  });
}

export function trackPaylinkLoadFailed(username, reason) {
  track("paylink_load_failed", {
    username: username,
    reason: reason
  });
}

/* ──────────────────────────────
   CONTACT INTERACTIONS
────────────────────────────── */
export function trackEmailClicked(username) {
  track("email_clicked", {
    username: username
  });
}

export function trackWhatsAppClicked(username) {
  track("whatsapp_clicked", {
    username: username
  });
}

/* ──────────────────────────────
   AMOUNT INPUT INTERACTIONS
────────────────────────────── */
export function trackAmountEntered(username, amount) {
  track("amount_entered", {
    username: username,
    amount: amount
  });
}

export function trackAmountFocus(username) {
  track("amount_focus", {
    username: username
  });
}