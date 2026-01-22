// PAYLA ACCOUNT RECOVERY
import { API_BASE } from './config.js';
const BACKEND_URL = API_BASE;

// -----------------------------
// DOM Elements
// -----------------------------
const steps = {
    identify: document.getElementById('step-identify'),
    verify: document.getElementById('step-verify'),
    reset: document.getElementById('step-reset'),
    success: document.getElementById('step-success')
};

const inputs = {
    email: document.getElementById('recovery-email'),
    code: document.querySelectorAll('.code-input'),
    newPassword: document.getElementById('new-password'),
    confirmPassword: document.getElementById('confirm-password')
};

const buttons = {
    backToLogin: document.getElementById('back-to-login'),
    continueIdentify: document.getElementById('continue-identify'),
    backToIdentify: document.getElementById('back-to-identify'),
    continueVerify: document.getElementById('continue-verify'),
    resendCode: document.getElementById('resend-code'),
    backToVerify: document.getElementById('back-to-verify'),
    continueReset: document.getElementById('continue-reset'),
    goToLogin: document.getElementById('go-to-login')
};

const displayElements = {
    verifyEmail: document.getElementById('verify-email-display'),
    countdown: document.getElementById('countdown'),
    strengthBar: document.querySelector('.strength-bar')
};

// -----------------------------
// State
// -----------------------------
let currentStep = 'identify';
let recoveryEmail = '';
let verificationCode = '';
let countdownInterval = null;
let remainingTime = 120; // 2 minutes

// -----------------------------
// UTILITIES
// -----------------------------
function showStep(step) {
    Object.values(steps).forEach(el => el.classList.remove('active'));
    steps[step].classList.add('active');
    currentStep = step;
}

function showError(id, message) {
    const el = document.getElementById(id);
    if (!el) return;
    if (message && el.querySelector('span')) el.querySelector('span').textContent = message;
    el.style.display = 'flex';
    setTimeout(() => el.style.display = 'none', 5000);
}

function hideError(id) {
    const el = document.getElementById(id);
    if (el) el.style.display = 'none';
}

function isValidEmail(email) {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

function setButtonLoading(button, isLoading) {
    if (!button) return;
    const btnText = button.querySelector('.btn-text');
    const btnLoader = button.querySelector('.btn-loader');
    if (isLoading) {
        button.disabled = true;
        button.classList.add('loading');
        if (btnText) btnText.style.opacity = '0';
        if (btnLoader) btnLoader.style.display = 'flex';
    } else {
        button.disabled = false;
        button.classList.remove('loading');
        if (btnText) btnText.style.opacity = '1';
        if (btnLoader) btnLoader.style.display = 'none';
    }
}

// -----------------------------
// PASSWORD STRENGTH
// -----------------------------
function checkPasswordStrength(password) {
    let score = 0;
    const requirements = {
        length: password.length >= 8,
        uppercase: /[A-Z]/.test(password),
        lowercase: /[a-z]/.test(password),
        number: /\d/.test(password),
        special: /[!@#$%^&*(),.?":{}|<>]/.test(password)
    };
    Object.values(requirements).forEach(req => req && score++);
    let strength = 'weak';
    if (score >= 4) strength = 'strong';
    else if (score >= 3) strength = 'good';
    else if (score >= 2) strength = 'fair';
    displayElements.strengthBar?.setAttribute('data-strength', strength);
    Object.entries(requirements).forEach(([key, valid]) => {
        const el = document.querySelector(`.requirement[data-requirement="${key}"]`);
        if (el) el.classList.toggle('valid', valid);
    });
    return strength;
}

// -----------------------------
// COUNTDOWN
// -----------------------------
function startCountdown() {
    clearInterval(countdownInterval);
    remainingTime = 120;
    updateCountdownDisplay();
    countdownInterval = setInterval(() => {
        remainingTime--;
        updateCountdownDisplay();
        if (remainingTime <= 0) clearInterval(countdownInterval);
    }, 1000);
}

function updateCountdownDisplay() {
    if (!displayElements.countdown) return;
    const min = Math.floor(remainingTime / 60);
    const sec = remainingTime % 60;
    displayElements.countdown.textContent = `${min.toString().padStart(2, '0')}:${sec.toString().padStart(2, '0')}`;
    buttons.resendCode.disabled = remainingTime > 0;
}

// -----------------------------
// CODE INPUTS
// -----------------------------
function setupCodeInputs() {
    inputs.code.forEach((input, i) => {
        input.addEventListener('input', e => {
            const val = e.target.value.replace(/\D/g, '');
            e.target.value = val;
            if (val && i < inputs.code.length - 1) inputs.code[i + 1].focus();
            verificationCode = Array.from(inputs.code).map(input => input.value).join('');
            if (verificationCode.length === 6) verifyCode();
        });
        input.addEventListener('keydown', e => {
            if (e.key === 'Backspace' && !e.target.value && i > 0) inputs.code[i - 1].focus();
        });
        input.addEventListener('paste', e => {
            e.preventDefault();
            const paste = e.clipboardData.getData('text').replace(/\D/g, '').slice(0, 6);
            paste.split('').forEach((n, idx) => { if (inputs.code[idx]) inputs.code[idx].value = n; });
            verificationCode = Array.from(inputs.code).map(input => input.value).join('');
        });
    });
}

// -----------------------------
// STEP 1: FORGOT PASSWORD
// -----------------------------
buttons.continueIdentify?.addEventListener('click', async () => {
    const email = inputs.email.value.trim();
    if (!isValidEmail(email)) { showError('email-error', 'Enter a valid email'); return; }
    hideError('email-error');
    setButtonLoading(buttons.continueIdentify, true);
    try {
        const resp = await fetch(`${BACKEND_URL}/auth/forgot-password`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email })
        });
        const data = await resp.json();
        if (!resp.ok) { showError('email-error', data.detail || 'Error sending code'); return; }

        recoveryEmail = email;
        displayElements.verifyEmail.textContent = email;
        showStep('verify');
        startCountdown();
        inputs.code[0]?.focus();
    } catch (err) {
        console.error(err);
        showError('email-error', 'Failed to send verification code');
    } finally { setButtonLoading(buttons.continueIdentify, false); }
});

