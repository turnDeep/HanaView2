#!/usr/bin/env python3
“””
統合株式分析システム - All-in-One版
ティッカー取得 → データ分析 → ステージ判定 → チャート生成

特徴:

- 並列処理による高速化
- リアルタイム進捗表示
- Web API対応
- エラーハンドリング
- メモリ効率化
  “””

import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from curl_cffi.requests import Session
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict
from typing import Optional, Dict, List, Tuple
import pandas_ta as ta
from datetime import datetime
import json
import os
import logging
from tqdm import tqdm
import warnings
warnings.filterwarnings(‘ignore’)

# ============================================================================

# ロギング設定

# ============================================================================

logging.basicConfig(
level=logging.INFO,
format=’%(asctime)s - %(levelname)s - %(message)s’,
handlers=[
logging.FileHandler(‘stock_analyzer.log’),
logging.StreamHandler()
]
)
logger = logging.getLogger(**name**)

# ============================================================================

# データクラス定義

# ============================================================================

@dataclass
class AnalysisResult:
“”“分析結果を格納するデータクラス”””
ticker: str
current_stage: int
stage_name: str
stage_start_date: str
score: int
judgment: str
action: str
latest_price: float
ma50: float
rs_rating: float
atr_multiple: float
success: bool
error_message: Optional[str] = None

# ============================================================================

# 1. ティッカー取得

# ============================================================================

def fetch_nasdaq_nyse_tickers() -> List[str]:
“”“NASDAQとNYSEのティッカーリストを取得してフィルタリング”””
logger.info(“📥 ティッカーリストを取得中…”)

```
nasdaq_url = "https://datahub.io/core/nasdaq-listings/_r/-/data/nasdaq-listed-symbols.csv"
nyse_url = "https://datahub.io/core/nyse-other-listings/_r/-/data/nyse-listed.csv"

try:
    # NASDAQ
    nasdaq_df = pd.read_csv(nasdaq_url)
    nasdaq_df.dropna(subset=['Symbol'], inplace=True)
    nasdaq_tickers = nasdaq_df['Symbol'].astype(str).tolist()
    
    # NYSE
    nyse_df = pd.read_csv(nyse_url)
    nyse_df.dropna(subset=['ACT Symbol'], inplace=True)
    nyse_tickers = nyse_df['ACT Symbol'].astype(str).tolist()
    
    # 結合・重複削除
    all_tickers = sorted(list(set(nasdaq_tickers + nyse_tickers)))
    
    # フィルタリング
    excluded_suffixes = ['.U', '.W', '.A', '.B']
    filtered = [t for t in all_tickers 
               if len(t) != 5 
               and not any(s in t for s in excluded_suffixes)
               and '$' not in t]
    
    logger.info(f"✅ {len(filtered)} 件のティッカーを取得")
    return filtered
    
except Exception as e:
    logger.error(f"❌ ティッカー取得エラー: {e}")
    return []
```

# ============================================================================

# 2. データ取得

# ============================================================================

def fetch_stock_data(ticker: str, period: str = “2y”) -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame]]:
“”“株価データを取得”””
session = Session(impersonate=“chrome110”)

```
try:
    data = yf.download(
        tickers=[ticker, "SPY"],
        period=period,
        session=session,
        progress=False
    )
    
    if data.empty or ticker not in data.columns.get_level_values(1):
        return None, None
    
    stock_data = data.xs(ticker, level=1, axis=1).copy()
    benchmark_data = data.xs("SPY", level=1, axis=1).copy()
    
    stock_data.dropna(inplace=True)
    benchmark_data.dropna(inplace=True)
    
    if stock_data.empty:
        return None, None
        
    return stock_data, benchmark_data
    
except Exception as e:
    logger.debug(f"{ticker}: データ取得エラー - {e}")
    return None, None
```

# ============================================================================

# 3. テクニカル指標計算

# ============================================================================

def calculate_ma_slope(series: pd.Series, period: int = 10) -> float:
“”“移動平均線の傾きを計算”””
if len(series) < period:
return 0.0

