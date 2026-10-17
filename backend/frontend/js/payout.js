// js/payout.js
import { API_BASE } from './config.js';

/* ============================================================
   CONFIG
   ============================================================ */
const CONFIG = {
    HISTORY_PAGE_SIZE: 4
};


/* ============================================================
   PAYOUT MANAGER
   ============================================================ */
class PayoutManager {
    constructor() {
        this.API_BASE = API_BASE;

        this.banks = [];
        this.currentAccount = null;
        this.earningsData = null;
        this.payouts = [];

        // History pagination state (used by the modal)
        this.historyCursor = null;
        this.historyHasMore = false;
        this.historyTotal = null;
        this.historyLoading = false;
        this.historyLoadedCount = 0;

        this.resolvedAccount = null;
        this.resolveRequestId = 0;
        this.resolveController = null;
        this.isSavingAccount = false;
        this.isLoadingHistory = false;
        this.toastTimeout = null;

        this.init();
    }

    async init() {
        this.setupEventListeners();

        await this.loadAllData();
    }

    /* ---------------------------------------------------------
       AUTHENTICATED REQUESTS
       --------------------------------------------------------- */

    async authFetch(url, options = {}) {
        const token = localStorage.getItem('idToken');

        if (!token) {
            window.location.href = '/entry';
            throw new Error('Unauthorized');
        }

        const headers = new Headers(options.headers || {});
        headers.set('Authorization', `Bearer ${token}`);

        const response = await fetch(url, {
            ...options,
            headers
        });

        if (response.status === 401) {
            window.location.href = '/entry';
            throw new Error('Unauthorized');
        }

        return response;
    }

    /* ---------------------------------------------------------
       INITIAL DATA LOADING
       --------------------------------------------------------- */

    async loadAllData() {
        await Promise.allSettled([
            this.loadEarnings(),
            this.loadPayoutAccount(),
            this.loadPayoutHistory(),
            this.loadBanks()
        ]);

        this.updatePayoutProgress();
    }

    /* ---------------------------------------------------------
       EARNINGS
       --------------------------------------------------------- */

    async loadEarnings() {
        try {
            const response = await this.authFetch(
                `${this.API_BASE}/payout/earnings`
            );

            if (!response.ok) {
                throw new Error(`Earnings request failed: ${response.status}`);
            }

            const data = await response.json();
            this.earningsData = data;

            const total = Number(data.total_earnings);
            const totalElement = document.getElementById('total-earnings');

            if (totalElement) {
                totalElement.textContent = `₦${this.formatAmount(
                    Number.isFinite(total) ? total : 0
                )}`;
            }

            const availableElement = document.getElementById('available-earnings');

            if (availableElement) {
                const available = Number(data.available_for_payout);

                availableElement.textContent = Number.isFinite(available)
                    ? `₦${this.formatAmount(available)}`
                    : '—';
            }

            const instructionElement =
                document.getElementById('payout-instruction');

            if (instructionElement) {
                instructionElement.textContent =
                    data.payout_instruction ||
                    'Settlement timing depends on payment-provider processing.';
            }

            const scheduleElement = document.getElementById('payout-schedule');

            if (scheduleElement) {
                scheduleElement.textContent =
                    data.next_payout || 'Schedule not confirmed';
            }

            this.updatePayoutDestination();
        } catch (error) {
            if (error.message === 'Unauthorized') return;

            console.error('Unable to load earnings:', error);

            const instructionElement =
                document.getElementById('payout-instruction');

            if (instructionElement) {
                instructionElement.textContent =
                    'Earnings information is temporarily unavailable.';
            }

            const totalElement = document.getElementById('total-earnings');
            if (totalElement) totalElement.textContent = 'Unavailable';

            const availableElement = document.getElementById('available-earnings');
            if (availableElement) availableElement.textContent = 'Unavailable';

            this.showToast('Could not load earnings. Please try again.', 'error');
        }
    }

    updatePayoutDestination() {
        const element = document.getElementById('payout-destination');
        if (!element) return;

        if (!this.currentAccount) {
            element.textContent = 'Add a payout account';
            return;
        }

        element.textContent = `To ${this.currentAccount.bank_name || 'your bank'}`;
    }

    /* ---------------------------------------------------------
       PAYOUT ACCOUNT
       --------------------------------------------------------- */

