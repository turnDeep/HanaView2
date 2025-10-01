import json
import os
import asyncio
import concurrent.futures
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
import pandas as pd
import numpy as np
from dotenv import load_dotenv
from .hwb_data_manager import HWBDataManager
import logging
import warnings

warnings.filterwarnings("ignore")
logger = logging.getLogger(__name__)
load_dotenv()

# --- Optimized Constants & Config ---
def get_env_bool(key, default):
    return os.getenv(key, str(default)).lower() in ('true', '1', 't')

# General
BATCH_SIZE = int(os.getenv('BATCH_SIZE', '50'))
MAX_WORKERS = int(os.getenv('MAX_WORKERS', '10'))
SIGNAL_COOLING_PERIOD = int(os.getenv('SIGNAL_COOLING_PERIOD', '10'))

# Rule 1: Trend Filter
ENABLE_DYNAMIC_TREND_FILTER = get_env_bool('ENABLE_DYNAMIC_TREND_FILTER', True)
WEEKLY_TREND_THRESHOLD = float(os.getenv('WEEKLY_TREND_THRESHOLD', '0.0'))
DAILY_MA_TOLERANCE = float(os.getenv('DAILY_MA_TOLERANCE', '0.03'))

# Rule 2: Setup
SETUP_MODE = os.getenv('SETUP_MODE', 'hybrid')
SETUP_LOOKBACK_DAYS = int(os.getenv('SETUP_LOOKBACK_DAYS', '30'))
ENABLE_ATR_DYNAMIC_ZONE = get_env_bool('ENABLE_ATR_DYNAMIC_ZONE', True)

# Rule 3: FVG Detection
FVG_MIN_GAP_PERCENTAGE = float(os.getenv('FVG_MIN_GAP_PERCENTAGE', '0.001'))
FVG_MAX_SEARCH_DAYS = int(os.getenv('FVG_MAX_SEARCH_DAYS', '20'))
ENABLE_VOLUME_CONFIRMATION = get_env_bool('ENABLE_VOLUME_CONFIRMATION', True)
ENABLE_DYNAMIC_MA_PROXIMITY = get_env_bool('ENABLE_DYNAMIC_MA_PROXIMITY', True)
MIN_FVG_SCORE = int(os.getenv('MIN_FVG_SCORE', '3'))

# Rule 4: Breakout
BREAKOUT_MODE = os.getenv('BREAKOUT_MODE', 'adaptive')
MIN_BREAKOUT_SCORE = int(os.getenv('MIN_BREAKOUT_SCORE', '5'))
ENABLE_VOLUME_FILTER = get_env_bool('ENABLE_VOLUME_FILTER', True)
ENABLE_MOMENTUM_FILTER = get_env_bool('ENABLE_MOMENTUM_FILTER', True)