```
y = series.tail(period).values
y_normalized = y / np.linalg.norm(y)
x = np.arange(len(y_normalized))

slope = np.polyfit(x, y_normalized, 1)[0]
return slope
```

def calculate_rs_rating(stock_data: pd.DataFrame, benchmark_data: pd.DataFrame) -> pd.Series:
“”“相対強度(RS Rating)を計算”””
common_index = stock_data.index.intersection(benchmark_data.index)
_stock = stock_data.loc[common_index]
_benchmark = benchmark_data.loc[common_index]

```
rs_line = (_stock['Close'] / _benchmark['Close'])

rs_rating = rs_line.rolling(window=252, min_periods=50).apply(
    lambda x: pd.Series(x).rank(pct=True).iloc[-1] * 100, raw=False
)
return rs_rating.fillna(0)
```

def calculate_indicators(stock_data: pd.DataFrame, benchmark_data: pd.DataFrame) -> pd.DataFrame:
“”“全テクニカル指標を計算”””
df = stock_data.copy()

```
# 移動平均
df['ma50'] = ta.sma(df['Close'], length=50)
df['ma200'] = ta.sma(df['Close'], length=200)
df['volume_ma50'] = ta.sma(df['Volume'], length=50)

# MA傾き
df['ma50_slope'] = df['ma50'].rolling(window=10).apply(
    lambda x: calculate_ma_slope(pd.Series(x), period=10), raw=False
)
df['ma50_slope'] = df['ma50_slope'].fillna(0)

# VWAP
df['vwap'] = ta.vwap(high=df['High'], low=df['Low'], close=df['Close'], volume=df['Volume'])
df['vwap_slope'] = df['vwap'].rolling(window=10).apply(
    lambda x: calculate_ma_slope(pd.Series(x), period=10), raw=False
)
df['vwap_slope'] = df['vwap_slope'].fillna(0)

# RS Rating
df['rs_rating'] = calculate_rs_rating(df, benchmark_data)
df['rs_rating_ma10'] = ta.sma(df['rs_rating'], length=10)

# ATR
df['atr'] = ta.atr(df['High'], df['Low'], df['Close'], length=14)
df['atr_ma_distance_multiple'] = np.where(
    df['atr'] > 0,
    abs(df['Close'] - df['ma50']) / df['atr'],
    0
)

df.dropna(inplace=True)
return df
```

# ============================================================================

# 4. ステージ分析エンジン

# ============================================================================

class StageAnalyzer:
“”“ステージ分析クラス”””

