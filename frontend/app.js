// ==========================================
// グローバルスコープ（ファイル先頭）
// ==========================================

// --- IndexedDB & Auth Config ---
const DB_NAME = 'HanaViewDB';
const DB_VERSION = 1;
const TOKEN_STORE_NAME = 'auth-tokens';

// --- Authentication Management (with IndexedDB support) ---
class AuthManager {
    static TOKEN_KEY = 'auth_token';
    static EXPIRY_KEY = 'auth_expiry';
    static PERMISSION_KEY = 'auth_permission';

    static async setTokenInDB(token) {
        return new Promise((resolve, reject) => {
            const request = indexedDB.open(DB_NAME, DB_VERSION);
            request.onerror = () => reject("Error opening DB for token storage");
            request.onupgradeneeded = event => {
                const db = event.target.result;
                if (!db.objectStoreNames.contains(TOKEN_STORE_NAME)) {
                    db.createObjectStore(TOKEN_STORE_NAME, { keyPath: 'id' });
                }
            };
            request.onsuccess = event => {
                const db = event.target.result;
                const transaction = db.transaction([TOKEN_STORE_NAME], 'readwrite');
                const store = transaction.objectStore(TOKEN_STORE_NAME);
                if (token) {
                    store.put({ id: 'auth_token', value: token });
                } else {
                    store.delete('auth_token');
                }
                transaction.oncomplete = () => resolve();
                transaction.onerror = () => reject("Error storing token in DB");
            };
        });
    }

    static async setAuthData(token, expiresIn, permission) {
        localStorage.setItem(this.TOKEN_KEY, token);
        const expiryTime = Date.now() + (expiresIn * 1000);
        localStorage.setItem(this.EXPIRY_KEY, expiryTime.toString());
        localStorage.setItem(this.PERMISSION_KEY, permission);
        try {
            await this.setTokenInDB(token);
            console.log(`Auth token and permission (${permission}) stored. Expires at:`, new Date(expiryTime).toLocaleString());
        } catch (error) {
            console.error("Failed to store token in IndexedDB:", error);
        }
    }

    static getToken() {
        const token = localStorage.getItem(this.TOKEN_KEY);
        const expiry = localStorage.getItem(this.EXPIRY_KEY);
        if (!token || !expiry || Date.now() > parseInt(expiry)) {
            if (token) this.clearAuthData();
            return null;
        }
        return token;
    }

    static getPermission() {
        return localStorage.getItem(this.PERMISSION_KEY);
    }

    static async clearAuthData() {
        localStorage.removeItem(this.TOKEN_KEY);
        localStorage.removeItem(this.EXPIRY_KEY);
        localStorage.removeItem(this.PERMISSION_KEY);
        try {
            await this.setTokenInDB(null);
            console.log('Auth data cleared from localStorage and IndexedDB');
        } catch (error) {
            console.error("Failed to clear token from IndexedDB:", error);
        }
    }

    static isAuthenticated() {
        return this.getToken() !== null;
    }

    static getAuthHeaders() {
        const token = this.getToken();
        return token ? { 'Authorization': `Bearer ${token}` } : {};
    }
}

// --- Authenticated Fetch Wrapper ---
async function fetchWithAuth(url, options = {}) {
    const authHeaders = AuthManager.getAuthHeaders();
    const response = await fetch(url, {
        ...options,
        headers: { ...options.headers, ...authHeaders }
    });

    if (response.status === 401) {
        console.log('Authentication failed (401), redirecting to auth screen');
        await AuthManager.clearAuthData();
        window.dispatchEvent(new CustomEvent('auth-required'));
        throw new Error('Authentication required');
    }
    return response;
}

// --- NotificationManager ---
class NotificationManager {
    constructor() {
        this.isSupported = 'Notification' in window && 'serviceWorker' in navigator && 'PushManager' in window;
        this.vapidPublicKey = null;
    }

    async init() {
        if (!this.isSupported) {
            console.log('Push notifications are not supported');
            return;
        }
        console.log('Initializing NotificationManager...');
        try {
            const response = await fetch('/api/vapid-public-key');
            const data = await response.json();
            this.vapidPublicKey = data.public_key;
            console.log('VAPID public key obtained');
        } catch (error) {
            console.error('Failed to get VAPID public key:', error);
            return;
        }
        const permission = await this.requestPermission();
        if (permission) {
            await this.subscribeUser();
        }
        navigator.serviceWorker.addEventListener('message', event => {
            if (event.data.type === 'data-updated' && event.data.data) {
                console.log('Data updated via push notification');
                if (typeof renderAllData === 'function') {
                    renderAllData(event.data.data);
                }
                this.showInAppNotification('データが更新されました');
            }
        });
    }

    async requestPermission() {
        const permission = await Notification.requestPermission();
        console.log('Notification permission:', permission);
        return permission === 'granted';
    }

    async subscribeUser() {
        try {
            const registration = await navigator.serviceWorker.ready;
            let subscription = await registration.pushManager.getSubscription();
            if (!subscription) {
                const convertedVapidKey = this.urlBase64ToUint8Array(this.vapidPublicKey);
                subscription = await registration.pushManager.subscribe({
                    userVisibleOnly: true,
                    applicationServerKey: convertedVapidKey
                });
            }
            await this.sendSubscriptionToServer(subscription);
            if ('sync' in registration) {
                await registration.sync.register('data-sync');
            }
        } catch (error) {
            console.error('Failed to subscribe user:', error);
        }
    }

