import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from curl_cffi.requests import Session
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict, field
from typing import Optional, Dict, List, Tuple
from datetime import datetime
import json
import os
import logging
from tqdm import tqdm
import warnings

warnings.filterwarnings('ignore')

# logger設定
logger = logging.getLogger(__name__)

# --- Data Classes ---
@dataclass
class StageAnalysisResult:
    """A dataclass to hold the analysis result for a single stock."""
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
    success: bool = True
    error_message: Optional[str] = None
    chart_json: Optional[Dict] = field(default=None, repr=False)
    stage_history: Optional[List[Dict]] = field(default=None, repr=False)
    # Store the dataframe for detailed analysis, but don't include in default repr
    full_data: Optional[pd.DataFrame] = field(default=None, repr=False)


def fetch_stock_data(ticker: str, period: str = "2y") -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame]]:
    """Fetches stock data for a given ticker and the SPY benchmark."""
    session = Session(impersonate="chrome110")
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

        return (stock_data, benchmark_data) if not stock_data.empty else (None, None)
    except Exception as e:
        logger.debug(f"{ticker}: Data fetch error - {e}")
        return None, None

def calculate_ma_slope(series: pd.Series, period: int = 10) -> float:
    """Calculates the slope of a moving average."""
    if len(series) < period:
        return 0.0
    y = series.tail(period).values
    y_normalized = y / np.linalg.norm(y)
    x = np.arange(len(y_normalized))
    slope = np.polyfit(x, y_normalized, 1)[0]
    return slope

def calculate_rs_rating(stock_data: pd.DataFrame, benchmark_data: pd.DataFrame) -> pd.Series:
    """Calculates the Relative Strength (RS) Rating."""
    common_index = stock_data.index.intersection(benchmark_data.index)
    _stock = stock_data.loc[common_index]
    _benchmark = benchmark_data.loc[common_index]
    rs_line = (_stock['Close'] / _benchmark['Close'])
    rs_rating = rs_line.rolling(window=252, min_periods=50).apply(
        lambda x: pd.Series(x).rank(pct=True).iloc[-1] * 100, raw=False
    )
    return rs_rating.fillna(0)

def calculate_indicators(stock_data: pd.DataFrame, benchmark_data: pd.DataFrame) -> pd.DataFrame:
    """Calculates all necessary technical indicators using standard pandas."""
    df = stock_data.copy()

    # EMA (Exponential Moving Average)
    df['ema9'] = df['Close'].ewm(span=9, adjust=False).mean()
    df['ema21'] = df['Close'].ewm(span=21, adjust=False).mean()

    # SMA (Simple Moving Average)
    df['ma50'] = df['Close'].rolling(window=50).mean()
    df['ma200'] = df['Close'].rolling(window=200).mean()
    df['volume_ma50'] = df['Volume'].rolling(window=50).mean()

    # MA50 Slope
    df['ma50_slope'] = df['ma50'].rolling(window=10).apply(
        lambda x: calculate_ma_slope(pd.Series(x), period=10), raw=False
    ).fillna(0)

    # VWAP (Volume Weighted Average Price)
    df['vwap'] = (df['Close'] * df['Volume']).cumsum() / df['Volume'].cumsum()

    # VWAP Slope
    df['vwap_slope'] = df['vwap'].rolling(window=10).apply(
        lambda x: calculate_ma_slope(pd.Series(x), period=10), raw=False
    ).fillna(0)

    # Relative Strength Rating
    df['rs_rating'] = calculate_rs_rating(df, benchmark_data)
    df['rs_rating_ma10'] = df['rs_rating'].rolling(window=10).mean()

    # ATR (Average True Range)
    high_low = df['High'] - df['Low']
    high_close = (df['High'] - df['Close'].shift()).abs()
    low_close = (df['Low'] - df['Close'].shift()).abs()

    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df['atr'] = true_range.rolling(window=14).mean()

    # ATR MA Distance Multiple
    df['atr_ma_distance_multiple'] = np.where(
        df['atr'] > 0, abs(df['Close'] - df['ma50']) / df['atr'], 0
    )

    df.dropna(inplace=True)
    return df