```
def __init__(self, indicators_df: pd.DataFrame, ticker: str, benchmark_indicators_df: pd.DataFrame):
    self.indicators_df = indicators_df
    self.ticker = ticker
    self.benchmark_indicators_df = benchmark_indicators_df
    self.latest_data = indicators_df.iloc[-1]
    self.latest_benchmark_data = benchmark_indicators_df.iloc[-1]
    self.analysis_date = self.latest_data.name.strftime('%Y-%m-%d')

def determine_current_stage(self) -> int:
    """現在のステージを判定"""
    ma50_slope = self.latest_data['ma50_slope']
    slope_threshold = 0.0015
    
    # ステージ4（下降）
    if ma50_slope < -slope_threshold:
        return 4
    
    # ステージ2（上昇）
    if ma50_slope > slope_threshold:
        transition_details = self.score_stage1_to_2()
        score = transition_details.get('score', 0)
        level = transition_details.get('level', 'C判定')
        
        if score >= 80 or level.startswith('A') or level.startswith('B'):
            return 2
    
    # ステージ1 or 3
    price = self.latest_data['Close']
    history_1y = self.indicators_df.iloc[-252:-1]
    history_150d = self.indicators_df.iloc[-151:-1]
    
    if history_1y.empty or len(history_1y) < 200:
        return 1
    
    high_1y = history_1y['High'].max()
    high_150d = history_150d['High'].max() if not history_150d.empty else high_1y
    
    if price < high_1y * 0.6:
        return 1
    
    if price >= high_150d * 0.7:
        return 3
    
    return 1

def score_stage1_to_2(self) -> Dict:
    """ステージ1→2のスコア計算"""
    score = 0
    details = {}
    
    # 1. 出来高
    volume_ratio = self.latest_data['Volume'] / self.latest_data['volume_ma50']
    if volume_ratio >= 2.5:
        score += 20
        details['出来高'] = f"A評価 ({volume_ratio:.1f}倍)"
    elif volume_ratio >= 2.0:
        score += 15
        details['出来高'] = f"B評価 ({volume_ratio:.1f}倍)"
    
    # 2. 価格ブレイク
    price_50day_high = self.indicators_df['Close'].tail(51).iloc[:-1].max()
    current_close = self.latest_data['Close']
    if current_close > price_50day_high * 1.03:
        score += 25
        details['価格ブレイク'] = "A評価"
    elif current_close > price_50day_high:
        score += 20
        details['価格ブレイク'] = "B評価"
    
    # 3. MA転換
    price_over_ma50 = self.latest_data['Close'] > self.latest_data['ma50']
    ma50_slope_up = self.latest_data['ma50_slope'] > 0.002
    if price_over_ma50 and ma50_slope_up:
        score += 20
        details['MA転換'] = "A評価"
    elif price_over_ma50 or ma50_slope_up:
        score += 10
        details['MA転換'] = "B評価"
    
    # 4. RS Rating
    rs = self.latest_data['rs_rating']
    if rs >= 85:
        score += 15
        details['RS Rating'] = f"A評価 ({rs:.0f})"
    elif rs >= 70:
        score += 10
        details['RS Rating'] = f"B評価 ({rs:.0f})"
    
    # 5. ボラティリティ
    atr_multiple = self.latest_data['atr_ma_distance_multiple']
    if 2.0 <= atr_multiple < 4.0:
        score += 15
        details['ボラティリティ'] = "A評価"
    elif 1.0 <= atr_multiple < 2.0:
        score += 10
        details['ボラティリティ'] = "B評価"
    
    # 6. 市場環境
    is_bull_market = self.latest_benchmark_data['Close'] > self.latest_benchmark_data['ma200']
    if is_bull_market:
        score += 5
        details['市場環境'] = "強気"
    
    # 確認メカニズム
    is_confirmed = False
    for i in range(1, 16):
        if len(self.indicators_df) < (50 + i + 1):
            continue
        
        breakout_day_index = -(i)
        breakout_day_data = self.indicators_df.iloc[breakout_day_index]
        historical_data = self.indicators_df.iloc[breakout_day_index - 50 : breakout_day_index]
        
        if historical_data.empty:
            continue
        
        price_50d_high_before = historical_data['Close'].max()
        
        if breakout_day_data['Close'] > price_50d_high_before:
            days_since = i - 1
            
            if days_since >= 2:
                days_to_confirm_df = self.indicators_df.iloc[-days_since:]
                days_above = (days_to_confirm_df['Close'] > price_50d_high_before * 0.98).sum()
                total_days = len(days_to_confirm_df)
                
                if days_above / total_days >= 0.8:
                    is_confirmed = True
                    break
    
    # 判定
    if score >= 85:
        level = "A判定 (強力な移行シグナル)"
        action = "自信を持ってエントリーを検討するべき理想的なブレイクアウト。"
    elif is_confirmed and score >= 70:
        level = "B判定 (移行シグナル)"
        action = "エントリーを検討。リスク管理のためポジションサイズ調整も考慮。"
    elif score >= 75 and not is_confirmed:
        level = "B-判定 (有望だが確認待ち)"
        action = f"高スコア({score}点)だが未確認。慎重にエントリー検討。"
    else:
        level = "C判定 (準備段階)"
        action = f"エントリーは見送り、全ての条件が揃うのを待つ (スコア: {score})。"
    
    return {"score": score, "level": level, "action": action, "details": details}

def score_stage2_to_3(self) -> Dict:
    """ステージ2→3のスコア計算"""
    score = 0
    
    # 過熱感
    atr_multiple = self.latest_data['atr_ma_distance_multiple']
    if atr_multiple >= 7.0:
        score += 30
    elif atr_multiple >= 5.0:
        score += 15
    
    # 大口の売り
    recent_data = self.indicators_df.tail(20)
    down_days_high_volume = recent_data[
        (recent_data['Close'] < recent_data['Close'].shift(1)) & 
        (recent_data['Volume'] > recent_data['volume_ma50'] * 1.5)
    ]
    if len(down_days_high_volume) >= 2:
        score += 25
    elif len(down_days_high_volume) == 1:
        score += 10
    
    # 上ヒゲ
    upper_wick = self.indicators_df['High'] - self.indicators_df[['Open', 'Close']].max(axis=1)
    is_long_wick = (upper_wick.tail(5) > (self.indicators_df['High'] - self.indicators_df['Low']).tail(5) * 0.5).any()
    if is_long_wick:
        score += 20
    
    # MA平坦化
    if abs(self.latest_data['ma50_slope']) < 0.001:
        score += 15
    
    # RS低下
    if self.latest_data['rs_rating'] < self.latest_data['rs_rating_ma10']:
        score += 10
    
    # 判定
    if score >= 75:
        level = "危険 (ステージ3移行が濃厚)"
        action = "ポジションの大部分の利益確定を強く推奨。"
    elif score >= 50:
        level = "警告 (トレンド鈍化)"
        action = "新規の買いは見送り、一部を利益確定。"
    else:
        level = "安全 (ステージ2継続)"
        action = "ポジションを維持し、トレンドの継続を期待する。"
    
    return {"score": score, "level": level, "action": action}

def analyze(self) -> Dict:
    """完全な分析を実行"""
    current_stage = self.determine_current_stage()
    
    if current_stage == 1:
        transition_analysis = self.score_stage1_to_2()
        transition_analysis['target_transition'] = "ステージ1 → 2"
    elif current_stage == 2:
        transition_analysis = self.score_stage2_to_3()
        transition_analysis['target_transition'] = "ステージ2 → 3"
    else:
        transition_analysis = {"score": 0, "level": "N/A", "action": "N/A", "target_transition": f"ステージ{current_stage}"}
    
    return {
        "ticker": self.ticker,
        "analysis_date": self.analysis_date,
        "current_stage": f"ステージ{current_stage}",
        "transition_analysis": transition_analysis
    }
```

