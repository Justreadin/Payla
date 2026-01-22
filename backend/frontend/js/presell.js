// presell.js
import { BACKEND_BASE } from './config.js';
const BACKEND_URL = BACKEND_BASE;
const USER_DATA_KEY = 'userData'; // LocalStorage key

document.addEventListener('DOMContentLoaded', async () => {
    const userDataRaw = localStorage.getItem(USER_DATA_KEY);
    const idToken = localStorage.getItem('idToken');

    if (!userDataRaw || !idToken) return;

    const user = JSON.parse(userDataRaw);

    try {
        const res = await fetch(`${BACKEND_URL}/api/presell/claim`, {
            method: 'POST',
            headers: { 
                'Authorization': `Bearer ${idToken}`
            }
        });

        const data = await res.json();

        if (!res.ok || !data.success) {
            console.warn('Presell claim failed:', data.message || data);
            return;
        }

        showPresellRewardModal(user);
        localStorage.setItem(USER_DATA_KEY, JSON.stringify(data.user));
    } catch (err) {
        console.error('Error claiming presell reward:', err);
    }
});

function showPresellRewardModal(user) {
    const modal = document.createElement('div');
    modal.className = 'presell-modal';
    modal.innerHTML = `
        <div class="presell-content">
            <button class="presell-close">✕</button>
            <h2>Welcome, Founding Creator! 🎉</h2>
            <p>You've successfully claimed your presell reward:</p>
            <ul>
                <li>💎 Payla Silver for 1 year</li>
                <li>🏅 Founding Creator Badge</li>
                <li>🚀 Early Access to features</li>
                <li>📩 Priority Support</li>
            </ul>
            <p>An email has been sent to <strong>${user.email}</strong></p>
            <button class="presell-ok">Got it!</button>
        </div>
    `;

    // Minimal styles
    const style = document.createElement('style');
    style.textContent = `
        .presell-modal { position: fixed; inset:0; background: rgba(0,0,0,0.85); display:flex; justify-content:center; align-items:center; z-index:9999; }
        .presell-content { background:#111; padding:30px; border-radius:20px; color:#fff; max-width:400px; text-align:center; position: relative; }
        .presell-content h2 { color:#39FF14; margin-bottom:16px; }
        .presell-content ul { text-align:left; padding-left:20px; margin-bottom:20px; }
        .presell-content button { margin-top:10px; padding:12px 20px; background:#39FF14; border:none; border-radius:12px; font-weight:bold; cursor:pointer; }
        .presell-close { position:absolute; top:10px; right:10px; background:none; border:none; font-size:18px; color:#fff; cursor:pointer; }
    `;
    document.head.appendChild(style);
    document.body.appendChild(modal);

    const closeModal = () => modal.remove();
    modal.querySelector('.presell-close').addEventListener('click', closeModal);
    modal.querySelector('.presell-ok').addEventListener('click', closeModal);
}