class HWBAnalyzer:
    """Performs the optimized HWB analysis with dynamic, adaptive rules."""
    def __init__(self):
        # In a real scenario, these would be dynamically determined.
        # For now, we hardcode to 'TRENDING' as per the spec's structure.
        self.market_regime = 'TRENDING'
        self.volatility_level = 'NORMAL'
        self.params = self._adaptive_parameters()

    def _adaptive_parameters(self):
        """Adjusts parameters based on market conditions."""
        params = {
            'TRENDING': {'setup_lookback': 30, 'fvg_search_days': 20, 'ma_proximity': 0.05, 'breakout_threshold': 0.003},
            'RANGING': {'setup_lookback': 45, 'fvg_search_days': 30, 'ma_proximity': 0.03, 'breakout_threshold': 0.005},
            'VOLATILE': {'setup_lookback': 20, 'fvg_search_days': 15, 'ma_proximity': 0.08, 'breakout_threshold': 0.008}
        }
        return params.get(self.market_regime, params['TRENDING'])

    def optimized_rule1(self, df_daily: pd.DataFrame, df_weekly: pd.DataFrame) -> bool:
        """Optimized Rule ①: Dynamic Trend Strength Evaluation."""
        if df_daily is None or df_daily.empty or df_weekly is None or df_weekly.empty: return False
        if 'sma200' not in df_weekly.columns or df_weekly['sma200'].isna().all(): return False

        weekly_trend_score = 0
        latest_weekly = df_weekly.iloc[-1]
        weekly_deviation = (latest_weekly['close'] - latest_weekly['sma200']) / latest_weekly['sma200']

        if weekly_deviation > 0.20: weekly_trend_score = 3
        elif weekly_deviation > 0.10: weekly_trend_score = 2
        elif weekly_deviation >= WEEKLY_TREND_THRESHOLD: weekly_trend_score = 1
        else: return False

        if weekly_trend_score >= 2 and ENABLE_DYNAMIC_TREND_FILTER:
            return True

        latest_daily = df_daily.iloc[-1]
        daily_sma200 = latest_daily.get('sma200')
        daily_ema200 = latest_daily.get('ema200')
        daily_close = latest_daily['close']

        return (daily_sma200 is not None and daily_close > daily_sma200 * (1 - DAILY_MA_TOLERANCE)) or \
               (daily_ema200 is not None and daily_close > daily_ema200 * (1 - DAILY_MA_TOLERANCE))

    def optimized_rule2_setups(self, df_daily: pd.DataFrame) -> List[Dict]:
        """Optimized Rule ②: Multi-layered Setup Detection System."""
        setups = []
        lookback_days = self.params['setup_lookback']
        if len(df_daily) < lookback_days: return setups

        if ENABLE_ATR_DYNAMIC_ZONE:
            atr = (df_daily['high'] - df_daily['low']).rolling(14).mean()
        else:
            atr = pd.Series(0, index=df_daily.index)

        scan_start_index = max(0, len(df_daily) - lookback_days)
        for i in range(scan_start_index, len(df_daily)):
            row = df_daily.iloc[i]
            if pd.isna(row.get('sma200')) or pd.isna(row.get('ema200')): continue

            zone_width = abs(row['sma200'] - row['ema200'])
            if ENABLE_ATR_DYNAMIC_ZONE and atr.iloc[i] > 0:
                 zone_width = max(zone_width, row['close'] * (atr.iloc[i] / row['close']) * 0.5)

            zone_upper = max(row['sma200'], row['ema200']) + zone_width * 0.2
            zone_lower = min(row['sma200'], row['ema200']) - zone_width * 0.2

            if zone_lower <= row['open'] <= zone_upper and zone_lower <= row['close'] <= zone_upper:
                setups.append({'date': df_daily.index[i], 'type': 'PRIMARY', 'confidence': 0.85})
            elif (zone_lower <= row['open'] <= zone_upper) or (zone_lower <= row['close'] <= zone_upper):
                body_center = (row['open'] + row['close']) / 2
                if zone_lower <= body_center <= zone_upper:
                    setups.append({'date': df_daily.index[i], 'type': 'SECONDARY', 'confidence': 0.65})
        return setups

    def optimized_fvg_detection(self, df_daily: pd.DataFrame, setup_date: datetime) -> List[Dict]:
        """Optimized Rule ③: Extended FVG Detection + Scoring System."""
        fvgs = []
        try:
            setup_idx = df_daily.index.get_loc(setup_date)
        except KeyError: return fvgs

        max_days = self.params['fvg_search_days']
        search_end = min(setup_idx + max_days, len(df_daily) - 1)

        vol_rolling_mean = df_daily['volume'].rolling(20).mean()
        volatility = df_daily['close'].pct_change().rolling(20).std()

        for i in range(setup_idx + 2, search_end):
            candle_1, candle_3 = df_daily.iloc[i-2], df_daily.iloc[i]
            if candle_3['low'] <= candle_1['high']: continue

            gap_percentage = (candle_3['low'] - candle_1['high']) / candle_1['high']
            if gap_percentage < FVG_MIN_GAP_PERCENTAGE: continue

            fvg_score = 0
            if gap_percentage > 0.005: fvg_score += 3
            elif gap_percentage > 0.002: fvg_score += 2
            else: fvg_score += 1

            volume_surge = candle_3['volume'] / vol_rolling_mean.iloc[i] if vol_rolling_mean.iloc[i] > 0 else 1
            if ENABLE_VOLUME_CONFIRMATION:
                if volume_surge > 1.5: fvg_score += 2
                elif volume_surge > 1.2: fvg_score += 1

            ma_deviation = None
            if ENABLE_DYNAMIC_MA_PROXIMITY:
                ma_center = (candle_3.get('sma200', 0) + candle_3.get('ema200', 0)) / 2
                if ma_center > 0:
                    price_center = (candle_3['open'] + candle_3['close']) / 2
                    ma_deviation = abs(price_center - ma_center) / ma_center
                    current_volatility = volatility.iloc[i]
                    if pd.notna(current_volatility):
                        dynamic_threshold = min(0.05 + current_volatility * 2, 0.10)
                        if ma_deviation <= dynamic_threshold * 0.5: fvg_score += 3
                        elif ma_deviation <= dynamic_threshold: fvg_score += 2
                        elif ma_deviation <= dynamic_threshold * 1.5: fvg_score += 1

            if fvg_score >= MIN_FVG_SCORE:
                fvgs.append({
                    'formation_date': df_daily.index[i], 'gap_percentage': gap_percentage,
                    'score': fvg_score, 'volume_surge': volume_surge, 'ma_deviation': ma_deviation,
                    'quality': 'HIGH' if fvg_score >= 6 else 'MEDIUM' if fvg_score >= 4 else 'LOW',
                    'lower_bound': candle_1['high'], 'upper_bound': candle_3['low']
                })
        return sorted(fvgs, key=lambda x: x['score'], reverse=True)

    def optimized_breakout_detection(self, df_daily: pd.DataFrame, setup: Dict, fvg: Dict) -> Optional[Dict]:
        """Optimized Rule ④: Multi-factor Confirmation Breakout System."""
        try:
            setup_idx = df_daily.index.get_loc(setup['date'])
            fvg_idx = df_daily.index.get_loc(fvg['formation_date'])
        except KeyError: return None

        lookback_window = min(20, fvg_idx - setup_idx)
        resistance_data = df_daily.iloc[max(0, fvg_idx - lookback_window) : fvg_idx]
        if resistance_data.empty: return None

        resistance_levels = {
            'high': resistance_data['high'].max(), 'close': resistance_data['close'].max(),
            'vwap': (resistance_data['close'] * resistance_data['volume']).sum() / resistance_data['volume'].sum() if resistance_data['volume'].sum() > 0 else resistance_data['close'].mean(),
            'pivot': (resistance_data['high'].max() + resistance_data['low'].min() + resistance_data['close'].iloc[-1]) / 3
        }
        main_resistance = np.median(list(resistance_levels.values()))

        if df_daily['low'].iloc[fvg_idx:].min() < fvg['lower_bound'] * 0.98:
            return {'status': 'violated'}

        current = df_daily.iloc[-1]
        recent_volatility = df_daily['close'].pct_change().rolling(20).std().iloc[-1]
        breakout_threshold = max(self.params['breakout_threshold'], min(0.01, recent_volatility * 3))

        cond_price = current['close'] > main_resistance * (1 + breakout_threshold)
        cond_volume = not ENABLE_VOLUME_FILTER or current['volume'] > df_daily['volume'].rolling(20).mean().iloc[-1] * 1.2
        cond_momentum = not ENABLE_MOMENTUM_FILTER or df_daily['close'].pct_change(5).iloc[-1] > 0

        breakout_score = sum([3 if cond_price else 0, 2 if cond_volume else 0, 1 if cond_momentum else 0])

        if breakout_score >= MIN_BREAKOUT_SCORE:
            return {
                'status': 'breakout', 'breakout_date': df_daily.index[-1],
                'breakout_price': current['close'], 'resistance_price': main_resistance,
                'breakout_score': breakout_score, 'confidence': 'HIGH' if breakout_score >= 7 else 'MEDIUM',
            }
        return None

