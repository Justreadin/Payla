// PAYLA ENTRY/AUTH - PREMIUM AUTHENTICATION FLOW
import { signInWithEmailAndPassword } from "https://www.gstatic.com/firebasejs/12.5.0/firebase-auth.js";
import { auth } from './firebasesdk.js';
import { BACKEND_BASE } from './config.js';

// Global Production Mute
if (window.location.hostname === 'payla.ng') {
    const noOp = () => {};
    console.log = noOp;
    console.info = noOp;
    console.debug = noOp;
    console.warn = noOp; 
    // We leave console.error active so you can still see if the site crashes
}

// Configuration
const BACKEND_URL = BACKEND_BASE;

// DOM Elements
const steps = {
    email: document.getElementById('stepEmail'),
    login: document.getElementById('stepLogin'),
    signup: document.getElementById('stepSignup'),
    confirmation: document.getElementById('stepConfirmation'),
    success: document.getElementById('stepSuccess')
};

const inputs = {
    email: document.getElementById('emailInput'),
    loginEmail: document.getElementById('loginEmail'),
    loginPass: document.getElementById('loginPassword'),
    signupName: document.getElementById('signupName'),
    signupEmail: document.getElementById('signupEmail'),
    signupPass: document.getElementById('signupPassword'),
    confirmationEmail: document.getElementById('confirmationEmail')
};

const btns = {
    continueEmail: document.getElementById('continueEmail'),
    continueLogin: document.getElementById('continueLogin'),
    continueSignup: document.getElementById('continueSignup'),
    resend: document.getElementById('resendEmail'),
    backToEmailFromLogin: document.getElementById('backToEmailFromLogin'),
    backToEmailFromSignup: document.getElementById('backToEmailFromSignup'),
    goToOnboarding: document.getElementById('goToOnboarding')
};

// -----------------------------
// UTILITIES
// -----------------------------

// Show only one step with smooth transition
function showStep(key) {
    Object.entries(steps).forEach(([name, el]) => {
        if (name === key) {
            el.classList.remove('hidden');
            setTimeout(() => el.classList.add('active'), 50);
        } else {
            el.classList.remove('active');
            setTimeout(() => el.classList.add('hidden'), 200);
        }
    });
}

// Email validation
function isValidEmail(email) {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

// Show button loading state
function setButtonLoading(button, isLoading) {
    if (!button) return;
    
    const btnText = button.querySelector('.btn-text');
    const btnLoader = button.querySelector('.btn-loader');

    if (isLoading) {
        button.disabled = true;
        if (btnText) btnText.style.opacity = '0';
        if (btnLoader) btnLoader.style.display = 'flex';
    } else {
        button.disabled = false;
        if (btnText) btnText.style.opacity = '1';
        if (btnLoader) btnLoader.style.display = 'none';
    }
}

// Show and hide error messages
function showError(id, message) {
    const el = document.getElementById(id);
    if (!el) return;
    
    if (message && el.querySelector('span')) {
        el.querySelector('span').textContent = message;
    }
    el.style.display = 'flex';
    setTimeout(() => (el.style.display = 'none'), 5000);
}

function hideError(id) {
    const el = document.getElementById(id);
    if (el) el.style.display = 'none';
}

// -----------------------------
// BACKEND API CALLS
// -----------------------------

async function checkEmail(email) {
    try {
        const res = await fetch(`${BACKEND_URL}/api/auth/check-email`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email })
        });

        if (!res.ok) throw new Error('Network error');

        const data = await res.json();
        return data.exists;
    } catch (err) {
        console.error(err);
        throw new Error('Network error. Try again.');
    }
}

// Polling for verification
let verificationInterval = null;

async function startEmailPolling(email) {
    verificationInterval = setInterval(async () => {
        try {
            const res = await fetch(`${BACKEND_URL}/api/auth/check-email-verified?email=${encodeURIComponent(email)}`);
            const data = await res.json();

            if (data.verified) {
                clearInterval(verificationInterval);
                showStep('success');

                if (data.user) {
                    localStorage.setItem('userData', JSON.stringify(data.user));
                }
            }
        } catch (err) {
            console.error('Verification check failed', err);
        }
    }, 5000);
}

function stopEmailPolling() {
    if (verificationInterval) {
        clearInterval(verificationInterval);
        verificationInterval = null;
    }
}

// -----------------------------
// STEP LOGIC
// -----------------------------

// Step 1: Email → Check
if (btns.continueEmail) {
    btns.continueEmail.addEventListener('click', async () => {
        const email = inputs.email.value.trim();

        if (!isValidEmail(email)) {
            showError('emailError', 'Please enter a valid email address');
            return;
        }

        hideError('emailError');
        setButtonLoading(btns.continueEmail, true);

        try {
            const exists = await checkEmail(email);

            inputs.loginEmail.value = email;
            inputs.signupEmail.value = email;
            inputs.confirmationEmail.textContent = email;

            if (exists) showStep('login');
            else showStep('signup');
        } catch (err) {
            showError('emailError', err.message);
        } finally {
            setButtonLoading(btns.continueEmail, false);
        }
    });
}

