import json
import sqlite3
import os
from pathlib import Path
import pandas as pd
from datetime import datetime, timedelta
import logging
import yfinance as yf
from curl_cffi import requests
from typing import Tuple, Dict, Optional, Set
from io import StringIO
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

class HWBDataManager:
    """
    Manages all data operations for the HWB scanner, including:
    - SQLite database for historical price data (hwb_cache.db)
    - Individual symbol JSON files for analysis results
    - Daily summary JSON files
    """
    def __init__(self, base_data_path='data/hwb'):
        self.base_dir = Path(base_data_path)
        self.db_path = self.base_dir / 'hwb_cache.db'
        self.symbols_dir = self.base_dir / 'symbols'
        self.daily_dir = self.base_dir / 'daily'
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.symbols_dir.mkdir(exist_ok=True)
        self.daily_dir.mkdir(exist_ok=True)
        self.session = requests.Session(impersonate="safari15_5")
        logger.info(f"HWBDataManager initialized. DB path: {self.db_path}")
        self._init_database()

    def _init_database(self):
        """
        Initializes the database and creates tables if they don't exist.
        This is called automatically on instantiation.
        """
        logger.info("Initializing database schema...")
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                # Daily prices table
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS daily_prices (
                    symbol TEXT NOT NULL,
                    date DATE NOT NULL,
                    open REAL NOT NULL, high REAL NOT NULL, low REAL NOT NULL, close REAL NOT NULL, volume INTEGER NOT NULL,
                    sma200 REAL, ema200 REAL,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (symbol, date)
                );
                """)
                # Weekly prices table
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS weekly_prices (
                    symbol TEXT NOT NULL,
                    week_start_date DATE NOT NULL,
                    open REAL NOT NULL, high REAL NOT NULL, low REAL NOT NULL, close REAL NOT NULL, volume INTEGER NOT NULL,
                    sma200 REAL,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (symbol, week_start_date)
                );
                """)
                # Data metadata table
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS data_metadata (
                    symbol TEXT PRIMARY KEY,
                    first_date DATE, last_date DATE, last_updated TIMESTAMP,
                    daily_count INTEGER, weekly_count INTEGER
                );
                """)
                # Russell 3000 symbols table
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS russell3000_symbols (
                    symbol TEXT PRIMARY KEY,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """)
                # Indexes
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_daily_symbol_date ON daily_prices(symbol, date DESC);")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_weekly_symbol_date ON weekly_prices(symbol, week_start_date DESC);")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_metadata_last_date ON data_metadata(last_date);")
                conn.commit()
                logger.info("Database schema initialized successfully.")
        except sqlite3.Error as e:
            logger.error(f"Database initialization failed: {e}", exc_info=True)
            raise

    def get_stock_data_with_cache(self, symbol: str, lookback_years: int = 10) -> Optional[Tuple[pd.DataFrame, pd.DataFrame]]:
        """
        Retrieves historical stock data for a symbol, utilizing a local SQLite cache
        to minimize API calls. It fetches `lookback_years` of data on the first run and
        performs incremental updates on subsequent runs.
        Returns a tuple of (daily_df, weekly_df), or None if data cannot be retrieved.
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                metadata = self._get_metadata(symbol, conn)
                today = datetime.now().date()
                needs_update = False

                if not metadata:
                    logger.info(f"'{symbol}': First time fetch. Getting full history.")
                    needs_update = True
                    start_date = today - timedelta(days=365 * lookback_years)
                elif metadata['last_date'] < today:
                    logger.info(f"'{symbol}': Cache is outdated (last: {metadata['last_date']}). Fetching delta.")
                    needs_update = True
                    start_date = metadata['last_date'] + timedelta(days=1)
                else:
                    logger.info(f"'{symbol}': Cache is up-to-date.")

                if needs_update:
                    df_new_daily, df_new_weekly = self._fetch_from_yfinance(symbol, start_date, today)

                    if (df_new_daily is not None and not df_new_daily.empty) or \
                       (df_new_weekly is not None and not df_new_weekly.empty):

                        df_old_daily = self._load_daily_from_db(symbol, conn, lookback_days=365*lookback_years)
                        df_old_weekly = self._load_weekly_from_db(symbol, conn, lookback_weeks=52*lookback_years)

                        df_full_daily = self._calculate_full_daily_ma(df_old_daily, df_new_daily)
                        df_full_weekly = self._calculate_full_weekly_ma(df_old_weekly, df_new_weekly)

                        self._save_to_db(symbol, conn, df_full_daily, df_full_weekly)
                        self._update_metadata(symbol, conn)
                    else:
                        logger.info(f"'{symbol}': No new data returned from yfinance.")

                final_df_daily = self._load_daily_from_db(symbol, conn, lookback_days=365 * lookback_years)
                final_df_weekly = self._load_weekly_from_db(symbol, conn, lookback_weeks=52 * lookback_years)

                if final_df_daily.empty:
                    logger.warning(f"'{symbol}': No data available after fetch/load process.")
                    return None

                return final_df_daily, final_df_weekly
        except Exception as e:
            logger.error(f"Error in get_stock_data_with_cache for '{symbol}': {e}", exc_info=True)
            return None

    def _get_metadata(self, symbol: str, conn) -> Optional[Dict]:
        query = "SELECT symbol, first_date, last_date, last_updated, daily_count, weekly_count FROM data_metadata WHERE symbol = ?"
        try:
            cursor = conn.cursor()
            row = cursor.execute(query, (symbol,)).fetchone()
            if row:
                row_dict = dict(zip([d[0] for d in cursor.description], row))
                row_dict['first_date'] = datetime.strptime(row_dict['first_date'], '%Y-%m-%d').date() if row_dict['first_date'] else None
                row_dict['last_date'] = datetime.strptime(row_dict['last_date'], '%Y-%m-%d').date() if row_dict['last_date'] else None
                return row_dict
            return None
        except Exception as e:
            logger.error(f"Failed to get metadata for {symbol}: {e}", exc_info=True)
            return None

    def _fetch_from_yfinance(self, symbol: str, start_date, end_date) -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame]]:
        logger.info(f"Fetching yfinance data for '{symbol}' from {start_date} to {end_date}")
        try:
            ticker = yf.Ticker(symbol, session=self.session)

            df_daily = ticker.history(start=start_date, end=end_date, interval="1d", auto_adjust=False)
            df_daily = df_daily[~df_daily.index.duplicated(keep='first')]

            week_start = start_date - timedelta(days=start_date.weekday())
            df_weekly = ticker.history(start=week_start, end=end_date, interval="1wk", auto_adjust=False)
            df_weekly = df_weekly[~df_weekly.index.duplicated(keep='first')]

            for df in [df_daily, df_weekly]:
                if df is not None and not df.empty:
                    # Make timezone naive to ensure consistency with data from DB
                    if df.index.tz is not None:
                        df.index = df.index.tz_localize(None)
                    df.rename(columns=str.lower, inplace=True)
                    df.dropna(subset=['open', 'high', 'low', 'close'], how='all', inplace=True)

            logger.info(f"'{symbol}': Fetched {len(df_daily)} new daily and {len(df_weekly)} new weekly records.")
            return df_daily, df_weekly

        except Exception as e:
            logger.error(f"yfinance fetch error for '{symbol}': {e}", exc_info=True)
            return None, None

    def _calculate_full_daily_ma(self, df_old: pd.DataFrame, df_new: Optional[pd.DataFrame]) -> pd.DataFrame:
        if df_new is None or df_new.empty: return df_old
        df_full = pd.concat([df_old, df_new])
        df_full = df_full[~df_full.index.duplicated(keep='last')].sort_index()
        df_full['sma200'] = df_full['close'].rolling(window=200, min_periods=50).mean()
        df_full['ema200'] = df_full['close'].ewm(span=200, min_periods=50, adjust=False).mean()
        return df_full

    def _calculate_full_weekly_ma(self, df_old: pd.DataFrame, df_new: Optional[pd.DataFrame]) -> pd.DataFrame:
        if df_new is None or df_new.empty: return df_old
        df_full = pd.concat([df_old, df_new])
        df_full = df_full[~df_full.index.duplicated(keep='last')].sort_index()
        df_full['sma200'] = df_full['close'].rolling(window=200, min_periods=50).mean()
        return df_full

    def _save_to_db(self, symbol: str, conn, df_daily: pd.DataFrame, df_weekly: pd.DataFrame):
        """
        Atomically replaces all data for a given symbol in the database.
        This prevents UNIQUE constraint errors from overlapping data fetches.
        """
        cursor = conn.cursor()
        try:
            # Start a transaction
            cursor.execute("BEGIN;")

            # Delete old entries for this symbol first
            cursor.execute("DELETE FROM daily_prices WHERE symbol = ?", (symbol,))
            cursor.execute("DELETE FROM weekly_prices WHERE symbol = ?", (symbol,))

            # Save the new, complete dataframes
            if df_daily is not None and not df_daily.empty:
                # Final safeguard against invalid data before saving
                df_daily = df_daily.dropna(subset=['open', 'high', 'low', 'close'], how='any')
                df_daily = df_daily[df_daily.index.notna()]

                if not df_daily.empty:
                    df_to_save = df_daily[['open', 'high', 'low', 'close', 'volume', 'sma200', 'ema200']].copy()
                    df_to_save['symbol'] = symbol
                    df_to_save.index.name = 'date'
                    df_to_save.reset_index(inplace=True)
                    df_to_save.to_sql('daily_prices', conn, if_exists='append', index=False)

            if df_weekly is not None and not df_weekly.empty:
                # Final safeguard against invalid data before saving
                df_weekly = df_weekly.dropna(subset=['open', 'high', 'low', 'close'], how='any')
                df_weekly = df_weekly[df_weekly.index.notna()]

                if not df_weekly.empty:
                    df_to_save = df_weekly[['open', 'high', 'low', 'close', 'volume', 'sma200']].copy()
                    df_to_save['symbol'] = symbol
                    df_to_save.index.name = 'week_start_date'
                    df_to_save.reset_index(inplace=True)
                    df_to_save.to_sql('weekly_prices', conn, if_exists='append', index=False)

            # Commit the transaction
            conn.commit()
            logger.info(f"Successfully replaced data for '{symbol}' in DB.")

        except Exception as e:
            logger.error(f"Failed to save data for '{symbol}', rolling back transaction. Error: {e}", exc_info=True)
            conn.rollback()
            raise

    def _update_metadata(self, symbol: str, conn):
        logger.info(f"Updating metadata for '{symbol}'...")
        try:
            cursor = conn.cursor()
            daily_stats_q = "SELECT COUNT(*), MIN(date), MAX(date) FROM daily_prices WHERE symbol = ?"
            weekly_stats_q = "SELECT COUNT(*), MIN(week_start_date), MAX(week_start_date) FROM weekly_prices WHERE symbol = ?"

            daily_count, first_daily, last_daily = cursor.execute(daily_stats_q, (symbol,)).fetchone()
            weekly_count, _, _ = cursor.execute(weekly_stats_q, (symbol,)).fetchone()

            metadata_values = {
                'symbol': symbol, 'first_date': first_daily, 'last_date': last_daily,
                'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'daily_count': daily_count, 'weekly_count': weekly_count,
            }

            cols = ', '.join(metadata_values.keys())
            placeholders = ', '.join('?' for _ in metadata_values)
            sql = f"INSERT OR REPLACE INTO data_metadata ({cols}) VALUES ({placeholders})"
            cursor.execute(sql, tuple(metadata_values.values()))
            conn.commit()
            logger.info(f"Metadata for '{symbol}' updated successfully.")
        except Exception as e:
            logger.error(f"Failed to update metadata for '{symbol}': {e}", exc_info=True)
            raise

    def _load_daily_from_db(self, symbol: str, conn, lookback_days: int) -> pd.DataFrame:
        query = "SELECT date, open, high, low, close, volume, sma200, ema200 FROM daily_prices WHERE symbol = ? ORDER BY date DESC LIMIT ?"
        try:
            df = pd.read_sql_query(query, conn, params=(symbol, lookback_days), index_col='date', parse_dates=['date'])
            return df.sort_index() if not df.empty else pd.DataFrame()
        except Exception as e:
            logger.error(f"Failed to load daily data for '{symbol}': {e}", exc_info=True)
            return pd.DataFrame()

    def _load_weekly_from_db(self, symbol: str, conn, lookback_weeks: int) -> pd.DataFrame:
        query = "SELECT week_start_date, open, high, low, close, volume, sma200 FROM weekly_prices WHERE symbol = ? ORDER BY week_start_date DESC LIMIT ?"
        try:
            df = pd.read_sql_query(query, conn, params=(symbol, lookback_weeks), index_col='week_start_date', parse_dates=['week_start_date'])
            return df.sort_index() if not df.empty else pd.DataFrame()
        except Exception as e:
            logger.error(f"Failed to load weekly data for '{symbol}': {e}", exc_info=True)
            return pd.DataFrame()

    def get_russell3000_symbols(self, cache_days: int = 7) -> set:
        """
        Retrieves the list of Russell 3000 symbols, using a cache to avoid
        frequent refetching.
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # Check for cached symbols
                query = f"SELECT symbol FROM russell3000_symbols WHERE last_updated > datetime('now', '-{cache_days} days')"
                cached_symbols = {row[0] for row in cursor.execute(query).fetchall()}

                if cached_symbols:
                    logger.info(f"Loaded {len(cached_symbols)} symbols from cache.")
                    return cached_symbols

                # If cache is old or empty, fetch new symbols
                logger.info("Symbol cache is outdated or empty. Fetching new list.")
                symbols = self._fetch_russell3000_symbols()

                if symbols:
                    cursor.execute('DELETE FROM russell3000_symbols')
                    cursor.executemany(
                        'INSERT INTO russell3000_symbols (symbol) VALUES (?)',
                        [(s,) for s in symbols]
                    )
                    conn.commit()
                    logger.info(f"Cached {len(symbols)} new symbols.")

                return symbols
        except Exception as e:
            logger.error(f"Failed to get Russell 3000 symbols: {e}", exc_info=True)
            return set()

    def _fetch_russell3000_symbols(self) -> set:
        """iShares ETFからRussell 3000のシンボルリストを取得"""
        symbols: Set[str] = set()
        try:
            # iShares Russell 3000 ETF (IWV)のホールディングスCSVを取得
            today = datetime.now()
            # The composition is updated annually in June, so fetching in July is ideal.
            # We assume the fetched CSV is valid for one year.
            # To ensure we get the data, we might need to check previous dates if today's fails.
            # For simplicity, we'll try the last few days.
            for i in range(365): # Try up to a year ago
                date_to_try = today - timedelta(days=i)
                date_str = date_to_try.strftime('%Y%m%d')
                url = f"https://www.ishares.com/us/products/239714/ishares-russell-3000-etf/1467271812596.ajax?fileType=csv&fileName=IWV_holdings&dataType=fund&asOfDate={date_str}"

                try:
                    logger.info(f"Attempting to fetch Russell 3000 holdings for {date_str}...")
                    response = self.session.get(url, timeout=30)
                    response.raise_for_status()

                    # Check if the response is valid CSV data and not an error page HTML
                    if response.text.strip().startswith('<'):
                        logger.warning(f"Received HTML instead of CSV for date {date_str}. Trying previous day.")
                        continue

                    lines = response.text.split('\n')

                    # Find the start of the data (the line with "Ticker")
                    data_start = -1
                    for i, line in enumerate(lines):
                        if 'Ticker' in line:
                            data_start = i
                            break

                    if data_start == -1:
                        logger.warning(f"Could not find 'Ticker' header in CSV for date {date_str}. Trying previous day.")
                        continue

                    csv_data = '\n'.join(lines[data_start:])
                    df = pd.read_csv(StringIO(csv_data))

                    if 'Ticker' in df.columns:
                        symbols = set(df['Ticker'].dropna().str.strip())
                        # Process symbols to replace dots with hyphens, common in stock tickers (e.g., BRK.B -> BRK-B)
                        symbols = {s.replace('.', '-') for s in symbols if isinstance(s, str) and s != '-'}
                        logger.info(f"Fetched {len(symbols)} Russell 3000 symbols from iShares ETF for date {date_str}")
                        return symbols # Success, exit the loop

                except requests.errors.RequestsError as re:
                    # Specifically handle HTTP errors (like 404 Not Found) quietly
                    logger.info(f"No data available for {date_str} (HTTP Status: {re.response.status_code if re.response else 'N/A'}). Trying previous day.")
                    continue
                except Exception as e:
                     logger.error(f"An unexpected error occurred while fetching for {date_str}: {e}")
                     # For unexpected errors, stop trying
                     break

            if not symbols:
                 logger.error("Failed to fetch Russell 3000 symbols after trying multiple dates.")

            return symbols

        except Exception as e:
            logger.error(f"Failed to fetch Russell 3000 from iShares: {e}", exc_info=True)
            return set()

    def save_symbol_data(self, symbol: str, data: dict):
        """Saves the analysis result for a single symbol to a JSON file."""
        try:
            filepath = self.symbols_dir / f"{symbol}.json"
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.info(f"Saved analysis for '{symbol}' to {filepath}")
        except Exception as e:
            logger.error(f"Failed to save symbol data for '{symbol}': {e}", exc_info=True)

    def load_symbol_data(self, symbol: str) -> Optional[dict]:
        """Loads the analysis result for a single symbol from its JSON file."""
        filepath = self.symbols_dir / f"{symbol}.json"
        if not filepath.exists() or os.path.getsize(filepath) == 0:
            return None
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError:
            logger.warning(f"Could not decode JSON for '{symbol}' from {filepath}. File might be corrupt or empty.")
            return None
        except Exception as e:
            logger.error(f"Failed to load symbol data for '{symbol}': {e}", exc_info=True)
            return None

    def save_daily_summary(self, summary_data: dict):
        """Saves the daily scan summary and updates the 'latest.json' pointer."""
        try:
            scan_date = summary_data.get("scan_date", datetime.now().strftime('%Y-%m-%d'))
            # Save the date-specific summary
            date_filepath = self.daily_dir / f"{scan_date}.json"
            with open(date_filepath, 'w', encoding='utf-8') as f:
                json.dump(summary_data, f, indent=2, ensure_ascii=False)
            logger.info(f"Saved daily summary to {date_filepath}")

            # Update the 'latest.json' file
            latest_filepath = self.daily_dir / "latest.json"
            # Use a simple copy for compatibility across systems instead of symlink
            with open(latest_filepath, 'w', encoding='utf-8') as f:
                json.dump(summary_data, f, indent=2, ensure_ascii=False)
            logger.info(f"Updated latest summary at {latest_filepath}")

        except Exception as e:
            logger.error(f"Failed to save daily summary: {e}", exc_info=True)