class HWBScanner:
    """Main class for scanning symbols using the OPTIMIZED HWB strategy."""
    def __init__(self):
        self.data_manager = HWBDataManager()
        self.analyzer = HWBAnalyzer()

    async def scan_all_symbols(self, progress_callback=None):
        symbols = list(self.data_manager.get_russell3000_symbols())
        total = len(symbols)
        logger.info(f"Optimized scan starting for {total} symbols.")
        scan_start_time = datetime.now()

        all_results = []
        processed_count = 0
        for i in range(0, total, BATCH_SIZE):
            batch = symbols[i:i + BATCH_SIZE]
            with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                future_to_symbol = {executor.submit(self._analyze_and_save_symbol, symbol): symbol for symbol in batch}
                for future in concurrent.futures.as_completed(future_to_symbol):
                    processed_count += 1
                    try:
                        result = future.result()
                        if result: all_results.extend(result)
                    except Exception as exc:
                        logger.error(f"'{future_to_symbol[future]}' generated an exception: {exc}", exc_info=True)
                    if progress_callback: await progress_callback(processed_count, total)
            await asyncio.sleep(0.1)

        summary = self._create_daily_summary(all_results, total, scan_start_time)
        self.data_manager.save_daily_summary(summary)
        logger.info("Optimized scan complete and daily summary saved.")
        return summary

    def _analyze_and_save_symbol(self, symbol: str) -> Optional[List[Dict]]:
        """Analyzes a single symbol with the optimized strategy and saves the result."""
        try:
            data = self.data_manager.get_stock_data_with_cache(symbol)
            if not data: return None
            df_daily, df_weekly = data
            if df_daily.empty or df_weekly.empty: return None

            df_daily.index = pd.to_datetime(df_daily.index)
            df_weekly.index = pd.to_datetime(df_weekly.index)
            df_daily = df_daily[~df_daily.index.duplicated(keep='last')]
            df_weekly = df_weekly[~df_weekly.index.duplicated(keep='last')]

            if not self.analyzer.optimized_rule1(df_daily, df_weekly): return None
            setups = self.analyzer.optimized_rule2_setups(df_daily)
            if not setups: return None

            all_fvgs, all_signals = [], []
            for s in setups: s['date'] = pd.to_datetime(s['date'])

            for setup in setups:
                fvgs = self.analyzer.optimized_fvg_detection(df_daily, setup['date'])
                for fvg in fvgs:
                    fvg.update({'setup_type': setup['type'], 'setup_confidence': setup['confidence'], 'setup_date': setup['date'].strftime('%Y-%m-%d')})
                    all_fvgs.append(fvg)

            active_fvgs = []
            for fvg in all_fvgs:
                breakout = self.analyzer.optimized_breakout_detection(df_daily, {'date': pd.to_datetime(fvg['setup_date'])}, fvg)
                if breakout and breakout.get('status') == 'breakout':
                    signal = {**fvg, **breakout}
                    signal['score'] = self._calculate_signal_score(signal)
                    all_signals.append(signal)
                    fvg['status'] = 'consumed'
                elif breakout and breakout.get('status') == 'violated':
                    fvg['status'] = 'violated'
                else:
                    fvg['status'] = 'active'
                active_fvgs.append(fvg)

            if not all_signals and not any(f['status'] == 'active' for f in active_fvgs): return None

            def stringify_dates(d):
                for k, v in d.items():
                    if isinstance(v, pd.Timestamp): d[k] = v.strftime('%Y-%m-%d')
                return d

            symbol_data = {
                "symbol": symbol, "last_updated": datetime.now().isoformat(),
                "market_regime": self.analyzer.market_regime,
                "setups": [stringify_dates(s.copy()) for s in setups],
                "fvgs": [stringify_dates(f.copy()) for f in active_fvgs],
                "signals": [stringify_dates(s.copy()) for s in all_signals]
            }
            symbol_data['chart_data'] = self._generate_lightweight_chart_data(symbol_data, df_daily, df_weekly)
            self.data_manager.save_symbol_data(symbol, symbol_data)

            summary_results = []
            for signal in all_signals:
                if (datetime.now() - pd.to_datetime(signal['breakout_date'])).days <= SIGNAL_COOLING_PERIOD:
                    summary_results.append({"symbol": symbol, "signal_type": "signal", "score": signal['score'], "signal_date": signal['breakout_date']})
            for fvg in active_fvgs:
                 if fvg['status'] == 'active' and fvg['quality'] in ['HIGH', 'MEDIUM']:
                    summary_results.append({"symbol": symbol, "signal_type": "candidate", "score": self._calculate_signal_score(fvg), "fvg_date": fvg['formation_date']})
            return summary_results

        except Exception as e:
            logger.error(f"Error analyzing symbol '{symbol}' with optimized scanner: {e}", exc_info=True)
            return None

    def _calculate_signal_score(self, signal_data: Dict) -> int:
        """Calculates a composite score (0-100) based on all factors."""
        setup_score = signal_data.get('setup_confidence', 0.5) * 35
        fvg_score = (signal_data.get('score', 0) / 10) * 40
        breakout_score = (signal_data.get('breakout_score', 0) / 8) * 30 if 'breakout_score' in signal_data else 0
        return int(min(setup_score + fvg_score + breakout_score, 100))

    def _generate_lightweight_chart_data(self, symbol_data: dict, df_daily: pd.DataFrame, df_weekly: pd.DataFrame) -> dict:
        """Generates a data object compatible with lightweight-charts."""
        df_plot = df_daily.copy()
        df_plot['weekly_sma200_val'] = df_weekly['sma200'].reindex(df_plot.index, method='ffill')

        def format_series(df, col):
            s = df[[col]].dropna()
            return [{"time": i.strftime('%Y-%m-%d'), "value": r[col]} for i, r in s.iterrows()]

        def clean_np_types(d):
            for k, v in d.items():
                if isinstance(v, (np.int64, np.int32)): d[k] = int(v)
                if isinstance(v, (np.float64, np.float32)): d[k] = float(v)
            return d

        candles = [{"time": i.strftime('%Y-%m-%d'), "open": r.open, "high": r.high, "low": r.low, "close": r.close} for i, r in df_plot.iterrows()]

        zones = []
        for fvg in symbol_data.get('fvgs', []):
            color_map = {'active': 'rgba(0, 200, 83, 0.2)', 'consumed': 'rgba(41, 98, 255, 0.2)', 'violated': 'rgba(255, 82, 82, 0.2)'}
            fill_color = color_map.get(fvg.get('status'), 'rgba(128, 128, 128, 0.2)')
            zones.append({"startTime": fvg['formation_date'], "endTime": datetime.now().strftime('%Y-%m-%d'), "topValue": fvg['upper_bound'], "bottomValue": fvg['lower_bound'], "fillColor": fill_color})

        markers = []
        for s in symbol_data.get('setups', []):
            markers.append({"time": s['date'], "position": "aboveBar", "color": "#FFD700" if s['type'] == 'PRIMARY' else '#F0E68C', "shape": "circle", "text": "S"})
        for s in symbol_data.get('signals', []):
            markers.append({"time": s['breakout_date'], "position": "belowBar", "color": "#2962FF", "shape": "arrowUp", "text": f"B @{s['breakout_price']:.2f}"})

        return {
            'candles': candles,
            'sma200': format_series(df_plot, 'sma200'), 'ema200': format_series(df_plot, 'ema200'),
            'weekly_sma200': format_series(df_plot, 'weekly_sma200_val'),
            'zones': [clean_np_types(z) for z in zones],
            'markers': [clean_np_types(m) for m in markers]
        }

    def _create_daily_summary(self, results: List[Dict], total_scanned: int, start_time: datetime) -> Dict:
        end_time = datetime.now()
        signals = sorted([r for r in results if r['signal_type'] == 'signal'], key=lambda x: x['score'], reverse=True)
        candidates = sorted([r for r in results if r['signal_type'] == 'candidate'], key=lambda x: x['score'], reverse=True)
        return {
            "scan_date": end_time.strftime('%Y-%m-%d'), "scan_time": end_time.strftime('%H:%M:%S'),
            "scan_duration_seconds": (end_time - start_time).total_seconds(), "total_scanned": total_scanned,
            "summary": {"signals_count": len(signals), "candidates_count": len(candidates), "signals": signals, "candidates": candidates},
            "performance": { "avg_time_per_symbol_ms": ((end_time - start_time).total_seconds() / total_scanned * 1000) if total_scanned > 0 else 0 }
        }

async def run_hwb_scan(progress_callback=None):
    """Entry point for running the HWB scan."""
    scanner = HWBScanner()
    summary = await scanner.scan_all_symbols(progress_callback)
    logger.info(f"Scan complete. Signals: {summary['summary']['signals_count']}, Candidates: {summary['summary']['candidates_count']}")
    return summary

async def analyze_single_ticker(symbol: str) -> Optional[Dict]:
    """Analyzes a single ticker and returns its full JSON data."""
    scanner = HWBScanner()
    scanner._analyze_and_save_symbol(symbol) # Run analysis and save
    # Load the potentially updated data to return it
    return scanner.data_manager.load_symbol_data(symbol)