# ============================================================================

# 5. ステージ開始日検出

# ============================================================================

def find_stage_start_date(ticker: str, stock_indicators: pd.DataFrame,
benchmark_indicators: pd.DataFrame, current_stage: int) -> str:
“”“現在のステージの開始日を特定”””
for i in range(1, len(stock_indicators)):
date_to_check_index = -i - 1
if abs(date_to_check_index) > len(stock_indicators) or len(stock_indicators.iloc[:date_to_check_index]) < 252:
break

```
    historical_stock_slice = stock_indicators.iloc[:date_to_check_index]
    historical_benchmark_slice = benchmark_indicators.loc[historical_stock_slice.index]
    
    try:
        analyzer = StageAnalyzer(historical_stock_slice, ticker, historical_benchmark_slice)
        stage = analyzer.determine_current_stage()
        if stage != current_stage:
            start_date = stock_indicators.index[date_to_check_index + 1]
            return start_date.strftime('%Y-%m-%d')
    except:
        continue

return stock_indicators.index[0].strftime('%Y-%m-%d')
```

# ============================================================================

# 6. チャート生成

# ============================================================================

def create_chart_json(ticker: str, df: pd.DataFrame, stage_history: Optional[pd.DataFrame] = None) -> Dict:
“”“Web表示用のインタラクティブチャートをJSON形式で生成”””
try:
fig = make_subplots(
rows=4, cols=1,
shared_xaxes=True,
vertical_spacing=0.02,
row_heights=[0.5, 0.15, 0.15, 0.2],
subplot_titles=(
f’{ticker} - 株価チャート（ステージ分析）’,
‘出来高’,
‘RS Rating（相対強度）’,
‘ATR & MA乖離率’
)
)

