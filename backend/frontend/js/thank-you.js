// thank-you.js - Payla Founding Creator Edition
import { API_BASE } from './config.js';

document.addEventListener("DOMContentLoaded", async () => {
    // ===== 1. CONFIG & GLOBALS =====
    const PRESELL_API_URL = API_BASE;
    const urlParams = new URLSearchParams(window.location.search);
    
    // Elements
    const elements = {
        reservedSpots: document.getElementById('reserved-spots'),
        stickySpots: document.getElementById('spots'),
        shareTwitter: document.getElementById('share-twitter'),
        copyLink: document.getElementById('copy-link'),
        shareCta: document.getElementById('share-cta'),
        toast: document.getElementById('success-toast'),
        voidEntry: document.querySelector('.void-entry'),
        countdown: document.getElementById('countdown') // Added for redirect
    };

    // Data from URL
    const emailParam = urlParams.get('email');

    // ===== 2. INITIALIZATION FLOW =====
    async function init() {
        handleVoidEntry();

        if (emailParam) {
            await fetchUserDetails(emailParam);
            cleanUrl();
        } else {
            loadFromStorage();
        }
        
        setupEventListeners();
        startRedirectTimer(); // Start the 30s countdown
    }

    // ===== NEW: REDIRECT LOGIC =====
    function startRedirectTimer() {
        let secondsLeft = 30;
        
        const interval = setInterval(() => {
            secondsLeft--;
            if (elements.countdown) {
                elements.countdown.textContent = secondsLeft;
            }

            if (secondsLeft <= 0) {
                clearInterval(interval);
                window.location.href = '/payla'; // Redirect to dashboard
            }
        }, 1000);
    }

    // ===== 3. DATA FETCHING =====
    async function fetchUserDetails(email) {
        try {
            const response = await fetch(`${PRESELL_API_URL}/presell/thank-you?email=${encodeURIComponent(email)}`);
            if (!response.ok) throw new Error("User not found");
            
            const data = await response.json();
            
            localStorage.setItem("payla_user_spot", data.current_spot);
            localStorage.setItem("payla_user_name", data.full_name);
            
            updateUI(data.current_spot);
        } catch (err) {
            console.error("Error fetching spot info:", err);
            updateUI(localStorage.getItem("payla_user_spot") || "127");
        }
    }

    function loadFromStorage() {
        const cachedSpot = localStorage.getItem("payla_user_spot");
        if (cachedSpot) {
            updateUI(cachedSpot);
        }
    }

    function updateUI(spotNumber) {
        if (elements.reservedSpots) elements.reservedSpots.textContent = spotNumber;
        if (elements.stickySpots) elements.stickySpots.textContent = spotNumber;
    }

    // ===== 4. SHARING LOGIC =====
    const getShareContent = () => {
        const spot = localStorage.getItem("payla_user_spot") || "127";
        const text = `I just secured my Payment Identity as Founding Creator #${spot} on Payla. 🚀\n\nOnly 500 spots exist. Get yours before they're gone:`;
        const url = `https://payla.ng`;
        return { text, url };
    };

    function shareToTwitter() {
        const { text, url } = getShareContent();
        const twitterUrl = `https://twitter.com/intent/tweet?text=${encodeURIComponent(text)}&url=${encodeURIComponent(url)}`;
        window.open(twitterUrl, '_blank');
    }

    function copyReferralLink() {
        const { url } = getShareContent();
        navigator.clipboard.writeText(url).then(() => {
            showToast();
        });
    }

    // ===== 5. UI HELPERS =====
    function handleVoidEntry() {
        setTimeout(() => {
            if (elements.voidEntry) {
                elements.voidEntry.style.opacity = '0';
                elements.voidEntry.style.pointerEvents = 'none';
                setTimeout(() => elements.voidEntry.remove(), 1000);
            }
        }, 2000);
    }

    function cleanUrl() {
        if (window.history.replaceState) {
            window.history.replaceState({}, document.title, window.location.pathname);
        }
    }

    function showToast() {
        if (!elements.toast) return;
        elements.toast.classList.add('show');
        setTimeout(() => {
            elements.toast.classList.remove('show');
        }, 3000);
    }

    function setupEventListeners() {
        elements.shareTwitter?.addEventListener('click', shareToTwitter);
        elements.copyLink?.addEventListener('click', copyReferralLink);
        elements.shareCta?.addEventListener('click', shareToTwitter);
    }

    init();
});