    async loadPayoutAccount() {
        try {
            const response = await this.authFetch(
                `${this.API_BASE}/payout/account`
            );

            if (!response.ok) {
                throw new Error(`Payout account request failed: ${response.status}`);
            }

            const account = await response.json();

            if (!account || !account.account_number) {
                this.currentAccount = null;
                this.showAddAccountState();
                return;
            }

            this.currentAccount = account;
            this.showAccountState(account);
        } catch (error) {
            if (error.message === 'Unauthorized') return;

            console.error('Unable to load payout account:', error);

            const accountInfo = document.getElementById('account-info');

            if (accountInfo) {
                accountInfo.textContent =
                    'Unable to load account details. Please retry.';
            }

            this.showToast('Could not load payout account. Please try again.', 'error');
        } finally {
            this.updatePayoutDestination();
            this.updatePayoutProgress();
        }
    }

    showAccountState(account) {
        const card = document.getElementById('account-card');
        const accountName = document.getElementById('account-name');
        const accountInfo = document.getElementById('account-info');
        const verifiedStatus = document.getElementById('verified-status');
        const verificationFooter = document.getElementById('verification-footer');
        const addButton = document.getElementById('add-account-btn');
        const editButton = document.getElementById('edit-account-btn');
        const mobileBtn = document.getElementById('mobile-account-btn');

        if (card) card.style.display = '';

        if (accountName) {
            accountName.textContent = account.account_name || 'Account holder';
        }

        if (accountInfo) {
            const number = account.account_number || '';
            const masked = number.length > 4
                ? `•••• ${number.slice(-4)}`
                : number;
            accountInfo.textContent =
                `${account.bank_name || 'Bank'} · ${masked}`;
        }

        if (verifiedStatus) {
            const verified = account.is_verified === true;

            verifiedStatus.innerHTML = `
                <i class="fas fa-shield-alt" aria-hidden="true"></i>
                <span>${verified ? 'Verified' : 'Verification unconfirmed'}</span>
            `;
            verifiedStatus.classList.toggle('unverified', !verified);
            verifiedStatus.style.display = 'inline-flex';
        }

        if (verificationFooter) {
            verificationFooter.innerHTML = `
                <i class="fas fa-circle-check" aria-hidden="true"></i>
                <span>${
                    account.is_verified === true
                        ? 'Your payout account has been verified.'
                        : 'The account verification status is not confirmed.'
                }</span>
            `;
            verificationFooter.style.display = 'flex';
        }

        if (addButton) addButton.style.display = 'none';
        if (editButton) editButton.style.display = '';
        if (mobileBtn) mobileBtn.textContent = 'Edit Account';
    }

    showAddAccountState() {
        const card = document.getElementById('account-card');
        const accountName = document.getElementById('account-name');
        const accountInfo = document.getElementById('account-info');
        const verifiedStatus = document.getElementById('verified-status');
        const verificationFooter = document.getElementById('verification-footer');
        const addButton = document.getElementById('add-account-btn');
        const editButton = document.getElementById('edit-account-btn');
        const mobileBtn = document.getElementById('mobile-account-btn');

        if (card) card.style.display = '';
        if (accountName) accountName.textContent = 'No payout account added';
        if (accountInfo) accountInfo.textContent = 'Add your bank details';

        if (verifiedStatus) {
            verifiedStatus.style.display = 'none';
            verifiedStatus.classList.remove('unverified');
        }

        if (verificationFooter) {
            verificationFooter.style.display = 'none';
        }

        if (addButton) addButton.style.display = '';
        if (editButton) editButton.style.display = 'none';
        if (mobileBtn) mobileBtn.textContent = 'Add Account';

        this.updatePayoutDestination();
        this.updatePayoutProgress();
    }

    /* ---------------------------------------------------------
       BANK LIST
       --------------------------------------------------------- */

    async loadBanks() {
        try {
            const response = await fetch(`${this.API_BASE}/payout/banks`);

            if (!response.ok) {
                throw new Error(`Bank list request failed: ${response.status}`);
            }

            const data = await response.json();
            this.banks = Array.isArray(data.banks) ? data.banks : [];

            this.renderBankOptions();
        } catch (error) {
            console.error('Unable to load banks:', error);

            const select = document.getElementById('bank-select');

            if (select) {
                select.innerHTML =
                    '<option value="">Banks unavailable. Retry later.</option>';
            }

            this.showToast('Could not load banks. Please try again.', 'error');
        }
    }

