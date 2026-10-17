import { InvoiceAPI } from './invoiceapi.js';
import {
  BACKEND_BASE,
  WHATSAPP_CHANNEL_STATUS,
  SMS_CHANNEL_STATUS,
  EMAIL_CHANNEL_STATUS,
} from './config.js';
import { authFetch } from './upgrade-handler.js';

const api = InvoiceAPI;

// ==================== CHANNEL FLAGS ====================

const CHANNEL_STATUSES = {
  whatsapp: WHATSAPP_CHANNEL_STATUS,
  sms: SMS_CHANNEL_STATUS,
  email: EMAIL_CHANNEL_STATUS,
};

const CHANNEL_LABELS = {
  whatsapp: 'WhatsApp',
  sms: 'SMS',
  email: 'Email',
};

const PRIORITY_LABELS = ['Primary', 'Secondary', 'Tertiary'];

// ==================== DOM ELEMENTS ====================

const toggleButtons = document.querySelectorAll('.preview-toggle-btn');
const formSection = document.getElementById('form-section');
const previewSection = document.getElementById('preview-section');

const steps = document.querySelectorAll('.step');
const stepContents = document.querySelectorAll('.step-content');
const backBtn = document.getElementById('back-btn');
const nextBtn = document.getElementById('next-btn');

const descriptionInput = document.getElementById('description');
const amountInput = document.getElementById('amount');
const currencySelect = document.getElementById('currency');
const dueDateInput = document.getElementById('due-date');
const countryCodeSelect = document.getElementById('country-code');
const clientPhoneLocalInput = document.getElementById('client-phone-local');
const clientEmailInput = document.getElementById('client-email');

const feePayerInput = document.getElementById('fee-payer');
const feePayerHint = document.getElementById('fee-payer-hint');

const autoRemindToggle = document.getElementById('auto-remind');
const reminderOptions = document.getElementById('reminder-options');

const toast = document.getElementById('draft-toast');
const shareModal = document.getElementById('share-modal');
const shareLinkEl = document.getElementById('share-link');
const modalClose = document.getElementById('modal-close');
const copyBtn = document.getElementById('copy-link');
const shareWhatsapp = document.getElementById('share-whatsapp');

const reminderModal = document.getElementById('reminder-settings-modal');
const reminderModalClose = document.getElementById('reminder-modal-close');
const cancelReminderBtn = document.getElementById('cancel-reminder');
const saveReminderBtn = document.getElementById('save-reminder');

const descriptionCounter = document.getElementById('description-counter');
const maxDescriptionLength = 70;

// Reminder controls
const channelChips = document.querySelectorAll('.channel-chips .chip');
const scheduleTabs = document.querySelectorAll('.schedule-tabs .tab');
const presetChips = document.querySelectorAll('.chip.preset');
const autoMode = document.getElementById('auto-mode');
const manualMode = document.getElementById('manual-mode');
const addDateBtn = document.querySelector('.add-date-btn');

// ==================== STATE ====================

let currentStep = 0;
let currentInvoiceId = null;
let userProfile = {};

let autosaveTimer = null;
let pendingAutosaveResolvers = [];
let autosaveInFlight = Promise.resolve(null);

let isPublishing = false;
let isPublished = false;

// ==================== CHANNEL FLAG APPLICATION ====================

/**
 * Apply the channel flags from config.js to the invoice UI.
 *
 * - Chips: active channels are clickable and pre-selected, disabled
 *   channels are greyed out with a "Soon" badge and excluded from
 *   the payload by collectReminderPayload and updateReminderChannels.
 * - Modal priority items: active channels are ordered first with
 *   Primary/Secondary/Tertiary badges, disabled ones follow with a
 *   "Coming soon" badge.
 * - Hint text: only active channels are listed in the
 *   "We try X, then Y" copy, with disabled channels appended as
 *   "coming soon".
 */
