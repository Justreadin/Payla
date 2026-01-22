import { InvoiceAPI } from './invoiceapi.js';
const api = InvoiceAPI;
import { BACKEND_BASE } from './config.js';

// ==================== DOM ELEMENTS ====================
const toggleButtons = document.querySelectorAll('.preview-toggle-btn');
const formSection = document.getElementById('form-section');
const previewSection = document.getElementById('preview-section');

const steps = document.querySelectorAll('.step');
const stepContents = document.querySelectorAll('.step-content');
const backBtn = document.getElementById('back-btn');
const nextBtn = document.getElementById('next-btn');
const sendFab = document.getElementById('send-fab');

const descriptionInput = document.getElementById('description');
const amountInput = document.getElementById('amount');
const currencySelect = document.getElementById('currency');
const dueDateInput = document.getElementById('due-date');
const countryCodeSelect = document.getElementById('country-code');
const clientPhoneLocalInput = document.getElementById('client-phone-local');
const clientEmailInput = document.getElementById('client-email');
const notesInput = document.getElementById('notes');

const autoRemindToggle = document.getElementById('auto-remind');
const reminderOptions = document.getElementById('reminder-options');

const toast = document.getElementById('draft-toast');
const shareModal = document.getElementById('share-modal');
const shareLinkEl = document.getElementById('share-link');
const modalClose = document.getElementById('modal-close');
const copyBtn = document.getElementById('copy-link');
const shareWhatsapp = document.getElementById('share-whatsapp');

// Reminder modal elements
const reminderModal = document.getElementById('reminder-settings-modal');
const reminderModalClose = document.getElementById('reminder-modal-close');
const cancelReminderBtn = document.getElementById('cancel-reminder');
const saveReminderBtn = document.getElementById('save-reminder');

// ==================== STATE ====================
let currentStep = 0;
let currentInvoiceId = null;
let userProfile = {};
let autosaveTimer;
let autosavePromise = null;
// ==================== HELPER ====================
async function authFetch(url, options = {}) {
  const token = localStorage.getItem('idToken');
  if (!token) {
    showToast('User not authenticated', 'error');
    window.location.href = '/entry';
    throw new Error('Unauthorized: No token');
  }

  const headers = { Authorization: `Bearer ${token}`, ...(options.headers || {}) };
  const res = await fetch(url, { ...options, headers });

  if (res.status === 401) {
    showToast('Unauthorized — please log in again', 'error');
    window.location.href = '/entry';
    throw new Error('Unauthorized');
  }

  return res;
}