    renderBankOptions() {
        const select = document.getElementById('bank-select');
        if (!select) return;

        const previousValue = select.value;

        select.innerHTML = '<option value="">Select your bank</option>';

        this.banks.forEach(bank => {
            if (!bank || !bank.code || !bank.name) return;

            const option = document.createElement('option');
            option.value = String(bank.code);
            option.textContent = bank.name;

            select.appendChild(option);
        });

        if (
            previousValue &&
            [...select.options].some(option => option.value === previousValue)
        ) {
            select.value = previousValue;
        }
    }

    /* ---------------------------------------------------------
       ACCOUNT RESOLUTION
       --------------------------------------------------------- */

    invalidateAccountResolution() {
        this.resolveRequestId++;
        this.resolvedAccount = null;

        if (this.resolveController) {
            this.resolveController.abort();
            this.resolveController = null;
        }

        const preview = document.getElementById('account-preview');
        const saveButton = document.getElementById('save-account-btn');

        if (preview) preview.style.display = 'none';

        if (saveButton) {
            saveButton.disabled = true;
            saveButton.textContent = 'Save Account';
        }
    }

    handleAccountInput(event) {
        const input = event.target;
        input.value = input.value.replace(/\D/g, '').slice(0, 10);

        this.invalidateAccountResolution();

        if (
            input.value.length === 10 &&
            document.getElementById('bank-select')?.value
        ) {
            this.validateForm();
        }
    }

    async validateForm() {
        const bankCode = document.getElementById('bank-select')?.value;
        const accountNumber =
            document.getElementById('account-number')?.value || '';

        const button = document.getElementById('save-account-btn');
        const preview = document.getElementById('account-preview');

        if (!button || !preview) return;

        this.invalidateAccountResolution();

        if (!bankCode || !/^\d{10}$/.test(accountNumber)) return;

        const requestId = this.resolveRequestId;

        this.resolveController = new AbortController();
        button.textContent = 'Verifying…';

        try {
            const params = new URLSearchParams({
                bank: bankCode,
                account: accountNumber
            });

            const response = await this.authFetch(
                `${this.API_BASE}/payout/resolve?${params.toString()}`,
                { signal: this.resolveController.signal }
            );

            if (!response.ok) {
                let message = 'Unable to verify these account details.';

                try {
                    const error = await response.json();
                    message = error.detail || message;
                } catch {
                    /* Retain fallback */
                }

                throw new Error(message);
            }

            const data = await response.json();

            if (requestId !== this.resolveRequestId) return;

            if (
                document.getElementById('bank-select')?.value !== bankCode ||
                document.getElementById('account-number')?.value !== accountNumber
            ) {
                return;
            }

            if (!data.account_name) {
                throw new Error('The bank did not return an account name.');
            }

            this.resolvedAccount = {
                bank_code: bankCode,
                account_number: accountNumber,
                account_name: data.account_name,
                bank_name: data.bank_name || 'Unknown Bank'
            };

            this.showPreview(this.resolvedAccount);
            button.disabled = false;
        } catch (error) {
            if (error.name === 'AbortError') return;
            if (error.message === 'Unauthorized') return;

            if (requestId === this.resolveRequestId) {
                console.error('Account resolution failed:', error);
                this.showToast(
                    error.message || 'Account verification failed.',
                    'error'
                );
            }
        } finally {
            if (requestId === this.resolveRequestId) {
                button.textContent = 'Save Account';
                this.resolveController = null;
            }
        }
    }

    showPreview(account) {
        const preview = document.getElementById('account-preview');
        const name = document.getElementById('preview-name');
        const bank = document.getElementById('preview-bank');

        if (!preview || !name || !bank) return;

        name.textContent = account.account_name || '';
        bank.textContent = account.bank_name || '';
        preview.style.display = 'block';
    }

    /* ---------------------------------------------------------
       SAVE ACCOUNT
       --------------------------------------------------------- */

    async saveAccount() {
        if (this.isSavingAccount) return;

        const bankCode = document.getElementById('bank-select')?.value;
        const accountNumber =
            document.getElementById('account-number')?.value || '';

        const button = document.getElementById('save-account-btn');
        const resolved = this.resolvedAccount;

        if (
            !resolved ||
            resolved.bank_code !== bankCode ||
            resolved.account_number !== accountNumber
        ) {
            this.showToast(
                'Verify the current bank details before saving.',
                'error'
            );
            return;
        }

        this.isSavingAccount = true;

        if (button) {
            button.disabled = true;
            button.textContent = 'Saving…';
        }

        try {
            const response = await this.authFetch(
                `${this.API_BASE}/payout/account`,
                {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        bank_code: bankCode,
                        account_number: accountNumber
                    })
                }
            );

