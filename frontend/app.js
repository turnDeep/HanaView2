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
            showAuthScreen();
            throw new Error('Authentication required');
        }
        return response;
    }

    // --- Main App Logic ---

    async function initializeApp() {
        try {
            if (AuthManager.isAuthenticated()) {
                showDashboard();
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
        const stage12Tab = document.querySelector('.tab-button[data-tab="stage12"]');

        console.log(`Applying permissions for level: ${permission}`);

        if (hwb200Tab) hwb200Tab.style.display = '';
        if (stage12Tab) stage12Tab.style.display = '';

        if (permission === 'standard') {
            console.log("Standard permission: Hiding 200MA and Stage1+2 tabs.");
            if (hwb200Tab) hwb200Tab.style.display = 'none';
            if (stage12Tab) stage12Tab.style.display = 'none';
        } else if (permission === 'secret') {
            console.log("Secret permission: Hiding Stage1+2 tab.");
            if (stage12Tab) stage12Tab.style.display = 'none';
        } else if (permission === 'ura') {
            console.log("Ura permission: All tabs visible.");
        }
    }

    function showDashboard() {
        if (authContainer) authContainer.style.display = 'none';
        if (dashboardContainer) dashboardContainer.style.display = 'block';

        applyTabPermissions();

        const notificationManager = new NotificationManager();
        notificationManager.init();

        if (!dashboardContainer.dataset.initialized) {
            console.log("HanaView Dashboard Initialized");
            initTabs();
            fetchDataAndRender();
            initSwipeNavigation();

            if (document.getElementById('hwb200-content')) {
                initHWB200MA();
            }
            if (document.getElementById('stage12-content')) {
                initStage12();
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
                showDashboard();
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
            if (targetTab === 'stage12' && window.stage12Manager) {
                window.stage12Manager.loadData();
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
            this.initEventListeners();
        }

        initEventListeners() {
            const analyzeBtn = document.getElementById('hwb-analyze-btn');
            if (analyzeBtn) {
                analyzeBtn.addEventListener('click', () => {
                    if (analyzeBtn.dataset.state === 'reset') {
                        this.resetAnalysisView();
                    } else {
                        this.analyzeTicker();
                    }
                });
            }

            const contentDiv = document.getElementById('hwb-content');
            if (contentDiv) {
                contentDiv.addEventListener('click', (e) => {
                    const analysisButton = e.target.closest('.hwb-analysis-button');
                    if (analysisButton) {
                        e.stopPropagation();
                        const symbol = analysisButton.dataset.symbol;
                        this.showAnalysisChart(symbol);
                        return;
                    }
                });
            }
        }

        async analyzeTicker() {
            const input = document.getElementById('hwb-ticker-input');
            const ticker = input.value.trim().toUpperCase();

            if (!ticker) {
                this.showStatus('ティッカーシンボルを入力してください', 'warning');
                return;
            }

            this.showStatus(`${ticker}のデータを確認中...`, 'info');

            try {
                let response = await fetchWithAuth(`/api/hwb/analyze_ticker?ticker=${ticker}`);

                if (!response.ok) {
                    if (response.status === 404) {
                        const error = await response.json();
                        this.showStatus(`ℹ️ ${error.detail}`, 'warning');

                        if (confirm(`${ticker}はまだ分析されていません。\n今すぐ分析しますか？（10-30秒かかります）`)) {
                            this.showStatus(`${ticker}を分析中... お待ちください`, 'info');
                            response = await fetchWithAuth(`/api/hwb/analyze_ticker?ticker=${ticker}&force=true`);

                            if (!response.ok) {
                                throw new Error(`分析に失敗しました: ${response.status}`);
                            }
                        } else {
                            this.showStatus('分析をキャンセルしました。', 'info');
                            return;
                        }
                    } else {
                        throw new Error(`エラーが発生しました: ${response.status}`);
                    }
                }

                const symbolData = await response.json();

                const summaryContainer = document.getElementById('hwb-content');
                if (summaryContainer) summaryContainer.style.display = 'none';

                const analysisContainer = document.getElementById('hwb-analysis-content');
                if (analysisContainer) {
                    analysisContainer.style.display = 'block';
                    analysisContainer.innerHTML = '';
                }

                this.renderAnalysisChart(symbolData);

                const analyzeBtn = document.getElementById('hwb-analyze-btn');
                if (analyzeBtn) {
                    analyzeBtn.textContent = 'リセット';
                    analyzeBtn.dataset.state = 'reset';
                }

                const hasSignals = symbolData.signals && symbolData.signals.length > 0;
                const statusMsg = hasSignals
                    ? `✅ ${ticker}: ${symbolData.signals.length}件のシグナル検出`
                    : `ℹ️ ${ticker}: 現在シグナルなし`;
                this.showStatus(statusMsg, 'info');

            } catch (error) {
                console.error('Analysis error:', error);
                this.showStatus(`❌ エラー: ${error.message}`, 'error');
                this.resetAnalysisView();
            }
        }

        resetAnalysisView() {
            const analysisContainer = document.getElementById('hwb-analysis-content');
            const summaryContainer = document.getElementById('hwb-content');
            const analyzeBtn = document.getElementById('hwb-analyze-btn');

            if (analysisContainer) {
                analysisContainer.style.display = 'none';
                analysisContainer.innerHTML = '';
            }
            if (summaryContainer) {
                summaryContainer.style.display = 'block';
            }
            if (analyzeBtn) {
                analyzeBtn.textContent = '分析';
                analyzeBtn.dataset.state = 'analyze';
            }
            this.showStatus('ティッカーを入力して分析を開始してください。', 'info');
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
                this.render();

                const { updated_at, summary } = this.summaryData;
                const displayDate = updated_at ? formatDateForDisplay(updated_at) : this.summaryData.scan_date;
                this.showStatus(
                    `最終更新: ${displayDate} | シグナル: ${summary.signals_count} | 監視銘柄: ${summary.candidates_count}`,
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

            summaryDiv.innerHTML = `
                <h2>200MAシステム</h2>
                <div class="scan-info">
                    データ更新: ${displayDate} | 処理銘柄: ${total_scanned}
                </div>
                <div class="hwb-summary-grid">
                    <div>
                        <h3>🚀 当日シグナル</h3>
                        <p class="summary-count">${summary.signals_count}</p>
                    </div>
                    <div>
                        <h3>📍 監視銘柄</h3>
                        <p class="summary-count">${summary.candidates_count}</p>
                    </div>
                </div>
            `;
            container.appendChild(summaryDiv);
        }

        renderLists(container) {
            const { signals = [], candidates = [] } = this.summaryData.summary;

            if (signals.length > 0) {
                this.renderSection(container, '🚀 当日シグナル', signals, 'signal');
            }
            if (candidates.length > 0) {
                this.renderSection(container, '📍 監視銘柄', candidates, 'candidate');
            }
        }

        async renderSection(container, title, items, type) {
            const section = document.createElement('div');
            section.className = 'hwb-charts-section';
            section.innerHTML = `<h2>${title}</h2>`;

            const grid = document.createElement('div');
            grid.className = 'hwb-chart-grid';

            const cards = items.map(item => {
                const card = this.createPlaceholderCard(item, type);
                grid.appendChild(card);
                return card;
            });

            section.appendChild(grid);
            container.appendChild(section);

            for (const card of cards) {
                await this.loadSymbolChart(card);
            }
        }

        createPlaceholderCard(item, type) {
            const card = document.createElement('div');
            card.className = 'hwb-chart-card';
            card.dataset.symbol = item.symbol;

            const scoreClass = item.score >= 80 ? 'high' : item.score >= 60 ? 'medium' : 'low';
            const signalType = type === 'signal' ? 'ブレイクアウト' : 'FVG検出';

            card.innerHTML = `
                <div class="hwb-chart-header">
                    <span class="hwb-chart-symbol">${item.symbol}</span>
                    <span class="hwb-chart-score ${scoreClass}">Score: ${item.score}/100</span>
                </div>
                <div class="hwb-chart-info">
                    <span>${signalType} on ${item.signal_date || item.fvg_date}</span>
                    <button class="hwb-analysis-button" data-symbol="${item.symbol}">詳細分析</button>
                </div>
                <div class="hwb-chart-placeholder">
                    <div class="loading-spinner-small"></div>
                    <p>チャートを読込中...</p>
                </div>
            `;
            return card;
        }

        async loadSymbolChart(card) {
            const symbol = card.dataset.symbol;
            card.dataset.chartLoaded = 'loading';

            const placeholder = card.querySelector('.hwb-chart-placeholder');
            placeholder.innerHTML = `<div class="loading-spinner-small"></div><p>チャートデータを読込中...</p>`;

            try {
                const response = await fetchWithAuth(`/api/hwb/symbols/${symbol}`);
                if (!response.ok) throw new Error(`Failed to load data for ${symbol}`);

                const symbolData = await response.json();

                placeholder.style.display = 'none';

                const chartContainer = document.createElement('div');
                chartContainer.className = 'hwb-chart-container';
                card.appendChild(chartContainer);

                this.renderLightweightChart(chartContainer, symbolData);

                card.dataset.chartLoaded = 'true';

            } catch (error) {
                console.error(`Error loading chart for ${symbol}:`, error);
                placeholder.innerHTML = `<p class="error-text">❌ チャート読込失敗</p>`;
                card.dataset.chartLoaded = 'error';
            }
        }

        renderLightweightChart(container, symbolData, width, height) {
            const chartData = symbolData.chart_data;

            if (!container || !chartData || !chartData.candles || chartData.candles.length === 0) {
                container.innerHTML = '<p>Chart data is not available.</p>';
                return;
            }

            const chart = LightweightCharts.createChart(container, {
                width: width || container.clientWidth,
                height: height || 300,
                layout: { backgroundColor: '#ffffff', textColor: '#333' },
                grid: { vertLines: { color: '#e1e1e1' }, horzLines: { color: '#e1e1e1' } },
                timeScale: { borderColor: '#cccccc', timeVisible: true },
            });

            const candleSeries = chart.addSeries(LightweightCharts.CandlestickSeries, {
                upColor: '#26a69a',
                downColor: '#ef5350',
                borderDownColor: '#ef5350',
                borderUpColor: '#26a69a',
                wickDownColor: '#ef5350',
                wickUpColor: '#26a69a',
            });
            candleSeries.setData(chartData.candles);

            // ボリュームチャート（v5の新しいペイン方式）
            if (chartData.volume && chartData.volume.length > 0) {
                const volumePane = chart.addPane();
                const volumeSeries = volumePane.addSeries(LightweightCharts.HistogramSeries, {
                    priceFormat: { type: 'volume' },
                });
                volumePane.priceScale().applyOptions({
                    scaleMargins: {
                        top: 0.9,
                        bottom: 0,
                    },
                });
                volumeSeries.setData(chartData.volume);
            }

            // 移動平均線
            const maLines = [
                { data: chartData.sma200, color: '#4a90e2', title: 'SMA 200' },
                { data: chartData.ema200, color: '#f5a623', title: 'EMA 200' },
                { data: chartData.weekly_sma200, color: '#d0021b', title: 'Weekly SMA 200' }
            ];

            maLines.forEach(ma => {
                if (ma.data && ma.data.length > 0) {
                    const maSeries = chart.addSeries(LightweightCharts.LineSeries, {
                        color: ma.color,
                        lineWidth: 2,
                        title: ma.title,
                        priceLineVisible: false,
                        lastValueVisible: false,
                    });
                    maSeries.setData(ma.data);
                }
            });

            // マーカー（v5の新しい方式）
            if (chartData.markers && chartData.markers.length > 0) {
                LightweightCharts.createSeriesMarkers(candleSeries, chartData.markers);
            }

            // シグナルがある場合、最新シグナルにズーム
            if (symbolData.signals && symbolData.signals.length > 0) {
                const latestSignal = symbolData.signals.sort((a, b) => new Date(b.breakout_date) - new Date(a.breakout_date))[0];
                const signalDate = new Date(latestSignal.breakout_date);

                const userTimezoneOffset = signalDate.getTimezoneOffset() * 60000;
                const signalTimeUTC = signalDate.getTime() + userTimezoneOffset;

                const fromDate = new Date(signalTimeUTC);
                fromDate.setMonth(fromDate.getMonth() - 3);
                const toDate = new Date(signalTimeUTC);
                toDate.setMonth(toDate.getMonth() + 3);

                const from = fromDate.toISOString().split('T')[0];
                const to = toDate.toISOString().split('T')[0];

                chart.timeScale().setVisibleRange({ from, to });
            } else {
                chart.timeScale().fitContent();
            }

            new ResizeObserver(entries => {
                if (entries.length > 0 && entries[0].contentRect.width > 0) {
                    chart.applyOptions({ width: entries[0].contentRect.width });
                }
            }).observe(container);
        }

        showStatus(message, type = 'info') {
            const statusDiv = document.getElementById('hwb-status');
            if (statusDiv) {
                statusDiv.textContent = message;
                statusDiv.className = `hwb-status-info ${type}`;
            }
        }

        async showAnalysisChart(symbol) {
            const summaryContainer = document.getElementById('hwb-content');
            if (summaryContainer) summaryContainer.style.display = 'none';

            const analysisContainer = document.getElementById('hwb-analysis-content');
            if (analysisContainer) {
                analysisContainer.style.display = 'block';
                analysisContainer.innerHTML = `<div class="loading-spinner"></div><p>Loading chart for ${symbol}...</p>`;
            }

            const analyzeBtn = document.getElementById('hwb-analyze-btn');
            if (analyzeBtn) {
                analyzeBtn.textContent = 'リセット';
                analyzeBtn.dataset.state = 'reset';
            }

            try {
                const response = await fetchWithAuth(`/api/hwb/symbols/${symbol}`);
                if (!response.ok) throw new Error(`Failed to load data for ${symbol}`);
                const symbolData = await response.json();
                this.renderAnalysisChart(symbolData);
            } catch (error) {
                console.error(`Error loading analysis chart for ${symbol}:`, error);
                this.showStatus(`❌ ${symbol}のチャート読込失敗`, 'error');
                this.resetAnalysisView();
            }
        }

        renderAnalysisChart(symbolData) {
            const container = document.getElementById('hwb-analysis-content');
            if (!container) return;

            container.innerHTML = '';

            if (!symbolData || !symbolData.chart_data || !symbolData.chart_data.candles || symbolData.chart_data.candles.length === 0) {
                container.innerHTML = `
                    <div class="hwb-analysis-info">
                        <h3>${symbolData.symbol} の分析結果</h3>
                        <p class="info-message">このシンボルはHWB戦略の条件を満たしていません。</p>
                    </div>
                `;
                return;
            }

            const infoSection = document.createElement('div');
            infoSection.className = 'hwb-analysis-info';
            infoSection.innerHTML = `
                <h3>${symbolData.symbol} の分析結果</h3>
                <div class="analysis-stats">
                    <div class="stat-item">
                        <span class="stat-label">セットアップ:</span>
                        <span class="stat-value">${symbolData.setups?.length || 0}件</span>
                    </div>
                    <div class="stat-item">
                        <span class="stat-label">FVG:</span>
                        <span class="stat-value">${symbolData.fvgs?.length || 0}件</span>
                    </div>
                    <div class="stat-item">
                        <span class="stat-label">シグナル:</span>
                        <span class="stat-value signal">${symbolData.signals?.length || 0}件</span>
                    </div>
                </div>
                <p class="last-updated">最終スキャン: ${symbolData.last_updated || 'N/A'}</p>
            `;
            container.appendChild(infoSection);

            const chartDiv = document.createElement('div');
            chartDiv.className = 'hwb-chart-container-large';
            container.appendChild(chartDiv);

            this.renderLightweightChart(chartDiv, symbolData, 900, 600);
        }
    }

    // --- Stage 1+2 Manager ---
    function initStage12() {
        window.stage12Manager = new Stage12Manager();
        console.log('Stage12Manager initialized');
    }

    class Stage12Manager {
        constructor() {
            this.summaryData = null;
            this.container = document.getElementById('stage12-content');
        }

        async loadData() {
            if (this.summaryData) {
                return;
            }
            this.showLoading('最新のステージ分析データを読み込み中...');
            try {
                const response = await fetchWithAuth('/api/stage/latest');
                if (!response.ok) {
                    if (response.status === 404) {
                        this.showError('ステージ分析データが見つかりません。スキャンを実行してください。');
                    } else {
                        throw new Error(`Server error: ${response.status}`);
                    }
                    return;
                }
                this.summaryData = await response.json();
                this.render();
            } catch (error) {
                console.error('Stage 1+2 summary loading error:', error);
                this.showError(`❌ データ読み込みエラー: ${error.message}`);
            }
        }

        render() {
            if (!this.summaryData || !this.summaryData.stocks || this.summaryData.stocks.length === 0) {
                this.showError('分析データが見つかりません。');
                return;
            }
            this.container.innerHTML = '';

            const header = document.createElement('div');
            header.className = 'stage12-header';
            header.innerHTML = `
                <h2>Stage 1 & 2 Candidates</h2>
                <p class="last-updated">Last Scan: ${formatDateForDisplay(this.summaryData.scan_timestamp)} | Found: ${this.summaryData.found_count} stocks</p>
            `;
            this.container.appendChild(header);

            const grid = document.createElement('div');
            grid.className = 'stage12-grid';
            this.container.appendChild(grid);

            this.summaryData.stocks.forEach(stock => {
                const stockCard = this.createStockCard(stock);
                grid.appendChild(stockCard);
            });
        }

        createStockCard(stock) {
            const card = document.createElement('div');
            card.className = 'stage12-card';
            card.dataset.symbol = stock.ticker;
            card.innerHTML = `
                <div class="stage12-card-header">
                    <h3>${stock.ticker}</h3>
                    <span class="stage-badge stage-${stock.current_stage}">Stage ${stock.current_stage}</span>
                </div>
                <div class="stage12-card-body">
                    <div class="info-grid">
                        <div><span>Price:</span> <strong>$${stock.latest_price.toFixed(2)}</strong></div>
                        <div><span>MA50:</span> <strong>$${stock.ma50.toFixed(2)}</strong></div>
                        <div><span>RS Rating:</span> <strong>${stock.rs_rating.toFixed(0)}</strong></div>
                        <div><span>Score:</span> <strong>${stock.score}</strong></div>
                    </div>
                    <div class="judgment-section">
                        <p><strong>Judgment:</strong> ${stock.judgment}</p>
                        <p><strong>Action:</strong> ${stock.action}</p>
                    </div>
                    <div class="chart-placeholder">Loading chart...</div>
                </div>
            `;
            card.addEventListener('click', () => this.showDetailedView(stock.ticker));
            return card;
        }

        async showDetailedView(ticker) {
            this.showLoading(`Loading detailed analysis for ${ticker}...`);
            try {
                const response = await fetchWithAuth(`/api/stage/symbol/${ticker}`);
                if (!response.ok) {
                    throw new Error(`Failed to load details for ${ticker} (Status: ${response.status})`);
                }
                const details = await response.json();
                this.renderDetailedView(details);
            } catch (error) {
                console.error(`Error fetching details for ${ticker}:`, error);
                this.showError(`❌ Failed to load analysis for ${ticker}.`);
            }
        }

        renderDetailedView(details) {
            this.container.innerHTML = '';

            const detailWrapper = document.createElement('div');
            detailWrapper.className = 'stage-detail-wrapper';

            const backButton = document.createElement('button');
            backButton.className = 'stage-detail-back-btn';
            backButton.innerHTML = '&larr; Back to List';
            backButton.onclick = () => this.render();

            const header = document.createElement('h2');
            header.textContent = `${details.ticker} - Detailed Analysis`;

            this.container.appendChild(backButton);
            this.container.appendChild(header);
            this.container.appendChild(detailWrapper);

            const chartContainer = document.createElement('div');
            chartContainer.id = 'stage-chart-container';
            chartContainer.className = 'stage-chart-container';

            const infoPanel = document.createElement('div');
            infoPanel.className = 'stage-info-panel';

            detailWrapper.appendChild(chartContainer);
            detailWrapper.appendChild(infoPanel);

            infoPanel.innerHTML = `
                <h4>Analysis Details</h4>
                <div class="info-item"><span>Ticker:</span> <strong>${details.ticker}</strong></div>
                <div class="info-item"><span>Stage:</span> <strong>${details.current_stage} (${details.stage_name})</strong></div>
                <div class="info-item"><span>Stage Start:</span> <strong>${details.stage_start_date}</strong></div>
                <hr>
                <div class="info-item"><span>Score:</span> <strong class="score">${details.score}</strong></div>
                <div class="info-item"><span>Judgment:</span> <strong>${details.judgment}</strong></div>
                <div class="info-item action"><span>Action:</span> <p>${details.action}</p></div>
                <hr>
                <div class="info-item"><span>Latest Price:</span> <strong>$${details.latest_price.toFixed(2)}</strong></div>
                <div class="info-item"><span>50-Day MA:</span> <strong>$${details.ma50.toFixed(2)}</strong></div>
                <div class="info-item"><span>RS Rating:</span> <strong>${details.rs_rating.toFixed(0)} / 100</strong></div>
                <div class="info-item"><span>ATR Multiple:</span> <strong>${details.atr_multiple.toFixed(2)}x</strong></div>
            `;

            if (details.chart_json) {
                this.renderStageChart(chartContainer, details);
            } else {
                chartContainer.innerHTML = '<p>Chart data not available.</p>';
            }
        }

        renderStageChart(container, details) {
            const chartData = details.chart_json;
            if (!container || !chartData || !chartData.candles || chartData.candles.length === 0) {
                container.innerHTML = '<p>Chart data is not available.</p>';
                return;
            }
            container.innerHTML = '';
            container.style.position = 'relative';

            const chart = LightweightCharts.createChart(container, {
                width: container.clientWidth,
                height: 500,
                layout: { backgroundColor: '#ffffff', textColor: '#333' },
                grid: { vertLines: { color: '#f1f1f1' }, horzLines: { color: '#f1f1f1' } },
                timeScale: { borderColor: '#cccccc', timeVisible: true },
                crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
            });

            const candleSeries = chart.addSeries(LightweightCharts.CandlestickSeries, {
                upColor: '#26a69a', downColor: '#ef5350', borderDownColor: '#ef5350',
                borderUpColor: '#26a69a', wickDownColor: '#ef5350', wickUpColor: '#26a69a',
            });
            candleSeries.setData(chartData.candles);

            // ボリュームチャート（v5の新しいペイン方式）
            if (chartData.volume && chartData.volume.length > 0) {
                const volumePane = chart.addPane();
                const volumeSeries = volumePane.addSeries(LightweightCharts.HistogramSeries, { 
                    priceFormat: { type: 'volume' } 
                });
                volumePane.priceScale().applyOptions({ 
                    scaleMargins: { top: 0.85, bottom: 0 } 
                });
                volumeSeries.setData(chartData.volume);
            }

            const maLines = [
                { data: chartData.ema9, color: '#FF6D00', title: 'EMA 9' },
                { data: chartData.ema21, color: '#2962FF', title: 'EMA 21' },
                { data: chartData.ma50, color: '#9C27B0', title: 'SMA 50' },
                { data: chartData.ma200, color: '#F50057', title: 'SMA 200' },
            ];
            maLines.forEach(ma => {
                if (ma.data && ma.data.length > 0) {
                    const maSeries = chart.addSeries(LightweightCharts.LineSeries, {
                        color: ma.color, lineWidth: 2, title: ma.title,
                        priceLineVisible: false, lastValueVisible: false,
                    });
                    maSeries.setData(ma.data);
                }
            });

            // Custom Stage Shading Overlay
            const stageOverlay = document.createElement('div');
            stageOverlay.className = 'stage-overlay';
            container.appendChild(stageOverlay);

            const stageColors = {
                1: 'rgba(38, 166, 154, 0.1)',
                2: 'rgba(255, 109, 0, 0.15)',
                3: 'rgba(239, 83, 80, 0.15)',
                4: 'rgba(156, 39, 176, 0.1)'
            };

            const drawStageOverlays = () => {
                stageOverlay.innerHTML = '';
                const timeScale = chart.timeScale();
                const chartWidth = container.clientWidth;

                const mainPane = container.querySelector('tr:first-child .chart-markup-table canvas');
                if (!mainPane) return;
                const mainPaneHeight = mainPane.clientHeight;

                if (!details.stage_history || details.stage_history.length === 0) return;

                for (let i = 0; i < details.stage_history.length; i++) {
                    const segment = details.stage_history[i];
                    const nextSegment = details.stage_history[i + 1];

                    const startCoord = timeScale.timeToCoordinate(segment.date);
                    const endCoord = nextSegment ? timeScale.timeToCoordinate(nextSegment.date) : chartWidth;

                    if (startCoord === null && endCoord === null) continue;

                    const left = Math.max(0, startCoord || 0);
                    const right = Math.min(chartWidth, endCoord || chartWidth);
                    const width = right - left;

                    if (width > 0) {
                        const rect = document.createElement('div');
                        rect.className = 'stage-rect';
                        rect.style.left = `${left}px`;
                        rect.style.width = `${width}px`;
                        rect.style.height = `${mainPaneHeight}px`;
                        rect.style.backgroundColor = stageColors[segment.stage] || 'transparent';

                        const label = document.createElement('span');
                        label.className = 'stage-label';
                        label.textContent = `第${segment.stage}ステージ`;
                        rect.appendChild(label);

                        stageOverlay.appendChild(rect);
                    }
                }
            };

            chart.timeScale().subscribeVisibleLogicalRangeChange(drawStageOverlays);
            new ResizeObserver(drawStageOverlays).observe(container);

            chart.timeScale().fitContent();
            setTimeout(drawStageOverlays, 50);
        }

        showLoading(message) {
            this.container.innerHTML = `
                <div class="loading-container">
                    <p>${message}</p>
                    <div class="loading-spinner"></div>
                </div>`;
        }

        showError(message) {
            this.container.innerHTML = `<div class="card"><p>${message}</p></div>`;
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
                const tabButtons = Array.from(document.querySelectorAll('.tab-button'));
                const currentIndex = tabButtons.findIndex(b => b.classList.contains('active'));
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
            const response = await fetchWithAuth('/api/subscribe', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(subscription)
            });
            if (!response.ok) {
                throw new Error(`Server returned ${response.status}`);
            }
            const result = await response.json();
            console.log('Push subscription registered:', result);
        } catch (error) {
            console.error('Error sending subscription to server:', error);
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