    async sendSubscriptionToServer(subscription) {
    try {
        // AuthManagerが存在するか確認（iPhone PWA対策）
        if (typeof AuthManager === 'undefined') {
            console.error('❌ AuthManager is not defined yet');
            throw new Error('認証マネージャーが読み込まれていません。ページを再読み込みしてください。');
        }

        if (!AuthManager.isAuthenticated()) {
            console.warn('Cannot register push subscription: not authenticated');
            return;
        }

        console.log('📤 Sending push subscription to server...');

        // fetchWithAuthも存在確認（念のため）
        if (typeof fetchWithAuth === 'undefined') {
            console.error('❌ fetchWithAuth is not defined yet');
            throw new Error('通信機能が読み込まれていません。ページを再読み込みしてください。');
        }

        const response = await fetchWithAuth('/api/subscribe', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(subscription)
        });

        if (!response.ok) {
            const errorText = await response.text();
            throw new Error(`Server returned ${response.status}: ${errorText}`);
        }

        const result = await response.json();
        console.log('✅ Push subscription registered:', result);
        this.showInAppNotification(`通知が有効になりました (権限: ${result.permission})`);
    } catch (error) {
        console.error('❌ Error sending subscription to server:', error);

        // より詳細なエラーメッセージ
        let errorMessage = error.message || '不明なエラー';
        if (error.message.includes('認証マネージャー') || error.message.includes('通信機能')) {
            errorMessage += '\n\niPhone PWAでこの問題が発生する場合：\n1. アプリを完全に終了\n2. Safariでページを開き直す\n3. 再度ホーム画面に追加';
        }

        alert(`⚠️ Push通知の登録に失敗しました:\n${errorMessage}`);
    }
}

    urlBase64ToUint8Array(base64String) {
        const padding = '='.repeat((4 - base64String.length % 4) % 4);
        const base64 = (base64String + padding)
            .replace(/\-/g, '+')
            .replace(/_/g, '/');
        const rawData = window.atob(base64);
        const outputArray = new Uint8Array(rawData.length);
        for (let i = 0; i < rawData.length; ++i) {
            outputArray[i] = rawData.charCodeAt(i);
        }
        return outputArray;
    }

    showInAppNotification(message) {
        const toast = document.createElement('div');
        toast.className = 'toast-notification';
        toast.textContent = message;
        toast.style.cssText = `
            position: fixed;
            bottom: 20px;
            right: 20px;
            background: #006B6B;
            color: white;
            padding: 15px 20px;
            border-radius: 8px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            z-index: 10000;
            animation: slideIn 0.3s ease-out;
        `;
        document.body.appendChild(toast);
        setTimeout(() => {
            toast.style.animation = 'slideOut 0.3s ease-out';
            setTimeout(() => {
                document.body.removeChild(toast);
            }, 300);
        }, 3000);
    }
}

// ==========================================
// DOMContentLoaded以降
// ==========================================