function applyChannelFlags() {
  const allChannels = Object.keys(CHANNEL_STATUSES);
  const activeChannels = allChannels.filter(
    (ch) => CHANNEL_STATUSES[ch] === 'active'
  );
  const disabledChannels = allChannels.filter(
    (ch) => CHANNEL_STATUSES[ch] !== 'active'
  );

  // 1. Chips — set active or disabled per the flag.
  document
    .querySelectorAll('.chip.channel[data-channel]')
    .forEach((chip) => {
      const channel = chip.dataset.channel;
      const status = CHANNEL_STATUSES[channel] || 'disabled';
      const label = CHANNEL_LABELS[channel] || channel;

      if (status === 'active') {
        chip.disabled = false;
        chip.classList.add('active');
        chip.removeAttribute('aria-disabled');
        chip.removeAttribute('title');
      } else {
        chip.disabled = true;
        chip.classList.remove('active');
        chip.setAttribute('aria-disabled', 'true');
        chip.title = `${label} is coming soon`;
      }
    });

  // 2. Modal priority items — mark disabled and relabel badges.
  document
    .querySelectorAll('.channel-priority .priority-item[data-channel]')
    .forEach((item) => {
      const channel = item.dataset.channel;
      const status = CHANNEL_STATUSES[channel] || 'disabled';
      const badge = item.querySelector('.priority-badge');

      if (status === 'active') {
        item.classList.add('active');
        item.classList.remove('is-disabled');

        const activeIndex = activeChannels.indexOf(channel);
        if (badge) {
          badge.textContent =
            PRIORITY_LABELS[activeIndex] || 'Active';
        }
      } else {
        item.classList.remove('active');
        item.classList.add('is-disabled');
        if (badge) badge.textContent = 'Coming soon';
      }
    });

  // 3. Reorder the modal so active channels come first.
  const priorityContainer = document.querySelector('.channel-priority');
  if (priorityContainer) {
    [...activeChannels, ...disabledChannels].forEach((channel) => {
      const item = priorityContainer.querySelector(
        `.priority-item[data-channel="${channel}"]`
      );
      if (item) priorityContainer.appendChild(item);
    });
  }

  // 4. Hint text — list only active channels in the "We try"
  //    sentence, then a quiet "coming soon" note for disabled ones.
  const hintEl = document.getElementById('channel-hint');
  if (hintEl) {
    const activeLabels = activeChannels.map(
      (ch) => CHANNEL_LABELS[ch] || ch
    );
    const disabledLabels = disabledChannels.map(
      (ch) => CHANNEL_LABELS[ch] || ch
    );

    let text = '';

    if (activeLabels.length === 1) {
      text = `We use ${activeLabels[0]}.`;
    } else if (activeLabels.length === 2) {
      text = `We try ${activeLabels[0]} first, then ${activeLabels[1]}.`;
    } else if (activeLabels.length > 2) {
      const head = activeLabels.slice(0, -1).join(', ');
      const tail = activeLabels[activeLabels.length - 1];
      text = `We try ${head}, then ${tail}.`;
    }

    if (disabledLabels.length > 0) {
      const verb =
        disabledLabels.length === 1 ? 'is' : 'are';
      text += ` ${disabledLabels.join(', ')} ${verb} coming soon.`;
    }

    hintEl.textContent = text.trim();
  }
}

// ==================== HELPERS ====================

