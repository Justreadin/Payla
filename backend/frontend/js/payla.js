// js/payla.js
import {
  trackLandingView,
  trackNavOpened,
  trackNavClosed,
  trackClaimOpen,
  trackPricingToggle,
  trackFaqOpen,
  trackUsernameCheckStarted,
  trackUsernameCheckResult,
  trackUsernameCheckFailed,
} from "./payla_analytics.js";

import { BACKEND_BASE } from "./config.js";

/* ============================================================
   CONFIG
   ============================================================ */

const USERNAME_RULES = {
  min: 3,
  max: 20,
  pattern: /^[a-zA-Z0-9_-]+$/,
  debounceMs: 500,
};

/* ============================================================
   01. NAV
   ============================================================ */

function initNav() {
  const nav = document.getElementById("nav");
  const toggle = document.getElementById("navToggle");
  const menu = document.getElementById("mobile-menu");

  if (!nav) return;

  const onScroll = () => {
    nav.classList.toggle("is-scrolled", window.scrollY > 24);
  };
  onScroll();
  window.addEventListener("scroll", onScroll, { passive: true });

  if (toggle && menu) {
    const setOpen = (open) => {
      toggle.setAttribute("aria-expanded", String(open));
      menu.hidden = !open;
      document.body.classList.toggle("menu-open", open);
      document.body.style.overflow = open ? "hidden" : "";    

      nav.classList.toggle("is-menu-open", open);
      if (open) trackNavOpened("toggle");
      else trackNavClosed("toggle");
    };

    toggle.addEventListener("click", () => {
      const isOpen = toggle.getAttribute("aria-expanded") === "true";
      setOpen(!isOpen);
    });

    menu.querySelectorAll("a").forEach((a) =>
      a.addEventListener("click", () => setOpen(false))
    );

    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && toggle.getAttribute("aria-expanded") === "true") {
        setOpen(false);
      }
    });

    window.addEventListener("resize", () => {
      if (window.innerWidth > 880 && toggle.getAttribute("aria-expanded") === "true") {
        setOpen(false);
      }
    });
  }

  /* Smooth anchor scroll fallback */
  const prefersReduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  document.querySelectorAll('a[href^="#"]').forEach((a) => {
    const href = a.getAttribute("href");
    if (!href || href === "#") return;

    a.addEventListener("click", (e) => {
      const target = document.querySelector(href);
      if (!target) return;
      e.preventDefault();

      const headerOffset =
        parseInt(
          getComputedStyle(document.documentElement).getPropertyValue("--header-height")
        ) || 76;

      const top = target.getBoundingClientRect().top + window.scrollY - headerOffset - 16;
      window.scrollTo({ top, behavior: prefersReduced ? "auto" : "smooth" });

      if (history.replaceState) history.replaceState(null, "", href);
    });
  });
}

/* ============================================================
   02. HERO USERNAME FIELD
   ============================================================ */

