# HanaView 設計書

## 1. システムアーキテクチャ

### 1.1 全体構成
```
┌─────────────────────────────────────────────────────┐
│                Docker Container                      │
│                                                      │
│  ┌────────────┐  ┌─────────────┐  ┌─────────────┐ │
│  │  Frontend  │  │   Backend   │  │     Cron    │ │
│  │  (PWA)     │←→│  (FastAPI)  │←─│    Jobs     │ │
│  │  +SW       │  │  +Security  │  └─────────────┘ │
│  └────────────┘  └─────────────┘                   │
│                        ↓                            │
│    ┌──────────────────┴──────────────────┐         │
│    │        Data Storage Layer            │         │
│    ├──────────────┬──────────────────────┤         │
│    │ JSON Files   │ SQLite (HWB Cache)   │         │
│    │ + Security   │ + Subscriptions      │         │
│    └──────────────┴──────────────────────┘         │
└─────────────────────────────────────────────────────┘
                        ↓
         External APIs & Services
  ┌──────────┬──────────┬──────────┬──────────┐
  │ yfinance │ OpenAI   │  Web     │  CNN     │
  │   API    │   API    │ Scraping │ F&G API  │
  └──────────┴──────────┴──────────┴──────────┘
```

### 1.2 コンポーネント設計

#### 1.2.1 Frontend層
- **技術スタック：** HTML5, CSS3, Vanilla JavaScript, PWA
- **主要ライブラリ：** 
  - lightweight-charts（チャート表示）
  - D3.js（ヒートマップ）
  - rectangle-plugin.js（カスタムチャートプラグイン）
- **責務：**
  - UIレンダリング
  - 認証処理（PIN入力）
  - ユーザーインタラクション処理
  - データの可視化
  - レスポンシブ対応
  - **【NEW】Service Worker管理**
  - **【NEW】Push通知受信・表示**
  - **【NEW】IndexedDB/LocalStorageによる認証状態管理**

#### 1.2.2 Backend層
- **技術スタック：** Python 3.11, FastAPI
- **主要ライブラリ：**
  - yfinance: 金融データ取得
  - curl-cffi: HTTPリクエスト処理
  - beautifulsoup4: HTML解析
  - openai: AI機能
  - pandas: データ処理
  - matplotlib: Fear & Greedゲージ生成
  - **【NEW】python-jose: JWT処理**
  - **【NEW】pywebpush: Push通知送信**
  - **【NEW】cryptography: VAPID鍵生成**
- **責務：**
  - APIエンドポイント提供
  - データ取得・加工
  - AI解説生成
  - ファイル管理
  - **【NEW】認証処理（PIN検証、JWTトークン発行）**
  - **【NEW】Push通知管理**
  - **【NEW】HWB銘柄スキャン**
  - **【NEW】セキュリティキー管理**

#### 1.2.3 データ層
- **JSON形式：**
  - `data/data_YYYY-MM-DD.json`: 市場データ
  - `data/security_keys.json`: セキュリティキー
  - `data/push_subscriptions.json`: Push購読情報
  - `data/hwb/symbols/{TICKER}.json`: 個別銘柄分析データ
  - `data/hwb/daily/{YYYY-MM-DD}.json`: HWBスキャン結果
  
- **SQLite形式：**
  - `data/hwb/hwb_cache.db`: 価格データキャッシュ
    - daily_prices テーブル
    - weekly_prices テーブル
    - data_metadata テーブル

- **CSV形式：**
  - `backend/russell3000.csv`: Russell 3000銘柄リスト

#### 1.2.4 セキュリティ層【NEW】
- **SecurityManager：**
  - JWT Secret Keyの自動生成・管理
  - VAPIDキーペアの自動生成・管理
  - 環境変数またはファイルからのキー読み込み
  - 鍵の安全な保存と復旧
  
- **認証フロー：**
  ```
  1. ユーザー: PIN入力
  2. Backend: PIN検証
  3. Backend: JWT + 通知トークン発行
  4. Frontend: LocalStorage + IndexedDB保存
  5. Frontend: 認証ヘッダー付与
  6. Backend: トークン検証
  ```

#### 1.2.5 HWBスキャナー層【NEW】
- **HWBDataManager：**
  - SQLiteデータベース管理
  - yfinanceからのデータ取得
  - 増分更新処理
  - キャッシュ戦略
  
- **HWBAnalyzer：**
  - ルール①: トレンドチェック
  - ルール②: セットアップ検出
  - ルール③: FVG検出
  - ルール④: ブレイクアウト検出
  - スコアリング計算
  