            if (!response.ok) {
                let message = 'Failed to save payout account.';

                try {
                    const error = await response.json();
                    message = error.detail || message;
                } catch {
                    /* Retain fallback */
                }

                throw new Error(message);
            }

            const account = await response.json();

            if (!account || !account.account_number) {
                throw new Error('The server returned an invalid account response.');
            }

            this.currentAccount = account;
            this.closeModal();
            this.showAccountState(account);
            this.updatePayoutDestination();
            this.updatePayoutProgress();

            this.showToast('Payout account saved successfully.');
        } catch (error) {
            if (error.message === 'Unauthorized') return;

            console.error('Unable to save payout account:', error);
            this.showToast(
                error.message || 'Failed to save payout account.',
                'error'
            );
        } finally {
            this.isSavingAccount = false;

            if (button) {
                button.textContent = 'Save Account';
                button.disabled = !this.resolvedAccount;
            }
        }
    }

    /* ---------------------------------------------------------
       RECENT PAYOUTS (main page grid)
       - Capped at CONFIG.HISTORY_PAGE_SIZE for a compact preview.
       - The full, paginated list lives in the history modal.
       --------------------------------------------------------- */

    async loadPayoutHistory() {
        if (this.isLoadingHistory) return;

        this.isLoadingHistory = true;

        const container = document.getElementById('payouts-list');

        if (container) {
            container.innerHTML =
                '<div class="empty-state">Loading transactions…</div>';
        }

        try {
            const params = new URLSearchParams({
                limit: String(CONFIG.HISTORY_PAGE_SIZE)
            });

            const response = await this.authFetch(
                `${this.API_BASE}/payout/history?${params.toString()}`
            );

            if (!response.ok) {
                throw new Error(`History request failed: ${response.status}`);
            }

            const data = await response.json();

            if (!Array.isArray(data.history)) {
                throw new Error('The server returned an invalid history response.');
            }

            // Cap on the client too — if the backend ignores ?limit,
            // we still only render HISTORY_PAGE_SIZE items in this grid.
            this.payouts = data.history.slice(0, CONFIG.HISTORY_PAGE_SIZE);
            this.renderPayouts();
        } catch (error) {
            if (error.message === 'Unauthorized') return;

            console.error('Unable to load transaction history:', error);

            if (container) {
                container.innerHTML =
                    '<div class="empty-state">Unable to load transactions. Please try again.</div>';
            }
        } finally {
            this.isLoadingHistory = false;
            this.updatePayoutProgress();
        }
    }

    renderPayouts() {
        const container = document.getElementById('payouts-list');
        if (!container) return;

        container.replaceChildren();

        if (!this.payouts.length) {
            container.innerHTML =
                '<div class="empty-state">No transactions yet</div>';
            return;
        }

        this.payouts.forEach(transaction => {
            container.appendChild(this.createHistoryItem(transaction));
        });
    }

    /* ---------------------------------------------------------
       PAYMENT / SETTLEMENT LABELS
       --------------------------------------------------------- */

    getPaymentStatusLabel(status) {
        const labels = {
            success: 'Payment successful',
            successful: 'Payment successful',
            failed: 'Payment failed',
            processing: 'Processing',
            pending: 'Pending',
            pending_settlement: 'Payment successful',
            settled: 'Payment successful',
            reversed: 'Reversed',
            abandoned: 'Abandoned'
        };

        return labels[String(status || 'processing').toLowerCase()]
            || 'Status unavailable';
    }

    getSettlementLabel(status) {
        const labels = {
            pending: 'Settlement pending',
            pending_settlement: 'Settlement pending',
            processing: 'Settlement processing',
            success: 'Settlement confirmed',
            successful: 'Settlement confirmed',
            settled: 'Settlement confirmed',
            failed: 'Settlement failed',
            reversed: 'Settlement reversed'
        };

        return labels[String(status || '').toLowerCase()]
            || 'Settlement status unavailable';
    }

    /* ---------------------------------------------------------
       HISTORY ITEM RENDERING
       --------------------------------------------------------- */

    createHistoryItem(transaction) {
        const item = document.createElement('article');
        item.className = 'payout-item';

        const rawDate =
            transaction.created_at || transaction.date || null;

        const dateValue = rawDate ? new Date(rawDate) : null;

        const dateLabel =
            dateValue && !Number.isNaN(dateValue.getTime())
                ? dateValue.toLocaleDateString('en-GB', {
                    day: 'numeric',
                    month: 'short',
                    year: 'numeric'
                })
                : 'Date unavailable';

        const amount = Number(transaction.amount);
        const safeAmount = Number.isFinite(amount) ? amount : 0;

        const sourceType = String(
            transaction.source_type || transaction.type || 'payment'
        ).toLowerCase();

        const sourceLabel =
            sourceType === 'invoice'
                ? 'Invoice payment'
                : sourceType === 'paylink'
                    ? 'Paylink payment'
                    : 'Payment';

        const paymentStatus = String(
            transaction.status || 'processing'
        ).toLowerCase();

        const isSuccessful =
            ['success', 'successful'].includes(paymentStatus);

        const statusClass = isSuccessful
            ? 'status-success'
            : paymentStatus === 'failed'
                ? 'status-failed'
                : 'status-pending';

        const transactionReference = String(
            transaction.reference ||
            transaction.paystack_reference ||
            ''
        ).trim();

        /* ----- Row 1: amount + status pill ----- */
        const topRow = document.createElement('div');
        topRow.className = 'payout-item__row';

        const amountEl = document.createElement('div');
        amountEl.className = 'payout-amount';
        amountEl.textContent = `₦${this.formatAmount(safeAmount)}`;

        const statusEl = document.createElement('div');
        statusEl.className = `status-indicator ${statusClass}`;
        statusEl.textContent = this.getPaymentStatusLabel(paymentStatus);

        topRow.append(amountEl, statusEl);
        item.appendChild(topRow);

        /* ----- Row 2: source + date ----- */
        const metaRow = document.createElement('div');
        metaRow.className = 'payout-item__row';

        const meta = document.createElement('div');
        meta.className = 'payout-meta';

        const sourceEl = document.createElement('span');
        sourceEl.className = 'payout-date';
        sourceEl.textContent = `${sourceLabel} · ${dateLabel}`;

        meta.appendChild(sourceEl);
        metaRow.appendChild(meta);
        item.appendChild(metaRow);

        /* ----- Description (only if it adds information) ----- */
        // Skip when the description is identical to the source label
        // (this is what was producing the duplicate "Invoice payment" line).
        if (
            transaction.description &&
            transaction.description.trim() !== sourceLabel
        ) {
            const description = document.createElement('p');
            description.className = 'payout-date';
            description.textContent = transaction.description;
            item.appendChild(description);
        }

        /* ----- Settlement status (optional) ----- */
        if (transaction.payout_status) {
            const settlement = document.createElement('p');
            settlement.className = 'payout-date payout-date--secondary';
            settlement.textContent =
                this.getSettlementLabel(transaction.payout_status);
            item.appendChild(settlement);
        }

        /* ----- Reference ----- */
        if (transactionReference) {
            const reference = document.createElement('p');
            reference.className = 'payout-ref';
            reference.textContent = `Ref ${transactionReference}`;
            item.appendChild(reference);
        }

        /* ----- Receipt (successful payments only) ----- */
        if (isSuccessful && transactionReference) {
            const receiptButton = document.createElement('button');
            receiptButton.type = 'button';
            receiptButton.className = 'receipt-download-btn';
            receiptButton.textContent = 'Download receipt';
            receiptButton.setAttribute(
                'aria-label',
                `Download receipt for transaction ${transactionReference}`
            );

            receiptButton.addEventListener('click', () => {
                this.downloadReceipt(transaction, receiptButton);
            });

            item.appendChild(receiptButton);
        }

        return item;
    }

    /* ---------------------------------------------------------
       RECEIPT DOWNLOAD
       --------------------------------------------------------- */

    async downloadReceipt(transaction, button) {
        const paymentStatus = String(
            transaction.status || ''
        ).toLowerCase();

        if (!['success', 'successful'].includes(paymentStatus)) {
            this.showToast(
                'A receipt is available only for successful payments.',
                'error'
            );
            return;
        }

        const reference = String(
            transaction.reference ||
            transaction.paystack_reference ||
            ''
        ).trim();

        if (!reference) {
            this.showToast('This transaction has no payment reference.', 'error');
            return;
        }

        const originalButtonText = button?.textContent || 'Download receipt';

        if (button) {
            button.disabled = true;
            button.textContent = 'Preparing receipt…';
        }

        let objectUrl = null;

        try {
            const response = await this.authFetch(
                `${this.API_BASE}/receipt/transaction/${encodeURIComponent(reference)}.pdf`
            );

            if (!response.ok) {
                let detail = '';

                try {
                    const errorData = await response.json();
                    detail = typeof errorData.detail === 'string'
                        ? errorData.detail
                        : '';
                } catch {
                    /* Non-JSON error response */
                }

                if (response.status === 403) {
                    this.showToast(
                        detail ||
                        'Receipt downloads require an eligible active subscription. Upgrade to Silver to access this feature.',
                        'error'
                    );
                    return;
                }

                if (response.status === 404) {
                    this.showToast(
                        detail || 'The receipt for this transaction was not found.',
                        'error'
                    );
                    return;
                }

                this.showToast(
                    detail || 'Unable to download this receipt. Please try again.',
                    'error'
                );
                return;
            }

            const contentType = (
                response.headers.get('content-type') || ''
            ).toLowerCase();

            if (!contentType.includes('application/pdf')) {
                throw new Error(
                    'The server did not return a PDF receipt. Please try again later.'
                );
            }

            const blob = await response.blob();

            if (!blob.size) {
                throw new Error('The receipt file is empty.');
            }

            objectUrl = URL.createObjectURL(blob);

            const downloadLink = document.createElement('a');
            downloadLink.href = objectUrl;
            downloadLink.download =
                `Payla-Receipt-${reference.replace(/[^a-zA-Z0-9_-]/g, '_')}.pdf`;
            downloadLink.style.display = 'none';

            document.body.appendChild(downloadLink);
            downloadLink.click();
            downloadLink.remove();

            this.showToast('Receipt downloaded successfully.');
        } catch (error) {
            if (error.message === 'Unauthorized') return;

            console.error('Unable to download receipt:', error);

            this.showToast(
                error.message || 'Unable to download this receipt. Please try again.',
                'error'
            );
        } finally {
            if (objectUrl) {
                window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
            }

            if (button) {
                button.disabled = false;
                button.textContent = originalButtonText;
            }
        }
    }

    /* ---------------------------------------------------------
       HISTORY MODAL — PAGINATED (page size = 4)
       --------------------------------------------------------- */

    async openHistoryModal() {
        const modal = document.getElementById('history-modal');
        const body = document.getElementById('history-modal-body');

        if (!modal || !body) return;

        // Reset pagination state
        this.historyCursor = null;
        this.historyHasMore = false;
        this.historyTotal = null;
        this.historyLoadedCount = 0;

        modal.classList.add('active');

        body.replaceChildren();

        const loadingEl = document.createElement('div');
        loadingEl.className = 'empty-state';
        loadingEl.textContent = 'Loading history…';
        body.appendChild(loadingEl);

        await this.loadHistoryPage(true);
    }

    async loadHistoryPage(isFirstPage = false) {
        if (this.historyLoading) return;

        const body = document.getElementById('history-modal-body');
        if (!body) return;

        this.historyLoading = true;

        // Disable the "load more" button if it's currently rendered
        const loadMoreBtn = body.querySelector('.history-load-more');

        if (loadMoreBtn) {
            loadMoreBtn.disabled = true;
            loadMoreBtn.innerHTML =
                '<span class="history-load-more__spinner"></span><span>Loading…</span>';
        }

        try {
            const params = new URLSearchParams({
                limit: String(CONFIG.HISTORY_PAGE_SIZE)
            });

            if (!isFirstPage && this.historyCursor) {
                params.set('cursor', this.historyCursor);
            }

            const response = await this.authFetch(
                `${this.API_BASE}/payout/history?${params.toString()}`
            );

            if (!response.ok) {
                throw new Error(`History request failed: ${response.status}`);
            }

            const data = await response.json();

            if (!Array.isArray(data.history)) {
                throw new Error('The server returned an invalid history response.');
            }

            // Update pagination state from the response
            this.historyCursor = data.next_cursor || null;
            this.historyHasMore = data.has_more === true;
            this.historyTotal = Number.isFinite(Number(data.total))
                ? Number(data.total)
                : null;

            if (isFirstPage) {
                body.replaceChildren();

                const stats = document.createElement('div');
                stats.className = 'history-stats';
                stats.innerHTML = this.buildStatsLine(
                    data.history.length,
                    this.historyTotal
                );
                body.appendChild(stats);
            } else {
                const existingPagination =
                    body.querySelector('.history-pagination');
                if (existingPagination) existingPagination.remove();

                const existingEnd = body.querySelector('.history-end');
                if (existingEnd) existingEnd.remove();
            }

            data.history.forEach(transaction => {
                body.appendChild(this.createHistoryItem(transaction));
            });

            this.historyLoadedCount += data.history.length;

            const stats = body.querySelector('.history-stats');
            if (stats) {
                stats.innerHTML = this.buildStatsLine(
                    this.historyLoadedCount,
                    this.historyTotal
                );
            }

            if (this.historyLoadedCount === 0) {
                const empty = document.createElement('div');
                empty.className = 'empty-state';
                empty.textContent = 'No transactions yet';
                body.appendChild(empty);
                return;
            }

            if (this.historyHasMore) {
                body.appendChild(this.buildPaginationBlock());
            } else {
                body.appendChild(this.buildEndMarker());
            }
        } catch (error) {
            if (error.message === 'Unauthorized') return;

            console.error('Unable to load history:', error);

            const errorEl = document.createElement('div');
            errorEl.className = 'empty-state';
            errorEl.textContent =
                'Unable to load history. Please try again.';

            if (isFirstPage) {
                body.replaceChildren(errorEl);
            } else {
                body.appendChild(errorEl);
            }
        } finally {
            this.historyLoading = false;
        }
    }

    buildStatsLine(loaded, total) {
        if (Number.isFinite(total) && total > 0) {
            return `Showing <strong>${loaded}</strong> of <strong>${total}</strong> transactions`;
        }
        return `Showing <strong>${loaded}</strong> transaction${loaded === 1 ? '' : 's'}`;
    }

    buildPaginationBlock() {
        const wrapper = document.createElement('div');
        wrapper.className = 'history-pagination';

        const progress = document.createElement('div');
        progress.className = 'history-pagination__progress';

        if (Number.isFinite(this.historyTotal) && this.historyTotal > 0) {
            progress.innerHTML =
                `<strong>${this.historyLoadedCount}</strong> of <strong>${this.historyTotal}</strong> loaded`;
        } else {
            progress.innerHTML =
                `<strong>${this.historyLoadedCount}</strong> loaded`;
        }

        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'history-load-more';
        button.innerHTML = '<span>Load more</span>';
        button.addEventListener('click', () => this.loadHistoryPage(false));

        wrapper.append(progress, button);
        return wrapper;
    }

    buildEndMarker() {
        const marker = document.createElement('div');
        marker.className = 'history-end';
        marker.textContent = 'End of history';
        return marker;
    }

    closeHistoryModal() {
        const modal = document.getElementById('history-modal');
        if (modal) modal.classList.remove('active');
    }

    /* ---------------------------------------------------------
       PAYOUT PROGRESS
       --------------------------------------------------------- */

    updatePayoutProgress() {
        const percentElement = document.getElementById('progress-percent');
        const countdownElement = document.getElementById('countdown-text');
        const circle = document.getElementById('progress-circle');

        if (!percentElement || !countdownElement || !circle) return;

        circle.classList.remove('pulse-active');
        circle.style.setProperty('--progress', '0');

        if (!this.currentAccount) {
            percentElement.textContent = '—';
            countdownElement.textContent =
                'Add a payout account to configure payouts.';
            return;
        }

        const settlementStatuses = this.payouts
            .map(transaction =>
                String(transaction.payout_status || '').toLowerCase()
            )
            .filter(Boolean);

        if (
            settlementStatuses.some(status =>
                ['pending', 'processing', 'pending_settlement'].includes(status)
            )
        ) {
            circle.classList.add('pulse-active');
            percentElement.textContent = '…';
            countdownElement.textContent =
                'Settlement status is being processed.';
            return;
        }

        if (settlementStatuses.includes('failed')) {
            circle.style.setProperty('--progress', '100');
            percentElement.textContent = '!';
            countdownElement.textContent =
                'A settlement failure was recorded. Review the transaction.';
            return;
        }

        if (
            settlementStatuses.some(status =>
                ['success', 'successful', 'settled'].includes(status)
            )
        ) {
            circle.style.setProperty('--progress', '100');
            percentElement.textContent = '✓';
            countdownElement.textContent =
                'Settlement is confirmed for recorded transactions.';
            return;
        }

        percentElement.textContent = '—';
        countdownElement.textContent =
            'No confirmed settlement update is available yet.';
    }

    /* ---------------------------------------------------------
       MODALS — ACCOUNT
       --------------------------------------------------------- */

    openModal() {
        const modal = document.getElementById('account-modal');
        if (!modal) return;

        this.invalidateAccountResolution();

        const bankSelect = document.getElementById('bank-select');
        const accountInput = document.getElementById('account-number');

        if (this.currentAccount) {
            if (bankSelect) {
                bankSelect.value = this.currentAccount.bank_code || '';
            }

            if (accountInput) {
                accountInput.value = this.currentAccount.account_number || '';
            }

            const preview = document.getElementById('account-preview');
            const saveButton = document.getElementById('save-account-btn');

            if (preview) preview.style.display = 'none';
            if (saveButton) saveButton.disabled = true;
        } else {
            this.resetForm();
        }

        modal.classList.add('active');
    }

    closeModal() {
        const modal = document.getElementById('account-modal');
        if (modal) modal.classList.remove('active');

        this.invalidateAccountResolution();
    }

    resetForm() {
        this.invalidateAccountResolution();

        const bankSelect = document.getElementById('bank-select');
        const accountInput = document.getElementById('account-number');
        const preview = document.getElementById('account-preview');
        const saveButton = document.getElementById('save-account-btn');

        if (bankSelect) bankSelect.value = '';
        if (accountInput) accountInput.value = '';
        if (preview) preview.style.display = 'none';

        if (saveButton) {
            saveButton.disabled = true;
            saveButton.textContent = 'Save Account';
        }
    }

    /* ---------------------------------------------------------
       EVENT LISTENERS
       --------------------------------------------------------- */

    setupEventListeners() {
        const addButton = document.getElementById('add-account-btn');
        const editButton = document.getElementById('edit-account-btn');
        const mobileAccountBtn = document.getElementById('mobile-account-btn');
        const modalClose = document.getElementById('modal-close');
        const cancelButton = document.getElementById('cancel-btn');
        const bankSelect = document.getElementById('bank-select');
        const accountInput = document.getElementById('account-number');
        const saveButton = document.getElementById('save-account-btn');
        const viewHistoryButton = document.getElementById('view-history-btn');
        const historyCloseButton =
            document.getElementById('history-modal-close');

        addButton?.addEventListener('click', () => this.openModal());
        editButton?.addEventListener('click', () => this.openModal());
        mobileAccountBtn?.addEventListener('click', () => this.openModal());

        modalClose?.addEventListener('click', () => this.closeModal());
        cancelButton?.addEventListener('click', () => this.closeModal());

        bankSelect?.addEventListener('change', () => {
            this.invalidateAccountResolution();

            if (
                bankSelect.value &&
                /^\d{10}$/.test(accountInput?.value || '')
            ) {
                this.validateForm();
            }
        });

        accountInput?.addEventListener('input', event => {
            this.handleAccountInput(event);
        });

        saveButton?.addEventListener('click', () => this.saveAccount());

        viewHistoryButton?.addEventListener(
            'click',
            () => this.openHistoryModal()
        );

        historyCloseButton?.addEventListener(
            'click',
            () => this.closeHistoryModal()
        );

        // Backdrop click closes either modal
        document.getElementById('account-modal')?.addEventListener(
            'click',
            event => {
                if (event.target.id === 'account-modal') {
                    this.closeModal();
                }
            }
        );

        document.getElementById('history-modal')?.addEventListener(
            'click',
            event => {
                if (event.target.id === 'history-modal') {
                    this.closeHistoryModal();
                }
            }
        );

        // Escape closes either modal
        document.addEventListener('keydown', event => {
            if (event.key === 'Escape') {
                this.closeModal();
                this.closeHistoryModal();
            }
        });
    }

    /* ---------------------------------------------------------
       UTILITIES
       --------------------------------------------------------- */

    formatAmount(value) {
        const amount = Number(value);

        return (Number.isFinite(amount) ? amount : 0).toLocaleString(
            'en-NG',
            {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2
            }
        );
    }

    showToast(message, type = 'success') {
        const toast = document.getElementById('success-toast');
        const messageElement = document.getElementById('toast-message');

        if (!toast || !messageElement) {
            console[type === 'error' ? 'error' : 'log'](message);
            return;
        }

        messageElement.textContent = message;
        toast.classList.toggle('error', type === 'error');
        toast.classList.add('show');

        window.clearTimeout(this.toastTimeout);

        this.toastTimeout = window.setTimeout(() => {
            toast.classList.remove('show');
        }, 3500);
    }
}


/* ============================================================
   BOOT
   ============================================================ */
document.addEventListener('DOMContentLoaded', () => {
    if (!localStorage.getItem('idToken')) {
        window.location.href = '/entry';
        return;
    }

    window.payoutManager = new PayoutManager();
});