// -----------------------------
// STEP 2: VERIFY CODE
// -----------------------------
async function verifyCode() {
    if (verificationCode.length !== 6) { showError('code-error', 'Enter 6-digit code'); return; }
    try {
        const resp = await fetch(`${BACKEND_URL}/auth/verify-reset-code`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email: recoveryEmail, code: verificationCode })
        });
        const data = await resp.json();
                if (!resp.ok || data.valid !== true) {
            showError('code-error', data.message || 'Invalid code');
            return;
        }
        window.RESET_EMAIL = recoveryEmail;
        window.RESET_CODE = verificationCode;
        showStep('reset');
        setTimeout(() => inputs.newPassword?.focus(), 300);
    } catch (err) {
        console.error(err);
        showError('code-error', 'Invalid or expired code');
    }
}
buttons.continueVerify?.addEventListener('click', verifyCode);

// Resend code
buttons.resendCode?.addEventListener('click', async () => {
    if (!recoveryEmail) return;
    setButtonLoading(buttons.resendCode, true);
    try {
        await fetch(`${BACKEND_URL}/auth/forgot-password`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email: recoveryEmail })
        });
        startCountdown();
        inputs.code.forEach(input => input.value = '');
        verificationCode = '';
    } catch (err) {
        console.error(err);
        showError('code-error', 'Failed to resend code');
    } finally { setButtonLoading(buttons.resendCode, false); }
});

// -----------------------------
// STEP 3: RESET PASSWORD
// -----------------------------
function validatePasswords() {
    const pass = inputs.newPassword.value;
    const confirm = inputs.confirmPassword.value;
    if (checkPasswordStrength(pass) === 'weak') { showError('password-error', 'Choose a stronger password'); return false; }
    if (pass !== confirm) { showError('password-error', 'Passwords do not match'); return false; }
    hideError('password-error');
    return true;
}

buttons.continueReset?.addEventListener('click', async () => {
    if (!validatePasswords()) return;
    setButtonLoading(buttons.continueReset, true);
    try {
        const resp = await fetch(`${BACKEND_URL}/auth/reset-password`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                email: window.RESET_EMAIL,
                code: window.RESET_CODE,
                new_password: inputs.newPassword.value
            })
        });
        const data = await resp.json();
        if (!resp.ok) { showError('password-error', data.detail || 'Failed to reset password'); return; }
        showStep('success');
    } catch (err) {
        console.error(err);
        showError('password-error', 'Failed to reset password');
    } finally { setButtonLoading(buttons.continueReset, false); }
});

// -----------------------------
// PASSWORD TOGGLE
// -----------------------------
document.querySelectorAll('.password-toggle').forEach(btn => {
    btn.addEventListener('click', e => {
        const input = e.target.closest('.input-wrapper').querySelector('input');
        const icon = e.target.closest('button').querySelector('i');
        if (input.type === 'password') { input.type = 'text'; icon.className = 'fas fa-eye-slash'; }
        else { input.type = 'password'; icon.className = 'fas fa-eye'; }
    });
});

// -----------------------------
// NAVIGATION
// -----------------------------
buttons.backToLogin?.addEventListener('click', () => window.location.href = '/entry');
buttons.backToIdentify?.addEventListener('click', () => { showStep('identify'); clearInterval(countdownInterval); });
buttons.backToVerify?.addEventListener('click', () => showStep('verify'));
buttons.goToLogin?.addEventListener('click', () => window.location.href = '/entry');

// -----------------------------
// INIT
// -----------------------------
document.addEventListener('DOMContentLoaded', () => {
    setupCodeInputs();
    checkPasswordStrength('');
    setTimeout(() => inputs.email?.focus(), 300);
});