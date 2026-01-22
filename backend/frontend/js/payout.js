// js/payout.js - Fully functional with History Modal
import { API_BASE } from './config.js';
class PayoutManager {
    constructor() {
        this.API_BASE = API_BASE;
        this.banks = [];
        this.currentAccount = null;
        this.earningsData = null;
        this.payouts = [];

        this.init();
    }

    async init() {
        this.setupEventListeners();
        this.setupScrollHandling();
        await this.loadAllData();
        this.setupPremiumInteractions();
        setInterval(() => this.checkPendingPayouts(), 5000);
    }

    // ==================== Helper ====================
    async authFetch(url, options = {}) {
        const headers = { ...this.getAuthHeaders(), ...(options.headers || {}) };
        const res = await fetch(url, { ...options, headers });

        if (res.status === 401) {
            this.showToast('Unauthorized — please log in again', 'error');
            window.location.href = '/entry'; // redirect
            throw new Error('Unauthorized');
        }

        return res;
    }

    // ==================== Auth ====================
    getAuthToken() {
        return localStorage.getItem('idToken') || '';
    }

    getAuthHeaders() {
        const token = this.getAuthToken();
        return token ? { 'Authorization': `Bearer ${token}` } : {};
    }
    

    // ==================== Data Loading ====================
    async loadAllData() {
        try {
            await Promise.all([
                this.loadEarnings(),
                this.loadPayoutAccount(),
                this.loadPayoutHistory(),
                this.loadBanks()
            ]);
            this.updatePayoutProgress();
        } catch (err) {
            console.error('Failed to load data:', err);
            this.showToast('Failed to load data. Please refresh.', 'error');
        }
    }

    async loadEarnings() {
        try {
            const res = await this.authFetch(`${this.API_BASE}/payout/earnings`);
            if (!res.ok) throw new Error(`Earnings ${res.status}`);

            const data = await res.json();
            this.earningsData = data;

            // 1. Update Figures with smooth transition
            const total = data.total_earnings || 0;
            const totalEl = document.getElementById('total-earnings');
            totalEl.textContent = `₦${this.formatAmount(total)} total`;
            
            // 2. Dynamic Status Handling
            const availableEl = document.getElementById('available-earnings');
            const instructionEl = document.getElementById('payout-instruction');
            
            availableEl.textContent = data.display_available;
            instructionEl.textContent = data.payout_instruction;

            // PREMIUM VISUAL FEEDBACK
            // We use the status text to determine the theme
            if (data.display_available.includes("Automated")) {
                availableEl.style.color = 'var(--neon-lime)'; 
                instructionEl.style.color = 'rgba(255,255,255,0.7)';
                instructionEl.classList.remove('pulse-warning');
            } else if (data.display_available.includes("Pending")) {
                availableEl.style.color = '#f59e0b'; // Premium Amber
                instructionEl.style.color = '#f59e0b';
            } else {
                availableEl.style.color = '#ff9e9e'; // Soft Coral Error
                instructionEl.style.color = '#ff9e9e';
                instructionEl.classList.add('pulse-warning'); // Adds a gentle premium glow
            }

            // 3. Update Payout Schedule
            if (document.getElementById('payout-schedule')) {
                document.getElementById('payout-schedule').textContent = data.next_payout;
            }
            
            if (document.getElementById('payout-destination')) {
                document.getElementById('payout-destination').textContent = `To ${data.payout_method}`;
            }

            this.uupdateNextPayoutInfo(data);

        } catch (err) {
            console.error('Earnings load failed:', err);
            document.getElementById('available-earnings').textContent = "Connection Error";
        }
    }


