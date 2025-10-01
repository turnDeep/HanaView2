import json
import os
import asyncio
import concurrent.futures
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
import pandas as pd
from .hwb_data_manager import HWBDataManager
import logging
import warnings

warnings.filterwarnings("ignore")
logger = logging.getLogger(__name__)

# --- Constants ---
BATCH_SIZE = 20
MAX_WORKERS = 5
SETUP_LOOKBACK_DAYS = 60
FVG_SEARCH_DAYS = 30
BREAKOUT_THRESHOLD = 0.001
FVG_ZONE_PROXIMITY = 0.10

class HWBAnalyzer:
    """Performs the HWB analysis. This class is stateless."""

    def check_rule1(self, df_daily: pd.DataFrame, df_weekly: pd.DataFrame) -> Dict[str, Any]:
        """Rule ①: Trend Check"""
        results = {"status": "failed", "weekly_sma200": False, "daily_sma200": False, "daily_ema200": False}
        if df_daily is None or df_daily.empty or df_weekly is None or df_weekly.empty:
            return results

        df_daily['weekly_sma200_val'] = df_weekly['sma200'].reindex(df_daily.index, method='ffill')
        latest = df_daily.iloc[-1]

        results["weekly_sma200"] = bool(pd.notna(latest.get('weekly_sma200_val')) and latest['close'] > latest['weekly_sma200_val'])
        results["daily_sma200"] = bool(pd.notna(latest.get('sma200')) and latest['close'] > latest['sma200'])
        results["daily_ema200"] = bool(pd.notna(latest.get('ema200')) and latest['close'] > latest['ema200'])

        if results["weekly_sma200"] and (results["daily_sma200"] or results["daily_ema200"]):
            results["status"] = "passed"

        return results

    def find_setups(self, df_daily: pd.DataFrame) -> List[Dict]:
        """Rule ②: Setup Detection"""
        setups = []
        valid_data = df_daily[df_daily['sma200'].notna() & df_daily['ema200'].notna()].tail(SETUP_LOOKBACK_DAYS)
        for i in range(len(valid_data)):
            row = valid_data.iloc[i]
            zone_upper = max(row['sma200'], row['ema200'])
            zone_lower = min(row['sma200'], row['ema200'])
            if zone_lower <= row['open'] <= zone_upper and zone_lower <= row['close'] <= zone_upper:
                setups.append({
                    'id': f"setup_{valid_data.index[i].strftime('%Y%m%d')}",
                    'date': valid_data.index[i].strftime('%Y-%m-%d'),
                    'zone_upper': zone_upper, 'zone_lower': zone_lower,
                    'sma200': row['sma200'], 'ema200': row['ema200'],
                    'candle': {'open': row['open'], 'close': row['close'], 'high': row['high'], 'low': row['low']}
                })
        return setups

    def detect_fvg(self, df_daily: pd.DataFrame, setup: Dict) -> List[Dict]:
        """Rule ③: FVG Detection"""
        fvgs = []
        setup_date = datetime.strptime(setup['date'], '%Y-%m-%d').date()
        df_daily.index = pd.to_datetime(df_daily.index).date
        try:
            setup_idx_loc = df_daily.index.get_loc(setup_date)
        except KeyError:
            return fvgs

        search_end = min(setup_idx_loc + FVG_SEARCH_DAYS, len(df_daily) - 2)
        for i in range(setup_idx_loc + 2, search_end):
            c1, c2, c3 = df_daily.iloc[i-2], df_daily.iloc[i-1], df_daily.iloc[i]
            if c3['low'] > c1['high']:
                ma_prox = self._check_ma_proximity(c3, c1)
                if ma_prox['condition_a_met'] or ma_prox['condition_b_met']:
                    gap = c3['low'] - c1['high']
                    fvgs.append({
                        'id': f"fvg_{df_daily.index[i].strftime('%Y%m%d')}_{i}",
                        'setup_id': setup['id'], 'formation_date': df_daily.index[i].strftime('%Y-%m-%d'),
                        'candle_1_high': c1['high'], 'candle_3_low': c3['low'],
                        'upper_bound': c3['low'], 'lower_bound': c1['high'],
                        'gap_size': gap, 'gap_percentage': (gap / c1['high']) * 100,
                        'ma_proximity': ma_prox, 'status': 'active'
                    })
        return fvgs

    def _check_ma_proximity(self, c3: pd.Series, c1: pd.Series) -> Dict[str, Any]:
        """Check if FVG is near a key moving average."""
        result = {'condition_a_met': False, 'condition_b_met': False, 'closest_ma': None, 'distance_percentage': 999}
        if pd.isna(c3.get('sma200')) or pd.isna(c3.get('ema200')): return result

        fvg_center = (c1['high'] + c3['low']) / 2
        for ma_name, ma_val in [('sma200', c3['sma200']), ('ema200', c3['ema200'])]:
            dist = abs(fvg_center - ma_val) / ma_val
            if dist < result['distance_percentage']:
                result['distance_percentage'] = dist
                result['closest_ma'] = ma_name
            if dist <= FVG_ZONE_PROXIMITY:
                result['condition_b_met'] = True
        return result

    def check_breakout(self, df_daily: pd.DataFrame, setup: Dict, fvg: Dict) -> Optional[Dict]:
        """Rule ④: Breakout Check"""
        setup_date = datetime.strptime(setup['date'], '%Y-%m-%d').date()
        fvg_date = datetime.strptime(fvg['formation_date'], '%Y-%m-%d').date()
        df_daily.index = pd.to_datetime(df_daily.index).date
        try:
            setup_idx, fvg_idx = df_daily.index.get_loc(setup_date), df_daily.index.get_loc(fvg_date)
        except KeyError: return None

        resistance_high = df_daily.iloc[setup_idx + 1 : fvg_idx]['high'].max()
        if pd.isna(resistance_high): resistance_high = df_daily.iloc[setup_idx]['high']

        if not df_daily.iloc[fvg_idx + 1:].empty and df_daily.iloc[fvg_idx + 1:]['low'].min() < fvg['lower_bound']:
            fvg['status'] = 'violated'
            return None

        current = df_daily.iloc[-1]
        if current['close'] > resistance_high * (1 + BREAKOUT_THRESHOLD):
            fvg['status'] = 'consumed'
            return {
                'id': f"signal_{df_daily.index[-1].strftime('%Y%m%d')}",
                'setup_id': setup['id'], 'fvg_id': fvg['id'], 'signal_type': 's2_breakout',
                'signal_date': df_daily.index[-1].strftime('%Y-%m-%d'),
                'breakout_price': current['close'], 'resistance_price': resistance_high,
                'breakout_percentage': (current['close'] / resistance_high - 1) * 100
            }
        return None