- **HWBScanner：**
  - 並列処理制御（最大5ワーカー）
  - バッチ処理（20銘柄ごと）
  - 進捗管理
  - デイリーサマリー生成

## 2. データフロー設計

### 2.1 初回アクセスフロー【NEW】
```
ユーザーアクセス
    ↓
Frontend: 認証状態確認（LocalStorage）
    ↓
 認証あり？
    ├── YES → Dashboard表示
    └── NO → PIN認証画面表示
             ↓
       ユーザー: PIN入力
             ↓
       Backend: PIN検証
             ↓
       Backend: JWTトークン発行
             ↓
       Frontend: LocalStorage + IndexedDB保存
             ↓
       Dashboard表示
```

### 2.2 データ取得フロー（拡張版）
```
6:15 JST → Cron Job (fetch)
    ↓
MarketDataFetcher.fetch_all_data()
    ↓
┌──────────────────────────────────────┐
│ 1. VIXデータ取得（yfinance）          │
│ 2. 10年債データ取得                   │
│ 3. 経済指標取得（Monex）              │
│ 4. 決算カレンダー取得（Monex）        │
│ 5. Fear & Greed Index取得(CNN API)   │
│ 6. ニュース取得（Yahoo Finance）      │
│ 7. ヒートマップデータ取得             │
│    - NASDAQ 100 (Wikipedia + yfinance)│
│    - S&P 500 (Wikipedia + yfinance)   │
│    - Sector ETFs (yfinance)           │
└──────────────────────────────────────┘
    ↓
data_raw.json保存

6:28 JST → Cron Job (generate)
    ↓
MarketDataFetcher.generate_report_with_notification()
    ↓
┌──────────────────────────────────────┐
│ 1. AI市況解説生成（OpenAI）          │
│ 2. AIニュース分析生成                │
│ 3. AIヒートマップ解説生成            │
│ 4. AI指標・決算解説生成              │
│ 5. AIコラム生成（日次/週次）         │
│ 6. Fear & Greedゲージ画像生成        │
└──────────────────────────────────────┘
    ↓
data_YYYY-MM-DD.json保存
    ↓
Push通知送信（全登録ユーザー）
    ↓
7日以前のファイル削除
```

### 2.3 HWBスキャンフロー【NEW】
```
5:30 JST → Cron Job (hwb_scanner)
    ↓
HWBScanner.scan_all_symbols()
    ↓
┌──────────────────────────────────────┐
│ Russell 3000銘柄リスト読み込み       │
│        ↓                              │
│ 並列処理開始（最大5ワーカー）        │
│        ↓                              │
│ 各銘柄について：                      │
│   1. SQLiteキャッシュ確認            │
│   2. 必要なら yfinance取得            │
│   3. 日足・週足データ作成            │
│   4. SMA/EMA計算                     │
│   5. 4つのルールチェック              │
│   6. スコアリング                     │
│   7. チャートデータ生成               │
│   8. JSON保存                         │
│        ↓                              │
│ 20銘柄ごとに3秒待機（レート制限対策）│
└──────────────────────────────────────┘
    ↓
デイリーサマリー生成
    ↓
data/hwb/daily/YYYY-MM-DD.json保存
    ↓
latest.jsonリンク更新
```

### 2.4 Push通知フロー【NEW】
```
Frontend初期化
    ↓
Service Worker登録
    ↓
VAPID公開鍵取得（/api/vapid-public-key）
    ↓
ユーザー: 通知許可
    ↓
PushManager.subscribe()
    ↓
購読情報をBackendに送信（/api/subscribe）
    ↓
Backend: push_subscriptions.json保存
    ↓
─────────────────────
データ更新完了
    ↓
Backend: 全購読者にPush送信
    ↓
Service Worker: push イベント受信
    ↓
通知表示
    ↓
ユーザークリック
    ↓
アプリ起動・データリロード
```

## 3. API設計

### 3.1 認証API【NEW】

#### 3.1.1 POST /api/auth/verify
- **説明：** PIN認証とトークン発行
- **リクエスト：**
  ```json
  {
    "pin": "123456"
  }
  ```
- **レスポンス：**
  ```json
  {
    "success": true,
    "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "expires_in": 2592000,
    "notification_cookie_set": true
  }
  ```
- **エラー：** 401 Unauthorized

### 3.2 Push通知API【NEW】

#### 3.2.1 GET /api/vapid-public-key
- **説明：** VAPID公開鍵取得（認証不要）
- **レスポンス：**
  ```json
  {
    "public_key": "BKxL..."
  }
  ```