```
    # ステージ背景色
    if stage_history is not None and not stage_history.empty:
        stage_colors = {1: 'rgba(0,255,0,0.1)', 2: 'rgba(0,255,0,0.2)', 
                      3: 'rgba(255,165,0,0.15)', 4: 'rgba(255,0,0,0.15)'}
        
        current_stage = None
        start_date = None
        
        for _, row in stage_history.iterrows():
            if current_stage != row['stage']:
                if current_stage is not None:
                    fig.add_vrect(
                        x0=start_date, x1=row['date'],
                        fillcolor=stage_colors.get(current_stage, 'rgba(128,128,128,0.1)'),
                        layer="below", line_width=0, row=1, col=1,
                        annotation_text=f"S{current_stage}",
                        annotation_position="top left"
                    )
                current_stage = row['stage']
                start_date = row['date']
        
        if current_stage is not None:
            fig.add_vrect(
                x0=start_date, x1=df.index[-1],
                fillcolor=stage_colors.get(current_stage, 'rgba(128,128,128,0.1)'),
                layer="below", line_width=0, row=1, col=1,
                annotation_text=f"S{current_stage}",
                annotation_position="top left"
            )
    
    # 1. ローソク足
    fig.add_trace(
        go.Candlestick(
            x=df.index.strftime('%Y-%m-%d').tolist(),
            open=df['Open'], high=df['High'],
            low=df['Low'], close=df['Close'],
            name='OHLC',
            increasing_line_color='#26a69a',
            decreasing_line_color='#ef5350'
        ),
        row=1, col=1
    )
    
    # 2. 移動平均線
    fig.add_trace(go.Scatter(
        x=df.index.strftime('%Y-%m-%d').tolist(), y=df['ma50'], 
        mode='lines', name='MA50', line=dict(color='orange', width=2)),
        row=1, col=1)
    
    fig.add_trace(go.Scatter(
        x=df.index.strftime('%Y-%m-%d').tolist(), y=df['ma200'],
        mode='lines', name='MA200', line=dict(color='blue', width=2)),
        row=1, col=1)
    
    if 'vwap' in df.columns:
        fig.add_trace(go.Scatter(
            x=df.index.strftime('%Y-%m-%d').tolist(), y=df['vwap'],
            mode='lines', name='VWAP', line=dict(color='green', width=1.5)),
            row=1, col=1)
    
    # 3. 出来高
    colors = ['#ef5350' if df['Close'].iloc[i] < df['Open'].iloc[i] else '#26a69a'
              for i in range(len(df))]
    
    fig.add_trace(go.Bar(
        x=df.index.strftime('%Y-%m-%d').tolist(), y=df['Volume'],
        name='出来高', marker_color=colors, opacity=0.7),
        row=2, col=1)
    
    if 'volume_ma50' in df.columns:
        fig.add_trace(go.Scatter(
            x=df.index.strftime('%Y-%m-%d').tolist(), y=df['volume_ma50'],
            mode='lines', name='出来高MA50', line=dict(color='purple', width=2)),
            row=2, col=1)
    
    # 4. RS Rating
    if 'rs_rating' in df.columns:
        fig.add_trace(go.Scatter(
            x=df.index.strftime('%Y-%m-%d').tolist(), y=df['rs_rating'],
            mode='lines', name='RS Rating', line=dict(color='blue', width=2),
            fill='tozeroy', fillcolor='rgba(0,100,255,0.1)'),
            row=3, col=1)
        
        if 'rs_rating_ma10' in df.columns:
            fig.add_trace(go.Scatter(
                x=df.index.strftime('%Y-%m-%d').tolist(), y=df['rs_rating_ma10'],
                mode='lines', name='RS MA10', line=dict(color='orange', width=1.5, dash='dash')),
                row=3, col=1)
        
        # 基準線
        fig.add_hline(y=85, line_dash="dot", line_color="green", 
                     annotation_text="強い(85)", row=3, col=1, opacity=0.6)
        fig.add_hline(y=70, line_dash="dot", line_color="lightgreen",
                     annotation_text="良い(70)", row=3, col=1, opacity=0.6)
        fig.add_hline(y=50, line_dash="dot", line_color="gray",
                     annotation_text="中立(50)", row=3, col=1, opacity=0.6)
    
    # 5. ATR
    if 'atr' in df.columns:
        fig.add_trace(go.Scatter(
            x=df.index.strftime('%Y-%m-%d').tolist(), y=df['atr'],
            mode='lines', name='ATR', line=dict(color='purple', width=2)),
            row=4, col=1)
    
    if 'atr_ma_distance_multiple' in df.columns:
        fig.add_trace(go.Scatter(
            x=df.index.strftime('%Y-%m-%d').tolist(), y=df['atr_ma_distance_multiple'],
            mode='lines', name='MA乖離率(ATR倍)', line=dict(color='red', width=2)),
            row=4, col=1)
        
        fig.add_hline(y=5, line_dash="dash", line_color="red",
                     annotation_text="過熱(5.0x)", row=4, col=1)
    
    # 統計情報
    latest = df.iloc[-1]
    stats_text = f"""<b>最新データ ({latest.name.strftime('%Y-%m-%d')})</b><br>
```

