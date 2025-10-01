# HanaView 詳細仕様書

## 1. システム仕様

### 1.1 動作環境仕様

#### 1.1.1 サーバー環境
| 項目 | 仕様 |
|------|------|
| OS | Linux (Docker対応、Debian Bookworm推奨) |
| Docker | 20.10以降 |
| Docker Compose | 2.0以降 |
| CPU | 2コア以上推奨（HWBスキャン時は4コア推奨） |
| メモリ | 8GB以上推奨（HWBスキャン実行時） |
| ストレージ | 20GB以上の空き容量（SQLite DB含む） |
| タイムゾーン | Asia/Tokyo（固定） |

#### 1.1.2 クライアント環境
| 項目 | 仕様 |
|------|------|
| ブラウザ | Chrome 90+, Safari 14+, Firefox 88+, Edge 90+ |
| 画面解像度 | デスクトップ: 1024x768以上、モバイル: 375x667以上 |
| JavaScript | 有効化必須 |
| Service Worker | 対応必須（Push通知機能） |
| IndexedDB | 対応必須（認証トークン保存） |
| HTTPS | 本番環境では必須（Push通知要件） |
| ネットワーク | ブロードバンド接続推奨 |

### 1.2 使用技術仕様

#### 1.2.1 Backend
| 技術 | バージョン | 用途 |
|------|------------|------|
| Python | 3.11-slim-bookworm | メイン言語 |
| FastAPI | 0.104.1 | Webフレームワーク |
| uvicorn | 0.24.0 | ASGIサーバー |
| yfinance | 0.2.65+ | 金融データ取得 |
| curl-cffi | 0.13.0+ | HTTPクライアント（ブラウザ偽装） |
| beautifulsoup4 | 4.12.2 | HTML解析 |
| lxml | 6.0.1 | HTMLパーサー |
| openai | 1.107.1 | AI機能 |
| pandas | 2.1.4 | データ処理 |
| matplotlib | 3.8.0 | Fear & Greedゲージ画像生成 |
| pytz | 2024.1 | タイムゾーン処理 |
| python-jose[cryptography] | 3.3.0 | JWT処理 |
| pywebpush | 2.0.1 | Push通知送信 |
| cryptography | 46.0.1 | VAPID鍵生成 |
| httpx | 0.25.2 | OpenAI HTTPクライアント |
| python-dotenv | 0.21.0 | 環境変数管理 |
| mplfinance | 0.12.10b0+ | 金融チャート |

#### 1.2.2 Frontend
| 技術 | バージョン | 用途 |
|------|------------|------|
| HTML5 | - | マークアップ |
| CSS3 | - | スタイリング |
| JavaScript | ES6+ | インタラクション |
| lightweight-charts | 最新（v5対応） | ローソク足チャート表示 |
| D3.js | v7 | ヒートマップ表示 |
| PWA | - | オフライン対応・通知 |
| Service Worker | - | Push通知受信 |

#### 1.2.3 Database
| 技術 | 用途 |
|------|------|
| SQLite3 | HWB価格データキャッシュ |
| JSON Files | 市況データ、設定データ |

## 2. データ仕様

### 2.1 データファイル仕様

#### 2.1.1 メインデータファイル
**ファイル名：** `data/data_YYYY-MM-DD.json`

**ファイル構造：**
```json
{
  "date": "2025-10-02",
  "last_updated": "2025-10-02T06:30:00+09:00",
  "market": {
    "vix": {
      "current": 15.23,
      "history": [
        {
          "time": "2025-10-01T09:00:00",
          "open": 15.10,
          "high": 15.45,
          "low": 15.05,
          "close": 15.23
        }
      ]
    },
    "t_note_future": {
      "current": 4.25,
      "history": [...]
    },
    "fear_and_greed": {
      "now": 48,
      "previous_close": 47,
      "prev_week": 45,
      "prev_month": 55,
      "prev_year": 70,
      "category": "Fear"
    },
    "ai_commentary": "現在の市場は..."
  },
  "news": {
    "summary": "今朝の3行サマリー...",
    "topics": [
      {
        "title": "トピックタイトル",
        "analysis": "事実、解釈、市場への影響を含む分析...",
        "url": "https://..."
      }
    ]
  },
  "nasdaq_heatmap_1d": {
    "stocks": [
      {
        "ticker": "AAPL",
        "performance": 2.5,
        "sector": "Technology",
        "industry": "Consumer Electronics",
        "market_cap": 3000000000000
      }
    ]
  },
  "nasdaq_heatmap_1w": {...},
  "nasdaq_heatmap_1m": {...},
  "nasdaq_heatmap": {
    "ai_commentary": "ナスダックの解説..."
  },
  "sp500_heatmap_1d": {...},
  "sp500_heatmap_1w": {...},
  "sp500_heatmap_1m": {...},
  "sector_etf_heatmap_1d": {
    "etfs": [
      {
        "ticker": "XLK",
        "performance": 1.8
      }
    ]
  },
  "sector_etf_heatmap_1w": {...},
  "sector_etf_heatmap_1m": {...},
  "sp500_combined_heatmap_1d": {
    "items": [...]
  },
  "sp500_heatmap": {
    "ai_commentary": "S&P500の解説..."
  },
  "indicators": {
    "economic": [
      {
        "datetime": "10/02 22:30",
        "name": "🇺🇸 ISM製造業景況指数",
        "importance": "★★★",
        "previous": "48.7",
        "forecast": "49.3",
        "type": "economic"
      }
    ],
    "us_earnings": [
      {
        "datetime": "10/02 16:00",
        "ticker": "AAPL",
        "company": "(Apple Inc.)",
        "type": "us_earnings"
      }
    ],
    "jp_earnings": [
      {
        "datetime": "10/02 15:00",
        "ticker": "7203",
        "company": "(トヨタ自動車)",
        "type": "jp_earnings"
      }
    ],
    "economic_commentary": "AI経済指標解説...",
    "earnings_commentary": "AI決算解説..."
  },
  "column": {
    "daily_report": {
      "title": "AI解説",
      "date": "2025-10-02T06:28:00+09:00",
      "content": "⭐本日の注目ポイント\n..."
    }
  }
}
```

#### 2.1.2 中間データファイル
**ファイル名：** `data/data_raw.json`
**用途：** データ取得（fetch）とレポート生成（generate）の分離
**保持期間：** 次回実行まで
**構造：** 最終データからAI生成コンテンツを除いたもの

