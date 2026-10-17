
import { BACKEND_BASE } from './config.js';

const BACKEND_URL = BACKEND_BASE;

let currentInvoiceId = null;

function getAuthHeader() {
  const token = localStorage.getItem('idToken');

  if (!token) {
    throw new Error('User not authenticated');
  }

  return {
    Authorization: `Bearer ${token}`,
  };
}

async function parseResponse(res, fallbackMessage) {
  if (!res.ok) {
    let detail = '';

    try {
      const data = await res.json();
      detail =
        data.detail?.message ||
        data.detail ||
        data.message ||
        '';
    } catch {
      try {
        detail = await res.text();
      } catch {
        // Keep the fallback message.
      }
    }

    if (typeof detail !== 'string') {
      detail = JSON.stringify(detail);
    }

    throw new Error(
      detail ? `${fallbackMessage}: ${detail}` : fallbackMessage
    );
  }

  return res.json();
}

// ── CREATE DRAFT ──
async function saveDraft(payload) {
  const res = await fetch(`${BACKEND_URL}/api/invoices/`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...getAuthHeader(),
    },
    body: JSON.stringify(payload),
  });

  const data = await parseResponse(res, 'Draft save failed');
  const id = data._id || data.id;

  if (!id) {
    throw new Error('Draft was saved but the response did not contain an invoice ID.');
  }

  currentInvoiceId = id;

  return data;
}

// ── UPDATE DRAFT ──
async function updateDraft(invoiceId, payload) {
  if (!invoiceId) {
    throw new Error('An invoice ID is required to update a draft.');
  }

  const res = await fetch(
    `${BACKEND_URL}/api/invoices/${encodeURIComponent(invoiceId)}`,
    {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
        ...getAuthHeader(),
      },
      body: JSON.stringify(payload),
    }
  );

  const data = await parseResponse(res, 'Draft update failed');

  currentInvoiceId = invoiceId;

  return data;
}

// ── PUBLISH INVOICE ──
async function publishInvoice(invoiceId) {
  if (!invoiceId) {
    throw new Error('An invoice ID is required to publish an invoice.');
  }

  const res = await fetch(
    `${BACKEND_URL}/api/invoices/${encodeURIComponent(invoiceId)}/publish`,
    {
      method: 'POST',
      headers: getAuthHeader(),
    }
  );

  const data = await parseResponse(res, 'Publish failed');

  // Keep the published invoice ID available to the calling page.
  // The caller can set the new published ID after inspecting the response.
  currentInvoiceId = data._id || data.id || invoiceId;

  return data;
}

// ── CREATE QUICK INVOICE ──
// Retain temporarily until dashboard and backend callers are checked.
async function createQuickInvoice(payload) {
  const res = await fetch(`${BACKEND_URL}/dashboard/quick-invoice`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...getAuthHeader(),
    },
    body: JSON.stringify(payload),
  });

  return parseResponse(res, 'Quick invoice creation failed');
}

// ── FETCH SINGLE INVOICE ──
async function getInvoice(invoiceId) {
  if (!invoiceId) {
    throw new Error('An invoice ID is required.');
  }

  const res = await fetch(
    `${BACKEND_URL}/api/invoices/${encodeURIComponent(invoiceId)}`,
    { headers: getAuthHeader() }
  );

  return parseResponse(res, 'Invoice not found');
}

// ── FETCH USER INVOICES ──
async function getUserInvoices() {
  const res = await fetch(`${BACKEND_URL}/api/invoices/`, {
    headers: getAuthHeader(),
  });

  return parseResponse(res, 'Failed to load invoices');
}

// ── VALIDATE PAYLOAD ──
function validateInvoicePayload(payload) {
  return Boolean(
    payload &&
    typeof payload.description === 'string' &&
    payload.description.trim().length >= 3 &&
    Number.isFinite(Number(payload.amount)) &&
    Number(payload.amount) > 0 &&
    payload.currency === 'NGN' &&
    payload.due_date &&
    payload.client_phone &&
    payload.client_phone.replace(/\D/g, '').length >= 10 &&
    ['merchant', 'client'].includes(payload.fee_payer)
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

  get currentInvoiceId() {
    return currentInvoiceId;
  },

  setCurrentInvoiceId(id) {
    currentInvoiceId = id || null;
  },

  reset() {
    currentInvoiceId = null;
  },
};