終値: <b>${latest[‘Close’]:.2f}</b><br>
MA50: ${latest[‘ma50’]:.2f} ({((latest[‘Close’]/latest[‘ma50’]-1)*100):+.1f}%)<br>
RS Rating: {latest.get(‘rs_rating’, 0):.0f}/100<br>
ATR倍率: {latest.get(‘atr_ma_distance_multiple’, 0):.2f}x”””

```
    fig.add_annotation(
        text=stats_text,
        xref="paper", yref="paper",
        x=0.02, y=0.98,
        showarrow=False,
        bgcolor="rgba(255,255,255,0.95)",
        bordercolor="black",
        borderwidth=2,
        align="left",
        font=dict(size=12)
    )
    
    # レイアウト
    fig.update_layout(
        title={
            'text': f'<b>{ticker}</b> - テクニカル分析チャート',
            'x': 0.5,
            'xanchor': 'center',
            'font': {'size': 20, 'color': '#1f77b4'}
        },
        xaxis_rangeslider_visible=False,
        height=900,
        showlegend=True,
        hovermode='x unified',
        template='plotly_white',
        font=dict(family="Arial, sans-serif", size=11)
    )
    
    # Y軸設定
    fig.update_yaxes(title_text="価格 (USD)", row=1, col=1)
    fig.update_yaxes(title_text="出来高", row=2, col=1)
    fig.update_yaxes(title_text="RS Rating", row=3, col=1)
    fig.update_yaxes(title_text="ATR / 乖離率", row=4, col=1)
    
    # JSON形式で返す
    return json.loads(fig.to_json())
    
except Exception as e:
    logger.error(f"{ticker}: チャート生成エラー - {e}")
    return None
```

# ============================================================================

# 7. 単一ティッカー分析（並列処理用）

# ============================================================================

def analyze_single_ticker(ticker: str, benchmark_df: pd.DataFrame,
benchmark_indicators: pd.DataFrame,
generate_chart: bool = False,
output_dir: str = ‘stage1or2’) -> Optional[AnalysisResult]:
“”“単一ティッカーの完全な分析”””
try:
# データ取得
stock_df, _ = fetch_stock_data(ticker, period=“2y”)