    async checkPendingPayouts() {
        // Find any payouts in the local list that are still 'pending'
        const pending = this.payouts.filter(p => p.status === 'pending');
        
        if (pending.length === 0) return;

        for (const payout of pending) {
            try {
                const res = await this.authFetch(`${this.API_BASE}/payout/transaction/${payout.reference}/payout_status`);
                if (!res.ok) continue;
                
                const data = await res.json();
                
                // If the status has changed in the backend
                if (data.payout_status === 'success') {
                    this.showToast(`₦${this.formatAmount(payout.amount)} successfully sent to your bank!`, 'success');
                    await this.loadAllData(); // Refresh everything to show the green 
                    this.openHistoryModal();
                } else if (data.payout_status === 'failed') {
                    this.showToast(`Payout of ₦${this.formatAmount(payout.amount)} failed. Please check bank details.`, 'error');
                    await this.loadAllData();
                }
            } catch (err) {
                console.error('Polling error:', err);
            }
        }
    }

    
    updatePayoutProgress() {
        const circle = document.getElementById('progress-circle');
        const percentText = document.getElementById('progress-percent');
        const countdownText = document.getElementById('countdown-text');

        // 'pending' = Payla is finalizing the record
        // 'settled' = Payla finished, but it's in the T+1 holding period
        const isProcessing = this.payouts.some(p => p.status === 'pending');
        const isSettling = this.payouts.some(p => p.status === 'settled');

        if (isProcessing) {
            circle.classList.add('pulse-active');
            percentText.textContent = "•••";
            countdownText.textContent = "Processing transaction...";
        } else if (isSettling) {
            circle.classList.add('pulse-active');
            circle.style.borderColor = 'var(--rose-gold)'; // Give it a "success-ish" color
            percentText.textContent = "90%";
            countdownText.textContent = "Settling to bank (Arriving tomorrow)...";
        } else if (this.payouts.length > 0) {
            circle.classList.remove('pulse-active');
            percentText.textContent = "100%";
            countdownText.textContent = "All earnings processed.";
        } else {
            circle.classList.remove('pulse-active');
            percentText.textContent = "0%";
            countdownText.textContent = "No earnings to process yet.";
        }
    }

    uupdateNextPayoutInfo(data) {
        const percentEl = document.getElementById('progress-percent');
        const circleEl = document.getElementById('progress-circle');
        const countdownEl = document.getElementById('countdown-text');

        if (!percentEl || !countdownEl) return;

        if (!data.is_automated) {
            percentEl.textContent = "0%";
            countdownEl.textContent = "Setup Required";
            return;
        }

        // Since it's T+1 (Automated), we simulate a progress towards the next 10:00 AM window
        const now = new Date();
        const hour = now.getHours();
        
        // Simple logic: if it's before 10 AM, we are close to payout. 
        // If after 10 AM, we are waiting for tomorrow.
        let progress;
        let text;

        if (hour < 10) {
            progress = Math.floor((hour / 10) * 100);
            text = "Processing for 10:00 AM";
        } else {
            progress = Math.floor(((hour - 10) / 14) * 100);
            text = "Next window: Tomorrow 10 AM";
        }

        percentEl.textContent = `${progress}%`;
        countdownEl.textContent = text;
        
        // Update CSS Variable for the progress ring if using conic-gradient
        if (circleEl) {
            circleEl.style.setProperty('--progress', `${progress}%`);
        }
    }
    async loadPayoutAccount() {
        try {
            const res = await fetch(`${this.API_BASE}/payout/account`, { headers: this.getAuthHeaders() });
            if (res.status === 404 || res.status === 401) {
                this.showAddAccountState();
                return;
            }
            if (!res.ok) throw new Error(`Account load ${res.status}`);
            const account = await res.json();
            if (!account || !account.account_number) {
                this.showAddAccountState();
                return;
            }
            this.currentAccount = account;
            this.showAccountState(account);
        } catch (err) {
            console.error('Account load error:', err);
            this.showAddAccountState();
        }
    }

    async loadPayoutHistory() {
        try {
            const res = await fetch(`${this.API_BASE}/payout/history`, { headers: this.getAuthHeaders() });
            if (!res.ok) throw new Error(`History ${res.status}`);
            const data = await res.json();
            this.payouts = data.history || [];
            this.renderPayouts();
        } catch (err) {
            console.error('Payout history failed:', err);
            const container = document.getElementById('payouts-list');
            container.innerHTML = '<div class="empty-state">No payout history yet</div>';
        }
    }

    async loadBanks() {
        try {
            const res = await fetch(`${this.API_BASE}/payout/banks`);
            if (!res.ok) throw new Error('Banks failed');
            const data = await res.json();
            this.banks = data.banks || [];
            this.renderBankOptions();
        } catch (err) {
            console.error('Banks load failed:', err);
            this.showToast('Failed to load banks', 'error');
        }
    }

    renderBankOptions() {
        const select = document.getElementById('bank-select');
        select.innerHTML = '<option value="">Choose your bank...</option>';
        this.banks.sort((a,b)=>a.name.localeCompare(b.name))
            .forEach(bank=>{
                const opt=document.createElement('option');
                opt.value=bank.code;
                opt.textContent=bank.name;
                select.appendChild(opt);
            });
    }