#### 2.1.3 セキュリティキーファイル【NEW】
**ファイル名：** `data/security_keys.json`
**パーミッション：** 0600（読み取り専用、所有者のみ）

```json
{
  "jwt_secret_key": "64文字のHEX文字列",
  "vapid_public_key": "Base64 URL-safe文字列（パディングなし）",
  "vapid_private_key": "Base64 URL-safe文字列（パディングなし）",
  "vapid_subject": "mailto:admin@hanaview.local",
  "created_at": "2025-10-02T00:00:00",
  "note": "Auto-generated security keys. DO NOT SHARE!"
}
```

#### 2.1.4 Push購読情報ファイル【NEW】
**ファイル名：** `data/push_subscriptions.json`

```json
{
  "subscription_id_hash": {
    "endpoint": "https://fcm.googleapis.com/...",
    "keys": {
      "p256dh": "...",
      "auth": "..."
    },
    "expirationTime": null
  }
}
```

#### 2.1.5 HWBデイリーサマリー【NEW】
**ファイル名：** `data/hwb/daily/YYYY-MM-DD.json`、`data/hwb/daily/latest.json`

```json
{
  "scan_date": "2025-10-02",
  "scan_time": "05:45:30",
  "scan_duration_seconds": 1234.56,
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
    "candidates": [
      {
        "symbol": "TSLA",
        "signal_type": "s1_fvg",
        "score": 72,
        "fvg_date": "2025-10-01"
      }
    ]
  },
  "performance": {
    "avg_time_per_symbol_ms": 432.1
  }
}
```

#### 2.1.6 HWB個別銘柄データ【NEW】
**ファイル名：** `data/hwb/symbols/{TICKER}.json`

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
  "setups": [
    {
      "id": "setup_20251001",
      "date": "2025-10-01",
      "zone_upper": 175.50,
      "zone_lower": 174.80,
      "sma200": 175.00,
      "ema200": 175.30,
      "candle": {
        "open": 175.00,
        "close": 175.20,
        "high": 175.50,
        "low": 174.80
      }
    }
  ],
  "fvgs": [
    {
      "id": "fvg_20251002_123",
      "setup_id": "setup_20251001",
      "formation_date": "2025-10-02",
      "candle_1_high": 174.50,
      "candle_3_low": 176.00,
      "upper_bound": 176.00,
      "lower_bound": 174.50,
      "gap_size": 1.50,
      "gap_percentage": 0.86,
      "ma_proximity": {
        "condition_a_met": false,
        "condition_b_met": true,
        "closest_ma": "sma200",
        "distance_percentage": 0.05
      },
      "status": "active"
    }
  ],
  "signals": [
    {
      "id": "signal_20251002",
      "setup_id": "setup_20251001",
      "fvg_id": "fvg_20251002_123",
      "signal_type": "s2_breakout",
      "signal_date": "2025-10-02",
      "breakout_price": 178.50,
      "resistance_price": 177.00,
      "breakout_percentage": 0.85,
      "score": 85
    }
  ],
  "chart_data": {
    "candles": [
      {
        "time": "2025-10-01",
        "open": 175.00,
        "high": 175.50,
        "low": 174.80,
        "close": 175.20
      }
    ],
    "sma200": [
      {"time": "2025-10-01", "value": 175.00}
    ],
    "ema200": [
      {"time": "2025-10-01", "value": 175.30}
    ],
    "weekly_sma200": [
      {"time": "2025-10-01", "value": 174.50}
    ],
    "zones": [
      {
        "type": "setup",
        "id": "setup_20251001",
        "startTime": "2025-10-01",
        "endTime": "2025-10-02",
        "topValue": 175.50,
        "bottomValue": 174.80,
        "fillColor": "rgba(255, 215, 0, 0.2)",
        "borderColor": "#FFD700"
      },
      {
        "type": "fvg",
        "id": "fvg_20251002_123",
        "startTime": "2025-10-02",
        "endTime": "2025-10-02",
        "topValue": 176.00,
        "bottomValue": 174.50,
        "fillColor": "rgba(0, 200, 83, 0.2)",
        "borderColor": "#00C853"
      }
    ],
    "markers": [
      {
        "time": "2025-10-02",
        "position": "belowBar",
        "color": "#2962FF",
        "shape": "arrowUp",
        "text": "B",
        "size": 2,
        "id": "signal_20251002"
      }
    ]
  }
}
```

### 2.2 データベース仕様【NEW】

#### 2.2.1 SQLite: hwb_cache.db
**ファイル名：** `data/hwb/hwb_cache.db`
**用途：** HWB戦略用の価格データキャッシュ
**保持期間：** 10年分（約2500営業日）

**テーブル定義：**

**daily_prices テーブル**
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

**weekly_prices テーブル**
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

**data_metadata テーブル**
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

### 2.3 ログファイル仕様

#### 2.3.1 Cronログ
**ファイル名：** `logs/cron.log`
```
2025-10-02 06:15:00: Starting job: fetch
2025-10-02 06:20:00: Successfully completed job: fetch
2025-10-02 06:28:00: Starting job: generate
2025-10-02 06:32:00: Successfully completed job: generate
```

#### 2.3.2 処理ログ
- `logs/fetch.log` - データ取得ログ
- `logs/generate.log` - レポート生成ログ
- `logs/hwb.log` - HWBスキャンログ
- `logs/cron_error.log` - Cronエラーログ

**フォーマット：** `YYYY-MM-DD HH:MM:SS - logger_name - LEVEL - メッセージ`

## 3. API仕様

### 3.1 認証API【NEW】

#### 3.1.1 POST /api/auth/verify
**説明：** PIN認証とJWTトークン発行

**リクエスト：**
```json
{
  "pin": "123456"
}
```

**レスポンス（成功）：**
```json
{
  "success": true,
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "expires_in": 2592000,
  "notification_cookie_set": true
}
```

**レスポンス（失敗）：**
- ステータスコード: 401 Unauthorized
```json
{
  "detail": "Incorrect authentication code"
}
```

**注意事項：**
- メイン認証用トークン（30日間有効）をレスポンスで返す
- 通知用トークン（24時間有効）をHttpOnlyクッキーで設定
- 最大5回の失敗でロックアウト（フロントエンド実装）

### 3.2 Push通知API【NEW】

#### 3.2.1 GET /api/vapid-public-key
**説明：** VAPID公開鍵取得（認証不要）

**リクエスト：** なし

**レスポンス：**
```json
{
  "public_key": "BKxL...（Base64 URL-safe文字列）"
}
```

#### 3.2.2 POST /api/subscribe
**説明：** Push通知購読登録
**認証：** 必要（クッキーまたはAuthorizationヘッダー）

**リクエスト：**
```json
{
  "endpoint": "https://fcm.googleapis.com/...",
  "keys": {
    "p256dh": "Base64文字列",
    "auth": "Base64文字列"
  },
  "expirationTime": null
}
```

**レスポンス：**
```json
{
  "status": "subscribed",
  "id": "hash_of_endpoint"
}
```

#### 3.2.3 POST /api/send-notification
**説明：** テスト通知送信（管理者機能）
**認証：** 必要

**リクエスト：** なし

**レスポンス：**
```json
{
  "sent": 5,
  "failed": 0
}
```

### 3.3 市場データAPI

#### 3.3.1 GET /api/data
**説明：** 最新の市場データ取得
**認証：** 必要【変更】

**リクエストヘッダー：**
```
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