#### 3.2.2 POST /api/subscribe
- **説明：** Push通知購読登録
- **認証：** 必要（クッキーまたはヘッダー）
- **リクエスト：**
  ```json
  {
    "endpoint": "https://fcm.googleapis.com/...",
    "keys": {
      "p256dh": "...",
      "auth": "..."
    },
    "expirationTime": null
  }
  ```
- **レスポンス：**
  ```json
  {
    "status": "subscribed",
    "id": "hash_of_endpoint"
  }
  ```

#### 3.2.3 POST /api/send-notification
- **説明：** テスト通知送信
- **認証：** 必要
- **レスポンス：**
  ```json
  {
    "sent": 5,
    "failed": 0
  }
  ```

### 3.3 HWB API【NEW】

#### 3.3.1 GET /api/hwb/daily/latest
- **説明：** 最新のHWBスキャン結果取得
- **認証：** 必要
- **レスポンス：**
  ```json
  {
    "scan_date": "2025-10-02",
    "scan_time": "05:45:30",
    "total_scanned": 2847,
    "summary": {
      "signals_count": 12,
      "candidates_count": 45,
      "signals": [
        {
          "symbol": "AAPL",
          "signal_type": "s2_breakout",
          "score": 85,
          "signal_date": "2025-10-02"
        }
      ],
      "candidates": [...]
    },
    "updated_at": "2025-10-02T05:45:30+09:00"
  }
  ```

#### 3.3.2 GET /api/hwb/symbols/{symbol}
- **説明：** 個別銘柄の詳細データ取得
- **認証：** 必要
- **レスポンス：**
  ```json
  {
    "symbol": "AAPL",
    "last_updated": "2025-10-02T05:30:00",
    "last_scan": "2025-10-02",
    "trend_check": {
      "status": "passed",
      "weekly_sma200": true,
      "daily_sma200": true,
      "daily_ema200": true
    },
    "setups": [...],
    "fvgs": [...],
    "signals": [...],
    "chart_data": {
      "candles": [...],
      "sma200": [...],
      "ema200": [...],
      "weekly_sma200": [...],
      "zones": [...],
      "markers": [...]
    }
  }
  ```

#### 3.3.3 GET /api/hwb/analyze_ticker
- **説明：** 任意ティッカーの分析実行
- **認証：** 必要
- **パラメータ：**
  - `ticker`: ティッカーシンボル（必須）
  - `force`: 強制再分析（デフォルト: false）
- **レスポンス：** GET /api/hwb/symbols/{symbol} と同様

### 3.4 既存API（変更あり）

#### 3.4.1 GET /api/data
- **認証：** **必要（変更）**
- **ヘッダー：** `Authorization: Bearer <token>`
- その他は既存と同じ

#### 3.4.2 GET /api/health
- **認証：** 不要（変更なし）

## 4. UI/UX設計

### 4.1 画面構成（拡張版）

#### 4.1.1 認証画面【NEW】
```
┌─────────────────────────────┐
│     認証が必要です            │
│  6桁の認証コードを入力       │
├─────────────────────────────┤
│  [_] [_] [_] [_] [_] [_]   │
├─────────────────────────────┤
│     エラーメッセージ領域      │
├─────────────────────────────┤
│        [認証ボタン]          │
└─────────────────────────────┘
```

#### 4.1.2 メインレイアウト
```
┌─────────────────────────────┐
│      Tab Navigation          │
│ [市況][ニュース][Nasdaq]    │
│ [SP500][指標][コラム][200MA]│
├─────────────────────────────┤
│                             │
│      Content Area           │
│                             │
│   - 各タブコンテンツ         │
│   - スワイプナビゲーション   │
│                             │
└─────────────────────────────┘
```

#### 4.1.3 HWB 200MAタブ【NEW】
```
┌─────────────────────────────┐
│ [ティッカー入力] [分析ボタン]│
│ ステータス: 最終更新...      │
├─────────────────────────────┤
│ 🤖 AI判定システム            │
│ 当日シグナル: 12件           │
│ 監視候補: 45件              │
├─────────────────────────────┤
│ 🚀 当日シグナル              │
│ [AAPL] [MSFT] [NVDA] ...    │
├─────────────────────────────┤
│ 📍 監視候補                  │
│ [TSLA] [GOOGL] [META] ...   │
└─────────────────────────────┘

クリック時：
┌─────────────────────────────┐
│ AAPL の分析結果              │
│ セットアップ: 2件            │
│ FVG: 3件 | シグナル: 1件     │
├─────────────────────────────┤
│                             │
│   Lightweight Charts        │
│   - ローソク足               │
│   - SMA200/EMA200          │
│   - Setup Zones (黄色)      │
│   - FVG Zones (緑色)        │
│   - Breakout Markers        │
│                             │
└─────────────────────────────┘
```

