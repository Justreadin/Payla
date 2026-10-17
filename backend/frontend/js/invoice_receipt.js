import { BACKEND_BASE } from "./config.js";

const API_URL = BACKEND_BASE.replace(/\/+$/, "");

const params = new URLSearchParams(window.location.search);
const suppliedInvoiceId = (params.get("invoice_id") || "").trim();
const reference =
  params.get("reference") ||
  params.get("trxref") ||
  "";

const elements = {
  statusIcon: document.getElementById("statusIcon"),
  statusLabel: document.getElementById("statusLabel"),
  title: document.getElementById("receiptTitle"),
  message: document.getElementById("statusMessage"),
  content: document.getElementById("receiptContent"),
  errorActions: document.getElementById("errorActions"),
  amount: document.getElementById("receiptAmount"),
  merchantName: document.getElementById("merchantName"),
  merchantEmail: document.getElementById("merchantEmail"),
  merchantLogoWrap: document.getElementById("merchantLogoWrap"),
  merchantLogo: document.getElementById("merchantLogo"),
  invoiceId: document.getElementById("receiptInvoiceId"),
  reference: document.getElementById("receiptReference"),
  date: document.getElementById("receiptDate"),
  customer: document.getElementById("receiptCustomer"),
  description: document.getElementById("receiptDescription"),
  download: document.getElementById("downloadReceipt"),
  print: document.getElementById("printReceipt"),
  done: document.getElementById("doneButton"),
  retry: document.getElementById("retryButton"),
  returnButton: document.getElementById("returnButton"),
};

let currentInvoice = null;
let polling = false;

function canonicalInvoiceId(id) {
  return id.startsWith("inv_") ? id : `inv_${id}`;
}

function shortInvoiceId(id) {
  return canonicalInvoiceId(id).replace(/^inv_/, "");
}