**レスポンス：** セクション2.1.1のJSON構造

**ステータスコード：**
- 200: 成功
- 401: 認証失敗
- 404: データファイルなし
- 500: サーバーエラー

#### 3.3.2 GET /api/health
**説明：** ヘルスチェック
**認証：** 不要

**レスポンス：**
```json
{
  "status": "healthy"
}
```

### 3.4 HWB戦略API【NEW】

#### 3.4.1 GET /api/hwb/daily/latest
**説明：** 最新のHWBスキャン結果取得
**認証：** 必要

**レスポンス：** セクション2.1.5のJSON構造

**追加フィールド：**
- `updated_at`: ファイル更新日時（ISO 8601形式）

**ステータスコード：**
- 200: 成功
- 401: 認証失敗
- 404: スキャン結果なし
- 500: サーバーエラー

#### 3.4.2 GET /api/hwb/symbols/{symbol}
**説明：** 個別銘柄の詳細データ取得
**認証：** 必要

**パラメータ：**
- `symbol`: ティッカーシンボル（大文字、例: AAPL）

**レスポンス：** セクション2.1.6のJSON構造

**ステータスコード：**
- 200: 成功
- 400: 無効なシンボル形式
- 401: 認証失敗
- 404: データなし
- 500: サーバーエラー

#### 3.4.3 GET /api/hwb/analyze_ticker
**説明：** 任意ティッカーの分析実行
**認証：** 必要

**クエリパラメータ：**
- `ticker`: ティッカーシンボル（必須）
- `force`: 強制再分析フラグ（デフォルト: false）

**動作：**
- `force=false`: 既存データを返す、なければ404
- `force=true`: 強制的に再分析を実行（10-30秒）

**レスポンス：** セクション2.1.6のJSON構造

**エラーレスポンス例（force=false、データなし）：**
```json
{
  "detail": "分析データが見つかりません。新規に分析しますか？"
}
```

**ステータスコード：**
- 200: 成功
- 400: パラメータエラー
- 401: 認証失敗
- 404: データなし（force=false時）
- 500: 分析失敗

### 3.5 外部API仕様

#### 3.5.1 OpenAI API
**エンドポイント：** `https://api.openai.com/v1/chat/completions`
**モデル：** 環境変数`OPENAI_MODEL`（デフォルト: gpt-4.1）

**リクエスト例：**
```python
{
  "model": "gpt-4.1",
  "messages": [
    {"role": "system", "content": "You are a helpful assistant designed to output JSON."},
    {"role": "user", "content": "プロンプト"}
  ],
  "max_tokens": 500,
  "temperature": 0.7,
  "response_format": {"type": "json_object"}
}
```

**特記事項：**
- `response_format`で必ずJSON出力を指定
- `httpx.Client(trust_env=False)`でプロキシを無効化
- エラー時はデフォルトメッセージで代替

#### 3.5.2 yfinance データ取得
**使用ライブラリ：** yfinance 0.2.65+
**セッション設定：** `curl_cffi.Session(impersonate="safari15_5")`

**主要ティッカー：**
- VIX: `^VIX`
- 10年債利回り: `^TNX`
- S&P500: `^GSPC`
- NASDAQ: `^IXIC`
- DOW: `^DJI`

**データ取得例：**
```python
ticker = yf.Ticker("^VIX", session=self.yf_session)
hist = ticker.history(period="60d", interval="1h")
hist.index = hist.index.tz_convert('Asia/Tokyo')
resampled = hist['Close'].resample('4h').ohlc()
```

**レート制限対策：**
- バッチサイズ: 20銘柄
- バッチ間待機: 3秒
- リトライ処理: 最大3回

#### 3.5.3 CNN Fear & Greed API
**エンドポイント：** `https://production.dataviz.cnn.io/index/fearandgreed/graphdata/{START_DATE}`

**データ取得：**
```python
start_date = (datetime.now() - timedelta(days=400)).strftime('%Y-%m-%d')
url = f"https://production.dataviz.cnn.io/index/fearandgreed/graphdata/{start_date}"
response = self.http_session.get(url)
data = response.json()
fg_data = data['fear_and_greed_historical']['data']
```

#### 3.5.4 Monex 経済指標・決算カレンダー
**経済指標URL：** `https://mst.monex.co.jp/pc/servlet/ITS/report/EconomyIndexCalendar`
**米国決算URL：** `https://mst.monex.co.jp/mst/servlet/ITS/fi/FIClosingCalendarUSGuest`
**日本決算URL：** `https://mst.monex.co.jp/mst/servlet/ITS/fi/FIClosingCalendarJPGuest`

**取得方法：**
- `curl_cffi.Session`でHTTP取得
- `BeautifulSoup`でHTML解析
- `pandas.read_html`でテーブル抽出

**文字コード：** Shift_JIS

## 4. 処理仕様

### 4.1 データ取得処理（fetch）

#### 4.1.1 実行タイミング
- **Cron設定：** 月〜金曜 6:15 JST
- **所要時間：** 約5-10分