### 4.2 カラースキーム（追加）
```css
/* 既存 */
--background: #E6F3F7;
--card-background: #FFFFFF;
--tab-text: #0fb1bd;
--tab-active-bg: #0fb1bd;
--text-primary: #212121;
--border-color: #e0e0e0;

/* HWB追加 */
--hwb-signal-bg: #d4edda;
--hwb-candidate-bg: #d1ecf1;
--hwb-score-high: #28a745;
--hwb-score-medium: #ffc107;
--hwb-score-low: #6c757d;
--hwb-setup-zone: rgba(255, 215, 0, 0.2);
--hwb-fvg-zone: rgba(0, 200, 83, 0.2);
--hwb-breakout-marker: #2962FF;
```

### 4.3 レスポンシブ対応
- **デスクトップ**（1024px以上）:
  - 2カラムレイアウト
  - HWBチャートグリッド: 2列
  
- **タブレット**（768px〜1023px）:
  - 1カラムレイアウト
  - HWBチャートグリッド: 1列
  
- **モバイル**（767px以下）:
  - シングルカラム
  - スワイプナビゲーション有効
  - PIN入力UI最適化

## 5. セキュリティ設計（拡張版）

### 5.1 認証・認可【NEW】

#### 5.1.1 PIN認証
- 6桁の数字
- 最大5回の失敗でロックアウト
- 環境変数での設定（`AUTH_PIN`）
- デフォルト: 123456（変更必須）

#### 5.1.2 JWTトークン
- **アルゴリズム：** HS256
- **有効期限：** 30日（設定可能）
- **クレーム：**
  ```json
  {
    "sub": "user",
    "type": "main",
    "exp": 1234567890
  }
  ```
- **保存先：** LocalStorage + IndexedDB

#### 5.1.3 通知トークン
- **有効期限：** 24時間（自動更新）
- **クレーム：**
  ```json
  {
    "sub": "user",
    "type": "notification",
    "exp": 1234567890
  }
  ```
- **保存先：** HttpOnlyクッキー（開発環境）、Secure Cookie（本番）

### 5.2 セキュリティキー管理【NEW】

#### 5.2.1 自動生成
- JWT Secret: 256ビット（32バイト）
- VAPID鍵: ECDSA P-256

#### 5.2.2 保存場所
```
data/
├── security_keys.json
│   ├── jwt_secret_key
│   ├── vapid_public_key
│   ├── vapid_private_key
│   ├── vapid_subject
│   └── created_at
```

#### 5.2.3 バックアップ
- 定期的な手動バックアップ推奨
- Docker volume の永続化
- `.gitignore` に追加

### 5.3 API セキュリティ

#### 5.3.1 認証フロー
```
Client Request
    ↓
Authorization Header Check
    ↓
JWT Verification
    ↓
   Valid?
    ├── YES → Process Request
    └── NO → 401 Unauthorized
```

#### 5.3.2 CORS設定
- 本番環境ではオリジン制限推奨
- 開発環境では許可

#### 5.3.3 レート制限
- yfinance: バッチサイズ20、3秒待機
- OpenAI: リトライ処理
- Push通知: 無効購読の自動削除

## 6. データベース設計【NEW】

### 6.1 SQLite: hwb_cache.db

#### 6.1.1 daily_prices テーブル
```sql
CREATE TABLE daily_prices (
    symbol TEXT NOT NULL,
    date DATE NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    volume INTEGER NOT NULL,
    sma200 REAL,
    ema200 REAL,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (symbol, date)
);
CREATE INDEX idx_daily_symbol_date ON daily_prices(symbol, date DESC);
```

#### 6.1.2 weekly_prices テーブル
```sql
CREATE TABLE weekly_prices (
    symbol TEXT NOT NULL,
    week_start_date DATE NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    volume INTEGER NOT NULL,
    sma200 REAL,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (symbol, week_start_date)
);
CREATE INDEX idx_weekly_symbol_date ON weekly_prices(symbol, week_start_date DESC);
```

#### 6.1.3 data_metadata テーブル
```sql
CREATE TABLE data_metadata (
    symbol TEXT PRIMARY KEY,
    first_date DATE,
    last_date DATE,
    last_updated TIMESTAMP,
    daily_count INTEGER,
    weekly_count INTEGER
);
CREATE INDEX idx_metadata_last_date ON data_metadata(last_date);
```

