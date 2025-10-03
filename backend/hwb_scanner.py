import json
import os
import asyncio
import concurrent.futures
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
import pandas as pd
import numpy as np
import uuid
from dotenv import load_dotenv
from .hwb_data_manager import HWBDataManager
import logging
import warnings

warnings.filterwarnings("ignore")
logger = logging.getLogger(__name__)
load_dotenv()

# --- Constants ---
BATCH_SIZE = int(os.getenv('BATCH_SIZE', '50'))
MAX_WORKERS = int(os.getenv('MAX_WORKERS', '10'))

# Rule 1: Trend Filter
WEEKLY_TREND_THRESHOLD = float(os.getenv('WEEKLY_TREND_THRESHOLD', '0.0'))

# Rule 2: Setup
SETUP_LOOKBACK_DAYS = int(os.getenv('SETUP_LOOKBACK_DAYS', '30'))
INITIAL_SCAN_MIN_HISTORY_DAYS = int(os.getenv('INITIAL_SCAN_MIN_HISTORY_DAYS', '1000'))  # 初回スキャン開始位置（週足200MA計算に約1000営業日必要）

# Rule 3: FVG Detection
FVG_MIN_GAP_PERCENTAGE = float(os.getenv('FVG_MIN_GAP_PERCENTAGE', '0.001'))
FVG_MAX_SEARCH_DAYS = int(os.getenv('FVG_MAX_SEARCH_DAYS', '20'))
MIN_FVG_SCORE = int(os.getenv('MIN_FVG_SCORE', '3'))

# Rule 4: Breakout
MIN_BREAKOUT_SCORE = int(os.getenv('MIN_BREAKOUT_SCORE', '5'))