#### 4.1.2 処理フロー
```
1. VIX指数データ取得（yfinance、60日分）
   ↓
2. 米国10年債金利データ取得（yfinance、60日分）
   ↓
3. Fear & Greed Index取得（CNN API、400日分）
   ↓
4. Fear & Greedゲージ画像生成（matplotlib）
   ↓
5. 経済指標カレンダー取得（Monex、26時間分）
   ↓
6. 決算カレンダー取得（米国・日本、Monex）
   ↓
7. ニュース取得（Yahoo Finance、yfinance API）
   - 月曜: 168時間分
   - 火〜金: 24時間分
   ↓
8. ヒートマップデータ取得
   - NASDAQ 100銘柄リスト（Wikipedia）
   - S&P 500銘柄リスト（Wikipedia）
   - 各銘柄の1d/1w/1mパフォーマンス（yfinance）
   - セクターETF（XLK, XLY, XLV等）のパフォーマンス
   ↓
9. data_raw.json保存
```

#### 4.1.3 Fear & Greed Index取得 詳細
```python
def fetch_fear_greed_index(self):
    start_date = (datetime.now() - timedelta(days=400)).strftime('%Y-%m-%d')
    url = f"{CNN_FEAR_GREED_URL}{start_date}"
    response = self.http_session.get(url, timeout=30)
    api_data = response.json()
    fg_data = api_data['fear_and_greed_historical']['data']
    
    current_value = fg_data[-1]['y']
    previous_close = self._get_historical_value(fg_data, 1)
    week_ago = self._get_historical_value(fg_data, 7)
    month_ago = self._get_historical_value(fg_data, 30)
    year_ago = self._get_historical_value(fg_data, 365)
    
    self.data['market']['fear_and_greed'] = {
        'now': round(current_value),
        'previous_close': round(previous_close) if previous_close else None,
        'prev_week': round(week_ago) if week_ago else None,
        'prev_month': round(month_ago) if month_ago else None,
        'prev_year': round(year_ago) if year_ago else None,
        'category': self._get_fear_greed_category(current_value)
    }
    
    # チャートデータ準備・画像生成
    chart_data = {...}
    generate_fear_greed_chart(chart_data)
```

### 4.2 レポート生成処理（generate）

#### 4.2.1 実行タイミング
- **Cron設定：** 月〜金曜 6:28 JST
- **所要時間：** 約3-5分

#### 4.2.2 処理フロー
```
1. data_raw.json読み込み
   ↓
2. AI市況解説生成（OpenAI API）
   - VIX、10年債、Fear & Greedデータ
   - 過去1ヶ月の推移分析
   - 300字程度
   ↓
3. AIニュース分析生成（OpenAI API）
   - 3行サマリー
   - 主要トピック3つ
   ↓
4. AIヒートマップ解説生成（OpenAI API）
   - NASDAQ解説（200-250字）
   - S&P500解説（250-300字、セクター分析含む）
   ↓
5. AI経済指標・決算解説生成（OpenAI API）
   - 経済指標解説（月曜: 400字、火〜金: 300字）
   - 決算解説（月曜: 400字、火〜金: 300字）
   ↓
6. AIコラム生成（OpenAI API）
   - 月曜: 週次レポート（400字）
   - 火〜金: 日次レポート（300字）
   - hana-memo-202509.txtを参考資料として使用
   ↓
7. data_YYYY-MM-DD.json保存
   ↓
8. data.json（最新へのコピー）更新
   ↓
9. Push通知送信（全登録ユーザー）
   ↓
10. 7日以前のdata_*.json削除
```

#### 4.2.3 AI生成例（市況解説）
```python
def generate_market_commentary(self):
    fg_now = self.data['market']['fear_and_greed']['now']
    vix_history = self.data['market']['vix']['history']
    tnote_history = self.data['market']['t_note_future']['history']
    
    prompt = f"""
あなたはプロの金融アナリストです。以下の市場データを分析し、
特にこの1ヶ月間の各指標の「推移」から読み取れる市場センチメントの変化を、
日本の個人投資家向けに300字程度で分かりやすく解説してください。

# 分析対象データ
- Fear & Greed Index: 現在{fg_now}、1週間前{fg_week}、1ヶ月前{fg_month}
- VIX指数: 過去1ヶ月の推移 {vix_history_str}
- 米国10年債金利: 過去1ヶ月の推移 {tnote_history_str}

# 出力形式
{{"response": "ここに解説を記述"}}
"""
    
    response = self._call_openai_api(
        messages=[
            {"role": "system", "content": "You are a helpful assistant designed to output JSON."},
            {"role": "user", "content": prompt}
        ],
        max_tokens=500,
        response_format={"type": "json_object"}
    )
    
    self.data['market']['ai_commentary'] = response['response']
```

### 4.3 HWBスキャン処理【NEW】

#### 4.3.1 実行タイミング
- **Cron設定：** 火〜土曜 5:30 JST（米国市場終了30分後）
- **所要時間：** 約50-70分（約3000銘柄）

#### 4.3.2 処理フロー
```
1. Russell 3000銘柄リスト読み込み（CSV）
   ↓
2. HWBDataManager初期化
   - SQLiteデータベース接続
   - テーブル存在確認・作成
   ↓
3. 並列スキャン開始（最大5ワーカー）
   ↓
4. 各銘柄について（バッチサイズ20）：
   ├─ キャッシュ確認（data_metadata）
   ├─ 必要なら yfinance で増分データ取得
   ├─ 日足・週足データ作成
   ├─ SMA200/EMA200計算
   ├─ HWBAnalyzer実行：
   │  ├─ ルール①: トレンドチェック
   │  ├─ ルール②: セットアップ検出
   │  ├─ ルール③: FVG検出
   │  └─ ルール④: ブレイクアウト検出
   ├─ スコアリング計算（0-100点）
   ├─ チャートデータ生成（lightweight-charts用）
   └─ JSON保存（data/hwb/symbols/{TICKER}.json）
   ↓
5. 20銘柄ごとに3秒待機（レート制限対策）
   ↓
6. デイリーサマリー生成
   - シグナル一覧
   - 候補一覧
   - パフォーマンス統計
   ↓
7. data/hwb/daily/YYYY-MM-DD.json保存
   ↓
8. latest.jsonリンク更新
```

#### 4.3.3 HWBルール詳細