function setDisplayLink(el, fullUrl) {
  if (!el || !fullUrl) return;

  const displayUrl = fullUrl.replace(/^https?:\/\//, '');

  el.textContent = displayUrl;
  el.dataset.fullUrl = fullUrl;
  el.style.cursor = 'pointer';

  el.onclick = () => {
    window.open(fullUrl, '_blank', 'noopener');
  };
}


// ==================== LOAD USER PROFILE ====================
async function loadUserProfile() {
  try {
    const backend = BACKEND_BASE;
    const res = await authFetch(`${backend}/api/profile/`);

    if (!res.ok) throw new Error(`Profile fetch failed: ${res.status}`);
    userProfile = await res.json();

    // Update preview elements
    const brandNameEl = document.getElementById('preview-brand-name');
    const handleEl = document.getElementById('preview-handle');
    const senderNameEl = document.getElementById('preview-sender-name');
    const senderPhoneEl = document.getElementById('preview-sender-phone');
    const senderEmailEl = document.getElementById('preview-sender-email');
    const poweredByEl = document.getElementById('preview-powered-by');
    const logoEl = document.getElementById('preview-logo-initials');

    if (brandNameEl) brandNameEl.textContent = userProfile.business_name || userProfile.full_name || 'Your Business';
    if (handleEl) handleEl.textContent = `payla.vip/@${userProfile.username || 'username'}`;
    if (senderNameEl) senderNameEl.textContent = userProfile.business_name || userProfile.full_name;
    if (senderPhoneEl)
      senderPhoneEl.textContent = userProfile.phone_number?.replace(/(\d{3})(\d{3})(\d{4})/, '$1 $2 $3') || '+234 801 234 5678';
    if (senderEmailEl) senderEmailEl.textContent = userProfile.email || 'you@payla.ng';
    if (poweredByEl) poweredByEl.textContent = userProfile.business_name || userProfile.full_name;

    // Logo handling
    if (userProfile.logo_url) {
      const logoUrl = userProfile.logo_url.startsWith('http')
        ? userProfile.logo_url
        : `${backend}${userProfile.logo_url}`;
      document.querySelectorAll('#preview-logo, .preview-logo').forEach((el) => {
        el.style.backgroundImage = `url(${logoUrl})`;
        const span = el.querySelector('span');
        if (span) span.style.display = 'none';
      });
    }

    // Fallback initials
    const initials = (userProfile.business_name || userProfile.full_name || 'YB')
      .split(' ')
      .map((w) => w[0])
      .join('')
      .slice(0, 2)
      .toUpperCase();
    if (logoEl) logoEl.textContent = initials;

  } catch (err) {
    console.error('Failed to load profile:', err);
  }
}

const descriptionCounter = document.getElementById('description-counter');
const maxDescriptionLength = 70;

descriptionInput.addEventListener('input', () => {
    // Trim excess characters just in case
    if (descriptionInput.value.length > maxDescriptionLength) {
        descriptionInput.value = descriptionInput.value.slice(0, maxDescriptionLength);
    }

    // Update remaining characters
    const remaining = maxDescriptionLength - descriptionInput.value.length;
    descriptionCounter.textContent = `${remaining} characters remaining`;
});


// ==================== MOBILE TOGGLE ====================
toggleButtons.forEach((button) => {
  button.addEventListener('click', () => {
    const target = button.getAttribute('data-target');
    toggleButtons.forEach((btn) => btn.classList.remove('active'));
    button.classList.add('active');
    if (formSection && previewSection) {
      formSection.style.display = target === 'form' ? 'flex' : 'none';
      previewSection.style.display = target === 'preview' ? 'flex' : 'none';
    }
  });
});

// ==================== STEPPER ====================
function updateStepper() {
  steps.forEach((step, i) => {
    step.classList.toggle('completed', i < currentStep);
    step.classList.toggle('active', i === currentStep);
  });

  stepContents.forEach((content, i) => {
    content.classList.toggle('active', i === currentStep);
  });

  if (backBtn) backBtn.style.visibility = currentStep === 0 ? 'hidden' : 'visible';
  if (nextBtn) nextBtn.textContent = currentStep === 2 ? 'Publish' : 'Next';
  if (sendFab) sendFab.classList.toggle('visible', currentStep === 2);
}

function validateStep(step) {
  if (step === 0) {
    const requiredFields = [
      { el: descriptionInput, name: "Description" },
      { el: amountInput, name: "Amount" },
      { el: dueDateInput, name: "Due Date" },
    ];

    let valid = true;
    requiredFields.forEach(({ el, name }) => {
      if (!el || !el.value.trim()) {
        el.classList.add("input-error");
        el.focus();
        alert(`${name} is required.`);
        valid = false;
      } else {
        el.classList.remove("input-error");
      }
    });

    return valid;
  }

  return true;
}

if (nextBtn)
  nextBtn.addEventListener('click', () => {
    if (currentStep === 0 && !validateStep(0)) return;
    if (currentStep < 2) {
      currentStep++;
      updateStepper();
    } else {
      publishInvoice();
    }
  });

if (backBtn)
  backBtn.addEventListener('click', () => {
    if (currentStep > 0) {
      currentStep--;
      updateStepper();
    }
  });

function cleanPhone(raw) {
  if (!raw) return "";

  let num = raw.replace(/\D/g, ""); // keep digits only

  // If number starts with 0 and length is 11 → trim first zero
  if (num.length === 11 && num.startsWith("0")) {
    num = num.substring(1);
  }

  // If user enters 10 digits starting with 0 → trim it
  if (num.length === 10 && num.startsWith("0")) {
    num = num.substring(1);
  }

  return num;
}


// ==================== REMINDER SYSTEM ====================
const channelChips = document.querySelectorAll('.channel-chips .chip');
const scheduleTabs = document.querySelectorAll('.schedule-tabs .tab');
const presetChips = document.querySelectorAll('.chip.preset');
const autoMode = document.getElementById('auto-mode');
const manualMode = document.getElementById('manual-mode');
const addDateBtn = document.querySelector('.add-date-btn');

channelChips.forEach(chip => chip.addEventListener('click', () => chip.classList.toggle('active')));
scheduleTabs.forEach(tab => {
  tab.addEventListener('click', () => {
    scheduleTabs.forEach(t => t.classList.remove('active'));
    tab.classList.add('active');
    autoMode.classList.toggle('hidden', tab.dataset.mode === 'manual');
    manualMode.classList.toggle('hidden', tab.dataset.mode === 'auto');
  });
});
presetChips.forEach(chip => chip.addEventListener('click', () => {
  presetChips.forEach(c => c.classList.remove('active'));
  chip.classList.add('active');
}));

addDateBtn?.addEventListener('click', () => {
  const row = document.createElement('div');
  row.className = 'manual-date-row';
  row.innerHTML = `
    <input type="datetime-local" class="manual-date-input">
    <button type="button" class="remove-date"><i class="fas fa-times"></i></button>
  `;
  document.querySelector('.manual-dates').insertBefore(row, addDateBtn);
});

document.addEventListener('click', e => {
  if (e.target.closest('.remove-date')) e.target.closest('.manual-date-row').remove();
});

autoRemindToggle.addEventListener("change", () => {
    const phone = cleanPhone(clientPhoneLocalInput.value);
    const email = clientEmailInput.value.trim();

    // User tries to enable reminders without contact
    if (autoRemindToggle.checked) {
        if (!phone && !email) {
            showToast("Add client contact info to enable reminders.");
            autoRemindToggle.checked = false;
            reminderOptions.style.display = "none";
            return;
        }

        // Valid → show options + update channels
        reminderOptions.style.display = "block";
        updateReminderChannels();
    } else {
        // Turning reminders OFF manually
        reminderOptions.style.display = "none";
    }

    // Always autosave after change
    scheduleAutosave();

    // Update preview
    updatePreview();
});

// ==================== COLLECT REMINDER DATA ====================
function collectReminderPayload() {
  const enabled = autoRemindToggle.checked;
  if (!enabled) return { auto_remind: false };

  const channels = Array.from(channelChips)
    .filter(c => c.classList.contains('active'))
    .map(c => c.dataset.channel);

  const isManual = document.querySelector('.schedule-tabs .tab.active').dataset.mode === 'manual';
  const customMessage = document.getElementById('custom-reminder-message')?.value.trim();

  if (isManual) {
    const dates = Array.from(document.querySelectorAll('.manual-date-input'))
      .map(input => input.value)
      .filter(v => v);
    return { auto_remind: true, method_priority: channels.length ? channels : ["whatsapp","sms","email"], custom_message: customMessage || null, manual_dates: dates };
  } else {
    const preset = document.querySelector('.chip.preset.active')?.dataset.preset || "gentle";
    return { auto_remind: true, method_priority: channels.length ? channels : ["whatsapp","sms","email"], preset, custom_message: customMessage || null };
  }
}

// ==================== PREVIEW ====================
function updatePreview() {
  const desc = descriptionInput?.value || '';
  const amount = amountInput?.value || '';
  const currency = currencySelect?.value || 'NGN';
  const symbol = currency === 'NGN' ? '₦' : '$';
  const countryCode = countryCodeSelect?.value || '+234';
  const phoneLocal = clientPhoneLocalInput?.value || '';
  const fullPhone = phoneLocal ? `${countryCode}${phoneLocal}` : '';

  const previewDesc = document.getElementById('preview-description');
  const previewAmount = document.getElementById('preview-amount');
  const previewDueDate = document.getElementById('preview-due-date');
  const previewDueIn = document.getElementById('preview-due-in');
  const summaryDesc = document.getElementById('summary-description');
  const summaryAmount = document.getElementById('summary-amount');
  const summaryDue = document.getElementById('summary-due-date');
  const summaryClient = document.getElementById('summary-client');

  if (previewDesc) previewDesc.textContent = desc;
  if (previewAmount) previewAmount.textContent = `${symbol}${Number(amount).toLocaleString()} ${currency}`;


  if (summaryDesc) summaryDesc.textContent = desc;
  if (summaryAmount) summaryAmount.textContent = `${symbol}${Number(amount).toLocaleString()} ${currency}`;
  if (summaryDue && dueDateInput?.value) {
    const date = new Date(dueDateInput.value);
    summaryDue.textContent = date.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric'
    });
}

  if (summaryClient) {
      const email = clientEmailInput?.value?.trim();
      summaryClient.textContent = fullPhone || email || 'Not provided';
  }
}