function setDisplayLink(element, fullUrl) {
  if (!element || !fullUrl) return;

  element.textContent = fullUrl.replace(/^https?:\/\//i, '');
  element.dataset.fullUrl = fullUrl;
  element.style.cursor = 'pointer';

  element.onclick = () => {
    window.open(fullUrl, '_blank', 'noopener,noreferrer');
  };
}

function showToast(message = 'Draft saved') {
  if (!toast) return;

  toast.textContent = message;
  toast.classList.add('show');

  window.setTimeout(() => {
    toast.classList.remove('show');
  }, 3000);
}

function cleanPhone(raw) {
  if (!raw) return '';

  let number = raw.replace(/\D/g, '');

  if (number.length === 11 && number.startsWith('0')) {
    number = number.substring(1);
  }

  if (number.length === 10 && number.startsWith('0')) {
    number = number.substring(1);
  }

  return number;
}

function getEffectiveFeePayer() {
  if (
    feePayerInput?.value === 'merchant' ||
    feePayerInput?.value === 'client'
  ) {
    return feePayerInput.value;
  }

  return userProfile.default_invoice_fee_payer === 'client'
    ? 'client'
    : 'merchant';
}

function updateFeePayerHint() {
  if (!feePayerHint) return;

  const selection = feePayerInput?.value || 'default';

  if (selection === 'default') {
    const defaultPayer = getEffectiveFeePayer();

    feePayerHint.textContent =
      defaultPayer === 'client'
        ? 'This invoice will use your account default: your client covers the payment fees.'
        : 'This invoice will use your account default: you cover the payment fees.';

    return;
  }

  feePayerHint.textContent =
    selection === 'client'
      ? 'Your client will cover the payment fees for this invoice, subject to the backend payment configuration.'
      : 'You will cover the payment fees for this invoice.';
}

function setDefaultDueDate() {
  if (!dueDateInput) return;

  const nextWeek = new Date();
  nextWeek.setDate(nextWeek.getDate() + 7);

  const year = nextWeek.getFullYear();
  const month = String(nextWeek.getMonth() + 1).padStart(2, '0');
  const day = String(nextWeek.getDate()).padStart(2, '0');

  dueDateInput.value = `${year}-${month}-${day}`;
}

function getFullClientPhone() {
  const localNumber = cleanPhone(clientPhoneLocalInput?.value || '');

  if (!localNumber) return '';

  const countryCode = countryCodeSelect?.value || '+234';

  return `${countryCode}${localNumber}`;
}

function getInvoiceId(data) {
  return data?._id || data?.id || data?.invoice_id || null;
}

// ==================== LOAD USER PROFILE ====================

async function loadUserProfile() {
  try {
    const response = await authFetch(`${BACKEND_BASE}/api/profile/`);

    if (!response.ok) {
      throw new Error(`Profile fetch failed: ${response.status}`);
    }

    userProfile = await response.json();

    const brandNameEl = document.getElementById('preview-brand-name');
    const handleEl = document.getElementById('preview-handle');
    const senderNameEl = document.getElementById('preview-sender-name');
    const senderPhoneEl = document.getElementById('preview-sender-phone');
    const senderEmailEl = document.getElementById('preview-sender-email');
    const poweredByEl = document.getElementById('preview-powered-by');
    const logoEl = document.getElementById('preview-logo-initials');

    const businessName =
      userProfile.business_name || userProfile.full_name || 'Your Business';

    if (brandNameEl) {
      brandNameEl.textContent = businessName;
    }

    if (handleEl) {
      // Respect the user's preferred domain. Free users always
      // have "ng"; Silver users can opt in to "vip".
      const domain =
        userProfile.preferred_domain === 'vip'
          ? 'payla.vip'
          : 'payla.ng';

      handleEl.textContent = `${domain}/@${
        userProfile.username || 'username'
      }`;
    }

    if (senderNameEl) {
      senderNameEl.textContent =
        userProfile.business_name || userProfile.full_name || '';
    }

    if (senderPhoneEl) {
      senderPhoneEl.textContent =
        userProfile.phone_number?.replace(
          /(\d{3})(\d{3})(\d{4})/,
          '$1 $2 $3'
        ) || '+234 801 234 5678';
    }

    if (senderEmailEl) {
      senderEmailEl.textContent = userProfile.email || 'you@payla.ng';
    }

    if (poweredByEl) {
      poweredByEl.textContent = businessName;
    }

    if (userProfile.logo_url) {
      const logoUrl = userProfile.logo_url.startsWith('http')
        ? userProfile.logo_url
        : `${BACKEND_BASE}${userProfile.logo_url}`;

      document.querySelectorAll('#preview-logo, .preview-logo').forEach((el) => {
        el.style.backgroundImage = `url("${logoUrl}")`;

        const initialsEl = el.querySelector('span');
        if (initialsEl) initialsEl.style.display = 'none';
      });
    }

    const initials = businessName
      .split(/\s+/)
      .filter(Boolean)
      .map((word) => word[0])
      .join('')
      .slice(0, 2)
      .toUpperCase();

    if (logoEl) {
      logoEl.textContent = initials || 'YB';
    }

    // "default" means inherit the account preference.
    // Do not convert the account default into an explicit invoice override.
    if (feePayerInput && !['merchant', 'client'].includes(feePayerInput.value)) {
      feePayerInput.value = 'default';
    }

    updateFeePayerHint();
  } catch (error) {
    console.error('Failed to load profile:', error);
    updateFeePayerHint();
  }
}

// ==================== DESCRIPTION COUNTER ====================

if (descriptionInput) {
  descriptionInput.addEventListener('input', () => {
    if (descriptionInput.value.length > maxDescriptionLength) {
      descriptionInput.value = descriptionInput.value.slice(
        0,
        maxDescriptionLength
      );
    }

    if (descriptionCounter) {
      const remaining =
        maxDescriptionLength - descriptionInput.value.length;

      descriptionCounter.textContent = `${remaining} characters remaining`;
    }
  });
}

// ==================== MOBILE TOGGLE ====================

toggleButtons.forEach((button) => {
  button.addEventListener('click', () => {
    const target = button.getAttribute('data-target');

    toggleButtons.forEach((item) => item.classList.remove('active'));
    button.classList.add('active');

    if (formSection && previewSection) {
      formSection.style.display = target === 'form' ? 'flex' : 'none';
      previewSection.style.display = target === 'preview' ? 'flex' : 'none';
    }
  });
});

// ==================== STEPPER ====================

function updateStepper() {
  steps.forEach((step, index) => {
    step.classList.toggle('completed', index < currentStep);
    step.classList.toggle('active', index === currentStep);
  });

  stepContents.forEach((content, index) => {
    content.classList.toggle('active', index === currentStep);
  });

  if (backBtn) {
    backBtn.style.visibility = currentStep === 0 ? 'hidden' : 'visible';
  }

  if (nextBtn) {
    nextBtn.textContent = currentStep === 2 ? 'Publish' : 'Next';
    nextBtn.disabled = isPublishing || isPublished;
  }
}

function validateStep(step) {
  if (step !== 0) return true;

  const requiredFields = [
    { element: descriptionInput, label: 'Description' },
    { element: amountInput, label: 'Amount' },
    { element: dueDateInput, label: 'Due date' },
  ];

  for (const { element, label } of requiredFields) {
    if (!element || !element.value.trim()) {
      element?.classList.add('input-error');
      element?.focus();
      alert(`${label} is required.`);
      return false;
    }

    element.classList.remove('input-error');
  }

  const amount = Number(amountInput.value);

  if (!Number.isFinite(amount) || amount <= 0) {
    amountInput.classList.add('input-error');
    amountInput.focus();
    alert('Enter a valid invoice amount greater than zero.');
    return false;
  }

  if (currencySelect && currencySelect.value !== 'NGN') {
    alert('Invoices currently support NGN only.');
    return false;
  }

  return true;
}

if (nextBtn) {
  nextBtn.addEventListener('click', async () => {
    if (isPublishing || isPublished) return;

    if (currentStep === 0 && !validateStep(0)) return;

    if (currentStep < 2) {
      currentStep++;
      updateStepper();
      return;
    }

    await publishInvoice();
  });
}

if (backBtn) {
  backBtn.addEventListener('click', () => {
    if (isPublishing || isPublished) return;

    if (currentStep > 0) {
      currentStep--;
      updateStepper();
    }
  });
}

// ==================== REMINDER SYSTEM ====================

channelChips.forEach((chip) => {
  chip.addEventListener('click', () => {
    if (chip.disabled) return;

    chip.classList.toggle('active');
    scheduleAutosave();
  });
});

scheduleTabs.forEach((tab) => {
  tab.addEventListener('click', () => {
    scheduleTabs.forEach((item) => item.classList.remove('active'));
    tab.classList.add('active');

    if (autoMode) {
      autoMode.classList.toggle('hidden', tab.dataset.mode === 'manual');
    }

    if (manualMode) {
      manualMode.classList.toggle('hidden', tab.dataset.mode === 'auto');
    }

    scheduleAutosave();
  });
});

presetChips.forEach((chip) => {
  chip.addEventListener('click', () => {
    presetChips.forEach((item) => item.classList.remove('active'));
    chip.classList.add('active');
    scheduleAutosave();
  });
});

if (addDateBtn) {
  addDateBtn.addEventListener('click', () => {
    const container = document.querySelector('.manual-dates');
    if (!container) return;

    const row = document.createElement('div');
    row.className = 'manual-date-row';

    const input = document.createElement('input');
    input.type = 'datetime-local';
    input.className = 'manual-date-input';
    input.setAttribute('aria-label', 'Reminder date and time');

    const removeButton = document.createElement('button');
    removeButton.type = 'button';
    removeButton.className = 'remove-date';
    removeButton.setAttribute('aria-label', 'Remove reminder date');
    removeButton.textContent = '×';

    row.append(input, removeButton);
    container.insertBefore(row, addDateBtn);
  });
}

document.addEventListener('click', (event) => {
  const removeButton = event.target.closest('.remove-date');

  if (!removeButton) return;

  removeButton.closest('.manual-date-row')?.remove();
  scheduleAutosave();
});

document.addEventListener('change', (event) => {
  if (event.target.matches('.manual-date-input')) {
    scheduleAutosave();
  }
});

function collectReminderPayload() {
  const enabled = Boolean(autoRemindToggle?.checked);

  if (!enabled) {
    return { auto_remind: false };
  }

  // Only include chips that are both active and enabled.
  // Disabled channels (e.g. WhatsApp while Meta is being set up)
  // are never sent to the backend.
  const channels = Array.from(channelChips)
    .filter((chip) => chip.classList.contains('active'))
    .filter((chip) => !chip.disabled)
    .map((chip) => chip.dataset.channel)
    .filter(Boolean);

  const activeTab = document.querySelector('.schedule-tabs .tab.active');
  const isManual = activeTab?.dataset.mode === 'manual';

  const customMessage =
    document.getElementById('custom-reminder-message')?.value.trim() || null;

  if (isManual) {
    const dates = Array.from(document.querySelectorAll('.manual-date-input'))
      .map((input) => input.value)
      .filter(Boolean);

    return {
      auto_remind: true,
      method_priority: channels,
      custom_message: customMessage,
      manual_dates: dates,
    };
  }

  const preset =
    document.querySelector('.chip.preset.active')?.dataset.preset || 'gentle';

  return {
    auto_remind: true,
    method_priority: channels,
    preset,
    custom_message: customMessage,
  };
}

function updateReminderChannels() {
  const phone = cleanPhone(clientPhoneLocalInput?.value || '');
  const email = clientEmailInput?.value.trim() || '';

  const hasPhone = phone.length === 10;
  const hasEmail = email.length > 3;

  if (!autoRemindToggle || !reminderOptions) return;

  if (!autoRemindToggle.checked) return;

  if (!hasPhone && !hasEmail) {
    autoRemindToggle.checked = false;
    reminderOptions.style.display = 'none';
    return;
  }

  reminderOptions.style.display = 'block';

  const anyActive = Array.from(channelChips).some(
    (chip) => chip.classList.contains('active') && !chip.disabled
  );

  if (!anyActive) {
    channelChips.forEach((chip) => chip.classList.remove('active'));

    if (hasPhone) {
      // Only auto-activate phone-based channels that are currently
      // enabled. WhatsApp is excluded while its flag is disabled.
      document
        .querySelectorAll(
          '.chip[data-channel="whatsapp"]:not([disabled]), .chip[data-channel="sms"]:not([disabled])'
        )
        .forEach((chip) => chip.classList.add('active'));
    }

    if (hasEmail) {
      document
        .querySelector('.chip[data-channel="email"]:not([disabled])')
        ?.classList.add('active');
    }
  }
}

if (autoRemindToggle) {
  autoRemindToggle.addEventListener('change', () => {
    const phone = cleanPhone(clientPhoneLocalInput?.value || '');
    const email = clientEmailInput?.value.trim() || '';

    if (autoRemindToggle.checked && !phone && !email) {
      showToast('Add client contact information to enable reminders.');
      autoRemindToggle.checked = false;

      if (reminderOptions) reminderOptions.style.display = 'none';
    } else {
      if (reminderOptions) {
        reminderOptions.style.display =
          autoRemindToggle.checked ? 'block' : 'none';
      }

      if (autoRemindToggle.checked) {
        updateReminderChannels();
      }
    }

    scheduleAutosave();
    updatePreview();
  });
}

// ==================== PREVIEW ====================

function updatePreview() {
  const description = descriptionInput?.value || '';
  const amount = amountInput?.value || '';
  const currency = currencySelect?.value || 'NGN';
  const symbol = currency === 'NGN' ? '₦' : '$';
  const fullPhone = getFullClientPhone();

  const previewDesc = document.getElementById('preview-description');
  const previewAmount = document.getElementById('preview-amount');
  const summaryDesc = document.getElementById('summary-description');
  const summaryAmount = document.getElementById('summary-amount');
  const summaryDue = document.getElementById('summary-due-date');
  const summaryClient = document.getElementById('summary-client');

  if (previewDesc) previewDesc.textContent = description;
  if (previewAmount) {
    previewAmount.textContent =
      `${symbol}${Number(amount || 0).toLocaleString()} ${currency}`;
  }

  if (summaryDesc) summaryDesc.textContent = description;
  if (summaryAmount) {
    summaryAmount.textContent =
      `${symbol}${Number(amount || 0).toLocaleString()} ${currency}`;
  }

  if (summaryDue && dueDateInput?.value) {
    const date = new Date(`${dueDateInput.value}T00:00:00`);

    summaryDue.textContent = date.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    });
  }

  if (summaryClient) {
    summaryClient.textContent =
      fullPhone || clientEmailInput?.value?.trim() || 'Not provided';
  }
}

