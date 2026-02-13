// dashboard_analytics.js
import { track } from "./web_analytics.js";

/* ──────────────────────────────
   PAGE VIEW & RETENTION
────────────────────────────── */
export function trackDashboardPageView() {
  track("dashboard_page_view", {
    page: "dashboard",
    timestamp: new Date().toISOString()
  });
}

export function trackDashboardSession() {
  track("dashboard_session", {
    session_id: generateSessionId(),
    timestamp: new Date().toISOString()
  });
}

export function trackDashboardEngagement(duration) {
  track("dashboard_engagement", {
    duration_seconds: duration,
    timestamp: new Date().toISOString()
  });
}

// Helper to generate a simple session ID
function generateSessionId() {
  return 'session_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
}

/* ──────────────────────────────
   HEARTBEAT (Every 30 seconds while user is on page)
────────────────────────────── */
export function trackDashboardHeartbeat(sessionId, activeTime) {
  track("dashboard_heartbeat", {
    session_id: sessionId,
    active_time_seconds: activeTime,
    timestamp: new Date().toISOString()
  });
}