class StageAnalyzer:
    """Analyzes the stage of a stock based on its indicators."""

    def __init__(self, indicators_df: pd.DataFrame, ticker: str, benchmark_indicators_df: pd.DataFrame):
        self.indicators_df = indicators_df
        self.ticker = ticker
        self.benchmark_indicators_df = benchmark_indicators_df
        self.latest_data = indicators_df.iloc[-1]
        self.latest_benchmark_data = benchmark_indicators_df.iloc[-1]
        self.analysis_date = self.latest_data.name.strftime('%Y-%m-%d')

    def determine_current_stage(self) -> int:
        """Determines the current stage of the stock."""
        ma50_slope = self.latest_data['ma50_slope']
        slope_threshold = 0.0015

        if ma50_slope < -slope_threshold: return 4

        if ma50_slope > slope_threshold:
            transition_details = self.score_stage1_to_2()
            if transition_details.get('score', 0) >= 80 or transition_details.get('level', 'C').startswith(('A', 'B')):
                return 2

        price = self.latest_data['Close']
        history_1y = self.indicators_df.iloc[-252:-1]
        if history_1y.empty or len(history_1y) < 200: return 1

        high_1y = history_1y['High'].max()
        high_150d = self.indicators_df.iloc[-151:-1]['High'].max() if len(self.indicators_df) > 151 else high_1y

        if price < high_1y * 0.6: return 1
        return 3 if price >= high_150d * 0.7 else 1

    def score_stage1_to_2(self) -> Dict:
        """Calculates a score for the Stage 1 to 2 transition."""
        score, details = 0, {}
        # Volume
        volume_ratio = self.latest_data['Volume'] / self.latest_data['volume_ma50']
        if volume_ratio >= 2.5: score += 20; details['Volume'] = f"A ({volume_ratio:.1f}x)"
        elif volume_ratio >= 2.0: score += 15; details['Volume'] = f"B ({volume_ratio:.1f}x)"
        # Price Breakout
        price_50d_high = self.indicators_df['Close'].tail(51).iloc[:-1].max()
        if self.latest_data['Close'] > price_50d_high * 1.03: score += 25; details['Breakout'] = "A"
        elif self.latest_data['Close'] > price_50d_high: score += 20; details['Breakout'] = "B"
        # MA Crossover
        if self.latest_data['Close'] > self.latest_data['ma50'] and self.latest_data['ma50_slope'] > 0.002: score += 20; details['MA'] = "A"
        elif self.latest_data['Close'] > self.latest_data['ma50'] or self.latest_data['ma50_slope'] > 0.002: score += 10; details['MA'] = "B"
        # RS Rating
        rs = self.latest_data['rs_rating']
        if rs >= 85: score += 15; details['RS'] = f"A ({rs:.0f})"
        elif rs >= 70: score += 10; details['RS'] = f"B ({rs:.0f})"
        # Volatility
        atr_mult = self.latest_data['atr_ma_distance_multiple']
        if 2.0 <= atr_mult < 4.0: score += 15; details['Volatility'] = "A"
        elif 1.0 <= atr_mult < 2.0: score += 10; details['Volatility'] = "B"
        # Market Environment
        if self.latest_benchmark_data['Close'] > self.latest_benchmark_data['ma200']: score += 5; details['Market'] = "Bull"

        # Confirmation
        is_confirmed = False
        for i in range(1, 16):
            if len(self.indicators_df) < (51 + i): continue
            breakout_day_idx = -i
            breakout_day = self.indicators_df.iloc[breakout_day_idx]
            hist_50d = self.indicators_df.iloc[breakout_day_idx - 50 : breakout_day_idx]
            if hist_50d.empty: continue
            if breakout_day['Close'] > hist_50d['Close'].max():
                days_since = i - 1
                if days_since >= 2:
                    confirm_df = self.indicators_df.iloc[-days_since:]
                    if (confirm_df['Close'] > hist_50d['Close'].max() * 0.98).sum() / len(confirm_df) >= 0.8:
                        is_confirmed = True; break

        if score >= 85: level, action = "A (Strong)", "Ideal breakout. Consider entry."
        elif is_confirmed and score >= 70: level, action = "B (Confirmed)", "Consider entry, manage risk."
        elif score >= 75: level, action = f"B- (Promising)", f"High score ({score}), but unconfirmed. Cautious entry."
        else: level, action = "C (Setup)", f"Wait for confirmation (Score: {score})."

        return {"score": score, "level": level, "action": action, "details": details}

    def score_stage2_to_3(self) -> Dict:
        """Calculates a score for the Stage 2 to 3 (topping) transition."""
        score = 0
        if self.latest_data['atr_ma_distance_multiple'] >= 7.0: score += 30
        elif self.latest_data['atr_ma_distance_multiple'] >= 5.0: score += 15

        recent_data = self.indicators_df.tail(20)
        down_days_high_vol = recent_data[(recent_data['Close'] < recent_data['Close'].shift(1)) & (recent_data['Volume'] > recent_data['volume_ma50'] * 1.5)]
        if len(down_days_high_vol) >= 2: score += 25
        elif len(down_days_high_vol) == 1: score += 10

        upper_wick = self.indicators_df['High'] - self.indicators_df[['Open', 'Close']].max(axis=1)
        if (upper_wick.tail(5) > (self.indicators_df['High'] - self.indicators_df['Low']).tail(5) * 0.5).any(): score += 20

        if abs(self.latest_data['ma50_slope']) < 0.001: score += 15
        if self.latest_data['rs_rating'] < self.latest_data['rs_rating_ma10']: score += 10

        if score >= 75: level, action = "Danger (Likely Stage 3)", "Strongly consider taking profits."
        elif score >= 50: level, action = "Warning (Trend stalling)", "Avoid new buys, consider partial profit."
        else: level, action = "Safe (Stage 2 continues)", "Hold position."

        return {"score": score, "level": level, "action": action}

    def analyze(self) -> Dict:
        """Performs a complete analysis."""
        current_stage = self.determine_current_stage()
        if current_stage == 1: analysis = self.score_stage1_to_2(); analysis['target'] = "1 -> 2"
        elif current_stage == 2: analysis = self.score_stage2_to_3(); analysis['target'] = "2 -> 3"
        else: analysis = {"score": 0, "level": "N/A", "action": "N/A", "target": f"Stage {current_stage}"}

        return {"ticker": self.ticker, "date": self.analysis_date, "stage": current_stage, "analysis": analysis}