document.addEventListener('DOMContentLoaded', () => {
    console.log("HanaView App Initializing...");

    // --- DOM Element References ---
    const authContainer = document.getElementById('auth-container');
    const dashboardContainer = document.querySelector('.container');
    const pinInputsContainer = document.getElementById('pin-inputs');
    const pinInputs = pinInputsContainer ? Array.from(pinInputsContainer.querySelectorAll('input')) : [];
    const authErrorMessage = document.getElementById('auth-error-message');
    const authSubmitButton = document.getElementById('auth-submit-button');
    const authLoadingSpinner = document.getElementById('auth-loading');

    // --- State ---
    let failedAttempts = 0;
    const MAX_ATTEMPTS = 5;
    let globalNotificationManager = null;

    // ✅ 認証エラーイベントのリスナー追加
    window.addEventListener('auth-required', () => {
        showAuthScreen();
    });

    // --- Main App Logic ---
    async function initializeApp() {
        // ✅ 古い認証データのクリーンアップ
        if (localStorage.getItem('auth_token') && !localStorage.getItem('auth_permission')) {
            console.log('🧹 Cleaning old authentication data...');
            await AuthManager.clearAuthData();
            // Service Workerの登録も解除
            if ('serviceWorker' in navigator) {
                const registrations = await navigator.serviceWorker.getRegistrations();
                for (let registration of registrations) {
                    await registration.unregister();
                }
            }
            alert('⚠️ 認証システムが更新されました。再度ログインしてください。');
            // ✅ ページをリロードしてService Workerを再登録
            location.reload();
            return; // これ以降の処理を実行しない
        }

        try {
            if (AuthManager.isAuthenticated()) {
                await showDashboard();
            } else {
                showAuthScreen();
            }
        } catch (error) {
            if (error.message !== 'Authentication required') {
                console.error('Error during authentication check:', error);
                if (authErrorMessage) authErrorMessage.textContent = 'サーバーとの通信に失敗しました。';
            }
            showAuthScreen();
        }
    }

    function applyTabPermissions() {
        const permission = AuthManager.getPermission();
        const hwb200Tab = document.querySelector('.tab-button[data-tab="hwb200"]');

        console.log(`Applying permissions for level: ${permission}`);

        if (hwb200Tab) hwb200Tab.style.display = '';

        if (permission === 'standard') {
            console.log("Standard permission: Hiding 200MA and Stage1+2 tabs.");
            if (hwb200Tab) hwb200Tab.style.display = 'none';
        } else if (permission === 'secret') {
            console.log("Secret permission: Hiding Stage1+2 tab.");
        } else if (permission === 'ura') {
            console.log("Ura permission: All tabs visible.");
        }
    }

async function showDashboard() {
    if (authContainer) authContainer.style.display = 'none';
    if (dashboardContainer) dashboardContainer.style.display = 'block';

    applyTabPermissions();

    // NotificationManager初期化前に必要な依存関係を確認
    if (typeof AuthManager === 'undefined' || typeof fetchWithAuth === 'undefined') {
        console.error('❌ Required dependencies not loaded. Skipping notification setup.');
        alert('⚠️ アプリの初期化に問題があります。ページを再読み込みしてください。');
        return;
    }

    if (!globalNotificationManager) {
        globalNotificationManager = new NotificationManager();
        try {
            // 少し待機してからNotificationManagerを初期化（iPhone PWA対策）
            await new Promise(resolve => setTimeout(resolve, 100));
            await globalNotificationManager.init();
            console.log('✅ Notifications initialized');
        } catch (error) {
            console.error('❌ Notification initialization failed:', error);
            alert('⚠️ Push通知の登録に失敗しました。ページを再読み込みしてください。');
        }
    }

    if (!dashboardContainer.dataset.initialized) {
        console.log("HanaView Dashboard Initialized");
        initTabs();
        fetchDataAndRender();
        initSwipeNavigation();

        if (document.getElementById('hwb200-content')) {
            initHWB200MA();
        }

        dashboardContainer.dataset.initialized = 'true';
    }
}

    function showAuthScreen() {
        if (authContainer) authContainer.style.display = 'flex';
        if (dashboardContainer) dashboardContainer.style.display = 'none';
        setupAuthForm();
    }

    function setupAuthForm() {
        if (!pinInputsContainer) return;
        pinInputs.forEach(input => { input.value = ''; input.disabled = false; });
        if(authSubmitButton) authSubmitButton.disabled = false;
        if(authErrorMessage) authErrorMessage.textContent = '';
        failedAttempts = 0;
        pinInputs[0]?.focus();

        pinInputs.forEach((input, index) => {
            input.addEventListener('input', () => {
                if (input.value.length === 1 && index < pinInputs.length - 1) {
                    pinInputs[index + 1].focus();
                }
            });
            input.addEventListener('keydown', (e) => {
                if (e.key === 'Backspace' && input.value.length === 0 && index > 0) {
                    pinInputs[index - 1].focus();
                }
            });
            input.addEventListener('paste', (e) => {
                e.preventDefault();
                const pasteData = e.clipboardData.getData('text').trim();
                if (/^\d{6}$/.test(pasteData)) {
                    pasteData.split('').forEach((char, i) => { if (pinInputs[i]) pinInputs[i].value = char; });
                    handleAuthSubmit();
                }
            });
        });

        if (authSubmitButton) {
            const newButton = authSubmitButton.cloneNode(true);
            authSubmitButton.parentNode.replaceChild(newButton, authSubmitButton);
            newButton.addEventListener('click', handleAuthSubmit);
        }
    }

    async function handleAuthSubmit() {
        const pin = pinInputs.map(input => input.value).join('');
        if (pin.length !== 6) {
            if (authErrorMessage) authErrorMessage.textContent = '6桁のコードを入力してください。';
            return;
        }
        setLoading(true);
        try {
            const response = await fetch('/api/auth/verify', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ pin: pin })
            });
            const data = await response.json();
            if (response.ok && data.success) {
                await AuthManager.setAuthData(data.token, data.expires_in, data.permission);
                console.log('✅ Authentication complete, token saved');
                await showDashboard();
            } else {
                failedAttempts++;
                pinInputs.forEach(input => input.value = '');
                pinInputs[0].focus();
                if (failedAttempts >= MAX_ATTEMPTS) {
                    if (authErrorMessage) authErrorMessage.textContent = '認証に失敗しました。';
                    pinInputs.forEach(input => input.disabled = true);
                    document.getElementById('auth-submit-button').disabled = true;
                } else {
                    if (authErrorMessage) authErrorMessage.textContent = '正しい認証コードを入力してください。';
                }
            }
        } catch (error) {
            console.error('Error during PIN verification:', error);
            if (authErrorMessage) authErrorMessage.textContent = '認証中にエラーが発生しました。';
        } finally {
            setLoading(false);
        }
    }

    function setLoading(isLoading) {
        if (authLoadingSpinner) authLoadingSpinner.style.display = isLoading ? 'block' : 'none';
        const submitBtn = document.getElementById('auth-submit-button');
        if (submitBtn) submitBtn.style.display = isLoading ? 'none' : 'block';
    }

    // --- Dashboard Functions ---

    async function fetchDataAndRender() {
        try {
            const response = await fetchWithAuth('/api/data');
            const data = await response.json();
            renderAllData(data);
        } catch (error) {
            if (error.message !== 'Authentication required') {
                console.error("Failed to fetch data:", error);
                document.getElementById('dashboard-content').innerHTML =
                    `<div class="card"><p>データの読み込みに失敗しました: ${error.message}</p></div>`;
            }
        }
    }

    // --- Tab-switching logic ---
    function initTabs() {
        const tabContainer = document.querySelector('.tab-container');
        tabContainer.addEventListener('click', (e) => {
            if (!e.target.matches('.tab-button')) return;
            const targetTab = e.target.dataset.tab;

            document.querySelectorAll('.tab-button').forEach(b => b.classList.toggle('active', b.dataset.tab === targetTab));
            document.querySelectorAll('.tab-pane').forEach(p => p.classList.toggle('active', p.id === `${targetTab}-content`));

            if (targetTab === 'hwb200' && window.hwb200Manager) {
                window.hwb200Manager.loadData();
            }

            setTimeout(() => window.scrollTo(0, 0), 0);
        });
    }

    // --- HWB 200MA Manager ---
    function initHWB200MA() {
        window.hwb200Manager = new HWB200MAManager();
        console.log('HWB200MAManager initialized');
    }

    class HWB200MAManager {
        constructor() {
            this.summaryData = null;
            this.currentView = 'summary';
            this.activeListType = 'signal_today'; // 初期値は当日ブレイクアウト
            this.initEventListeners();
        }

        initEventListeners() {
            const searchBtn = document.getElementById('hwb-analyze-btn');
            if (searchBtn) {
                searchBtn.addEventListener('click', () => {
                    if (searchBtn.dataset.state === 'reset') {
                        this.resetToSummary();
                    } else {
                        this.searchTicker();
                    }
                });
            }
        }

        async searchTicker() {
            const input = document.getElementById('hwb-ticker-input');
            const ticker = input.value.trim().toUpperCase();

            if (!ticker) {
                this.showStatus('ティッカーシンボルを入力してください', 'warning');
                return;
            }

            this.showStatus(`${ticker}のデータを検索中...`, 'info');

            try {
                const response = await fetchWithAuth(`/api/hwb/symbols/${ticker}`);

                if (!response.ok) {
                    if (response.status === 404) {
                        this.showStatus(`❌ ${ticker}はスキャン対象外またはシグナルなし`, 'warning');
                        return;
                    }
                    throw new Error(`検索に失敗しました: ${response.status}`);
                }

                const symbolData = await response.json();

                this.currentView = 'search';
                this.renderSearchResults(ticker, symbolData);

                const searchBtn = document.getElementById('hwb-analyze-btn');
                if (searchBtn) {
                    searchBtn.textContent = 'リセット';
                    searchBtn.dataset.state = 'reset';
                }

                this.showStatus(`✅ ${ticker}の検索結果を表示中`, 'info');

            } catch (error) {
                console.error('Search error:', error);
                this.showStatus(`❌ エラー: ${error.message}`, 'error');
            }
        }

        resetToSummary() {
            this.currentView = 'summary';
            const input = document.getElementById('hwb-ticker-input');
            if (input) input.value = '';

            const searchBtn = document.getElementById('hwb-analyze-btn');
            if (searchBtn) {
                searchBtn.textContent = '検索';
                searchBtn.dataset.state = 'search';
            }

            this.render();

            const { updated_at, summary } = this.summaryData;
            const displayDate = updated_at ? formatDateForDisplay(updated_at) : this.summaryData.scan_date;
            
            const todayCount = summary.signals_today?.length || 0;
            const recentCount = summary.signals_recent?.length || 0;
            const candidatesCount = summary.candidates?.length || 0;
            
            this.showStatus(
                `最終更新: ${displayDate} | 当日: ${todayCount} | 直近: ${recentCount} | 監視: ${candidatesCount}`,
                'info'
            );
        }

        renderSearchResults(ticker, symbolData) {
            const container = document.getElementById('hwb-content');
            container.innerHTML = '';

            const resultDiv = document.createElement('div');
            resultDiv.className = 'hwb-search-results';

            const signals = symbolData.signals || [];

            if (signals.length === 0) {
                resultDiv.innerHTML = `
                    <div class="hwb-summary">
                        <h2>${ticker} の検索結果</h2>
                        <p class="info-message">このシンボルにはブレイクアウトシグナルがありません。</p>
                    </div>
                `;
                container.appendChild(resultDiv);
                return;
            }

            // シグナル日付でグループ化
            const signalsByDate = {};
            signals.forEach(signal => {
                const date = signal.breakout_date;
                if (!signalsByDate[date]) {
                    signalsByDate[date] = [];
                }
                signalsByDate[date].push(signal);
            });

            resultDiv.innerHTML = `
                <div class="hwb-summary">
                    <h2>${ticker} の検索結果</h2>
                    <div class="scan-info">
                        ブレイクアウトシグナル: ${signals.length}件
                    </div>
                </div>
            `;

            // 日付ごとにセクション作成
            const sortedDates = Object.keys(signalsByDate).sort().reverse();

            sortedDates.forEach(date => {
                const section = document.createElement('div');
                section.className = 'hwb-charts-section';
                // 日付フォーマットを変更（T00:00:00を削除）
                const formattedDate = date.split('T')[0];
                section.innerHTML = `<h2>📅 ${formattedDate}</h2>`;

                const list = document.createElement('div');
                list.className = 'hwb-symbol-list';

                signalsByDate[date].forEach(signal => {
                    const item = document.createElement('div');
                    item.className = 'hwb-symbol-item';

                    // RS Ratingを表示
                    let rsRatingHtml = '';
                    if (signal.rs_rating !== undefined && signal.rs_rating !== null) {
                        const rsClass = this.getRSClass(signal.rs_rating);
                        rsRatingHtml = `<span class="hwb-rs-badge ${rsClass}">RS ${signal.rs_rating}</span>`;
                    }

                    item.innerHTML = `
                        <span class="hwb-symbol-name">${ticker}</span>
                        ${rsRatingHtml}
                        <span class="hwb-symbol-date">${formattedDate}</span>
                    `;
                    list.appendChild(item);
                });

                section.appendChild(list);
                resultDiv.appendChild(section);
            });

            container.appendChild(resultDiv);
        }

        async loadData() {
            this.showStatus('最新のサマリーを読み込み中...', 'info');
            try {
                const response = await fetchWithAuth('/api/hwb/daily/latest');
                if (!response.ok) {
                    if (response.status === 404) {
                        this.showStatus('データがありません。スキャンを実行してください。', 'warning');
                        document.getElementById('hwb-content').innerHTML =
                            '<div class="card"><p>データがありません。スキャンを実行してください。</p></div>';
                    } else {
                        throw new Error(`サーバーエラー: ${response.status}`);
                    }
                    return;
                }

                this.summaryData = await response.json();
                this.currentView = 'summary';
                this.render();

                const { updated_at, summary } = this.summaryData;
                const displayDate = updated_at ? formatDateForDisplay(updated_at) : this.summaryData.scan_date;
                
                const todayCount = summary.signals_today?.length || 0;
                const recentCount = summary.signals_recent?.length || 0;
                const candidatesCount = summary.candidates?.length || 0;
                
                this.showStatus(
                    `最終更新: ${displayDate} | 当日: ${todayCount} | 直近: ${recentCount} | 監視: ${candidatesCount}`,
                    'info'
                );

            } catch (error) {
                console.error('HWB summary loading error:', error);
                this.showStatus(`❌ データ読み込みエラー: ${error.message}`, 'error');
            }
        }

        render() {
            if (!this.summaryData) return;
            const container = document.getElementById('hwb-content');
            container.innerHTML = '';

            this.renderSummary(container);
            this.renderLists(container);
        }

        renderSummary(container) {
            const { updated_at, scan_date, scan_time, total_scanned, summary } = this.summaryData;
            const summaryDiv = document.createElement('div');
            summaryDiv.className = 'hwb-summary';
            const displayDate = updated_at ? formatDateForDisplay(updated_at) : `${scan_date} ${scan_time}`;

            const todayCount = summary.signals_today?.length || 0;
            const recentCount = summary.signals_recent?.length || 0;
            const candidatesCount = summary.candidates?.length || 0;

            summaryDiv.innerHTML = `
                <h2>200MAシステム</h2>
                <div class="scan-info">
                    データ更新: ${displayDate} | 処理銘柄: ${total_scanned}
                </div>
                <div class="hwb-summary-grid">
                    <div class="summary-card ${this.activeListType === 'signal_today' ? 'active' : ''}" data-list-type="signal_today">
                        <h3>当日ブレイクアウト</h3>
                        <p class="summary-count">${todayCount}</p>
                    </div>
                    <div class="summary-card ${this.activeListType === 'signal_recent' ? 'active' : ''}" data-list-type="signal_recent">
                        <h3>直近5営業日</h3>
                        <p class="summary-count">${recentCount}</p>
                    </div>
                    <div class="summary-card ${this.activeListType === 'candidate' ? 'active' : ''}" data-list-type="candidate">
                        <h3>監視銘柄</h3>
                        <p class="summary-count">${candidatesCount}</p>
                    </div>
                </div>
            `;

            // クリックイベントを追加
            const cards = summaryDiv.querySelectorAll('.summary-card');
            cards.forEach(card => {
                card.style.cursor = 'pointer';
                card.addEventListener('click', () => {
                    const listType = card.dataset.listType;
                    this.activeListType = listType;
                    this.refreshView();
                });
            });

            container.appendChild(summaryDiv);
        }

        renderLists(container) {
            const { signals_today = [], signals_recent = [], candidates = [] } = this.summaryData.summary;

            // activeListTypeに応じて表示するリストを切り替え
            if (this.activeListType === 'signal_today' && signals_today.length > 0) {
                this.renderSymbolList(container, '当日ブレイクアウト', signals_today, 'signal_today');
            } else if (this.activeListType === 'signal_recent' && signals_recent.length > 0) {
                this.renderSymbolList(container, '直近5営業日以内', signals_recent, 'signal_recent');
            } else if (this.activeListType === 'candidate' && candidates.length > 0) {
                this.renderSymbolList(container, '監視銘柄', candidates, 'candidate');
            }
        }

        // ビューをリフレッシュするメソッドを追加
        refreshView() {
            const container = document.getElementById('hwb-content');
            if (container && this.summaryData) {
                container.innerHTML = '';
                this.renderSummary(container);
                this.renderLists(container);
            }
        }

// renderSymbolListメソッドを修正
renderSymbolList(container, title, items, type) {
    const section = document.createElement('div');
    section.className = 'hwb-symbol-section';
    section.innerHTML = `<h2>${title}</h2>`;

    const list = document.createElement('div');
    list.className = 'hwb-symbol-list';

    // RS rating降順でソート（当日ブレイクアウトと直近5営業日の場合）
    let sortedItems = [...items];
    if (type === 'signal_today' || type === 'signal_recent') {
        sortedItems.sort((a, b) => {
            const rsA = a.rs_rating !== undefined && a.rs_rating !== null ? a.rs_rating : -1;
            const rsB = b.rs_rating !== undefined && b.rs_rating !== null ? b.rs_rating : -1;
            return rsB - rsA; // 降順
        });
    }

    sortedItems.forEach(item => {
        const symbolItem = document.createElement('div');
        symbolItem.className = 'hwb-symbol-item';

        let dateInfo = '';
        let rsRatingHtml = '';

        if (type === 'signal_today' || type === 'signal_recent') {
            // 日付フォーマットを変更（T00:00:00を削除）
            dateInfo = item.signal_date ? item.signal_date.split('T')[0] : '';

            // RS Ratingの表示
            if (item.rs_rating !== undefined && item.rs_rating !== null) {
                const rsClass = this.getRSClass(item.rs_rating);
                rsRatingHtml = `<span class="hwb-rs-badge ${rsClass}">RS ${item.rs_rating}</span>`;
            }
        } else {
            // 監視銘柄の日付フォーマットも変更
            dateInfo = item.fvg_date ? item.fvg_date.split('T')[0] : '';
        }

        symbolItem.innerHTML = `
            <span class="hwb-symbol-name">${item.symbol}</span>
            ${rsRatingHtml}
            <span class="hwb-symbol-date">${dateInfo}</span>
        `;
        list.appendChild(symbolItem);
    });

    section.appendChild(list);
    container.appendChild(section);
}

// ✅ RS Ratingの色分けメソッドを追加
getRSClass(rsRating) {
    if (rsRating >= 90) return 'rs-excellent';  // 緑
    if (rsRating >= 80) return 'rs-good';       // 青
    if (rsRating >= 70) return 'rs-average';    // 黄
    return 'rs-weak';                           // 灰色
}

        showStatus(message, type = 'info') {
            const statusDiv = document.getElementById('hwb-status');
            if (statusDiv) {
                statusDiv.textContent = message;
                statusDiv.className = `hwb-status-info ${type}`;
            }
        }
    }

    // --- Existing rendering functions ---
    function formatDateForDisplay(dateInput) {
        if (!dateInput) return '';
        try {
            const date = new Date(dateInput);
            if (isNaN(date.getTime())) return '';
            return `${date.getFullYear()}年${date.getMonth() + 1}月${date.getDate()}日 ${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`;
        } catch (e) { return ''; }
    }

    function renderLightweightChart(containerId, data, title) {
        const container = document.getElementById(containerId);
        if (!container || !data || data.length === 0) {
            container.innerHTML = `<p>Chart data for ${title} is not available.</p>`;
            return;
        }
        container.innerHTML = '';

        const chart = LightweightCharts.createChart(container, {
            width: container.clientWidth,
            height: 300,
            layout: {
                backgroundColor: '#ffffff',
                textColor: '#333333'
            },
            grid: {
                vertLines: { color: '#e1e1e1' },
                horzLines: { color: '#e1e1e1' }
            },
            crosshair: {
                mode: LightweightCharts.CrosshairMode.Normal
            },
            timeScale: {
                borderColor: '#cccccc',
                timeVisible: true,
                secondsVisible: false
            },
            handleScroll: false,
            handleScale: false
        });

        const candlestickSeries = chart.addSeries(LightweightCharts.CandlestickSeries, {
            upColor: '#26a69a',
            downColor: '#ef5350',
            borderDownColor: '#ef5350',
            borderUpColor: '#26a69a',
            wickDownColor: '#ef5350',
            wickUpColor: '#26a69a'
        });

        const chartData = data.map(item => ({
            time: (new Date(item.time).getTime() / 1000),
            open: item.open,
            high: item.high,
            low: item.low,
            close: item.close
        }));

        candlestickSeries.setData(chartData);
        chart.timeScale().fitContent();

        new ResizeObserver(entries => {
            if (entries.length > 0 && entries[0].contentRect.width > 0) {
                chart.applyOptions({ width: entries[0].contentRect.width });
            }
        }).observe(container);
    }

    function renderMarketOverview(container, marketData, lastUpdated) {
        if (!container) return;
        container.innerHTML = '';
        const card = document.createElement('div');
        card.className = 'card';
        let content = '';
        if (marketData.fear_and_greed) { content += `<div class="market-section"><h3>Fear & Greed Index</h3><div class="fg-container" style="display: flex; justify-content: center; align-items: center; min-height: 400px;"><img src="/fear_and_greed_gauge.png?v=${new Date().getTime()}" alt="Fear and Greed Index Gauge" style="max-width: 100%; height: auto;"></div></div>`; }
        content += `<div class="market-grid"><div class="market-section"><h3>VIX (4h足)</h3><div class="chart-container" id="vix-chart-container"></div></div><div class="market-section"><h3>米国10年債金利 (4h足)</h3><div class="chart-container" id="t-note-chart-container"></div></div></div>`;
        if (marketData.ai_commentary) { const dateHtml = formatDateForDisplay(lastUpdated) ? `<p class="ai-date">${formatDateForDisplay(lastUpdated)}</p>` : ''; content += `<div class="market-section"><div class="ai-header"><h3>AI解説</h3>${dateHtml}</div><p>${marketData.ai_commentary.replace(/\n/g, '<br>')}</p></div>`; }
        card.innerHTML = content;
        container.appendChild(card);
        if (marketData.vix && marketData.vix.history) { renderLightweightChart('vix-chart-container', marketData.vix.history, 'VIX'); }
        if (marketData.t_note_future && marketData.t_note_future.history) { renderLightweightChart('t-note-chart-container', marketData.t_note_future.history, '10y T-Note'); }
    }

    function renderNews(container, newsData, lastUpdated) {
        if (!container || !newsData || (!newsData.summary && (!newsData.topics || newsData.topics.length === 0))) { container.innerHTML = '<div class="card"><p>ニュースデータがありません。</p></div>'; return; }
        container.innerHTML = '';
        const card = document.createElement('div');
        card.className = 'card news-card';
        if (newsData.summary) {
            const summaryContainer = document.createElement('div');
            summaryContainer.className = 'news-summary';
            const summaryHeader = document.createElement('div');
            summaryHeader.className = 'news-summary-header';
            let title = '<h3>今朝のサマリー</h3>';
            let dateString = '';
            if (lastUpdated) { const date = new Date(lastUpdated); if (date.getDay() === 1) title = '<h3>先週のサマリー</h3>'; dateString = `${date.getFullYear()}年${date.getMonth() + 1}月${date.getDate()}日 ${date.getHours()}:${String(date.getMinutes()).padStart(2, '0')}`; }
            summaryHeader.innerHTML = `${title}<p class="summary-date">${dateString}</p>`;
            const summaryBody = document.createElement('div');
            summaryBody.className = 'news-summary-body';
            summaryBody.innerHTML = `<p>${newsData.summary.replace(/\n/g, '<br>')}</p><img src="icons/suit.PNG" alt="suit" class="summary-image">`;
            summaryContainer.appendChild(summaryHeader);
            summaryContainer.appendChild(summaryBody);
            card.appendChild(summaryContainer);
        }
        if (newsData.topics && newsData.topics.length > 0) {
            const topicsOuterContainer = document.createElement('div');
            topicsOuterContainer.className = 'main-topics-outer-container';
            topicsOuterContainer.innerHTML = '<h3>主要トピック</h3>';
            const topicsContainer = document.createElement('div');
            topicsContainer.className = 'main-topics-container';
            newsData.topics.forEach((topic, index) => {
                const topicBox = document.createElement('div');
                topicBox.className = `topic-box topic-${index + 1}`;
                const topicContent = topic.analysis ? `<p>${topic.analysis.replace(/\n/g, '<br>')}</p>` : `<p>${topic.body}</p>`;
                const sourceIcon = `<a href="${topic.url}" target="_blank" class="source-link"><img src="${topic.source_icon_url || 'icons/external-link.svg'}" alt="Source" class="source-icon" onerror="this.onerror=null;this.src='icons/external-link.svg';"></a>`;
                topicBox.innerHTML = `<div class="topic-number-container"><div class="topic-number">${index + 1}</div></div><div class="topic-details"><p class="topic-title">${topic.title}</p><div class="topic-content">${topicContent}${sourceIcon}</div></div>`;
                topicsContainer.appendChild(topicBox);
            });
            topicsOuterContainer.appendChild(topicsContainer);
            card.appendChild(topicsOuterContainer);
        }
        container.appendChild(card);
    }

    function getPerformanceColor(p) { if (p >= 3) return '#00c853'; if (p > 1) return '#66bb6a'; if (p > 0) return '#2e7d32'; if (p == 0) return '#888888'; if (p > -1) return '#e53935'; if (p > -3) return '#ef5350'; return '#c62828'; }

    function renderGridHeatmap(container, title, heatmapData) {
        if (!container) return;
        container.innerHTML = '';
        let items = heatmapData?.items || heatmapData?.stocks || [];
        const isSP500 = title.includes('SP500');
        if (items.length > 0) {
            if (isSP500) { const stocks = items.filter(d => d.market_cap).sort((a, b) => b.market_cap - a.market_cap).slice(0, 30); const etfs = items.filter(d => !d.market_cap); items = [...stocks, ...etfs]; }
            else { items.sort((a, b) => b.market_cap - a.market_cap); items = items.slice(0, 30); }
        }
        if (items.length === 0) return;
        const card = document.createElement('div');
        card.className = 'card';
        const heatmapWrapper = document.createElement('div');
        heatmapWrapper.className = 'heatmap-wrapper';
        heatmapWrapper.innerHTML = `<h2 class="heatmap-main-title">${title}</h2>`;
        const itemsPerRow = 6, margin = { top: 10, right: 10, bottom: 10, left: 10 }, containerWidth = container.clientWidth || 1000, width = containerWidth - margin.left - margin.right, tilePadding = 5, tileWidth = (width - (itemsPerRow - 1) * tilePadding) / itemsPerRow, tileHeight = tileWidth, etfGap = isSP500 ? tileHeight * 0.5 : 0;
        let yPos = 0; const yPositions = [];
        for (let i = 0; i < items.length; i++) { if (isSP500 && i === items.findIndex(d => !d.market_cap)) { if (i % itemsPerRow !== 0) yPos += tileHeight + tilePadding; yPos += etfGap; } yPositions.push(yPos); if ((i + 1) % itemsPerRow === 0 && i + 1 < items.length) yPos += tileHeight + tilePadding; }
        const totalHeight = yPos + tileHeight;
        const svg = d3.create("svg").attr("viewBox", `0 0 ${containerWidth} ${totalHeight + margin.top + margin.bottom}`).attr("width", "100%").attr("height", "auto");
        const g = svg.append("g").attr("transform", `translate(${margin.left},${margin.top})`);
        const tooltip = d3.select("body").append("div").attr("class", "heatmap-tooltip").style("opacity", 0);
        const nodes = g.selectAll("g").data(items).enter().append("g").attr("transform", (d, i) => `translate(${(i % itemsPerRow) * (tileWidth + tilePadding)},${yPositions[i]})`);
        nodes.append("rect").attr("width", tileWidth).attr("height", tileHeight).attr("fill", d => getPerformanceColor(d.performance)).on("mouseover", (e, d) => { tooltip.transition().duration(200).style("opacity", .9); tooltip.html(`<strong>${d.ticker}</strong><br/>Perf: ${d.performance.toFixed(2)}%`).style("left", `${e.pageX + 5}px`).style("top", `${e.pageY - 28}px`); }).on("mouseout", () => tooltip.transition().duration(500).style("opacity", 0));
        const text = nodes.append("text").attr("class", "stock-label").attr("x", tileWidth / 2).attr("y", tileHeight / 2).attr("text-anchor", "middle").attr("dominant-baseline", "central").style("pointer-events", "none");
        text.append("tspan").attr("class", "ticker-label").style("font-size", `${Math.max(10, Math.min(tileWidth / 3, 24)) * 1.5}px`).text(d => d.ticker);
        text.append("tspan").attr("class", "performance-label").attr("x", tileWidth / 2).attr("dy", "1.2em").style("font-size", `${Math.max(8, Math.min(tileWidth / 4, 18)) * 1.5}px`).text(d => `${d.performance.toFixed(2)}%`);
        heatmapWrapper.appendChild(svg.node());
        card.appendChild(heatmapWrapper);
        container.appendChild(card);
    }

    function renderIndicators(container, indicatorsData) {
        if (!container) return;
        container.innerHTML = '';
        const { economic = [], us_earnings = [], jp_earnings = [], economic_commentary, earnings_commentary } = indicatorsData || {};
        const economicCard = document.createElement('div');
        economicCard.className = 'card';
        economicCard.innerHTML = '<h3>経済指標カレンダー (重要度★★以上)</h3>';
        const relevantIndicators = economic.filter(ind => (ind.importance?.match(/★/g) || []).length >= 2);
        if (relevantIndicators.length > 0) { const table = document.createElement('table'); table.className = 'indicators-table'; table.innerHTML = `<thead><tr><th>発表日</th><th>発表時刻</th><th>指標名</th><th>重要度</th><th>前回</th><th>予測</th></tr></thead>`; const tbody = document.createElement('tbody'); relevantIndicators.forEach(ind => { const row = document.createElement('tr'); const [date, time] = (ind.datetime || ' / ').split(' '); row.innerHTML = `<td>${date||'--'}</td><td>${time||'--'}</td><td>${ind.name||'--'}</td><td class="importance-${(ind.importance.match(/★/g)||[]).length}">${ind.importance}</td><td>${ind.previous||'--'}</td><td>${ind.forecast||'--'}</td>`; tbody.appendChild(row); }); table.appendChild(tbody); economicCard.appendChild(table); } else { economicCard.innerHTML += '<p>予定されている重要経済指標はありません。</p>'; }
        if (economic_commentary) { const div = document.createElement('div'); div.className = 'ai-commentary'; div.innerHTML = `<div class="ai-header"><h3>AI解説</h3></div><p>${economic_commentary.replace(/\n/g, '<br>')}</p>`; economicCard.appendChild(div); }
        container.appendChild(economicCard);
        const allEarnings = [...us_earnings, ...jp_earnings].sort((a,b) => (a.datetime||'').localeCompare(b.datetime||''));
        const earningsCard = document.createElement('div');
        earningsCard.className = 'card';
        earningsCard.innerHTML = '<h3>注目決算</h3>';
        if (allEarnings.length > 0) { const table = document.createElement('table'); table.className = 'indicators-table'; table.innerHTML = `<thead><tr><th>発表日時</th><th>ティッカー</th><th>企業名</th></tr></thead>`; const tbody = document.createElement('tbody'); allEarnings.forEach(e => { const row = document.createElement('tr'); row.innerHTML = `<td>${e.datetime||'--'}</td><td>${e.ticker||'--'}</td><td>${e.company||''}</td>`; tbody.appendChild(row); }); table.appendChild(tbody); earningsCard.appendChild(table); } else { earningsCard.innerHTML += '<p>予定されている注目決算はありません。</p>'; }
        if (earnings_commentary) { const div = document.createElement('div'); div.className = 'ai-commentary'; div.innerHTML = `<div class="ai-header"><h3>AI解説</h3></div><p>${earnings_commentary.replace(/\n/g, '<br>')}</p>`; earningsCard.appendChild(div); }
        container.appendChild(earningsCard);
    }

    function renderColumn(container, columnData) {
        if (!container) return;
        container.innerHTML = '';
        if (typeof columnData === 'string') { container.innerHTML = `<div class="card"><p>${columnData}</p></div>`; return; }
        const report = columnData ? (columnData.daily_report || columnData.weekly_report) : null;
        if (report && report.content) { const card = document.createElement('div'); card.className = 'card'; const dateHtml = formatDateForDisplay(report.date) ? `<p class="ai-date">${formatDateForDisplay(report.date)}</p>` : ''; card.innerHTML = `<div class="column-container"><div class="ai-header"><h3>${report.title || 'AI解説'}</h3>${dateHtml}</div><div class="column-content">${report.content.replace(/\n/g, '<br>')}</div></div>`; container.appendChild(card); }
        else { container.innerHTML = `<div class="card"><p>${report && report.error ? '生成が失敗しました。' : 'AI解説はまだありません。（月曜日に週間分、火〜金曜日に当日分が生成されます）'}</p></div>`; }
    }

    function renderHeatmapCommentary(container, commentary, lastUpdated) {
        if (!container || !commentary) return;
        const card = document.createElement('div');
        card.className = 'card';
        const dateHtml = formatDateForDisplay(lastUpdated) ? `<p class="ai-date">${formatDateForDisplay(lastUpdated)}</p>` : '';
        card.innerHTML = `<div class="ai-commentary"><div class="ai-header"><h3>AI解説</h3>${dateHtml}</div><p>${commentary.replace(/\n/g, '<br>')}</p></div>`;
        container.appendChild(card);
    }

    function renderAllData(data) {
        console.log("Rendering all data:", data);
        const lastUpdatedEl = document.getElementById('last-updated');
        if (lastUpdatedEl && data.last_updated) { lastUpdatedEl.textContent = `Last updated: ${new Date(data.last_updated).toLocaleString('ja-JP')}`; }
        renderMarketOverview(document.getElementById('market-content'), data.market, data.last_updated);
        renderNews(document.getElementById('news-content'), data.news, data.last_updated);
        renderGridHeatmap(document.getElementById('nasdaq-heatmap-1d'), 'Nasdaq (1-Day)', data.nasdaq_heatmap_1d);
        renderGridHeatmap(document.getElementById('nasdaq-heatmap-1w'), 'Nasdaq (1-Week)', data.nasdaq_heatmap_1w);
        renderGridHeatmap(document.getElementById('nasdaq-heatmap-1m'), 'Nasdaq (1-Month)', data.nasdaq_heatmap_1m);
        renderHeatmapCommentary(document.getElementById('nasdaq-commentary'), data.nasdaq_heatmap?.ai_commentary, data.last_updated);
        renderGridHeatmap(document.getElementById('sp500-heatmap-1d'), 'SP500 & Sector ETFs (1-Day)', data.sp500_combined_heatmap_1d);
        renderGridHeatmap(document.getElementById('sp500-heatmap-1w'), 'SP500 & Sector ETFs (1-Week)', data.sp500_combined_heatmap_1w);
        renderGridHeatmap(document.getElementById('sp500-heatmap-1m'), 'SP500 & Sector ETFs (1-Month)', data.sp500_combined_heatmap_1m);
        renderHeatmapCommentary(document.getElementById('sp500-commentary'), data.sp500_heatmap?.ai_commentary, data.last_updated);
        renderIndicators(document.getElementById('indicators-content'), data.indicators, data.last_updated);
        renderColumn(document.getElementById('column-content'), data.column);
    }

    // --- Swipe Navigation ---
    function initSwipeNavigation() {
        const contentArea = document.getElementById('dashboard-content');
        let touchstartX = 0;
        let touchstartY = 0;
        let hasScrolledVertically = false;
        const verticalScrollThreshold = 10;
        const horizontalSwipeThreshold = 100;
        contentArea.addEventListener('touchstart', e => {
            touchstartX = e.touches[0].screenX;
            touchstartY = e.touches[0].screenY;
            hasScrolledVertically = false;
        }, { passive: true });
        contentArea.addEventListener('touchmove', e => {
            if (hasScrolledVertically) return;
            const touchmoveY = e.touches[0].screenY;
            const deltaY = Math.abs(touchmoveY - touchstartY);
            if (deltaY > verticalScrollThreshold) {
                hasScrolledVertically = true;
            }
        }, { passive: true });
        contentArea.addEventListener('touchend', e => {
            if (hasScrolledVertically) return;
            const touchendX = e.changedTouches[0].screenX;
            const deltaX = touchendX - touchstartX;
            if (Math.abs(deltaX) > horizontalSwipeThreshold) {
                const tabButtons = Array.from(document.querySelectorAll('.tab-button'))
                    .filter(btn => btn.style.display !== 'none');
                const currentIndex = tabButtons.findIndex(b => b.classList.contains('active'));

                if (currentIndex === -1) return;

                let nextIndex = (deltaX > 0) ? currentIndex - 1 : currentIndex + 1;
                if (nextIndex < 0) {
                    nextIndex = tabButtons.length - 1;
                } else if (nextIndex >= tabButtons.length) {
                    nextIndex = 0;
                }
                if (tabButtons[nextIndex]) {
                    tabButtons[nextIndex].click();
                }
            }
        }, { passive: true });
    }

    // --- Auto Reload Function ---
    function setupAutoReload() {
        const LAST_RELOAD_KEY = 'lastAutoReloadDate';
        setInterval(() => {
            const now = new Date();
            const day = now.getDay();
            const hours = now.getHours();
            const minutes = now.getMinutes();
            const isWeekday = day >= 1 && day <= 5;
            const isReloadTime = hours === 6 && minutes === 30;
            if (isWeekday && isReloadTime) {
                const today = now.toISOString().split('T')[0];
                const lastReloadDate = localStorage.getItem(LAST_RELOAD_KEY);
                if (lastReloadDate !== today) {
                    console.log('Auto-reloading page at 6:30 on a weekday...');
                    localStorage.setItem(LAST_RELOAD_KEY, today);
                    location.reload();
                }
            }
        }, 60000);
    }

    // --- App Initialization ---
    initializeApp();
    setupAutoReload();
});