**ルール①: トレンドチェック**
```python
def check_rule1(self, df_daily, df_weekly):
    df_daily['weekly_sma200_val'] = df_weekly['sma200'].reindex(df_daily.index, method='ffill')
    latest = df_daily.iloc[-1]
    
    results = {
        "weekly_sma200": latest['close'] > latest['weekly_sma200_val'],
        "daily_sma200": latest['close'] > latest['sma200'],
        "daily_ema200": latest['close'] > latest['ema200']
    }
    
    # 週足SMA200上 AND (日足SMA200上 OR 日足EMA200上)
    if results["weekly_sma200"] and (results["daily_sma200"] or results["daily_ema200"]):
        results["status"] = "passed"
    else:
        results["status"] = "failed"
    
    return results
```

**ルール②: セットアップ検出**
```python
def find_setups(self, df_daily):
    setups = []
    valid_data = df_daily[df_daily['sma200'].notna() & df_daily['ema200'].notna()]
    
    for i in range(len(valid_data)):
        row = valid_data.iloc[i]
        zone_upper = max(row['sma200'], row['ema200'])
        zone_lower = min(row['sma200'], row['ema200'])
        
        # ローソク足のOPENとCLOSEがゾーン内
        if (zone_lower <= row['open'] <= zone_upper and 
            zone_lower <= row['close'] <= zone_upper):
            setups.append({
                'id': f"setup_{valid_data.index[i].strftime('%Y%m%d')}",
                'date': valid_data.index[i].strftime('%Y-%m-%d'),
                'zone_upper': zone_upper,
                'zone_lower': zone_lower,
                'sma200': row['sma200'],
                'ema200': row['ema200'],
                'candle': {...}
            })
    
    return setups
```

**ルール③: FVG検出**
```python
def detect_fvg(self, df_daily, setup):
    fvgs = []
    setup_date = datetime.strptime(setup['date'], '%Y-%m-%d').date()
    setup_idx = df_daily.index.get_loc(setup_date)
    
    # セットアップ後30日間を検索
    search_end = min(setup_idx + FVG_SEARCH_DAYS, len(df_daily) - 2)
    
    for i in range(setup_idx + 2, search_end):
        c1 = df_daily.iloc[i-2]  # 1本目
        c2 = df_daily.iloc[i-1]  # 2本目（スキップ）
        c3 = df_daily.iloc[i]    # 3本目
        
        # FVG条件: c3のLow > c1のHigh
        if c3['low'] > c1['high']:
            gap = c3['low'] - c1['high']
            ma_proximity = self._check_ma_proximity(c3, c1)
            
            # 移動平均線の近傍チェック
            if ma_proximity['condition_a_met'] or ma_proximity['condition_b_met']:
                fvgs.append({
                    'id': f"fvg_{df_daily.index[i].strftime('%Y%m%d')}_{i}",
                    'setup_id': setup['id'],
                    'formation_date': df_daily.index[i].strftime('%Y-%m-%d'),
                    'upper_bound': c3['low'],
                    'lower_bound': c1['high'],
                    'gap_size': gap,
                    'gap_percentage': (gap / c1['high']) * 100,
                    'ma_proximity': ma_proximity,
                    'status': 'active'
                })
    
    return fvgs
```

**ルール④: ブレイクアウト検出**
```python
def check_breakout(self, df_daily, setup, fvg):
    setup_idx = df_daily.index.get_loc(setup_date)
    fvg_idx = df_daily.index.get_loc(fvg_date)
    
    # セットアップ後からFVG前までの最高値を抵抗線とする
    resistance_high = df_daily.iloc[setup_idx + 1 : fvg_idx]['high'].max()
    
    # FVG後にFVG下限を割り込んだらFVG無効
    if df_daily.iloc[fvg_idx + 1:]['low'].min() < fvg['lower_bound']:
        fvg['status'] = 'violated'
        return None
    
    # 現在の終値が抵抗線を上抜け（閾値: 0.1%）
    current = df_daily.iloc[-1]
    if current['close'] > resistance_high * (1 + BREAKOUT_THRESHOLD):
        fvg['status'] = 'consumed'
        return {
            'id': f"signal_{df_daily.index[-1].strftime('%Y%m%d')}",
            'signal_type': 's2_breakout',
            'signal_date': df_daily.index[-1].strftime('%Y-%m-%d'),
            'breakout_price': current['close'],
            'resistance_price': resistance_high,
            'breakout_percentage': (current['close'] / resistance_high - 1) * 100
        }
    
    return None
```

### 4.4 フロントエンド処理

#### 4.4.1 初期化処理（認証対応版）
```javascript
async function initializeApp() {
    // 認証状態確認
    if (AuthManager.isAuthenticated()) {
        showDashboard();
    } else {
        showAuthScreen();
    }
}

async function showDashboard() {
    // 認証済み
    authContainer.style.display = 'none';
    dashboardContainer.style.display = 'block';
    
    // 通知マネージャー初期化
    const notificationManager = new NotificationManager();
    await notificationManager.init();
    
    // タブ初期化
    initTabs();
    
    // データ取得・レンダリング
    await fetchDataAndRender();
    
    // HWB200MAマネージャー初期化
    if (document.getElementById('hwb200-content')) {
        initHWB200MA();
    }
}
```

#### 4.4.2 認証処理【NEW】
```javascript
async function handleAuthSubmit() {
    const pin = pinInputs.map(input => input.value).join('');
    
    const response = await fetch('/api/auth/verify', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pin })
    });
    
    const data = await response.json();
    
    if (response.ok && data.success) {
        // LocalStorage + IndexedDB保存
        await AuthManager.setAuthData(data.token, data.expires_in);
        showDashboard();
    } else {
        // エラー表示
        failedAttempts++;
        if (failedAttempts >= MAX_ATTEMPTS) {
            // ロックアウト
        }
    }
}
```

#### 4.4.3 認証付きFetch【NEW】
```javascript
async function fetchWithAuth(url, options = {}) {
    const authHeaders = AuthManager.getAuthHeaders();
    const response = await fetch(url, {
        ...options,
        headers: { ...options.headers, ...authHeaders }
    });
    
    if (response.status === 401) {
        // 認証失効時の処理
        await AuthManager.clearAuthData();
        showAuthScreen();
        throw new Error('Authentication required');
    }
    
    return response;
}
```