function initHeroUsername() {
  const form = document.getElementById("heroClaimForm");
  const field = document.getElementById("heroClaimField");
  const input = document.getElementById("heroUsername");
  const feedback = document.getElementById("heroFeedback");
  const submitBtn = document.getElementById("heroClaimBtn");

  if (!form || !field || !input || !feedback || !submitBtn) return;

  let debounceTimer = null;
  let currentRequest = null;
  let isAvailable = false;
  let lastCheckedValue = "";

  const setState = (state) => {
    field.classList.remove("is-loading", "is-valid", "is-error");
    if (state) field.classList.add(state);
  };

  const setFeedback = (message, state) => {
    feedback.textContent = message || "";
    feedback.classList.remove("is-valid", "is-error");
    if (state === "valid") feedback.classList.add("is-valid");
    if (state === "error") feedback.classList.add("is-error");
  };

  const setAvailable = (value) => {
    isAvailable = value;
    submitBtn.disabled = !value;
  };

  const reset = () => {
    setState(null);
    setFeedback("", null);
    setAvailable(false);
  };

  const checkAvailability = async (username) => {
    if (currentRequest) {
      try { currentRequest.abort(); } catch (_) {}
    }
    const controller = new AbortController();
    currentRequest = controller;

    setState("is-loading");
    setFeedback("Checking availability…", null);
    trackUsernameCheckStarted(username);

    try {
      const res = await fetch(
        `${BACKEND_BASE}/api/onboarding/validate-username?username=${encodeURIComponent(username)}`,
        { signal: controller.signal }
      );
      const data = await res.json();

      if (input.value.trim().toLowerCase() !== username) return;

      if (data && data.available) {
        setState("is-valid");
        setFeedback(`${username} is available.`, "valid");
        setAvailable(true);
        lastCheckedValue = username;
        trackUsernameCheckResult(username, true);
      } else {
        setState("is-error");
        setFeedback(`@${username} is already taken. Try another.`, "error");
        setAvailable(false);
        trackUsernameCheckResult(username, false);
      }
    } catch (err) {
      if (err && err.name === "AbortError") return;
      setState("is-error");
      setFeedback("Couldn't check availability. Try again.", "error");
      setAvailable(false);
      trackUsernameCheckFailed("network");
    } finally {
      currentRequest = null;
    }
  };

  const handleInput = () => {
    const raw = input.value;
    const username = raw.trim().toLowerCase();

    if (raw !== username && document.activeElement === input) {
      const selStart = input.selectionStart;
      input.value = username;
      try { input.setSelectionRange(selStart, selStart); } catch (_) {}
    }

    if (debounceTimer) clearTimeout(debounceTimer);

    if (username.length === 0) return reset();

    if (username.length < USERNAME_RULES.min) {
      setState(null);
      setFeedback(`At least ${USERNAME_RULES.min} characters.`, "error");
      setAvailable(false);
      return;
    }
    if (username.length > USERNAME_RULES.max) {
      setState("is-error");
      setFeedback(`Up to ${USERNAME_RULES.max} characters.`, "error");
      setAvailable(false);
      return;
    }
    if (!USERNAME_RULES.pattern.test(username)) {
      setState("is-error");
      setFeedback("Letters, numbers, hyphens and underscores only.", "error");
      setAvailable(false);
      return;
    }

    if (username === lastCheckedValue && isAvailable) {
      setState("is-valid");
      setFeedback(`${username} is available.`, "valid");
      return;
    }

    setState(null);
    setFeedback("", null);
    setAvailable(false);

    debounceTimer = setTimeout(() => checkAvailability(username), USERNAME_RULES.debounceMs);
  };

  input.addEventListener("input", handleInput);

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const username = input.value.trim().toLowerCase();

    if (!isAvailable || username !== lastCheckedValue) {
      setState("is-error");
      setFeedback("Please choose an available username first.", "error");
      input.focus();
      return;
    }

    trackClaimOpen("hero", { hasUsername: true, usernameLength: username.length });

    /* Emit event — modal listens for it */
    document.dispatchEvent(
      new CustomEvent("payla:open-claim", {
        detail: { username, source: "hero" },
      })
    );
  });
}

/* ============================================================
   03. CLAIM TRIGGERS
   ============================================================ */

function initClaimTriggers() {
  document.querySelectorAll("[data-claim-trigger]").forEach((trigger) => {
    trigger.addEventListener("click", (e) => {
      e.preventDefault();

      const verified = getVerifiedUsername();
      trackClaimOpen("cta", {
        hasUsername: Boolean(verified),
        usernameLength: verified?.length || 0,
      });

      document.dispatchEvent(
        new CustomEvent("payla:open-claim", {
          detail: { username: verified, source: trigger.dataset.claimSource || "cta" },
        })
      );
    });
  });
}

function getVerifiedUsername() {
  const field = document.getElementById("heroClaimField");
  const input = document.getElementById("heroUsername");
  if (!field || !input) return null;
  if (!field.classList.contains("is-valid")) return null;
  const v = input.value.trim().toLowerCase();
  return v || null;
}

/* ============================================================
   04. PRICING TOGGLE
   ============================================================ */

