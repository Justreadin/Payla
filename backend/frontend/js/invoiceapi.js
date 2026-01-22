
import { BACKEND_BASE } from './config.js';
const BACKEND_URL = BACKEND_BASE;

let currentInvoiceId = null;

function getAuthHeader() {
  const token = localStorage.getItem("idToken");
  if (!token) throw new Error("User not authenticated");
  return { Authorization: `Bearer ${token}` };
}

// ── CREATE DRAFT (Normal Invoice) ──
async function saveDraft(payload) {
  const res = await fetch(`${BACKEND_URL}/api/invoices/`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...getAuthHeader() },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    const err = await res.text();
    throw new Error(`Draft save failed: ${err}`);
  }

  const data = await res.json();
  currentInvoiceId = data._id;
  return data;
}

// ── UPDATE DRAFT ──
async function updateDraft(invoiceId, payload) {
  const res = await fetch(`${BACKEND_URL}/api/invoices/${invoiceId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...getAuthHeader() },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    const err = await res.text();
    throw new Error(`Draft update failed: ${err}`);
  }

  return await res.json();
}

// ── PUBLISH INVOICE (Normal Invoice) ──
async function publishInvoice(invoiceId) {
  const res = await fetch(`${BACKEND_URL}/api/invoices/${invoiceId}/publish`, {
    method: "POST",
    headers: getAuthHeader(),
  });

  if (!res.ok) {
    const err = await res.text();
    throw new Error(`Publish failed: ${err}`);
  }

  const data = await res.json();
  currentInvoiceId = null; // Reset draft ID
  return data;
}

// ── CREATE QUICK INVOICE ──
async function createQuickInvoice(payload) {
  const res = await fetch(`${BACKEND_URL}/dashboard/quick-invoice`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...getAuthHeader() },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    const err = await res.text();
    throw new Error(`Quick invoice creation failed: ${err}`);
  }

  return await res.json();
}

// ── FETCH SINGLE INVOICE ──
async function getInvoice(invoiceId) {
  const res = await fetch(`${BACKEND_URL}/api/invoices/${invoiceId}`, { headers: getAuthHeader() });
  if (!res.ok) throw new Error("Invoice not found");
  return await res.json();
}

// ── FETCH USER INVOICES ──
async function getUserInvoices() {
  const res = await fetch(`${BACKEND_URL}/api/invoices/`, { headers: getAuthHeader() });
  if (!res.ok) throw new Error("Failed to load invoices");
  return await res.json();
}

// ── VALIDATE PAYLOAD ──
function validateInvoicePayload(payload) {
  return (
    payload.description?.trim().length >= 3 &&
    payload.amount > 0 &&
    ["NGN", "USD", "EUR"].includes(payload.currency) &&
    payload.due_date &&
    payload.client_phone?.replace(/\D/g, "").length >= 10
  );
}

// ── EXPORT ──
export const InvoiceAPI = {
  BACKEND_URL,
  saveDraft,
  updateDraft,
  publishInvoice,
  createQuickInvoice,
  getInvoice,
  getUserInvoices,
  validateInvoicePayload,

  get currentInvoiceId() { return currentInvoiceId; },
  setCurrentInvoiceId(id) { currentInvoiceId = id; },
  reset() { currentInvoiceId = null; },
};