#### 4.4.4 Push通知初期化【NEW】
```javascript
class NotificationManager {
    async init() {
        // VAPID公開鍵取得
        const response = await fetch('/api/vapid-public-key');
        this.vapidPublicKey = (await response.json()).public_key;
        
        // 通知許可要求
        const permission = await Notification.requestPermission();
        if (permission === 'granted') {
            await this.subscribeUser();
        }
    }
    
    async subscribeUser() {
        const registration = await navigator.serviceWorker.ready;
        const subscription = await registration.pushManager.subscribe({
            userVisibleOnly: true,
            applicationServerKey: this.urlBase64ToUint8Array(this.vapidPublicKey)
        });
        
        // サーバーに購読情報送信
        await fetch('/api/subscribe', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify(subscription)
        });
    }
}
```

#### 4.4.5 HWB銘柄分析【NEW】
```javascript
class HWB200MAManager {
    async analyzeTicker() {
        const ticker = input.value.trim().toUpperCase();
        
        // まず既存データ確認（force=false）
        let response = await fetchWithAuth(`/api/hwb/analyze_ticker?ticker=${ticker}`);
        
        if (!response.ok && response.status === 404) {
            // 新規分析確認
            if (confirm(`${ticker}はまだ分析されていません。\n今すぐ分析しますか？`)) {
                response = await fetchWithAuth(`/api/hwb/analyze_ticker?ticker=${ticker}&force=true`);
            }
        }
        
        const symbolData = await response.json();
        this.renderAnalysisChart(symbolData);
    }
    
    renderAnalysisChart(symbolData) {
        // lightweight-charts でチャート描画
        const chart = LightweightCharts.createChart(container, {...});
        
        // ローソク足
        const candleSeries = chart.addSeries(LightweightCharts.CandlestickSeries, {...});
        candleSeries.setData(symbolData.chart_data.candles);
        
        // 移動平均線
        const sma200 = chart.addSeries(LightweightCharts.LineSeries, {...});
        sma200.setData(symbolData.chart_data.sma200);
        
        // ゾーン描画（RectanglePrimitive使用）
        symbolData.chart_data.zones.forEach(zone => {
            const rectPrimitive = new RectanglePrimitive({
                points: [
                    {time: new Date(zone.startTime).getTime() / 1000, price: zone.topValue},
                    {time: new Date(zone.endTime).getTime() / 1000, price: zone.bottomValue}
                ],
                fillColor: zone.fillColor,
                borderColor: zone.borderColor,
                borderWidth: 1.5
            });
            auxiliarySeries.attachPrimitive(rectPrimitive);
        });
        
        // マーカー
        candleSeries.setMarkers(symbolData.chart_data.markers);
    }
}
```

## 5. エラー処理仕様

### 5.1 エラーコード定義（拡張版）

| コード | 説明 | 発生箇所 | 対処 |
|--------|------|----------|------|
| E001 | OpenAI APIキー未設定 | data_fetcher.py | 環境変数確認、AI機能スキップ |
| E002 | データファイル読み込み失敗 | data_fetcher.py、main.py | ファイル存在確認 |
| E003 | 外部API接続失敗 | data_fetcher.py | リトライまたはスキップ |
| E004 | Fear&Greedデータ取得失敗 | data_fetcher.py | キャッシュまたはデフォルト値使用 |
| E005 | AI生成失敗 | data_fetcher.py | デフォルトメッセージ表示 |
| E006 | ヒートマップデータ取得失敗 | data_fetcher.py | 前回データまたは簡易表示 |
| **E007** | **HWBスキャンエラー** | **hwb_scanner.py** | **ログ記録、該当銘柄スキップ** |
| **E008** | **認証エラー** | **main.py、app.js** | **再ログイン要求** |
| **E009** | **Push通知エラー** | **data_fetcher.py** | **無効購読削除、ログ記録** |

### 5.2 エラーハンドリング実装

#### 5.2.1 リトライ処理（外部API）
```python
MAX_RETRIES = 3
RETRY_DELAY = 5  # 秒

def fetch_with_retry(self, fetch_func):
    for attempt in range(MAX_RETRIES):
        try:
            return fetch_func()
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                logger.warning(f"Attempt {attempt + 1} failed: {e}, retrying in {RETRY_DELAY}s...")
                time.sleep(RETRY_DELAY)
            else:
                logger.error(f"Failed after {MAX_RETRIES} attempts: {e}")
                raise MarketDataError("E003", str(e))
```

