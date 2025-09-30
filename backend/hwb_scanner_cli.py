#!/usr/bin/env python
"""HWBスキャナーCLI実行用スクリプト"""

import asyncio
import sys
import logging
from backend.hwb_scanner import run_hwb_scan
from backend.notifier import send_push_notification_to_all

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

async def main():
    """メイン実行関数"""
    print("HWBスキャン開始...")

    try:
        result = await run_hwb_scan()
        print(f"スキャン完了: {len(result.get('signals', []))}件のシグナル検出")

        # 完了通知を送信
        await send_push_notification_to_all(
            title="HWB 日次スキャン完了",
            body=f"{len(result.get('signals', []))}件のシグナル、{len(result.get('candidates', []))}件の候補を検出しました。"
        )

        return 0

    except Exception as e:
        print(f"エラー: {e}")

        # エラー通知を送信
        await send_push_notification_to_all(
            title="HWB 日次スキャン失敗",
            body="HWBスキャンの実行中にエラーが発生しました。"
        )

        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)