function formatAmount(amount, currency = "NGN") {
  const numericAmount = Number(amount);

  if (!Number.isFinite(numericAmount)) {
    return "—";
  }

  try {
    return new Intl.NumberFormat("en-NG", {
      style: "currency",
      currency,
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(numericAmount);
  } catch {
    return `${currency} ${numericAmount.toFixed(2)}`;
  }
}

function formatDate(value) {
  if (!value) return "Awaiting payment timestamp";

  let dateValue = value;

  // Firestore timestamps can be returned as { seconds, nanoseconds }.
  if (typeof value === "object" && value.seconds) {
    dateValue = value.seconds * 1000;
  }

  const date = new Date(dateValue);

  if (Number.isNaN(date.getTime())) {
    return "Date unavailable";
  }

  return new Intl.DateTimeFormat("en-NG", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Africa/Lagos",
  }).format(date);
}

function showState(kind, title, message) {
  elements.statusIcon.className = `status-icon ${kind}`;
  elements.statusIcon.textContent =
    kind === "success" ? "✓" :
    kind === "error" ? "!" : "…";

  elements.statusLabel.textContent =
    kind === "success" ? "PAYMENT CONFIRMED" :
    kind === "error" ? "PAYMENT NOT CONFIRMED" :
    "VERIFYING PAYMENT";

  elements.title.textContent = title;
  elements.message.textContent = message;
}

function showError(message) {
  showState("error", "We couldn't confirm your payment", message);
  elements.content.hidden = true;
  elements.errorActions.hidden = false;
}

function getPaymentReference(invoice) {
  return (
    invoice.transaction_reference ||
    invoice.paystack_reference ||
    ""
  );
}

function renderReceipt(invoice) {
  const canonicalId = canonicalInvoiceId(
    invoice._id || suppliedInvoiceId
  );

  const merchantName =
    invoice.sender_business_name ||
    invoice.sender_username ||
    "Payla merchant";

  const customerName =
    invoice.client_name ||
    invoice.client_email ||
    "Customer";

  elements.amount.textContent = formatAmount(
    invoice.amount,
    invoice.currency || "NGN"
  );

  elements.merchantName.textContent = merchantName;
  elements.merchantEmail.textContent = invoice.sender_email || "";
  elements.invoiceId.textContent = canonicalId;
  elements.reference.textContent = getPaymentReference(invoice) || reference;
  elements.date.textContent = formatDate(invoice.paid_at);
  elements.customer.textContent = customerName;
  elements.description.textContent =
    invoice.description || "Payment for invoice";

  const logo = invoice.sender_logo;

  if (typeof logo === "string" && /^https?:\/\//i.test(logo)) {
    elements.merchantLogo.src = logo;
    elements.merchantLogoWrap.hidden = false;

    elements.merchantLogo.onerror = () => {
      elements.merchantLogoWrap.hidden = true;
    };
  } else {
    elements.merchantLogo.removeAttribute("src");
    elements.merchantLogoWrap.hidden = true;
  }

  elements.content.hidden = false;
  elements.errorActions.hidden = true;
  showState(
    "success",
    "Payment successful!",
    "Your payment has been confirmed. Your receipt is ready."
  );
}

async function fetchInvoice() {
  const response = await fetch(
    `${API_URL}/api/invoices/${encodeURIComponent(suppliedInvoiceId)}`,
    { cache: "no-store" }
  );

  if (!response.ok) {
    if (response.status === 404) {
      throw new Error("We couldn't find this invoice. Check the invoice link.");
    }

    throw new Error("Unable to retrieve the invoice. Please try again.");
  }

  return response.json();
}

async function checkPayment({ retry = false } = {}) {
  if (polling) return;
  polling = true;

  elements.errorActions.hidden = true;
  elements.content.hidden = true;

  showState(
    "pending",
    "Confirming your payment",
    retry
      ? "Checking the latest payment status with Payla."
      : "Paystack has returned you to Payla. We're checking the payment record."
  );

  try {
    if (!suppliedInvoiceId) {
      throw new Error("The invoice ID is missing from this receipt link.");
    }

    if (!reference) {
      throw new Error("The payment reference is missing from this receipt link.");
    }

    // Allow the webhook time to update Firestore after Paystack redirects.
    const maxAttempts = 15;

    for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
      const invoice = await fetchInvoice();

      const storedReference = getPaymentReference(invoice);

      if (
        storedReference &&
        storedReference !== reference
      ) {
        throw new Error(
          "This payment reference does not match the invoice's recorded payment."
        );
      }

      if (invoice.status === "paid") {
        if (!storedReference || storedReference !== reference) {
          throw new Error(
            "The invoice is marked paid, but this payment reference could not be verified."
          );
        }

        currentInvoice = invoice;
        renderReceipt(invoice);
        polling = false;
        return;
      }

      if (invoice.status === "failed" || invoice.status === "overdue") {
        throw new Error(
          invoice.status === "overdue"
            ? "This invoice is overdue and payment has not been confirmed."
            : "The invoice does not show a confirmed successful payment."
        );
      }

      if (attempt < maxAttempts - 1) {
        await new Promise((resolve) => setTimeout(resolve, 2000));
      }
    }

    showError(
      "Your payment may have succeeded, but Payla hasn't confirmed it yet. " +
      "Wait a little and check again. Please don't pay a second time while " +
      "the original transaction is being checked."
    );
  } catch (error) {
    showError(
      error instanceof Error
        ? error.message
        : "Something went wrong while checking your payment."
    );
  } finally {
    polling = false;
  }
}

function getReceiptPdfUrl() {
  if (!currentInvoice) {
    throw new Error("The receipt is not ready yet.");
  }

  const invoiceId = canonicalInvoiceId(
    currentInvoice._id || suppliedInvoiceId
  );

  const query = new URLSearchParams({ token: reference });

  return `${API_URL}/api/receipt/invoice/${encodeURIComponent(invoiceId)}.pdf?${query}`;
}

elements.download.addEventListener("click", () => {
  try {
    window.location.assign(getReceiptPdfUrl());
  } catch (error) {
    showError(error.message || "The receipt is not ready to download.");
  }
});

elements.print.addEventListener("click", () => {
  if (currentInvoice) {
    window.print();
  }
});

elements.done.addEventListener("click", () => {
  window.location.assign(`/i/${encodeURIComponent(shortInvoiceId(suppliedInvoiceId))}`);
});

elements.retry.addEventListener("click", () => {
  checkPayment({ retry: true });
});

elements.returnButton.addEventListener("click", () => {
  if (suppliedInvoiceId) {
    window.location.assign(`/i/${encodeURIComponent(shortInvoiceId(suppliedInvoiceId))}`);
  } else {
    window.location.assign("/");
  }
});

checkPayment();