# --- Service Class ---
class StageAnalyzerService:
    """A service class to handle stock stage analysis."""

    def __init__(self, data_dir='data'):
        self.data_dir = data_dir
        self.stage_data_dir = os.path.join(self.data_dir, 'stage')
        os.makedirs(self.stage_data_dir, exist_ok=True)

    def _find_stage_history(self, ticker: str, stock_indicators: pd.DataFrame,
                              benchmark_indicators: pd.DataFrame) -> List[Dict]:
        """Finds the historical stage transitions for a stock."""
        history = []
        last_stage = -1
        # Analyze the last 2 years of data for stage history
        for i in range(min(len(stock_indicators), 504), 0, -1):
            current_date_index = -i
            historical_slice = stock_indicators.iloc[:current_date_index]

            if len(historical_slice) < 252: continue

            try:
                # Align benchmark data for the historical slice
                historical_benchmark_slice = benchmark_indicators.loc[historical_slice.index]
                analyzer = StageAnalyzer(historical_slice, ticker, historical_benchmark_slice)
                current_stage = analyzer.determine_current_stage()

                if current_stage != last_stage:
                    transition_date = stock_indicators.index[current_date_index].strftime('%Y-%m-%d')
                    history.append({"date": transition_date, "stage": current_stage})
                    last_stage = current_stage
            except Exception:
                continue # Ignore errors in historical analysis
        return history

    def find_stage_start_date(self, ticker: str, stock_indicators: pd.DataFrame,
                              benchmark_indicators: pd.DataFrame, current_stage: int) -> str:
        """Finds the start date of the current stage."""
        for i in range(1, len(stock_indicators)):
            date_to_check_index = -i - 1
            if abs(date_to_check_index) > len(stock_indicators) or len(stock_indicators.iloc[:date_to_check_index]) < 252:
                break

            historical_stock_slice = stock_indicators.iloc[:date_to_check_index]
            historical_benchmark_slice = benchmark_indicators.loc[historical_stock_slice.index]

            try:
                analyzer = StageAnalyzer(historical_stock_slice, ticker, historical_benchmark_slice)
                stage = analyzer.determine_current_stage()
                if stage != current_stage:
                    start_date = stock_indicators.index[date_to_check_index + 1]
                    return start_date.strftime('%Y-%m-%d')
            except Exception:
                continue
        return stock_indicators.index[0].strftime('%Y-%m-%d')

    def _prepare_chart_data(self, df: pd.DataFrame) -> Dict:
        """Formats the analysis dataframe into a structure for Lightweight Charts."""
        # Ensure index is datetime for string formatting
        df.index = pd.to_datetime(df.index)

        # Create a copy to avoid SettingWithCopyWarning
        df_copy = df.copy()
        df_copy.index = df_copy.index.strftime('%Y-%m-%d')

        chart_data = {}

        # Candle data
        candles_df = df_copy[['Open', 'High', 'Low', 'Close']].reset_index()
        chart_data['candles'] = candles_df.rename(columns={
            'index': 'time', 'Open': 'open', 'High': 'high', 'Low': 'low', 'Close': 'close'
        }).to_dict('records')

        # Volume data with color
        volume_df = df_copy[['Volume', 'Close', 'Open']].reset_index()
        volume_df['color'] = np.where(
            volume_df['Close'] > volume_df['Open'],
            'rgba(38, 166, 154, 0.5)',  # up
            'rgba(239, 83, 80, 0.5)'   # down
        )
        chart_data['volume'] = volume_df[['index', 'Volume', 'color']].rename(
            columns={'index': 'time', 'Volume': 'value'}
        ).to_dict('records')

        # Moving averages data
        ma_cols = ['ema9', 'ema21', 'ma50', 'ma200']
        for col in ma_cols:
            if col in df_copy.columns:
                chart_data[col] = df_copy[[col]].dropna().reset_index().rename(
                    columns={'index': 'time', col: 'value'}
                ).to_dict('records')

        return chart_data

    def _analyze_single_ticker(self, ticker: str, benchmark_df: pd.DataFrame,
                              benchmark_indicators: pd.DataFrame) -> Optional[StageAnalysisResult]:
        """Internal method to analyze a single ticker."""
        try:
            stock_df, _ = fetch_stock_data(ticker, period="2y")
            if stock_df is None or len(stock_df) < 252: return None

            stock_indicators = calculate_indicators(stock_df, benchmark_df)
            if stock_indicators.empty: return None

            analyzer = StageAnalyzer(stock_indicators, ticker, benchmark_indicators)
            analysis = analyzer.analyze()

            current_stage_num = analysis['stage']
            transition_analysis = analysis['analysis']
            score = transition_analysis.get('score', 0)

            is_stage1_candidate = (current_stage_num == 1 and score >= 50)
            is_stage2 = (current_stage_num == 2)
            if not (is_stage1_candidate or is_stage2): return None

            stage_start_date = self.find_stage_start_date(ticker, stock_indicators, benchmark_indicators, current_stage_num)
            stage_history = self._find_stage_history(ticker, stock_indicators, benchmark_indicators)
            latest = stock_indicators.iloc[-1]
            stage_names = {1: 'Accumulation', 2: 'Advancing', 3: 'Distribution', 4: 'Declining'}

            return StageAnalysisResult(
                ticker=ticker,
                current_stage=current_stage_num,
                stage_name=stage_names.get(current_stage_num, 'N/A'),
                stage_start_date=stage_start_date,
                score=score,
                judgment=transition_analysis.get('level', 'N/A'),
                action=transition_analysis.get('action', 'N/A'),
                latest_price=float(latest['Close']),
                ma50=float(latest['ma50']),
                rs_rating=float(latest.get('rs_rating', 0)),
                atr_multiple=float(latest.get('atr_ma_distance_multiple', 0)),
                full_data=stock_indicators,
                stage_history=stage_history
            )
        except Exception as e:
            logger.debug(f"Analysis failed for {ticker}: {e}")
            return None

    def run_full_analysis_pipeline(self, max_workers: int = 4, max_tickers: Optional[int] = None) -> Dict:
        """Runs the full analysis pipeline for all tickers."""
        logger.info("🚀 Starting full stage analysis pipeline...")

        # In a real scenario, fetch tickers from a reliable source. Using a static file for now.
        ticker_file = os.path.join(os.path.dirname(__file__), 'russell3000.csv')
        try:
            tickers_df = pd.read_csv(ticker_file)
            tickers = tickers_df['ticker'].tolist()
        except Exception as e:
            logger.error(f"Could not read ticker file: {e}")
            return {"status": "error", "message": "Ticker file not found."}

        if max_tickers: tickers = tickers[:max_tickers]

        logger.info(f"Analyzing {len(tickers)} tickers with {max_workers} workers...")
        _, benchmark_df = fetch_stock_data("SPY", period="2y")
        if benchmark_df is None:
            logger.error("Failed to fetch benchmark data (SPY).")
            return {"status": "error", "message": "Failed to fetch benchmark data."}
        benchmark_indicators = calculate_indicators(benchmark_df, benchmark_df.copy())

        results: List[StageAnalysisResult] = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_ticker = {executor.submit(self._analyze_single_ticker, t, benchmark_df, benchmark_indicators): t for t in tickers}
            for future in tqdm(as_completed(future_to_ticker), total=len(tickers), desc="Analyzing Tickers"):
                result = future.result()
                if result:
                    results.append(result)

        logger.info(f"✅ Analysis complete. Found {len(results)} promising stocks.")
        if not results:
            return {"status": "completed", "found": 0, "results": []}

        # Sort and save summary
        results.sort(key=lambda r: (1 if r.current_stage == 2 else 2, -r.score))

        summary_data = {
            "scan_timestamp": datetime.now().isoformat(),
            "found_count": len(results),
            "stocks": [asdict(r) for r in results]
        }

        # Remove non-serializable data before saving
        for stock in summary_data['stocks']:
            stock.pop('full_data', None)
            stock.pop('chart_json', None)

        summary_path = os.path.join(self.stage_data_dir, 'latest.json')
        try:
            with open(summary_path, 'w', encoding='utf-8') as f:
                json.dump(summary_data, f, indent=2)
            logger.info(f"Successfully saved summary to {summary_path}")
        except Exception as e:
            logger.error(f"Failed to save summary file: {e}")

        return {"status": "completed", "found": len(results)}

    def get_latest_summary(self) -> Optional[Dict]:
        """Loads the latest analysis summary from a JSON file."""
        summary_path = os.path.join(self.stage_data_dir, 'latest.json')
        if not os.path.exists(summary_path):
            return None
        try:
            with open(summary_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Error loading stage analysis summary: {e}")
            return None

    def analyze_single_ticker_details(self, ticker: str) -> Optional[Dict]:
        """
        Performs a detailed analysis for a single ticker and returns
        all necessary data for the frontend, including the chart JSON.
        """
        logger.info(f"Performing detailed analysis for {ticker}...")
        _, benchmark_df = fetch_stock_data(ticker, period="2y")
        if benchmark_df is None: return None
        benchmark_indicators = calculate_indicators(benchmark_df, benchmark_df.copy())

        result = self._analyze_single_ticker(ticker, benchmark_df, benchmark_indicators)

        if result and result.full_data is not None:
            # Prepare the chart data using the new method
            result.chart_json = self._prepare_chart_data(result.full_data)

            # Prepare data for API response
            api_response = asdict(result)
            api_response.pop('full_data', None) # Don't send the full dataframe
            return api_response

        return None

# --- Instantiate the service for use in the API ---
stage_analyzer_service = StageAnalyzerService(data_dir=os.path.join(os.path.dirname(__file__), '..', 'data'))