[
  descriptionInput,
  amountInput,
  currencySelect,
  dueDateInput,
  countryCodeSelect,
  clientPhoneLocalInput,
  clientEmailInput,
].forEach((element) => {
  if (!element) return;

  element.addEventListener('input', updatePreview);
  element.addEventListener('change', updatePreview);
});

if (clientPhoneLocalInput) {
  clientPhoneLocalInput.addEventListener('input', () => {
    clientPhoneLocalInput.value = cleanPhone(clientPhoneLocalInput.value);
    updateReminderChannels();
    updatePreview();
  });
}

if (clientEmailInput) {
  clientEmailInput.addEventListener('input', () => {
    updateReminderChannels();
    updatePreview();
  });
}

// ==================== COLLECT INVOICE DATA ====================

function collectInvoiceData() {
  const selection = feePayerInput?.value || 'default';

  return {
    description: descriptionInput?.value?.trim() || '',
    amount: Number(amountInput?.value) || 0,
    currency: currencySelect?.value || 'NGN',
    due_date: dueDateInput?.value || null,
    client_phone: getFullClientPhone(),
    client_email: clientEmailInput?.value?.trim() || null,
    
    // null explicitly means: inherit the account preference.
    // Explicit "merchant" or "client" means an invoice-level override.
    fee_payer:
      selection === 'merchant' || selection === 'client'
        ? selection
        : null,

    auto_remind: Boolean(autoRemindToggle?.checked),
    reminder_settings: collectReminderPayload(),
  };
}