#### 5.2.2 認証エラー処理【NEW】
```javascript
// Frontend
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

```python
# Backend
async def get_current_user(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authorization header missing or invalid")
    
    token = authorization[7:]
    try:
        payload = jwt.decode(token, security_manager.jwt_secret, algorithms=[ALGORITHM])
        if payload.get("type") != "main":
            raise HTTPException(status_code=401, detail="Invalid token type")
        return payload.get("sub")
    except JWTError:
        raise HTTPException(status_code=401, detail="Token validation failed")
```

#### 5.2.3 HWBスキャンエラー処理【NEW】
```python
def _analyze_and_save_symbol(self, symbol: str) -> Optional[Dict]:
    try:
        data = self.data_manager.get_stock_data_with_cache(symbol)
        if not data:
            return None
        
        df_daily, df_weekly = data
        # 重複インデックス削除（防御的コーディング）
        df_daily = df_daily[~df_daily.index.duplicated(keep='last')]
        df_weekly = df_weekly[~df_weekly.index.duplicated(keep='last')]
        
        # 分析実行
        trend_check = self.analyzer.check_rule1(df_daily, df_weekly)
        if trend_check["status"] != "passed":
            return None
        
        # ... 以下の処理
        
    except Exception as e:
        logger.error(f"Error analyzing symbol '{symbol}': {e}", exc_info=True)
        return None
```

## 6. Cron仕様

### 6.1 スケジュール設定（更新版）

**Dockerfile内のcrontab設定：**
```cron
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
TZ=Asia/Tokyo

# データ取得（月〜金 6:15）
15 6 * * 1-5 . /app/backend/cron-env.sh && /app/backend/run_job.sh fetch >> /app/logs/cron_error.log 2>&1

# レポート生成＋Push通知（月〜金 6:28）
28 6 * * 1-5 . /app/backend/cron-env.sh && /app/backend/run_job.sh generate >> /app/logs/cron_error.log 2>&1

# HWBスキャン（火〜土 5:30、米国市場終了30分後）
30 5 * * 2-6 . /app/backend/cron-env.sh && python -m backend.hwb_scanner_cli >> /app/logs/hwb.log 2>&1
```

### 6.2 実行スクリプト

#### 6.2.1 run_job.sh
```bash
#!/bin/bash
set -e

APP_DIR="/app"
LOG_DIR="${APP_DIR}/logs"
JOB_TYPE=$1

mkdir -p "$LOG_DIR"

echo "$(date): Starting job: ${JOB_TYPE}" >> "${LOG_DIR}/cron.log"

# 作業ディレクトリ移動（重要）
cd "${APP_DIR}"

# Pythonパス設定
export PYTHONPATH="${APP_DIR}:${PYTHONPATH}"

# Python実行
if python3 -m backend.data_fetcher ${JOB_TYPE} >> "${LOG_DIR}/${JOB_TYPE}.log" 2>&1; then
    echo "$(date): Successfully completed job: ${JOB_TYPE}" >> "${LOG_DIR}/cron.log"
else
    echo "$(date): Failed to complete job: ${JOB_TYPE}" >> "${LOG_DIR}/cron.log"
    exit 1
fi
```

#### 6.2.2 cron-env.sh（環境変数エクスポート）
```bash
#!/bin/bash
# start.shで自動生成される環境変数エクスポートファイル
export OPENAI_API_KEY="..."
export AUTH_PIN="123456"
export TZ="Asia/Tokyo"
# ... その他の環境変数
```

## 7. Docker仕様

### 7.1 コンテナ構成

**docker-compose.yml:**
```yaml
services:
  app:
    build: .
    env_file:
      - ./.env
    ports:
      - "3000:8000"
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
    environment:
      - TZ=Asia/Tokyo
    restart: unless-stopped
```

### 7.2 ビルド仕様

**Dockerfile:**
```dockerfile
FROM python:3.11-slim-bookworm
WORKDIR /app

# タイムゾーン設定（最優先）
ENV TZ=Asia/Tokyo

# システムパッケージインストール
RUN apt-get update && apt-get install -y \
    cron \
    curl \
    tzdata \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# タイムゾーン設定
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Pythonパッケージインストール
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# アプリケーションファイルコピー
COPY backend /app/backend
COPY frontend /app/frontend

# 起動スクリプトコピー・実行権限付与
COPY start.sh /app/start.sh
RUN chmod +x /app/start.sh
RUN chmod +x /app/backend/run_job.sh

# Cron設定（TZ環境変数を含む）
RUN ( \
    echo "SHELL=/bin/bash" ; \
    echo "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin" ; \
    echo "TZ=Asia/Tokyo" ; \
    echo "" ; \
    echo "15 6 * * 1-5 . /app/backend/cron-env.sh && /app/backend/run_job.sh fetch >> /app/logs/cron_error.log 2>&1" ; \
    echo "28 6 * * 1-5 . /app/backend/cron-env.sh && /app/backend/run_job.sh generate >> /app/logs/cron_error.log 2>&1" ; \
    echo "30 5 * * 2-6 . /app/backend/cron-env.sh && python -m backend.hwb_scanner_cli >> /app/logs/hwb.log 2>&1" \
) | crontab -

# ログディレクトリ作成
RUN mkdir -p /app/logs

# 起動
CMD [ "/app/start.sh" ]
```

### 7.3 起動スクリプト

**start.sh:**
```bash
#!/bin/bash
set -e

mkdir -p /app/logs

# Cron環境変数ファイル作成
ENV_FILE="/app/backend/cron-env.sh"
printenv | sed 's/^\(.*\)$/export \1/g' > "${ENV_FILE}"
chmod +x "${ENV_FILE}"

# タイムゾーン設定確認
export TZ=Asia/Tokyo

# Cron再起動
service cron restart

# Uvicorn起動（フォアグラウンド）
exec uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

## 8. セキュリティ仕様（拡張版）

### 8.1 認証・認可【NEW】

#### 8.1.1 PIN認証
- **形式：** 6桁の数字
- **設定方法：** 環境変数`AUTH_PIN`
- **デフォルト：** 123456（本番環境では変更必須）
- **検証：** FastAPI側でPIN一致確認
- **ロックアウト：** フロントエンド実装（5回失敗）

#### 8.1.2 JWTトークン
- **アルゴリズム：** HS256
- **Secret Key：** 自動生成256ビット（`security_keys.json`保存）
- **有効期限：** 30日間（`JWT_ACCESS_TOKEN_EXPIRE_DAYS`で設定可能）
- **クレーム：**
```json
{
  "sub": "user",
  "type": "main",
  "exp": 1234567890
}
```
- **保存先：** LocalStorage（フロントエンド） + IndexedDB（バックアップ）
- **送信方法：** Authorizationヘッダー（`Bearer <token>`）

#### 8.1.3 通知トークン
- **有効期限：** 24時間（自動更新）
- **クレーム：**
```json
{
  "sub": "user",
  "type": "notification",
  "exp": 1234567890
}
```
- **保存先：** HttpOnlyクッキー（`notification_token`）
- **SameSite：** lax（開発）、none（本番HTTPS）
- **Secure：** HTTPS時のみtrue

### 8.2 セキュリティキー管理【NEW】

#### 8.2.1 自動生成
```python
# JWT Secret: 256ビット（32バイト）
jwt_secret = secrets.token_hex(32)

# VAPID鍵: ECDSA P-256
private_key = ec.generate_private_key(ec.SECP256R1(), default_backend())
# DER形式でエクスポート
private_der = private_key.private_bytes(
    encoding=serialization.Encoding.DER,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption()
)
# Base64 URL-safe、パディングなし
vapid_private_key = base64.urlsafe_b64encode(private_der).decode('utf-8').rstrip('=')
```

#### 8.2.2 保存と読み込み
1. 起動時、`data/security_keys.json`存在確認
2. 存在しない場合、新規生成
3. 環境変数優先（`JWT_SECRET_KEY`、`VAPID_PUBLIC_KEY`など）
4. ファイルパーミッション: 0600
5. バックアップ推奨（定期的な手動バックアップ）

### 8.3 APIセキュリティ

#### 8.3.1 認証フロー
```
Client Request
    ↓
Authorization Header Check
    ↓
JWT Decode & Verify
    ↓
Payload Validation (type, exp)
    ↓
   Valid?
    ├─ YES → Process Request
    └─ NO → 401 Unauthorized
```

#### 8.3.2 CORS設定
- 開発環境: 全オリジン許可（デフォルト）
- 本番環境: 特定オリジンのみ許可（推奨）

#### 8.3.3 レート制限
- yfinance: バッチサイズ20、3秒待機
- OpenAI: エラー時リトライ、max_tokens制限
- Push通知: 無効購読の自動削除（410エラー）

### 8.4 データ保護

#### 8.4.1 機密情報の管理
- APIキー: 環境変数（`.env`）、Git除外
- セキュリティキー: JSONファイル、Git除外、パーミッション制限
- Push購読情報: JSONファイル、Git除外

#### 8.4.2 .gitignore設定
```
/data/
__pycache__/
*.pyc
/jules-scratch/
.env
*.log
```

## 9. 運用仕様

### 9.1 初回セットアップ手順（更新版）

1. **リポジトリクローン**
```bash
git clone <repository-url>
cd hanaview
```

2. **環境変数設定**
```bash
cp .env.example .env
nano .env
# 最低限以下を設定：
# OPENAI_API_KEY=sk-...
# AUTH_PIN=123456（変更推奨）
```

3. **Docker起動**
```bash
docker-compose up -d --build
```

4. **セキュリティキー確認**
```bash
docker-compose exec app cat /app/data/security_keys.json
# 自動生成されたキーが表示される
# このファイルを必ずバックアップ！
```

5. **初回データ取得（オプション）**
```bash
docker-compose exec app python -m backend.data_fetcher fetch
docker-compose exec app python -m backend.data_fetcher generate
```

6. **HWBスキャン実行（オプション）**
```bash
docker-compose exec app python -m backend.hwb_scanner_cli
```

7. **ブラウザアクセス**
```
http://localhost:3000
PIN入力: 123456（または設定したPIN）
```

### 9.2 メンテナンス作業

#### 9.2.1 定期メンテナンス（月次）
- ログファイルのクリーンアップ
- Dockerイメージの更新
- セキュリティキーのバックアップ確認
- HWBデータベースのサイズ確認

#### 9.2.2 ログローテーション
```bash
# logs/ディレクトリのクリーンアップ
find /app/logs -name "*.log" -mtime +30 -delete
```

#### 9.2.3 データベース最適化
```bash
# HWB SQLiteデータベースのVACUUM
docker-compose exec app sqlite3 /app/data/hwb/hwb_cache.db "VACUUM;"
```

### 9.3 バックアップ仕様

#### 9.3.1 バックアップ対象
```
data/
├── security_keys.json（最重要！）
├── data_YYYY-MM-DD.json（7日間自動保持）
├── push_subscriptions.json
└── hwb/
    ├── hwb_cache.db（10年分のデータ）
    └── daily/*.json（スキャン結果）
```

#### 9.3.2 バックアップスクリプト例
```bash
#!/bin/bash
BACKUP_DIR="/backup/hanaview"
DATE=$(date +%Y%m%d)

# 重要ファイルのバックアップ
tar -czf "${BACKUP_DIR}/hanaview_${DATE}.tar.gz" \
  data/security_keys.json \
  data/push_subscriptions.json \
  data/hwb/hwb_cache.db

# 古いバックアップの削除（30日以前）
find "${BACKUP_DIR}" -name "hanaview_*.tar.gz" -mtime +30 -delete
```

### 9.4 トラブルシューティング

#### 9.4.1 コンテナが起動しない
```bash
docker-compose logs -f
docker-compose restart
```

#### 9.4.2 Cronジョブが実行されない
```bash
# Cron状態確認
docker-compose exec app service cron status

# Cronログ確認
docker-compose exec app cat /app/logs/cron.log

# タイムゾーン確認
docker-compose exec app date
docker-compose exec app cat /etc/timezone
```

#### 9.4.3 認証できない
```bash
# セキュリティキー確認
docker-compose exec app cat /app/data/security_keys.json

# ブラウザのLocalStorage/IndexedDBクリア
# DevTools > Application > Storage > Clear site data
```

#### 9.4.4 Push通知が届かない
```bash
# VAPID鍵確認
docker-compose exec app cat /app/data/security_keys.json | grep vapid

# 購読情報確認
docker-compose exec app cat /app/data/push_subscriptions.json

# Service Worker登録確認
# DevTools > Application > Service Workers
```

#### 9.4.5 HWBスキャンが完了しない
```bash
# HWBログ確認
docker-compose exec app tail -f /app/logs/hwb.log

# データベース確認
docker-compose exec app sqlite3 /app/data/hwb/hwb_cache.db "SELECT COUNT(*) FROM data_metadata;"

# 手動スキャン実行
docker-compose exec app python -m backend.hwb_scanner_cli
```

## 10. パフォーマンス仕様

### 10.1 処理時間目標

| 処理 | 目標時間 | 実績（参考） |
|------|----------|--------------|
| データ取得（fetch） | 10分以内 | 約5-8分 |
| レポート生成（generate） | 5分以内 | 約3-5分 |
| HWBスキャン | 60分以内 | 約50-70分（3000銘柄） |
| ページ読み込み | 3秒以内 | 約1-2秒 |
| 認証処理 | 1秒以内 | 約0.5秒 |
| 個別銘柄分析（既存） | 即座 | 約0.1秒 |
| 個別銘柄分析（新規） | 30秒以内 | 約10-30秒 |

### 10.2 最適化手法

#### 10.2.1 Backend
- yfinanceのセッション再利用
- curl-cffiによるブラウザ偽装
- SQLiteによる価格データキャッシング
- 並列処理（HWBスキャン: 最大5ワーカー）
- バッチ処理（20銘柄ごとに3秒待機）

#### 10.2.2 Frontend
- lightweight-chartsによる軽量チャート描画
- D3.jsによる効率的なヒートマップ描画
- Service Workerによるリソースキャッシング
- LocalStorage/IndexedDBによる認証状態キャッシング
- 遅延読み込み（HWBチャートカード）

#### 10.2.3 Database
- 複合インデックス（symbol, date）
- LIMIT句による必要最小限のデータ取得
- 増分更新（既存データの再利用）

---

**最終更新：** 2025年10月2日
**バージョン：** 2.0.0（認証・Push通知・HWB戦略対応版）