```
    if stock_df is None or len(stock_df) < 252:
        return None
    
    # 指標計算
    stock_indicators = calculate_indicators(stock_df, benchmark_df)
    
    if stock_indicators.empty:
        return None
    
    # ステージ分析
    analyzer = StageAnalyzer(stock_indicators, ticker, benchmark_indicators)
    analysis = analyzer.analyze()
    
    current_stage_str = analysis['current_stage']
    current_stage_num = int(current_stage_str.replace('ステージ', ''))
    
    transition_analysis = analysis['transition_analysis']
    score = transition_analysis.get('score', 0)
    level = transition_analysis.get('level', 'N/A')
    action = transition_analysis.get('action', 'N/A')
    
    # フィルタリング条件
    is_stage1_candidate = (current_stage_num == 1 and score >= 50)
    is_stage2 = (current_stage_num == 2)
    
    if not (is_stage1_candidate or is_stage2):
        return None
    
    # ステージ開始日
    stage_start_date = find_stage_start_date(
        ticker, stock_indicators, benchmark_indicators, current_stage_num
    )
    
    # 最新データ
    latest = stock_indicators.iloc[-1]
    
    # チャート生成（オプション）
    if generate_chart:
        chart_path = os.path.join(output_dir, f'{ticker}_chart.png')
        create_chart_image(ticker, stock_indicators, chart_path)
    
    # 結果を返す
    stage_names = {
        1: '底固め期',
        2: '上昇期',
        3: '天井圏',
        4: '下降期'
    }
    
    return AnalysisResult(
        ticker=ticker,
        current_stage=current_stage_num,
        stage_name=stage_names.get(current_stage_num, 'N/A'),
        stage_start_date=stage_start_date,
        score=score,
        judgment=level,
        action=action,
        latest_price=float(latest['Close']),
        ma50=float(latest['ma50']),
        rs_rating=float(latest['rs_rating']),
        atr_multiple=float(latest['atr_ma_distance_multiple']),
        success=True
    )
    
except Exception as e:
    logger.debug(f"{ticker}: 分析エラー - {e}")
    return None
```

# ============================================================================

# 8. メイン分析パイプライン（並列処理）

# ============================================================================

def run_full_analysis(
use_existing_tickers: bool = False,
ticker_file: str = ‘stock.csv’,
max_tickers: Optional[int] = None,
max_workers: int = 4,
generate_charts: bool = False,
output_dir: str = ‘stage1or2’,
output_csv: str = ‘stage1or2.csv’
) -> Tuple[pd.DataFrame, List[AnalysisResult]]:
“””
完全な分析パイプラインを実行

```
Args:
    use_existing_tickers: 既存のstock.csvを使用するか
    ticker_file: ティッカーファイルのパス
    max_tickers: 処理する最大ティッカー数
    max_workers: 並列処理のワーカー数
    generate_charts: チャート画像を生成するか
    output_dir: チャート出力ディレクトリ
    output_csv: 結果CSV出力パス

Returns:
    (DataFrame, List[AnalysisResult]): 結果のDataFrameとAnalysisResultリスト
"""

logger.info("="*70)
logger.info("🚀 統合株式分析システムを開始")
logger.info("="*70)

# 出力ディレクトリ作成
if generate_charts:
    os.makedirs(output_dir, exist_ok=True)

# ステップ1: ティッカー取得
if use_existing_tickers and os.path.exists(ticker_file):
    logger.info(f"📂 既存の{ticker_file}からティッカーを読み込み")
    with open(ticker_file, 'r', encoding='utf-8-sig') as f:
        tickers = [line.strip() for line in f if line.strip()]
else:
    logger.info("🌐 NASDAQ/NYSEからティッカーをダウンロード")
    tickers = fetch_nasdaq_nyse_tickers()
    
    # stock.csvに保存
    with open(ticker_file, 'w') as f:
        for ticker in tickers:
            f.write(f"{ticker}\n")
    logger.info(f"💾 {ticker_file}に保存完了")

if max_tickers:
    tickers = tickers[:max_tickers]
    logger.info(f"🔢 先頭{max_tickers}銘柄のみ処理")

logger.info(f"📊 合計 {len(tickers)} 銘柄を分析予定")

# ステップ2: ベンチマークデータ取得
logger.info("\n🔄 ベンチマークデータ(SPY)を取得中...")
benchmark_df, _ = fetch_stock_data("SPY", period="2y")

if benchmark_df is None:
    logger.error("❌ ベンチマークデータの取得に失敗")
    return pd.DataFrame(), []

benchmark_indicators = calculate_indicators(benchmark_df, benchmark_df.copy())
logger.info("✅ ベンチマークデータ準備完了")

# ステップ3: 並列処理で全ティッカーを分析
logger.info(f"\n⚡ {max_workers}並列で分析開始...")

results = []

with ThreadPoolExecutor(max_workers=max_workers) as executor:
    # ジョブを投入
    future_to_ticker = {
        executor.submit(
            analyze_single_ticker,
            ticker,
            benchmark_df,
            benchmark_indicators,
            generate_charts,
            output_dir
        ): ticker
        for ticker in tickers
    }
    
    # 進捗バー付きで結果を収集
    with tqdm(total=len(tickers), desc="分析進捗", unit="銘柄") as pbar:
        for future in as_completed(future_to_ticker):
            ticker = future_to_ticker[future]
            try:
                result = future.result()
                if result:
                    results.append(result)
            except Exception as e:
                logger.debug(f"{ticker}: エラー - {e}")
            finally:
                pbar.update(1)

# ステップ4: 結果をDataFrameに変換
if not results:
    logger.warning("⚠️  条件に合う銘柄が見つかりませんでした")
    return pd.DataFrame(), []

results_df = pd.DataFrame([asdict(r) for r in results])

# 優先度でソート（ステージ2 > ステージ1、スコア降順）
results_df['priority'] = results_df['current_stage'].apply(lambda x: 1 if x == 2 else 2)
results_df = results_df.sort_values(['priority', 'score'], ascending=[True, False])
results_df = results_df.drop('priority', axis=1)

# CSV出力
output_cols = ['ticker', 'current_stage', 'stage_name', 'stage_start_date', 
               'score', 'judgment', 'action', 'latest_price', 'ma50', 'rs_rating']
results_df[output_cols].to_csv(output_csv, index=False, encoding='utf-8-sig')

# 統計
stage2_count = len(results_df[results_df['current_stage'] == 2])
stage1_count = len(results_df[results_df['current_stage'] == 1])

logger.info("\n" + "="*70)
logger.info(f"✅ 分析完了: {len(results)} 件の有望銘柄を発見")
logger.info(f"   - ステージ2（上昇期）: {stage2_count} 件")
logger.info(f"   - ステージ1（底固め期）: {stage1_count} 件")
logger.info(f"📄 結果を {output_csv} に保存しました")
if generate_charts:
    logger.info(f"🖼️  チャート画像を {output_dir}/ に保存しました")
logger.info("="*70 + "\n")

return results_df, results
```