// Step 2: Login
if (btns.continueLogin) {
    btns.continueLogin.addEventListener('click', async () => {
        const email = inputs.loginEmail.value;
        const pass = inputs.loginPass.value;

        if (!pass) {
            showError('loginError', 'Please enter your password');
            return;
        }

        hideError('loginError');
        setButtonLoading(btns.continueLogin, true);

        try {
            const userCred = await signInWithEmailAndPassword(auth, email, pass);
            const idToken = await userCred.user.getIdToken();
            localStorage.setItem('idToken', idToken);

            const res = await fetch(`${BACKEND_URL}/api/auth/login-email`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ id_token: idToken })
            });
            if (!res.ok) {
                const errorData = await res.json().catch(() => ({}));
                throw new Error(errorData.message || 'Authentication failed');
            }
            const data = await res.json();
            if (!res.ok) {
                throw new Error(data.message || 'Login failed');
            }

            if (data.requires_verification) {
                showStep('confirmation');
                startEmailPolling(email);
            } else {
                localStorage.setItem('userData', JSON.stringify(data.user));

                if (data.user.onboarding_complete) {
                    window.location.href = 'dashboard';
                } else {
                    window.location.href = 'onboarding';
                }
            }
        } catch (err) {
            console.error(err);
            showError('loginError', 'Invalid email or password');
        } finally {
            setButtonLoading(btns.continueLogin, false);
        }
    });
}

// Step 3: Signup
if (btns.continueSignup) {
    btns.continueSignup.addEventListener('click', async () => {
        const name = inputs.signupName.value.trim();
        const email = inputs.signupEmail.value;
        const pass = inputs.signupPass.value;

        if (!name) {
            showError('passwordError', 'Enter your full name');
            return;
        }

        if (pass.length < 8) {
            showError('passwordError', 'Password must be at least 8 characters');
            return;
        }

        hideError('passwordError');
        setButtonLoading(btns.continueSignup, true);

        try {
            await fetch(`${BACKEND_URL}/api/auth/signup-email`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ full_name: name, email, password: pass })
            });

            const userCred = await signInWithEmailAndPassword(auth, email, pass);
            const idToken = await userCred.user.getIdToken();
            localStorage.setItem('idToken', idToken);

            showStep('confirmation');
            startEmailPolling(email);
        } catch (err) {
            console.error(err);
            showError('passwordError', 'Signup failed. Try again.');
        } finally {
            setButtonLoading(btns.continueSignup, false);
        }
    });
}

// Resend verification
if (btns.resend) {
    btns.resend.addEventListener('click', async () => {
        const email = inputs.confirmationEmail.textContent;

        setButtonLoading(btns.resend, true);

        try {
            await fetch(`${BACKEND_URL}/api/auth/resend-verification`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email })
            });

            const textEl = btns.resend.querySelector('.btn-text');
            textEl.textContent = 'Sent!';
            setTimeout(() => (textEl.textContent = 'Resend Email'), 2000);
        } catch (err) {
            console.error(err);
            showError('confirmationError', 'Failed to resend email');
        } finally {
            setButtonLoading(btns.resend, false);
        }
    });
}

// -----------------------------
// BACK BUTTONS
// -----------------------------
if (btns.backToEmailFromLogin) {
    btns.backToEmailFromLogin.addEventListener('click', () => showStep('email'));
}

if (btns.backToEmailFromSignup) {
    btns.backToEmailFromSignup.addEventListener('click', () => showStep('email'));
}

// Go to onboarding
if (btns.goToOnboarding) {
    btns.goToOnboarding.addEventListener('click', () => {
        window.location.href = '/onboarding';
    });
}

// -----------------------------
// ENTER KEY SUPPORT
// -----------------------------
function initializeEnterKeySupport() {
    const enterInputs = [
        inputs.email,
        inputs.loginPass,
        inputs.signupPass,
        inputs.signupName
    ];

    enterInputs.forEach(input => {
        if (input) {
            input.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') {
                    const active = document.querySelector('.form-step.active');
                    const btn = active.querySelector('.btn-primary');
                    if (btn && !btn.disabled) btn.click();
                }
            });
        }
    });
}

// -----------------------------
// INIT
// -----------------------------
function initializeApp() {
    initializeEnterKeySupport();

    // Hide all error messages initially
    document.querySelectorAll('.error-message').forEach(el => {
        el.style.display = 'none';
    });

    // Optional auto redirect if token exists
    if (localStorage.getItem('idToken')) {
        console.log("User already authenticated");
    }
}

document.addEventListener('DOMContentLoaded', initializeApp);
window.addEventListener('beforeunload', stopEmailPolling);

// Make showStep globally available for debugging
window.showStep = showStep;