    renderPayouts() {
        const container = document.getElementById('payouts-list');
        container.innerHTML = '';
        
        if (this.payouts.length === 0) {
            container.innerHTML = '<div class="empty-state">No payouts yet</div>';
            return;
        }

        this.payouts.forEach(p => {
            const item = document.createElement('div');
            item.className = 'payout-item';
            const date = new Date(p.created_at || p.date).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });

            // Logic for Dynamic Status Labels and Classes
            let statusLabel = p.status.charAt(0).toUpperCase() + p.status.slice(1);
            let statusClass = 'status-failed';

            if (p.status === 'success') {
                statusClass = 'status-success';
            } else if (p.status === 'pending') {
                statusClass = 'status-pending';
                statusLabel = 'Processing';
            } else if (p.status === 'pending_settlement') {
                statusClass = 'status-pending'; // Keeps the orange/yellow color
                statusLabel = 'Settling (T+1)'; // Explains the bank delay clearly
            }

            item.innerHTML = `
                <div class="payout-meta">
                    <div class="payout-date">${date}</div>
                    <div class="payout-amount">₦${this.formatAmount(p.amount)}</div>
                </div>
                <div class="status-indicator ${statusClass}">
                    ${statusLabel}
                </div>
            `;
            container.appendChild(item);
        });
    }

    // ==================== UI States ====================
    showAccountState(account) {
        document.getElementById('account-name').textContent = account.account_name || 'Unknown';
        document.getElementById('account-info').textContent = `${account.bank_name} •••• ${account.account_number.slice(-4)}`;
        document.getElementById('verified-status').style.display = 'flex';
        document.getElementById('verification-footer').style.display = 'flex';
        document.getElementById('add-account-btn').style.display = 'none';
        document.getElementById('mobile-add-btn').style.display = 'none';
        document.getElementById('edit-account-btn').textContent='Edit';
    }
    showAddAccountState() {
        document.getElementById('account-name').textContent='No payout account set up';
        document.getElementById('account-info').textContent='Add your bank account to receive payments';
        document.getElementById('verified-status').style.display='none';
        document.getElementById('verification-footer').style.display='none';
        document.getElementById('add-account-btn').style.display='flex';
        document.getElementById('mobile-add-btn').style.display='flex';
        document.getElementById('edit-account-btn').textContent='Add';
    }

    // ==================== Modal & Form ====================
    setupEventListeners() {
        // Account modal
        document.getElementById('add-account-btn').onclick = () => this.openModal();
        document.getElementById('mobile-add-btn').onclick = () => this.openModal();
        document.getElementById('edit-account-btn').onclick = () => this.openModal();
        document.getElementById('modal-close').onclick = () => this.closeModal();
        document.getElementById('cancel-btn').onclick = () => this.closeModal();
        document.getElementById('save-account-btn').onclick = () => this.saveAccount();
        document.getElementById('bank-select').onchange = () => this.validateForm();
        document.getElementById('account-number').oninput = (e)=>this.handleAccountInput(e);
        document.getElementById('account-modal').onclick = (e)=>{if(e.target===document.getElementById('account-modal')) this.closeModal();};
        // History modal
        const historyBtn = document.getElementById('view-history-btn');
        const historyModal = document.getElementById('history-modal');
        const historyClose = document.getElementById('history-modal-close');

        if(historyBtn && historyModal && historyClose){
            historyBtn.onclick = (e)=>{e.preventDefault(); this.openHistoryModal();};
            historyClose.onclick = ()=>this.closeHistoryModal();
            historyModal.onclick = (e)=>{if(e.target===historyModal) this.closeHistoryModal();};
        }
    }

    openModal() {
        const modal = document.getElementById('account-modal');
        modal.classList.add('active');
        this.resetForm();
        
        if (this.currentAccount) {
            document.getElementById('bank-select').value = this.currentAccount.bank_code;
            document.getElementById('account-number').value = this.currentAccount.account_number;
            this.showPreview(this.currentAccount);
            this.validateForm(); // Enable the save button
        }
    }

    closeModal() {document.getElementById('account-modal').classList.remove('active'); this.resetForm();}

    resetForm() {
        document.getElementById('bank-select').value='';
        document.getElementById('account-number').value='';
        document.getElementById('account-preview').style.display='none';
        document.getElementById('save-account-btn').disabled=true;
    }

    handleAccountInput(e) {
        let value = e.target.value.replace(/\D/g,'').slice(0,10);
        e.target.value=value;
        if(value.length===10) this.validateForm();
        else document.getElementById('account-preview').style.display='none';
    }
    validateForm() {
        const bank = document.getElementById('bank-select').value;
        const number = document.getElementById('account-number').value;
        
        document.getElementById('save-account-btn').disabled = !(bank && number.length === 10);
    }

    async saveAccount() {
        const bankSelect = document.getElementById('bank-select');
        const bankCode = bankSelect.value;
        const accountNumber = document.getElementById('account-number').value;
        // --- THE FIX: Get the bank name from the selected option ---
        const bankName = bankSelect.options[bankSelect.selectedIndex].text;

        const btn = document.getElementById('save-account-btn');
        btn.disabled = true; 
        btn.textContent = 'Verifying...';

        try {
            const res = await fetch(`${this.API_BASE}/payout/account`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', ...this.getAuthHeaders() },
                body: JSON.stringify({ 
                    bank_code: bankCode, 
                    account_number: accountNumber,
                    bank_name: bankName, // Now this is defined!
                })
            });

            if (!res.ok) {
                const err = await res.json(); 
                throw new Error(err.detail || 'Failed to save account');
            }

            const account = await res.json();
            this.currentAccount = account;
            this.showAccountState(account);
            this.closeModal();
            this.showToast('Payout account saved successfully ✓');
        } catch (err) {
            console.error(err); 
            this.showToast(err.message || 'Failed to save account', 'error');
        } finally {
            btn.disabled = false; 
            btn.textContent = 'Save Account';
        }
    }
    showPreview(account){
        document.getElementById('preview-name').textContent=account.account_name;
        document.getElementById('preview-bank').textContent=account.bank_name;
        document.getElementById('account-preview').style.display='block';
        document.getElementById('save-account-btn').disabled=false;
    }

    // ==================== Payout History Modal ====================
    openHistoryModal(){
        const modal=document.getElementById('history-modal');
        const body=document.getElementById('history-modal-body');
        if(this.payouts.length===0){body.innerHTML='<div class="empty-state">No payout history yet</div>';}
        else{
            body.innerHTML='';
            this.payouts.forEach(p=>{
                const item=document.createElement('div'); item.className='payout-item';
                const date=new Date(p.created_at||p.date).toLocaleDateString('en-GB',{day:'numeric',month:'short',year:'numeric'});
                const statusClass=p.status==='success'?'status-success':p.status==='pending'?'status-pending':'status-failed';
                item.innerHTML=`
                    <div class="payout-meta">
                        <div class="payout-date">${date}</div>
                        <div class="payout-amount">₦${this.formatAmount(p.amount)}</div>
                    </div>
                    <div class="status-indicator ${statusClass}">
                        ${p.status.charAt(0).toUpperCase()+p.status.slice(1)}
                    </div>
                `;
                body.appendChild(item);
            });
        }
        modal.classList.add('active');
    }

    closeHistoryModal(){document.getElementById('history-modal').classList.remove('active');}

    // ==================== UI Helpers ====================
    formatAmount(amount){return new Intl.NumberFormat('en-NG').format(amount||0);}

    showToast(message,type='success'){
        const toast=document.getElementById('success-toast');
        const msgEl=document.getElementById('toast-message');
        msgEl.textContent=message;
        toast.className='elegant-toast';
        if(type==='error') toast.style.background='rgba(220,38,38,0.9)';
        else if(type==='info') toast.style.background='rgba(100,100,100,0.9)';
        else toast.style.background='var(--rose-gold)';
        toast.classList.add('show');
        setTimeout(()=>toast.classList.remove('show'),4000);
    }

    setupPremiumInteractions(){
        document.querySelectorAll('.ultra-glass').forEach(card=>{
            card.addEventListener('mouseenter',()=>{card.style.transform='translateY(-4px)';card.style.borderColor='rgba(232,180,184,0.3)';});
            card.addEventListener('mouseleave',()=>{card.style.transform='translateY(0)';card.style.borderColor='rgba(232,180,184,0.12)';});
        });
    }

    setupScrollHandling(){}
}

// Start when DOM is ready
document.addEventListener('DOMContentLoaded',()=>{
    if(!localStorage.getItem('idToken')){window.location.href='/login'; return;}
    new PayoutManager();
});