class HWBAnalyzer:
    """HWB分析エンジン（時系列週足フィルター対応版）"""
    
    def __init__(self):
        self.market_regime = 'TRENDING'
        self.params = self._adaptive_parameters()

    def _adaptive_parameters(self):
        """市場環境に応じたパラメータ調整"""
        params = {
            'TRENDING': {
                'setup_lookback': 30, 
                'fvg_search_days': 20, 
                'ma_proximity': 0.05, 
                'breakout_threshold': 0.003
            },
        }
        return params.get(self.market_regime, params['TRENDING'])

    def optimized_rule1(self, df_daily: pd.DataFrame, df_weekly: pd.DataFrame) -> bool:
        """Rule ①: 週足トレンドフィルター（現時点チェック用）"""
        if df_weekly is None or df_weekly.empty:
            return False
        if 'sma200' not in df_weekly.columns or df_weekly['sma200'].isna().all():
            return False

        latest_weekly = df_weekly.iloc[-1]
        if pd.isna(latest_weekly['sma200']) or latest_weekly['sma200'] == 0:
            return False

        weekly_deviation = (latest_weekly['close'] - latest_weekly['sma200']) / latest_weekly['sma200']
        return weekly_deviation >= WEEKLY_TREND_THRESHOLD

    def check_weekly_trend_at_date(self, df_weekly: pd.DataFrame, check_date: pd.Timestamp) -> bool:
        """
        🔥 重要な修正：特定日時点での週足トレンドフィルター
        
        過去のセットアップを検証する際、「その時点」で週足200MA以上だったかをチェック
        
        Args:
            df_weekly: 週足データフレーム
            check_date: チェックする日付（セットアップ日など）
        
        Returns:
            その日時点で週足200MA以上ならTrue
        """
        if df_weekly is None or df_weekly.empty:
            return False
        
        # check_date以前の週足データのみを使用（未来のデータを見ない）
        df_weekly_historical = df_weekly[df_weekly.index <= check_date]
        
        if df_weekly_historical.empty:
            return False
        
        if 'sma200' not in df_weekly_historical.columns or df_weekly_historical['sma200'].isna().all():
            return False
        
        # その時点での最新週足データ
        latest_weekly_at_date = df_weekly_historical.iloc[-1]
        
        if pd.isna(latest_weekly_at_date['sma200']) or latest_weekly_at_date['sma200'] == 0:
            return False
        
        weekly_deviation = (
            (latest_weekly_at_date['close'] - latest_weekly_at_date['sma200']) 
            / latest_weekly_at_date['sma200']
        )
        
        return weekly_deviation >= WEEKLY_TREND_THRESHOLD

    def optimized_rule2_setups(
        self, 
        df_daily: pd.DataFrame, 
        df_weekly: pd.DataFrame,
        full_scan: bool = False,
        scan_start_date: Optional[pd.Timestamp] = None
    ) -> List[Dict]:
        """
        Rule ②: セットアップ検出（週足フィルター統合＋全期間対応版）
        
        重要な修正:
        1. full_scan=True時は全期間（200日目以降）をスキャン
        2. 各セットアップ候補で、その日時点の週足フィルターをチェック
        3. scan_start_dateが指定されている場合、その日以降のみスキャン
        
        Args:
            df_daily: 日足データ
            df_weekly: 週足データ
            full_scan: 初回分析時はTrue（全期間スキャン）
            scan_start_date: 開始日（差分分析時に使用）
        """
        setups = []
        
        # スキャン範囲の決定
        if full_scan:
            # 🔥 初回分析時：200MA計算に必要な最小期間から全期間スキャン
            scan_start_index = max(0, INITIAL_SCAN_MIN_HISTORY_DAYS)
            logger.info(f"セットアップ検出：全期間スキャン（{scan_start_index}日目〜{len(df_daily)}日目）")
        elif scan_start_date:
            # 差分分析時：指定日以降
            try:
                scan_start_index = df_daily.index.searchsorted(scan_start_date)
            except:
                scan_start_index = max(0, len(df_daily) - SETUP_LOOKBACK_DAYS)
        else:
            # デフォルト：最近N日
            scan_start_index = max(0, len(df_daily) - SETUP_LOOKBACK_DAYS)
        
        if scan_start_index >= len(df_daily):
            return setups
        
        # ATR計算（全期間）
        atr = (df_daily['high'] - df_daily['low']).rolling(14).mean()
        
        for i in range(scan_start_index, len(df_daily)):
            row = df_daily.iloc[i]
            setup_date = df_daily.index[i]
            
            # 🔥 重要：この日付時点で週足200MAフィルターをチェック
            if not self.check_weekly_trend_at_date(df_weekly, setup_date):
                continue
            
            if pd.isna(row.get('sma200')) or pd.isna(row.get('ema200')):
                continue

            # MAゾーン計算
            zone_width = abs(row['sma200'] - row['ema200'])
            if atr.iloc[i] > 0:
                zone_width = max(zone_width, row['close'] * (atr.iloc[i] / row['close']) * 0.5)

            zone_upper = max(row['sma200'], row['ema200']) + zone_width * 0.2
            zone_lower = min(row['sma200'], row['ema200']) - zone_width * 0.2

            # セットアップ判定
            if zone_lower <= row['open'] <= zone_upper and zone_lower <= row['close'] <= zone_upper:
                setup = {
                    'id': str(uuid.uuid4()),
                    'date': setup_date,
                    'type': 'PRIMARY',
                    'confidence': 0.85,
                    'status': 'active',
                    'weekly_deviation': self._get_weekly_deviation_at_date(df_weekly, setup_date)  # 記録
                }
                setups.append(setup)
            elif (zone_lower <= row['open'] <= zone_upper) or (zone_lower <= row['close'] <= zone_upper):
                body_center = (row['open'] + row['close']) / 2
                if zone_lower <= body_center <= zone_upper:
                    setup = {
                        'id': str(uuid.uuid4()),
                        'date': setup_date,
                        'type': 'SECONDARY',
                        'confidence': 0.65,
                        'status': 'active',
                        'weekly_deviation': self._get_weekly_deviation_at_date(df_weekly, setup_date)
                    }
                    setups.append(setup)
        
        logger.info(f"セットアップ検出完了：{len(setups)}件")
        return setups

    def _get_weekly_deviation_at_date(self, df_weekly: pd.DataFrame, check_date: pd.Timestamp) -> Optional[float]:
        """指定日時点での週足200MAからの乖離率を取得（記録用）"""
        try:
            df_weekly_historical = df_weekly[df_weekly.index <= check_date]
            if df_weekly_historical.empty:
                return None
            
            latest = df_weekly_historical.iloc[-1]
            if pd.isna(latest['sma200']) or latest['sma200'] == 0:
                return None
            
            return (latest['close'] - latest['sma200']) / latest['sma200']
        except:
            return None

    def optimized_fvg_detection(self, df_daily: pd.DataFrame, setup: Dict) -> List[Dict]:
        """Rule ③: FVG検出（setup_id紐付け版）"""
        fvgs = []
        setup_date = setup['date']
        
        try:
            setup_idx = df_daily.index.get_loc(setup_date)
        except KeyError:
            return fvgs

        max_days = self.params['fvg_search_days']
        search_end = min(setup_idx + max_days, len(df_daily) - 1)

        vol_rolling_mean = df_daily['volume'].rolling(20).mean()
        volatility = df_daily['close'].pct_change().rolling(20).std()

        for i in range(setup_idx + 2, search_end):
            candle_1, candle_3 = df_daily.iloc[i-2], df_daily.iloc[i]
            
            # FVG条件: candle_3のlowがcandle_1のhighより上
            if candle_3['low'] <= candle_1['high']:
                continue

            gap_percentage = (candle_3['low'] - candle_1['high']) / candle_1['high']
            if gap_percentage < FVG_MIN_GAP_PERCENTAGE:
                continue

            # スコアリング
            fvg_score = 0
            if gap_percentage > 0.005:
                fvg_score += 3
            elif gap_percentage > 0.002:
                fvg_score += 2
            else:
                fvg_score += 1

            # ボリューム確認
            volume_surge = candle_3['volume'] / vol_rolling_mean.iloc[i] if vol_rolling_mean.iloc[i] > 0 else 1
            if volume_surge > 1.5:
                fvg_score += 2
            elif volume_surge > 1.2:
                fvg_score += 1

            # MA proximity
            ma_deviation = None
            ma_center = (candle_3.get('sma200', 0) + candle_3.get('ema200', 0)) / 2
            if ma_center > 0:
                price_center = (candle_3['open'] + candle_3['close']) / 2
                ma_deviation = abs(price_center - ma_center) / ma_center
                current_volatility = volatility.iloc[i]
                if pd.notna(current_volatility):
                    dynamic_threshold = min(0.05 + current_volatility * 2, 0.10)
                    if ma_deviation <= dynamic_threshold * 0.5:
                        fvg_score += 3
                    elif ma_deviation <= dynamic_threshold:
                        fvg_score += 2
                    elif ma_deviation <= dynamic_threshold * 1.5:
                        fvg_score += 1

            if fvg_score >= MIN_FVG_SCORE:
                fvg = {
                    'id': str(uuid.uuid4()),
                    'setup_id': setup['id'],
                    'formation_date': df_daily.index[i],
                    'gap_percentage': gap_percentage,
                    'score': fvg_score,
                    'volume_surge': volume_surge,
                    'ma_deviation': ma_deviation,
                    'quality': 'HIGH' if fvg_score >= 6 else 'MEDIUM' if fvg_score >= 4 else 'LOW',
                    'lower_bound': candle_1['high'],
                    'upper_bound': candle_3['low'],
                    'status': 'active'
                }
                fvgs.append(fvg)
        
        return sorted(fvgs, key=lambda x: x['score'], reverse=True)

    def optimized_breakout_detection_all_periods(
        self, 
        df_daily: pd.DataFrame, 
        setup: Dict, 
        fvg: Dict
    ) -> Optional[Dict]:
        """Rule ④: ブレイクアウト検出（全期間スキャン版）"""
        try:
            setup_idx = df_daily.index.get_loc(setup['date'])
            fvg_idx = df_daily.index.get_loc(fvg['formation_date'])
        except KeyError:
            return None

        # レジスタンスレベル計算
        lookback_window = min(20, fvg_idx - setup_idx)
        resistance_data = df_daily.iloc[max(0, fvg_idx - lookback_window) : fvg_idx]
        
        if resistance_data.empty:
            return None

        resistance_levels = {
            'high': resistance_data['high'].max(),
            'close': resistance_data['close'].max(),
            'vwap': (resistance_data['close'] * resistance_data['volume']).sum() / resistance_data['volume'].sum() 
                    if resistance_data['volume'].sum() > 0 
                    else resistance_data['close'].mean(),
            'pivot': (resistance_data['high'].max() + resistance_data['low'].min() + resistance_data['close'].iloc[-1]) / 3
        }
        main_resistance = np.median(list(resistance_levels.values()))

        # FVG違反チェック
        post_fvg_data = df_daily.iloc[fvg_idx:]
        if post_fvg_data['low'].min() < fvg['lower_bound'] * 0.98:
            return {'status': 'violated', 'violated_date': post_fvg_data['low'].idxmin()}

        # ブレイクアウトチェック（FVG形成日から現在まで）
        vol_ma = df_daily['volume'].rolling(20).mean()
        
        for i in range(fvg_idx + 1, len(df_daily)):
            current = df_daily.iloc[i]
            recent_volatility = df_daily['close'].pct_change().rolling(20).std().iloc[i]
            breakout_threshold = max(self.params['breakout_threshold'], min(0.01, recent_volatility * 3))

            cond_price = current['close'] > main_resistance * (1 + breakout_threshold)
            cond_volume = current['volume'] > vol_ma.iloc[i] * 1.2 if pd.notna(vol_ma.iloc[i]) else False
            cond_momentum = df_daily['close'].pct_change(5).iloc[i] > 0

            breakout_score = sum([
                3 if cond_price else 0,
                2 if cond_volume else 0,
                1 if cond_momentum else 0
            ])

            if breakout_score >= MIN_BREAKOUT_SCORE:
                return {
                    'status': 'breakout',
                    'breakout_date': df_daily.index[i],
                    'breakout_price': current['close'],
                    'resistance_price': main_resistance,
                    'breakout_score': breakout_score,
                    'confidence': 'HIGH' if breakout_score >= 7 else 'MEDIUM',
                }
        
        return None


