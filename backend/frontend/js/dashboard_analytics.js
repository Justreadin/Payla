// dashboard_analytics.js
// Dashboard-level analytics: page view, session, heartbeat, engagement.
// All events funnel through the low-level track() in web_analytics.js.

import { track } from "./web_analytics.js";


/* ──────────────────────────────
   HELPERS
────────────────────────────── */

function nowIso() {
  return new Date().toISOString();
}

function generateSessionId() {
  return 'session_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
}


/* ──────────────────────────────
   PAGE VIEW
────────────────────────────── */

export function trackDashboardPageView() {
  track("dashboard_page_view", {
    page: "dashboard",
    timestamp: nowIso()
  });
}


/* ──────────────────────────────
   SESSION
────────────────────────────── */

export function trackDashboardSession() {
  track("dashboard_session", {
    session_id: generateSessionId(),
    timestamp: nowIso()
  });
}


/* ──────────────────────────────
   HEARTBEAT — every 30s while user is on the page
────────────────────────────── */

export function trackDashboardHeartbeat(sessionId, activeTime) {
  track("dashboard_heartbeat", {
    session_id: sessionId,
    active_time_seconds: activeTime,
    timestamp: nowIso()
  });
}


/* ──────────────────────────────
   ENGAGEMENT — fired on leave
────────────────────────────── */

export function trackDashboardEngagement(duration) {
  track("dashboard_engagement", {
    duration_seconds: duration,
    timestamp: nowIso()
  });
}