// Live bindings
[descriptionInput, amountInput, currencySelect, dueDateInput, countryCodeSelect, clientPhoneLocalInput].forEach(el => {
  if (el) el.addEventListener('input', updatePreview);
});
if (dueDateInput) dueDateInput.addEventListener('change', updatePreview);

// Default due date
if (dueDateInput) {
  const nextWeek = new Date();
  nextWeek.setDate(nextWeek.getDate()+7);
  dueDateInput.valueAsDate = nextWeek;
}


clientPhoneLocalInput.addEventListener("input", () => {
    clientPhoneLocalInput.value = cleanPhone(clientPhoneLocalInput.value);
    updateReminderChannels();
    updatePreview();
});

clientEmailInput.addEventListener("input", () => {
    updateReminderChannels();
    updatePreview();
});

function updateReminderChannels() {
  const phone = cleanPhone(clientPhoneLocalInput.value);
  const email = clientEmailInput.value.trim();

  const hasPhone = phone.length === 10;
  const hasEmail = email.length > 3;

  // User turned reminders off manually — do NOT auto-enable
  if (!autoRemindToggle.checked) return;

  // If neither phone nor email → disable reminders
  if (!hasPhone && !hasEmail) {
    autoRemindToggle.checked = false;
    reminderOptions.style.display = "none";
    return;
  }

  reminderOptions.style.display = "block";

  // Reset all channels
  const anyActive = Array.from(channelChips).some(c => c.classList.contains("active"));
  if (!anyActive) {
    channelChips.forEach(c => c.classList.remove("active"));
    if (phone) {
      document.querySelector('.chip[data-channel="whatsapp"]').classList.add("active");
      document.querySelector('.chip[data-channel="sms"]').classList.add("active");
    }
    if (email) {
      document.querySelector('.chip[data-channel="email"]').classList.add("active");
    }
  }
}

