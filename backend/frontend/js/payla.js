// payla.js - UI & Interaction Edition
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
        // Both buttons that should redirect to Favour's link
        seeHowItWorksBtns: document.querySelectorAll('#lock-year, #sticky-paid'),
        stickyCta: document.querySelector('.sticky-cta'),
        footer: document.querySelector('.footer')
    };

    const REDIRECT_URL = "https://payla.ng/@payla";

    // ===== STICKY CTA BEHAVIOR =====
    function setupStickyCTA() {
        if (!elements.stickyCta || !elements.footer) return;
        let ticking = false;
        let isHidden = false;

        function updateStickyCTA() {
            if (ticking) return;
            ticking = true;
            requestAnimationFrame(() => {
                const footerRect = elements.footer.getBoundingClientRect();
                // Hide CTA when footer is visible
                const shouldHide = footerRect.top <= window.innerHeight - elements.stickyCta.offsetHeight - 20;

                if (shouldHide !== isHidden) {
                    isHidden = shouldHide;
                    elements.stickyCta.style.opacity = shouldHide ? '0' : '1';
                    elements.stickyCta.style.transform = shouldHide ? 'translateX(-50%) translateY(100px)' : 'translateX(-50%) translateY(0)';
                    elements.stickyCta.style.pointerEvents = shouldHide ? 'none' : 'auto';
                }
                ticking = false;
            });
        }

        updateStickyCTA();
        window.addEventListener('scroll', updateStickyCTA, { passive: true });
        window.addEventListener('resize', updateStickyCTA, { passive: true });
    }

    // ===== INITIALIZATION =====
    function init() {
        // Track initial landing
        trackLandingView();

        // Header scroll effect
        window.addEventListener('scroll', () => { 
            elements.header?.classList.toggle('scrolled', window.scrollY > 40); 
        }, { passive: true });

        // [CREATE] MY PAYLA LINK Buttons
        elements.joinBtns.forEach(btn => btn.addEventListener('click', () => {
            trackContinueClick("hero_or_sticky");
            window.location.href = "/entry";
        }));

        // SEE HOW IT WORKS Buttons (Redirect to @favour)
        elements.seeHowItWorksBtns.forEach(btn => btn.addEventListener('click', () => {
            trackLockYearClick("hero_or_sticky"); // Keep analytics if desired
            window.location.href = REDIRECT_URL;
        }));

        setupStickyCTA();

        // Remove loading overlay
        setTimeout(() => {
            const voidEntry = document.querySelector('.void-entry');
            if (voidEntry) {
                voidEntry.style.opacity = '0';
                voidEntry.style.pointerEvents = 'none';
                setTimeout(() => voidEntry.remove(), 1000);
            }
        }, 2400);
    }

    init();
});