class HWBScanner:
    """Main class for scanning symbols using the HWB strategy."""
    def __init__(self):
        self.data_manager = HWBDataManager()
        self.analyzer = HWBAnalyzer()

    async def scan_all_symbols(self, progress_callback=None):
        """Scan all symbols, generate JSON files, and create a daily summary."""
        symbols = list(self.data_manager.get_russell3000_symbols())
        total = len(symbols)
        logger.info(f"Scan starting for {total} symbols.")
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
                        if result: all_results.append(result)
                    except Exception as exc:
                        logger.error(f"'{future_to_symbol[future]}' generated an exception: {exc}", exc_info=True)
                    if progress_callback: await progress_callback(processed_count, total)
            await asyncio.sleep(0.1)

        summary = self._create_daily_summary(all_results, total, scan_start_time)
        self.data_manager.save_daily_summary(summary)
        logger.info("Scan complete and daily summary saved.")
        return summary

    def _analyze_and_save_symbol(self, symbol: str) -> Optional[Dict]:
        """Analyzes a single symbol and saves the result to a JSON file."""
        try:
            data = self.data_manager.get_stock_data_with_cache(symbol)
            if not data: return None
            df_daily, df_weekly = data

            # Defensive coding: remove any potential duplicate dates from the index
            df_daily = df_daily[~df_daily.index.duplicated(keep='last')]
            df_weekly = df_weekly[~df_weekly.index.duplicated(keep='last')]

            existing_data = self.data_manager.load_symbol_data(symbol) or {
                "symbol": symbol, "last_updated": None, "setups": [], "fvgs": [], "signals": []
            }

            trend_check = self.analyzer.check_rule1(df_daily, df_weekly)
            if trend_check["status"] != "passed":
                return None # No need to analyze further if trend is not bullish

            new_setups = self.analyzer.find_setups(df_daily)
            if not new_setups: return None

            # Merge setups: keep old, add new if ID doesn't exist
            existing_setup_ids = {s['id'] for s in existing_data['setups']}
            for setup in new_setups:
                if setup['id'] not in existing_setup_ids:
                    existing_data['setups'].append(setup)

            new_analysis_found = False
            for setup in existing_data['setups']:
                new_fvgs = self.analyzer.detect_fvg(df_daily, setup)
                existing_fvg_ids = {f['id'] for f in existing_data['fvgs']}
                for fvg in new_fvgs:
                    if fvg['id'] not in existing_fvg_ids:
                        existing_data['fvgs'].append(fvg)
                        new_analysis_found = True

            for fvg in existing_data['fvgs']:
                if fvg['status'] != 'active': continue
                breakout = self.analyzer.check_breakout(df_daily, next(s for s in existing_data['setups'] if s['id'] == fvg['setup_id']), fvg)
                if breakout:
                    existing_signal_ids = {s['id'] for s in existing_data['signals']}
                    if breakout['id'] not in existing_signal_ids:
                        breakout['score'] = self._calculate_score(setup, fvg, breakout)
                        existing_data['signals'].append(breakout)
                        new_analysis_found = True

            if new_analysis_found:
                existing_data['last_updated'] = datetime.now().isoformat()
                existing_data['last_scan'] = datetime.now().strftime('%Y-%m-%d')
                existing_data['trend_check'] = trend_check

                # Generate and add chart data before saving
                existing_data['chart_data'] = self._generate_lightweight_chart_data(existing_data, df_daily)

                self.data_manager.save_symbol_data(symbol, existing_data)

                # Return a summary for the daily report
                latest_signal = existing_data['signals'][-1] if existing_data['signals'] else None
                if latest_signal:
                    return {"symbol": symbol, "signal_type": "s2_breakout", "score": latest_signal['score'], "signal_date": latest_signal['signal_date']}
                else:
                    # It's a candidate if new FVGs were found but no breakout
                    latest_fvg = existing_data['fvgs'][-1]
                    return {"symbol": symbol, "signal_type": "s1_fvg", "score": self._calculate_score(setup, latest_fvg, None), "fvg_date": latest_fvg['formation_date']}

            return None

        except Exception as e:
            logger.error(f"Error analyzing symbol '{symbol}': {e}", exc_info=True)
            return None

    def _calculate_score(self, setup: Dict, fvg: Dict, breakout: Optional[Dict]) -> int:
        """Calculates a score for the signal/candidate (0-100)."""
        score = 0
        # Setup score (max 30)
        zone_width_perc = (setup['zone_upper'] - setup['zone_lower']) / setup['candle']['close']
        score += max(0, 30 - (zone_width_perc * 2000))
        # FVG score (max 40)
        score += min(40, fvg.get('gap_percentage', 0) * 50)
        # Breakout score (max 30)
        if breakout:
            score += min(30, breakout.get('breakout_percentage', 0) * 20)
        return int(min(score, 100))

    def _generate_lightweight_chart_data(self, symbol_data: dict, df_daily: pd.DataFrame) -> dict:
        """Generates a data object compatible with lightweight-charts."""
        df_plot = df_daily.tail(180).copy()
        df_plot.index = pd.to_datetime(df_plot.index)

        def format_series(df, column):
            series = df[[column]].dropna()
            return [{"time": idx.strftime('%Y-%m-%d'), "value": row[column]} for idx, row in series.iterrows()]

        candles = [{"time": idx.strftime('%Y-%m-%d'), "open": r.open, "high": r.high, "low": r.low, "close": r.close} for idx, r in df_plot.iterrows()]

        zones = []
        for setup in symbol_data.get('setups', []):
            zones.append({
                "type": "setup", "id": setup['id'],
                "startTime": setup['date'], "endTime": datetime.now().strftime('%Y-%m-%d'),
                "topValue": setup['zone_upper'], "bottomValue": setup['zone_lower'],
                "fillColor": "rgba(255, 215, 0, 0.2)", "borderColor": "#FFD700"
            })
        for fvg in symbol_data.get('fvgs', []):
             zones.append({
                "type": "fvg", "id": fvg['id'],
                "startTime": fvg['formation_date'], "endTime": datetime.now().strftime('%Y-%m-%d'),
                "topValue": fvg['upper_bound'], "bottomValue": fvg['lower_bound'],
                "fillColor": "rgba(0, 200, 83, 0.2)", "borderColor": "#00C853"
            })

        markers = []
        for signal in symbol_data.get('signals', []):
            markers.append({
                "time": signal['signal_date'], "position": "belowBar", "color": "#2962FF",
                "shape": "arrowUp", "text": "B", "size": 2, "id": signal['id']
            })

        return {
            'candles': candles,
            'sma200': format_series(df_plot, 'sma200'),
            'ema200': format_series(df_plot, 'ema200'),
            'weekly_sma200': format_series(df_plot, 'weekly_sma200_val'),
            'zones': zones,
            'markers': markers
        }

    def _create_daily_summary(self, results: List[Dict], total_scanned: int, start_time: datetime) -> Dict:
        """Creates the daily summary JSON from the scan results."""
        end_time = datetime.now()
        signals = sorted([r for r in results if r['signal_type'] == 's2_breakout'], key=lambda x: x['score'], reverse=True)
        candidates = sorted([r for r in results if r['signal_type'] == 's1_fvg'], key=lambda x: x['score'], reverse=True)

        return {
            "scan_date": end_time.strftime('%Y-%m-%d'),
            "scan_time": end_time.strftime('%H:%M:%S'),
            "scan_duration_seconds": (end_time - start_time).total_seconds(),
            "total_scanned": total_scanned,
            "summary": {
                "signals_count": len(signals),
                "candidates_count": len(candidates),
                "signals": signals,
                "candidates": candidates,
            },
            "performance": { "avg_time_per_symbol_ms": ((end_time - start_time).total_seconds() / total_scanned) * 1000 if total_scanned > 0 else 0 }
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