// ==================== AUTOSAVE ====================
function collectInvoiceData() {
  const countryCode = countryCodeSelect?.value || '+234';
  const phoneLocal = cleanPhone(clientPhoneLocalInput?.value || '');
  const fullPhone = phoneLocal ? `${countryCode}${phoneLocal}` : '';

  return {
    description: descriptionInput?.value,
    amount: parseFloat(amountInput?.value) || 0,
    currency: currencySelect?.value,
    due_date: dueDateInput?.value,
    client_phone: fullPhone,
    client_email: clientEmailInput?.value || null,
    notes: notesInput?.value || null,
    auto_remind: autoRemindToggle?.checked || false,
    reminder_settings: collectReminderPayload()
  };
}

function showToast(msg='Draft saved') {
  if (!toast) return;
  toast.textContent = msg;
  toast.classList.add('show');
  setTimeout(() => toast.classList.remove('show'), 3000);
}

function scheduleAutosave() {
  clearTimeout(autosaveTimer);

  autosavePromise = new Promise(async (resolve) => {
    autosaveTimer = setTimeout(async () => {
      const data = collectInvoiceData();
      try {
        if (currentInvoiceId) {
          await api.updateDraft(currentInvoiceId, data);
        } else {
          const draft = await api.saveDraft(data);
          currentInvoiceId = draft._id || draft.id;
          api.setCurrentInvoiceId(currentInvoiceId);
        }
        showToast();
        resolve(currentInvoiceId);
      } catch (err) {
        console.error('Autosave failed:', err);
        resolve(null);
      }
    }, 1500);
  });

  return autosavePromise;
}
// Bind autosave to form inputs
[descriptionInput, amountInput, currencySelect, dueDateInput, countryCodeSelect, clientPhoneLocalInput, clientEmailInput, notesInput].forEach(el => {
  if (el) el.addEventListener('input', scheduleAutosave);
  if (el) el.addEventListener('change', scheduleAutosave);
});

