// web_analytics.js
import { initializeApp } from "https://www.gstatic.com/firebasejs/12.6.0/firebase-app.js";
import { getAnalytics, logEvent } from "https://www.gstatic.com/firebasejs/12.6.0/firebase-analytics.js";

const firebaseConfig = {
  apiKey: "AIzaSyCa9qT--u3f2moMgDiCXj2RnLSDTVvoZZs",
  authDomain: "payla-elite.firebaseapp.com",
  projectId: "payla-elite",
  storageBucket: "payla-elite.firebasestorage.app",
  messagingSenderId: "956501713797",
  appId: "1:956501713797:web:e5dcce5cfe11c0d0de1aec",
  measurementId: "G-M54H2BT7X2"
};

const app = initializeApp(firebaseConfig);
const analytics = getAnalytics(app);

/**
 * Low-level tracker
 * @param {string} event
 * @param {object} params
 */
export function track(event, params = {}) {
  try {
    logEvent(analytics, event, params);
  } catch (e) {
    console.warn("Analytics skipped:", e);
  }
}