## 7. エラー処理設計（拡張版）

### 7.1 エラーコード定義（追加）

| コード | 説明 | 対処 |
|--------|------|------|
| E001 | OpenAI APIキー未設定 | 環境変数確認 |
| E002 | データファイル読み込み失敗 | ファイル存在確認 |
| E003 | 外部API接続失敗 | リトライまたはスキップ |
| E004 | Fear&Greedデータ取得失敗 | キャッシュまたはデフォルト値使用 |
| E005 | AI生成失敗 | デフォルトメッセージ表示 |
| E006 | ヒートマップデータ取得失敗 | 前回データまたは簡易表示 |
| **E007** | **HWBスキャンエラー** | **ログ記録、スキップ** |
| **E008** | **認証エラー** | **再ログイン要求** |
| **E009** | **Push通知エラー** | **無効購読削除** |

### 7.2 認証エラー処理【NEW】
```javascript
async function fetchWithAuth(url, options) {
    const response = await fetch(url, {
        ...options,
        headers: { ...options.headers, ...AuthManager.getAuthHeaders() }
    });
    
    if (response.status === 401) {
        await AuthManager.clearAuthData();
        showAuthScreen();
        throw new Error('Authentication required');
    }
    return response;
}
```

## 8. パフォーマンス設計（拡張版）

### 8.1 HWBスキャン最適化【NEW】
- **並列処理：** 最大5ワーカー
- **バッチサイズ：** 20銘柄ごと
- **キャッシング：** SQLiteによる増分更新
- **データ保持：** 10年分（約2500営業日）
- **処理時間：** 約60分（3000銘柄）

### 8.2 Frontend最適化
- **遅延読み込み：**
  - チャートライブラリ: 初回表示時のみ
  - 画像: Fear & Greed ゲージのみ
  
- **キャッシュ戦略：**
  - Service Worker によるリソースキャッシュ
  - LocalStorage による認証状態キャッシュ
  - IndexedDB による補助ストレージ

### 8.3 データベースパフォーマンス
- **インデックス：** symbol + date の複合インデックス
- **クエリ最適化：** LIMIT句の活用
- **バキューム：** 定期的なデータベース最適化

## 9. 運用設計（拡張版）

### 9.1 Cronスケジュール（更新）
```cron
# データ取得（月〜金 6:15）
15 6 * * 1-5 . /app/backend/cron-env.sh && /app/backend/run_job.sh fetch

# レポート生成＋Push通知（月〜金 6:28）
28 6 * * 1-5 . /app/backend/cron-env.sh && /app/backend/run_job.sh generate

# HWBスキャン（火〜土 5:30、米国市場終了30分後）
30 5 * * 2-6 . /app/backend/cron-env.sh && python -m backend.hwb_scanner_cli
```

### 9.2 ログ管理
```
logs/
├── cron.log          # Cron実行ログ
├── cron_error.log    # Cronエラーログ
├── fetch.log         # データ取得ログ
├── generate.log      # レポート生成ログ
└── hwb.log           # HWBスキャンログ
```

### 9.3 データ管理
```
data/
├── data_YYYY-MM-DD.json (7日間保持)
├── data.json (最新へのコピー)
├── security_keys.json (永続化)
├── push_subscriptions.json (永続化)
└── hwb/
    ├── hwb_cache.db (永続化)
    ├── symbols/ (随時更新)
    │   └── {TICKER}.json
    └── daily/ (随時追加)
        ├── YYYY-MM-DD.json
        └── latest.json
```

### 9.4 監視項目（追加）
- Cronジョブの実行状況
- 認証成功/失敗率
- Push通知送信成功率
- HWBスキャン完了率
- データベースサイズ
- APIクォータ使用状況

## 10. テスト設計（拡張版）

### 10.1 認証テスト【NEW】
- PIN認証の成功/失敗
- JWTトークンの発行/検証
- トークン有効期限の動作
- ロックアウト機能

### 10.2 Push通知テスト【NEW】
- 購読登録の成功/失敗
- 通知送信の成功/失敗
- 無効購読の自動削除
- Service Worker の動作

### 10.3 HWBスキャンテスト【NEW】
- 個別ルールの動作確認
- スコアリング計算の正確性
- SQLiteキャッシュの動作
- チャートデータ生成の確認

### 10.4 既存機能テスト
- データ取得関数のモック化
- AI生成機能のテスト
- エラー処理のテスト
- エンドツーエンドの動作確認