// ==================== RESET FORM ====================
function resetInvoiceForm() {
  // Reset stepper
  currentStep = 0;
  updateStepper();

  // Reset fields
  descriptionInput.value = '';
  amountInput.value = '';
  currencySelect.value = 'NGN';
  const nextWeek = new Date(); nextWeek.setDate(nextWeek.getDate()+7);
  dueDateInput.valueAsDate = nextWeek;
  countryCodeSelect.value = '+234';
  clientPhoneLocalInput.value = '';
  clientEmailInput.value = '';
  notesInput.value = '';
  autoRemindToggle.checked = true;
  if (reminderOptions) reminderOptions.style.display = 'block';

  // Reset channels
  document.querySelectorAll('.channel-chips .chip').forEach(c => c.classList.add('active'));

  // Reset presets
  document.querySelectorAll('.chip.preset').forEach(c => c.classList.remove('active'));
  const defaultPreset = document.querySelector('.chip.preset[data-preset="gentle"]');
  if (defaultPreset) defaultPreset.classList.add('active');

  // Reset manual dates
  document.querySelectorAll('.manual-date-row').forEach((row, idx) => {
    if (idx>0) row.remove();
  });
  const firstManualInput = document.querySelector('.manual-date-input');
  if (firstManualInput) firstManualInput.value = '';

  // Reset schedule tabs to auto
  document.querySelector('.schedule-tabs .tab[data-mode="auto"]')?.click();

  // Reset invoice ID
  currentInvoiceId = null;
  api.setCurrentInvoiceId(null);

  // Update preview
  updatePreview();
  window.scrollTo({top:0, behavior:'smooth'});
}

// ==================== PUBLISH INVOICE ====================
async function publishInvoice() {
  try {
    // Ensure draft is saved before publishing
    if (!currentInvoiceId) {
      showToast('Saving draft before publishing...');
      const savedId = await scheduleAutosave();
      if (!savedId) {
        alert('Failed to save draft. Cannot publish.');
        return;
      }
    } else {
      // Wait for any pending autosave
      if (autosavePromise) {
        await autosavePromise;
      }
    }

    // 1️⃣ Publish draft — backend returns PUBLISHED invoice
    const published = await api.publishInvoice(currentInvoiceId);

    // 2️⃣ Update currentInvoiceId to PUBLISHED ID
    currentInvoiceId = published.id || published._id;
    api.setCurrentInvoiceId(currentInvoiceId);

    // 3️⃣ Generate share link
    const shortId = currentInvoiceId.split('_')[1];
    const paylaLink = `${window.location.origin}/i/${shortId}`;

    if (shareLinkEl) {
      setDisplayLink(shareLinkEl, paylaLink);
    }

    if (shareModal) shareModal.classList.add('open');

    // 4️⃣ Save reminder settings for published invoice
    if (autoRemindToggle?.checked) {
      const reminderPayload = collectReminderPayload();
      await fetch(`${api.BACKEND_URL}/api/reminders/invoice/${currentInvoiceId}`, {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json', 
          Authorization: `Bearer ${localStorage.getItem('idToken')}` 
        },
        body: JSON.stringify(reminderPayload)
      });
    }

    showToast('Invoice published successfully!');
  } catch (err) {
    console.error('Publish failed:', err);
    alert('Failed to send invoice. Try again.');
  }
}

// ==================== MODAL ACTIONS ====================
if (sendFab) sendFab.addEventListener('click', publishInvoice);
if (modalClose) modalClose.addEventListener('click', () => { shareModal?.classList.remove('open'); resetInvoiceForm(); });

if (copyBtn) copyBtn.addEventListener('click', () => {
  navigator.clipboard.writeText(
    shareLinkEl?.dataset.fullUrl || ''
  ).then(() => {
    const txt = copyBtn.textContent;
    copyBtn.textContent = 'Copied!';
    setTimeout(() => copyBtn.textContent = txt, 2000);
  });
});


if (shareWhatsapp) shareWhatsapp.addEventListener('click', () => {
  const link = shareLinkEl?.dataset.fullUrl || '';
  const msg = `Hi! Here's your invoice: ${link}`;
  window.open(`https://wa.me/?text=${encodeURIComponent(msg)}`, '_blank');
  shareModal?.classList.remove('open');
  resetInvoiceForm();
});

// ==================== REMINDER MODAL ====================
if (reminderModalClose) reminderModalClose.addEventListener('click', ()=>reminderModal.classList.remove('open'));
if (cancelReminderBtn) cancelReminderBtn.addEventListener('click', ()=>reminderModal.classList.remove('open'));
if (saveReminderBtn) saveReminderBtn.addEventListener('click', ()=>{ reminderModal.classList.remove('open'); showToast('Reminder saved'); });

// ==================== INIT ====================
document.addEventListener('DOMContentLoaded', ()=>{
  loadUserProfile();
  updateStepper();
  updatePreview();
   reminderOptions.style.display = autoRemindToggle.checked ? 'block' : 'none';
});