function initPricingToggle() {
  const btns = document.querySelectorAll(".pricing__toggle-btn");
  const amounts = document.querySelectorAll(".plan-card__amount[data-monthly]");
  const periods = document.querySelectorAll(".plan-card__period[data-monthly]");
  const saving = document.querySelector('[data-billing-note="annual"]');

  if (!btns.length) return;

  const setBilling = (mode) => {
    btns.forEach((b) => {
      const active = b.dataset.billing === mode;
      b.classList.toggle("is-active", active);
      b.setAttribute("aria-selected", String(active));
    });

    amounts.forEach((el) => {
      const next = el.dataset[mode];
      if (next && el.textContent.trim() !== next) {
        el.style.transition = "opacity 180ms ease, transform 180ms ease";
        el.style.opacity = "0";
        el.style.transform = "translateY(-4px)";
        setTimeout(() => {
          el.textContent = next;
          el.style.opacity = "1";
          el.style.transform = "translateY(0)";
        }, 140);
      }
    });

    periods.forEach((el) => {
      if (el.dataset[mode]) el.textContent = el.dataset[mode];
    });

    if (saving) saving.hidden = mode !== "annual";

    trackPricingToggle(mode);
  };

  btns.forEach((b) => b.addEventListener("click", () => setBilling(b.dataset.billing)));

  const initial = document.querySelector(".pricing__toggle-btn.is-active");
  if (initial) {
    /* Set text without firing analytics on load */
    const mode = initial.dataset.billing;
    amounts.forEach((el) => {
      if (el.dataset[mode]) el.textContent = el.dataset[mode];
    });
    periods.forEach((el) => {
      if (el.dataset[mode]) el.textContent = el.dataset[mode];
    });
    if (saving) saving.hidden = mode !== "annual";
  }
}

/* ============================================================
   05. FAQ
   ============================================================ */

function initFaq() {
  const items = document.querySelectorAll(".faq__item");
  if (!items.length) return;

  items.forEach((item) => {
    item.addEventListener("toggle", () => {
      if (!item.open) return;
      items.forEach((other) => {
        if (other !== item && other.open) other.open = false;
      });
      const q = item.querySelector("summary")?.textContent?.trim() || "";
      trackFaqOpen(q);
    });
  });
}

/* ============================================================
   06. SCROLL REVEAL
   ============================================================ */

function initScrollReveal() {
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  if (!("IntersectionObserver" in window)) return;

  const selectors = [
    ".section-head",
    ".hero__content",
    ".hero__visual",
    ".problem__headline",
    ".problem__copy",
    ".problem__quotes",
    ".problem__resolution",
    ".product__block-copy",
    ".product__block-visual",
    ".product__analytics-copy",
    ".screen-frame--analytics",
    ".layla__copy",
    ".layla__visual",
    ".how__step",
    ".trust__head",
    ".trust__flow",
    ".trust__points",
    ".pricing__toggle",
    ".plan-card",
    ".founding",
    ".faq__item",
    ".final-cta__title",
    ".final-cta__lines",
    ".final-cta .btn",
  ].join(",");

  const candidates = document.querySelectorAll(selectors);
  if (!candidates.length) return;

  /* Stagger grids */
  [".how__step", ".plan-card", ".faq__item"].forEach((sel) => {
    document.querySelectorAll(sel).forEach((el, i) => {
      const mod = Math.min(i, 3);
      if (mod > 0) el.classList.add(`reveal--delay-${mod}`);
    });
  });

  candidates.forEach((el) => el.classList.add("reveal"));

  const obs = new IntersectionObserver(
    (entries, o) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("is-visible");
          o.unobserve(entry.target);
        }
      });
    },
    { rootMargin: "0px 0px -10% 0px", threshold: 0.08 }
  );

  candidates.forEach((el) => obs.observe(el));
}

/* ============================================================
   07. INIT
   ============================================================ */

function init() {
  trackLandingView();

  const safe = (label, fn) => {
    try { fn(); } catch (e) { console.error(`[Payla] ${label}:`, e); }
  };

  safe("nav", initNav);
  safe("hero username", initHeroUsername);
  safe("claim triggers", initClaimTriggers);
  safe("pricing", initPricingToggle);
  safe("faq", initFaq);
  safe("reveal", initScrollReveal);

  document.documentElement.classList.add("payla-ready");
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}