class HWBScanner:
    """メインスキャナー（全期間対応版）"""
    
    def __init__(self):
        self.data_manager = HWBDataManager()
        self.analyzer = HWBAnalyzer()

    async def scan_all_symbols(self, progress_callback=None):
        """全シンボルスキャン"""
        symbols = list(self.data_manager.get_russell3000_symbols())
        total = len(symbols)
        logger.info(f"スキャン開始: {total}銘柄")
        scan_start_time = datetime.now()

        all_results = []
        processed_count = 0
        
        for i in range(0, total, BATCH_SIZE):
            batch = symbols[i:i + BATCH_SIZE]
            with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                future_to_symbol = {
                    executor.submit(self._analyze_and_save_symbol, symbol): symbol 
                    for symbol in batch
                }
                for future in concurrent.futures.as_completed(future_to_symbol):
                    processed_count += 1
                    try:
                        result = future.result()
                        if result:
                            all_results.extend(result)
                    except Exception as exc:
                        logger.error(f"エラー: {future_to_symbol[future]} - {exc}", exc_info=True)
                    if progress_callback:
                        await progress_callback(processed_count, total)
            await asyncio.sleep(0.1)

        summary = self._create_daily_summary(all_results, total, scan_start_time)
        self.data_manager.save_daily_summary(summary)
        logger.info("スキャン完了")
        return summary

    def _analyze_and_save_symbol(self, symbol: str) -> Optional[List[Dict]]:
        """単一銘柄分析（状態ベース差分処理版）"""
        try:
            data = self.data_manager.get_stock_data_with_cache(symbol)
            if not data:
                return None
            
            df_daily, df_weekly = data
            if df_daily.empty or df_weekly.empty:
                return None

            df_daily.index = pd.to_datetime(df_daily.index)
            df_weekly.index = pd.to_datetime(df_weekly.index)
            df_daily = df_daily[~df_daily.index.duplicated(keep='last')]
            df_weekly = df_weekly[~df_weekly.index.duplicated(keep='last')]

            # Rule ①: 現時点のトレンドフィルター（初期チェック）
            if not self.analyzer.optimized_rule1(df_daily, df_weekly):
                return None

            # 既存データ確認
            existing_data = self.data_manager.load_symbol_data(symbol)
            
            if existing_data:
                result = self._differential_analysis(symbol, df_daily, df_weekly, existing_data)
            else:
                # 🔥 初回分析は全期間スキャン
                result = self._full_analysis(symbol, df_daily, df_weekly)
            
            return result

        except Exception as e:
            logger.error(f"分析エラー: {symbol} - {e}", exc_info=True)
            return None

    def _differential_analysis(
        self, 
        symbol: str, 
        df_daily: pd.DataFrame, 
        df_weekly: pd.DataFrame,
        existing_data: dict
    ) -> Optional[List[Dict]]:
        """差分分析（週足フィルター対応版）"""
        existing_setups = existing_data.get('setups', [])
        existing_fvgs = existing_data.get('fvgs', [])
        existing_signals = existing_data.get('signals', [])
        
        # 日付変換
        for item in existing_setups + existing_fvgs + existing_signals:
            if 'date' in item:
                item['date'] = pd.to_datetime(item['date'])
            if 'formation_date' in item:
                item['formation_date'] = pd.to_datetime(item['formation_date'])
            if 'breakout_date' in item:
                item['breakout_date'] = pd.to_datetime(item['breakout_date'])
        
        active_setups = [s for s in existing_setups if s.get('status') == 'active']
        active_fvgs = [f for f in existing_fvgs if f.get('status') == 'active']
        
        last_analyzed_date = pd.to_datetime(existing_data.get('last_updated', '2000-01-01')).date()
        latest_data_date = df_daily.index[-1].date()
        
        if latest_data_date <= last_analyzed_date:
            logger.debug(f"{symbol}: 新しいデータなし")
            return self._create_summary_from_existing(existing_data)
        
        logger.info(f"{symbol}: 差分分析 ({last_analyzed_date} → {latest_data_date})")
        
        updated = False
        new_fvgs_found = []
        
        # アクティブセットアップからFVG探索
        if active_setups:
            for setup in active_setups:
                setup_date = setup['date']
                setup_idx = df_daily.index.get_loc(setup_date)
                
                setup_fvgs = [f for f in existing_fvgs if f.get('setup_id') == setup['id']]
                if setup_fvgs:
                    last_fvg_date = max(f['formation_date'] for f in setup_fvgs)
                    search_start_date = last_fvg_date + pd.Timedelta(days=1)
                    search_start = df_daily.index.searchsorted(search_start_date)
                else:
                    search_start = setup_idx + 2
                
                search_end = min(setup_idx + FVG_MAX_SEARCH_DAYS, len(df_daily) - 1)
                new_data_start = df_daily.index.searchsorted(
                    pd.Timestamp(last_analyzed_date) + pd.Timedelta(days=1)
                )
                search_start = max(search_start, new_data_start)
                
                if search_start >= search_end:
                    continue
                
                new_fvgs = self._detect_fvg_in_range(df_daily, setup, search_start, search_end)
                
                if new_fvgs:
                    existing_data['fvgs'].extend(new_fvgs)
                    new_fvgs_found.extend(new_fvgs)
                    updated = True
        
        # ブレイクアウトチェック
        all_active_fvgs = active_fvgs + new_fvgs_found
        
        if all_active_fvgs:
            for fvg in all_active_fvgs:
                setup = next((s for s in existing_setups if s['id'] == fvg['setup_id']), None)
                if not setup or setup.get('status') == 'consumed':
                    continue
                
                fvg_date = fvg['formation_date']
                fvg_idx = df_daily.index.get_loc(fvg_date)
                new_data_start = df_daily.index.searchsorted(
                    pd.Timestamp(last_analyzed_date) + pd.Timedelta(days=1)
                )
                check_start = max(fvg_idx + 1, new_data_start)
                
                if check_start >= len(df_daily):
                    continue
                
                breakout = self._check_breakout_in_range(
                    df_daily, setup, fvg, check_start, len(df_daily)
                )
                
                if breakout and breakout.get('status') == 'breakout':
                    signal = {**fvg, **breakout}
                    signal['score'] = self._calculate_signal_score(signal)
                    existing_data['signals'].append(signal)
                    
                    setup['status'] = 'consumed'
                    for related_fvg in existing_data['fvgs']:
                        if related_fvg.get('setup_id') == setup['id']:
                            related_fvg['status'] = 'consumed'
                    
                    updated = True
                    break
                
                elif breakout and breakout.get('status') == 'violated':
                    fvg['status'] = 'violated'
                    fvg['violated_date'] = breakout.get('violated_date')
                    updated = True
        
        # 新規セットアップ探索（週足フィルター対応）
        if not active_setups or all(s.get('status') == 'consumed' for s in existing_setups):
            logger.info(f"{symbol}: 新セットアップ探索")
            
            new_start_date = pd.Timestamp(last_analyzed_date) + pd.Timedelta(days=1)
            
            # 🔥 週足フィルター付きでセットアップ検出
            new_setups = self.analyzer.optimized_rule2_setups(
                df_daily, 
                df_weekly,
                full_scan=False,
                scan_start_date=new_start_date
            )
            
            if new_setups:
                existing_data['setups'].extend(new_setups)
                updated = True
                logger.info(f"{symbol}: {len(new_setups)}件の新セットアップ")
        
        if updated:
            existing_data['last_updated'] = datetime.now().isoformat()
            self._save_symbol_data_with_chart(symbol, existing_data, df_daily, df_weekly)
        
        return self._create_summary_from_existing(existing_data)

    def _full_analysis(
        self,
        symbol: str,
        df_daily: pd.DataFrame,
        df_weekly: pd.DataFrame
    ) -> Optional[List[Dict]]:
        """
        🔥 初回フルスキャン（全期間対応版）
        
        重要な変更:
        - full_scan=True で全期間（6年分）をスキャン
        - 各セットアップは週足フィルターを通過したもののみ
        """
        logger.info(f"{symbol}: 初回フルスキャン（全期間：{len(df_daily)}日分）")
        
        # Rule ②: セットアップ検出（全期間、週足フィルター統合）
        setups = self.analyzer.optimized_rule2_setups(
            df_daily, 
            df_weekly, 
            full_scan=True  # 🔥 全期間スキャン
        )
        
        if not setups:
            logger.info(f"{symbol}: セットアップなし（全期間）")
            return None

        consumed_setups = set()
        consumed_fvgs = set()
        all_fvgs = []
        all_signals = []

        for s in setups:
            s['date'] = pd.to_datetime(s['date'])

        # 各セットアップに対してFVG検出 → ブレイクアウト検出
        for setup in setups:
            if setup['id'] in consumed_setups:
                setup['status'] = 'consumed'
                continue

            fvgs = self.analyzer.optimized_fvg_detection(df_daily, setup)
            signal_found_for_this_setup = False
            
            for fvg in fvgs:
                if fvg['id'] in consumed_fvgs:
                    fvg['status'] = 'consumed'
                    all_fvgs.append(fvg)
                    continue

                breakout = self.analyzer.optimized_breakout_detection_all_periods(
                    df_daily, setup, fvg
                )

                if breakout:
                    if breakout.get('status') == 'breakout':
                        signal = {**fvg, **breakout}
                        signal['score'] = self._calculate_signal_score(signal)
                        all_signals.append(signal)
                        
                        consumed_setups.add(setup['id'])
                        consumed_fvgs.add(fvg['id'])
                        fvg['status'] = 'consumed'
                        setup['status'] = 'consumed'
                        signal_found_for_this_setup = True
                        break
                    
                    elif breakout.get('status') == 'violated':
                        fvg['status'] = 'violated'
                        fvg['violated_date'] = breakout.get('violated_date')
                else:
                    fvg['status'] = 'active'
                
                all_fvgs.append(fvg)
            
            if not signal_found_for_this_setup:
                setup['status'] = 'active'

        if not all_signals and not any(f['status'] == 'active' for f in all_fvgs):
            logger.info(f"{symbol}: アクティブなFVG/シグナルなし")
            return None

        def stringify_dates(d):
            for k, v in d.items():
                if isinstance(v, pd.Timestamp):
                    d[k] = v.strftime('%Y-%m-%d')
            return d

        symbol_data = {
            "symbol": symbol,
            "last_updated": datetime.now().isoformat(),
            "market_regime": self.analyzer.market_regime,
            "setups": [stringify_dates(s.copy()) for s in setups],
            "fvgs": [stringify_dates(f.copy()) for f in all_fvgs],
            "signals": [stringify_dates(s.copy()) for s in all_signals]
        }
        
        logger.info(
            f"{symbol}: 完了 - セットアップ:{len(setups)}, "
            f"FVG:{len(all_fvgs)}, シグナル:{len(all_signals)}"
        )
        
        self._save_symbol_data_with_chart(symbol, symbol_data, df_daily, df_weekly)
        return self._create_summary_from_data(symbol, all_signals, all_fvgs)

    def _detect_fvg_in_range(self, df_daily: pd.DataFrame, setup: Dict, start_idx: int, end_idx: int) -> List[Dict]:
        """指定範囲内でFVG検出"""
        fvgs = []
        vol_rolling_mean = df_daily['volume'].rolling(20).mean()
        
        for i in range(start_idx, end_idx):
            if i < 2:
                continue
            
            candle_1, candle_3 = df_daily.iloc[i-2], df_daily.iloc[i]
            if candle_3['low'] <= candle_1['high']:
                continue
            
            gap_percentage = (candle_3['low'] - candle_1['high']) / candle_1['high']
            if gap_percentage < FVG_MIN_GAP_PERCENTAGE:
                continue
            
            fvg_score = 1 if gap_percentage > 0.001 else 0
            if fvg_score >= MIN_FVG_SCORE:
                fvg = {
                    'id': str(uuid.uuid4()),
                    'setup_id': setup['id'],
                    'formation_date': df_daily.index[i],
                    'gap_percentage': gap_percentage,
                    'score': fvg_score,
                    'quality': 'MEDIUM',
                    'lower_bound': candle_1['high'],
                    'upper_bound': candle_3['low'],
                    'status': 'active'
                }
                fvgs.append(fvg)
        
        return fvgs

    def _check_breakout_in_range(self, df_daily: pd.DataFrame, setup: Dict, fvg: Dict, start_idx: int, end_idx: int) -> Optional[Dict]:
        """指定範囲内でブレイクアウトチェック"""
        try:
            setup_idx = df_daily.index.get_loc(setup['date'])
            fvg_idx = df_daily.index.get_loc(fvg['formation_date'])
        except KeyError:
            return None
        
        lookback_window = min(20, fvg_idx - setup_idx)
        resistance_data = df_daily.iloc[max(0, fvg_idx - lookback_window) : fvg_idx]
        
        if resistance_data.empty:
            return None
        
        main_resistance = resistance_data['high'].max()
        
        for i in range(start_idx, end_idx):
            current = df_daily.iloc[i]
            if current['close'] > main_resistance * 1.003:
                return {
                    'status': 'breakout',
                    'breakout_date': df_daily.index[i],
                    'breakout_price': current['close'],
                    'resistance_price': main_resistance,
                    'breakout_score': 6,
                    'confidence': 'MEDIUM'
                }
        
        return None

    def _save_symbol_data_with_chart(self, symbol: str, symbol_data: dict, df_daily: pd.DataFrame, df_weekly: pd.DataFrame):
        """日付変換とチャートデータ付きで保存"""
        def stringify_dates(d):
            for k, v in d.items():
                if isinstance(v, pd.Timestamp):
                    d[k] = v.strftime('%Y-%m-%d')
            return d
        
        symbol_data['setups'] = [stringify_dates(s.copy()) for s in symbol_data['setups']]
        symbol_data['fvgs'] = [stringify_dates(f.copy()) for f in symbol_data['fvgs']]
        symbol_data['signals'] = [stringify_dates(s.copy()) for s in symbol_data['signals']]
        
        symbol_data['chart_data'] = self._generate_lightweight_chart_data(symbol_data, df_daily, df_weekly)
        self.data_manager.save_symbol_data(symbol, symbol_data)

    def _create_summary_from_existing(self, existing_data: dict) -> List[Dict]:
        """既存データからサマリー作成"""
        symbol = existing_data['symbol']
        signals = existing_data.get('signals', [])
        fvgs = existing_data.get('fvgs', [])
        return self._create_summary_from_data(symbol, signals, fvgs)

    def _create_summary_from_data(self, symbol: str, signals: list, fvgs: list) -> List[Dict]:
        """シグナルとFVGからサマリー作成"""
        summary_results = []
        
        for signal in signals:
            summary_results.append({
                "symbol": symbol,
                "signal_type": "signal",
                "score": signal.get('score', 50),
                "signal_date": signal.get('breakout_date')
            })
        
        for fvg in fvgs:
            if fvg.get('status') == 'active' and fvg.get('quality') in ['HIGH', 'MEDIUM']:
                summary_results.append({
                    "symbol": symbol,
                    "signal_type": "candidate",
                    "score": self._calculate_signal_score(fvg),
                    "fvg_date": fvg.get('formation_date')
                })
        
        return summary_results

    def _calculate_signal_score(self, signal_data: Dict) -> int:
        """総合スコア計算（0-100）"""
        setup_score = signal_data.get('setup_confidence', 0.5) * 35
        fvg_score = (signal_data.get('score', 0) / 10) * 40
        breakout_score = (signal_data.get('breakout_score', 0) / 8) * 30 if 'breakout_score' in signal_data else 0
        return int(min(setup_score + fvg_score + breakout_score, 100))

    def _generate_lightweight_chart_data(self, symbol_data: dict, df_daily: pd.DataFrame, df_weekly: pd.DataFrame) -> dict:
        """チャートデータ生成"""
        df_plot = df_daily.copy()
        df_plot['weekly_sma200_val'] = df_weekly['sma200'].reindex(df_plot.index, method='ffill')

        def format_series(df, col):
            s = df[[col]].dropna()
            return [{"time": i.strftime('%Y-%m-%d'), "value": r[col]} for i, r in s.iterrows()]

        def clean_np_types(d):
            for k, v in d.items():
                if isinstance(v, (np.int64, np.int32)):
                    d[k] = int(v)
                if isinstance(v, (np.float64, np.float32)):
                    d[k] = float(v)
            return d

        candles = [{
            "time": i.strftime('%Y-%m-%d'),
            "open": r.open,
            "high": r.high,
            "low": r.low,
            "close": r.close
        } for i, r in df_plot.iterrows()]

        volume_data = []
        for i, r in df_plot.iterrows():
            color = '#26a69a' if r['close'] >= r['open'] else '#ef5350'
            volume_data.append({
                "time": i.strftime('%Y-%m-%d'),
                "value": r['volume'],
                "color": color
            })

        markers = []

        for fvg in symbol_data.get('fvgs', []):
            try:
                formation_date = pd.to_datetime(fvg['formation_date'])
                if formation_date in df_plot.index:
                    formation_idx = df_plot.index.get_loc(formation_date)
                    if formation_idx >= 1:
                        middle_candle_date = df_plot.index[formation_idx - 1]
                        color_map = {
                            'active': '#FFD700',
                            'consumed': '#9370DB',
                            'violated': '#808080'
                        }
                        markers.append({
                            "time": middle_candle_date.strftime('%Y-%m-%d'),
                            "position": "inBar",
                            "color": color_map.get(fvg.get('status'), '#FFD700'),
                            "shape": "circle",
                            "text": "🐮"
                        })
            except Exception as e:
                logger.warning(f"FVGマーカー生成エラー: {symbol_data.get('symbol', 'N/A')} - {e}")

        for s in symbol_data.get('signals', []):
            markers.append({
                "time": s['breakout_date'],
                "position": "belowBar",
                "color": "#FF00FF",
                "shape": "arrowUp",
                "text": "Break"
            })

        return {
            'candles': candles,
            'sma200': format_series(df_plot, 'sma200'),
            'ema200': format_series(df_plot, 'ema200'),
            'weekly_sma200': format_series(df_plot, 'weekly_sma200_val'),
            'volume': [clean_np_types(v) for v in volume_data],
            'markers': [clean_np_types(m) for m in markers]
        }

    def _create_daily_summary(self, results: List[Dict], total_scanned: int, start_time: datetime) -> Dict:
        """日次サマリー作成（重複排除機能付き）"""
        end_time = datetime.now()

        def _merge_and_sort(items: List[Dict], date_key: str) -> List[Dict]:
            merged = {}
            for item in items:
                if date_key not in item or 'symbol' not in item:
                    continue
                key = (item['symbol'], item[date_key])
                if key not in merged or item['score'] > merged[key]['score']:
                    merged[key] = item
            return sorted(list(merged.values()), key=lambda x: x['score'], reverse=True)

        all_signals = [r for r in results if r.get('signal_type') == 'signal']
        all_candidates = [r for r in results if r.get('signal_type') == 'candidate']

        unique_signals = _merge_and_sort(all_signals, 'signal_date')
        unique_candidates = _merge_and_sort(all_candidates, 'fvg_date')
        
        return {
            "scan_date": end_time.strftime('%Y-%m-%d'),
            "scan_time": end_time.strftime('%H:%M:%S'),
            "scan_duration_seconds": (end_time - start_time).total_seconds(),
            "total_scanned": total_scanned,
            "summary": {
                "signals_count": len(unique_signals),
                "candidates_count": len(unique_candidates),
                "signals": unique_signals,
                "candidates": unique_candidates
            },
            "performance": {
                "avg_time_per_symbol_ms": ((end_time - start_time).total_seconds() / total_scanned * 1000) if total_scanned > 0 else 0
            }
        }


async def run_hwb_scan(progress_callback=None):
    """スキャン実行エントリーポイント"""
    scanner = HWBScanner()
    summary = await scanner.scan_all_symbols(progress_callback)
    logger.info(f"完了 - シグナル: {summary['summary']['signals_count']}, 候補: {summary['summary']['candidates_count']}")
    return summary


async def analyze_single_ticker(symbol: str) -> Optional[Dict]:
    """単一銘柄分析"""
    scanner = HWBScanner()
    scanner._analyze_and_save_symbol(symbol)
    return scanner.data_manager.load_symbol_data(symbol)