// ==================== AUTOSAVE ====================

async function saveDraftNow() {
  const data = collectInvoiceData();

  let response;

  if (currentInvoiceId) {
    response = await authFetch(
      `${api.BACKEND_URL}/api/invoices/${encodeURIComponent(currentInvoiceId)}`,
      {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      }
    );
  } else {
    response = await authFetch(`${api.BACKEND_URL}/api/invoices/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
  }

  if (!response.ok) {
    const body = await response.text().catch(() => '');
    throw new Error(
      `Draft save failed (${response.status})${body ? `: ${body}` : ''}`
    );
  }

  const result = await response.json();
  const returnedId = getInvoiceId(result);

  if (returnedId) {
    currentInvoiceId = returnedId;
    api.setCurrentInvoiceId(returnedId);
  }

  if (!currentInvoiceId) {
    throw new Error('The server did not return an invoice ID.');
  }

  return currentInvoiceId;
}

function runPendingAutosave() {
  clearTimeout(autosaveTimer);
  autosaveTimer = null;

  if (pendingAutosaveResolvers.length === 0) {
    return autosaveInFlight;
  }

  const resolvers = pendingAutosaveResolvers.splice(0);

  // Serialize saves so a slower, older request cannot finish after a newer
  // request and silently overwrite the latest draft.
  const saveTask = autosaveInFlight
    .catch(() => null)
    .then(() => saveDraftNow());

  autosaveInFlight = saveTask.catch(() => null);

  saveTask
    .then((invoiceId) => {
      showToast('Draft saved');
      resolvers.forEach((resolve) => resolve(invoiceId));
    })
    .catch((error) => {
      console.error('Autosave failed:', error);
      showToast('Failed to save draft');
      resolvers.forEach((resolve) => resolve(null));
    });

  return saveTask;
}

function scheduleAutosave() {
  if (isPublishing || isPublished) {
    return Promise.resolve(currentInvoiceId);
  }

  const promise = new Promise((resolve) => {
    pendingAutosaveResolvers.push(resolve);
  });

  clearTimeout(autosaveTimer);

  autosaveTimer = window.setTimeout(() => {
    runPendingAutosave();
  }, 1500);

  return promise;
}

async function flushAutosave() {
  if (pendingAutosaveResolvers.length > 0) {
    await runPendingAutosave();
  }

  await autosaveInFlight;

  // If edits queued another debounced save while a previous request was
  // running, flush that save too before publishing.
  if (pendingAutosaveResolvers.length > 0) {
    await runPendingAutosave();
    await autosaveInFlight;
  }

  return currentInvoiceId;
}

[
  descriptionInput,
  amountInput,
  currencySelect,
  dueDateInput,
  countryCodeSelect,
  clientPhoneLocalInput,
  clientEmailInput,
].forEach((element) => {
  if (!element) return;

  element.addEventListener('input', scheduleAutosave);
  element.addEventListener('change', scheduleAutosave);
});

if (feePayerInput) {
  feePayerInput.addEventListener('change', () => {
    updateFeePayerHint();
    scheduleAutosave();
  });
}

const customReminderMessage = document.getElementById(
  'custom-reminder-message'
);

if (customReminderMessage) {
  customReminderMessage.addEventListener('input', scheduleAutosave);
  customReminderMessage.addEventListener('change', scheduleAutosave);
}

// ==================== RESET FORM ====================

function resetInvoiceForm() {
  clearTimeout(autosaveTimer);
  autosaveTimer = null;

  // Do not let an old form's queued saves create or update a draft after reset.
  pendingAutosaveResolvers.splice(0).forEach((resolve) => resolve(null));

  currentStep = 0;
  currentInvoiceId = null;
  isPublished = false;

  api.setCurrentInvoiceId(null);

  if (descriptionInput) descriptionInput.value = '';
  if (amountInput) amountInput.value = '';
  if (currencySelect) currencySelect.value = 'NGN';

  setDefaultDueDate();

  if (countryCodeSelect) countryCodeSelect.value = '+234';
  if (clientPhoneLocalInput) clientPhoneLocalInput.value = '';
  if (clientEmailInput) clientEmailInput.value = '';

  if (feePayerInput) feePayerInput.value = 'default';
  updateFeePayerHint();

  if (autoRemindToggle) autoRemindToggle.checked = false;
  if (reminderOptions) reminderOptions.style.display = 'none';

  // Reset the chips so active channels are on and disabled ones are off.
  applyChannelFlags();

  presetChips.forEach((chip) => chip.classList.remove('active'));

  document
    .querySelector('.chip.preset[data-preset="gentle"]')
    ?.classList.add('active');

  document.querySelectorAll('.manual-date-row').forEach((row) => row.remove());

  document.querySelector('.schedule-tabs .tab[data-mode="auto"]')?.click();

  if (descriptionCounter && descriptionInput) {
    descriptionCounter.textContent =
      `${maxDescriptionLength - descriptionInput.value.length} characters remaining`;
  }

  if (shareLinkEl) {
    shareLinkEl.textContent = '';
    delete shareLinkEl.dataset.fullUrl;
    shareLinkEl.onclick = null;
  }

  if (copyBtn) copyBtn.disabled = false;

  if (nextBtn) nextBtn.disabled = false;

  updateStepper();
  updatePreview();

  window.scrollTo({ top: 0, behavior: 'smooth' });
}

// ==================== PUBLISH INVOICE ====================

async function publishInvoice() {
  if (isPublishing || isPublished) return;

  if (!validateStep(0)) {
    currentStep = 0;
    updateStepper();
    return;
  }

  isPublishing = true;
  updateStepper();

  try {
    showToast('Saving your invoice...');

    // Wait for the latest debounced or in-flight draft save.
    let draftId = await flushAutosave();

    // If no autosave has created a draft yet, create one now.
    if (!draftId) {
      draftId = await saveDraftNow();
    }

    if (!draftId) {
      throw new Error('Could not save the invoice draft.');
    }

    // Publishing makes the invoice available to the customer.
    // Payment initialization must happen separately when the customer pays.
    const published = await api.publishInvoice(draftId);
    const publishedId = getInvoiceId(published) || draftId;

    currentInvoiceId = publishedId;
    api.setCurrentInvoiceId(publishedId);
    isPublished = true;

    // Prefer a canonical URL supplied by the backend.
    // Fall back to the existing /i/{shortId} URL convention.
    let invoiceUrl =
      published.invoice_url ||
      published.payment_url ||
      published.public_url ||
      '';

    if (invoiceUrl && !/^https?:\/\//i.test(invoiceUrl)) {
      invoiceUrl = new URL(invoiceUrl, window.location.origin).href;
    }

    if (!invoiceUrl) {
      const shortId = publishedId.replace(/^inv_/, '');
      invoiceUrl = `${window.location.origin}/i/${encodeURIComponent(shortId)}`;
    }

    if (shareLinkEl) {
      setDisplayLink(shareLinkEl, invoiceUrl);
    }

    if (shareModal) {
      shareModal.classList.add('open');
    }

    // Save reminder settings separately. A reminder-save failure must not
    // turn a successfully published invoice into a reported publish failure.
    if (autoRemindToggle?.checked) {
      try {
        const reminderResponse = await authFetch(
          `${api.BACKEND_URL}/api/reminders/invoice/${encodeURIComponent(publishedId)}`,
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(collectReminderPayload()),
          }
        );

        if (!reminderResponse.ok) {
          console.error(
            'Invoice published, but reminder settings could not be saved:',
            reminderResponse.status
          );
          showToast('Invoice published, but reminders could not be saved.');
          return;
        }
      } catch (reminderError) {
        console.error(
          'Invoice published, but reminder settings could not be saved:',
          reminderError
        );
        showToast('Invoice published, but reminders could not be saved.');
        return;
      }
    }

    showToast('Invoice published successfully!');
  } catch (error) {
    console.error('Publish failed:', error);

    alert(
      'Failed to publish the invoice. Your draft may still be saved. Please try again.'
    );
  } finally {
    isPublishing = false;
    updateStepper();
  }
}

// ==================== MODAL ACTIONS ====================


if (modalClose) {
  modalClose.addEventListener('click', () => {
    shareModal?.classList.remove('open');
    resetInvoiceForm();
  });
}

if (copyBtn) {
  copyBtn.addEventListener('click', async () => {
    const link = shareLinkEl?.dataset.fullUrl || '';

    if (!link) {
      showToast('No invoice link is available to copy.');
      return;
    }

    try {
      await navigator.clipboard.writeText(link);

      const originalText = copyBtn.textContent;
      copyBtn.textContent = 'Copied!';
      copyBtn.disabled = true;

      window.setTimeout(() => {
        copyBtn.textContent = originalText;
        copyBtn.disabled = false;
      }, 2000);
    } catch (error) {
      console.error('Could not copy invoice link:', error);
      showToast('Could not copy the link. Please copy it manually.');
    }
  });
}

if (shareWhatsapp) {
  shareWhatsapp.addEventListener('click', () => {
    const link = shareLinkEl?.dataset.fullUrl || '';

    if (!link) {
      showToast('No invoice link is available to share.');
      return;
    }

    const message = `Hi! Here's your invoice: ${link}`;
    const whatsappUrl = `https://wa.me/?text=${encodeURIComponent(message)}`;

    window.open(whatsappUrl, '_blank', 'noopener,noreferrer');

    shareModal?.classList.remove('open');
    resetInvoiceForm();
  });
}

// ==================== REMINDER MODAL ====================

if (reminderModalClose) {
  reminderModalClose.addEventListener('click', () => {
    reminderModal?.classList.remove('open');
  });
}

if (cancelReminderBtn) {
  cancelReminderBtn.addEventListener('click', () => {
    reminderModal?.classList.remove('open');
  });
}

if (saveReminderBtn) {
  saveReminderBtn.addEventListener('click', () => {
    // This preserves the existing modal interaction. The invoice's reminder
    // configuration is saved through the publish flow above.
    reminderModal?.classList.remove('open');
    showToast('Reminder settings updated.');
  });
}

// ==================== INIT ====================

async function initializeInvoicePage() {
  // Apply the channel flags before anything else, so the chips are
  // in their correct state before the first autosave or payload build.
  applyChannelFlags();

  if (feePayerInput) {
    feePayerInput.value = 'default';
  }

  setDefaultDueDate();
  updateStepper();
  updatePreview();
  updateFeePayerHint();

  if (reminderOptions) {
    reminderOptions.style.display = autoRemindToggle?.checked ? 'block' : 'none';
  }

  await loadUserProfile();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initializeInvoicePage, {
    once: true,
  });
} else {
  initializeInvoicePage();
}