# ============================================================================

# 9. Web API用エンドポイント（オプション）

# ============================================================================

def get_analysis_summary(results: List[AnalysisResult]) -> Dict:
“”“分析結果のサマリーをJSON形式で返す”””
if not results:
return {“status”: “no_results”, “count”: 0}

```
stage2_tickers = [r.ticker for r in results if r.current_stage == 2]
stage1_tickers = [r.ticker for r in results if r.current_stage == 1]

high_score_tickers = [r.ticker for r in results if r.score >= 75]

return {
    "status": "success",
    "total_count": len(results),
    "stage2_count": len(stage2_tickers),
    "stage1_count": len(stage1_tickers),
    "high_score_count": len(high_score_tickers),
    "stage2_tickers": stage2_tickers[:10],  # 上位10件
    "stage1_tickers": stage1_tickers[:10],
    "high_score_tickers": high_score_tickers[:10],
    "timestamp": datetime.now().isoformat()
}
```

# ============================================================================

# 10. メイン実行

# ============================================================================

if **name** == ‘**main**’:
import argparse

```
parser = argparse.ArgumentParser(description='統合株式分析システム')
parser.add_argument('--max-tickers', type=int, default=50, help='処理する最大銘柄数')
parser.add_argument('--workers', type=int, default=4, help='並列処理のワーカー数')
parser.add_argument('--charts', action='store_true', help='チャート画像を生成')
parser.add_argument('--use-existing', action='store_true', help='既存のstock.csvを使用')
parser.add_argument('--output-dir', default='stage1or2', help='チャート出力ディレクトリ')
parser.add_argument('--output-csv', default='stage1or2.csv', help='結果CSV出力パス')

args = parser.parse_args()

# 分析実行
df_results, results_list = run_full_analysis(
    use_existing_tickers=args.use_existing,
    max_tickers=args.max_tickers,
    max_workers=args.workers,
    generate_charts=args.charts,
    output_dir=args.output_dir,
    output_csv=args.output_csv
)

# サマリー表示
if results_list:
    summary = get_analysis_summary(results_list)
    print("\n📊 分析サマリー:")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
```