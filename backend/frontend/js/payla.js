// payla.js - FAST EDITION
import { 
  trackLandingView, 
  trackContinueClick, 
  trackLockYearClick 
} from "./payla_analytics.js";

document.addEventListener('DOMContentLoaded', () => {
    // ===== ELEMENTS =====
    const elements = {
        header: document.getElementById('header'),
        joinBtns: document.querySelectorAll('#join-waitlist, #sticky-free'),
        seeHowItWorksBtns: document.querySelectorAll('#lock-year, #sticky-paid'),
        stickyCta: document.querySelector('.sticky-cta'),
        footer: document.querySelector('.footer')
    };

    const REDIRECT_URL = "https://payla.ng/@payla";

    // ===== STICKY CTA BEHAVIOR =====
    function setupStickyCTA() {
        if (!elements.stickyCta || !elements.footer) return;
        let ticking = false;

        function updateStickyCTA() {
            if (ticking) return;
            ticking = true;
            requestAnimationFrame(() => {
                const footerRect = elements.footer.getBoundingClientRect();
                const shouldHide = footerRect.top <= window.innerHeight - elements.stickyCta.offsetHeight - 20;

                // Simple visibility toggle (Less math = Faster)
                elements.stickyCta.style.opacity = shouldHide ? '0' : '1';
                elements.stickyCta.style.pointerEvents = shouldHide ? 'none' : 'auto';
                // Reset transform slightly to avoid GPU glitches
                elements.stickyCta.style.transform = shouldHide ? 'translateX(-50%) translateY(20px)' : 'translateX(-50%) translateY(0)';
                
                ticking = false;
            });
        }

        window.addEventListener('scroll', updateStickyCTA, { passive: true });
        updateStickyCTA(); // Run once on load
    }

    // ===== INITIALIZATION =====
    function init() {
        // 1. Track Landing immediately
        trackLandingView();

        // 2. Setup Header Scroll (Lightweight)
        window.addEventListener('scroll', () => { 
            if(elements.header) {
                elements.header.classList.toggle('scrolled', window.scrollY > 40); 
            }
        }, { passive: true });

        // 3. Setup Buttons
        elements.joinBtns.forEach(btn => btn.addEventListener('click', () => {
            trackContinueClick("hero_or_sticky");
            window.location.href = "/entry";
        }));

        elements.seeHowItWorksBtns.forEach(btn => btn.addEventListener('click', () => {
            trackLockYearClick("hero_or_sticky");
            window.location.href = REDIRECT_URL;
        }));

        // 4. Setup Sticky CTA
        setupStickyCTA();

        // 🚨 REMOVED: The setTimeout(2400) "Void" block. 
        // The site will now be interactive instantly.
    }

    init();
});