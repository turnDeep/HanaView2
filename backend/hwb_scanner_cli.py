#!/usr/bin/env python
"""HWBスキャナーCLI実行用スクリプト"""

import asyncio
import sys
import logging
from .hwb_scanner import run_hwb_scan

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# backend/hwb_scanner_cli.py
async def main():
    """メイン実行関数"""
    print("HWBスキャン開始...")

    try:
        result = await run_hwb_scan()
        signals_count = result['summary']['signals_count']
        candidates_count = result['summary']['candidates_count']
        
        print(f"スキャン完了: {signals_count}件のシグナル検出")
        
        # Push通知送信を追加
        try:
            from .data_fetcher import MarketDataFetcher
            fetcher = MarketDataFetcher()
            
            # 通知データをカスタマイズ
            notification_data = {
                "title": "HWBスキャン完了",
                "body": f"シグナル: {signals_count}件 | 候補: {candidates_count}件",
                "type": "hwb-scan"
            }
            
            sent_count = fetcher.send_push_notifications(notification_data)
            print(f"Push通知送信: {sent_count}件")
        except Exception as e:
            print(f"通知送信エラー: {e}")
        
        return 0

    except Exception as e:
        print(f"エラー: {e}")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)