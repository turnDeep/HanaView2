#!/usr/bin/env python3
"""
Stage Analysis CLI - Wrapper for StageAnalyzerService

This script provides a command-line interface to trigger the full
stage analysis pipeline defined in the StageAnalyzerService.
"""
import argparse
import logging
import os
import sys

# Ensure the script can find other modules in the 'backend' directory
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from stage_analyzer_service import stage_analyzer_service
except ImportError:
    print("Error: Could not import StageAnalyzerService. Make sure you are running from the correct directory.")
    sys.exit(1)

# --- Logger Setup ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


def main():
    """Main function to parse arguments and run the analysis."""
    parser = argparse.ArgumentParser(description='Stage Analysis CLI for HanaView')
    parser.add_argument(
        '--max-tickers',
        type=int,
        default=None,
        help='Maximum number of tickers to process (for testing).'
    )
    parser.add_argument(
        '--workers',
        type=int,
        default=8,
        help='Number of parallel workers for the analysis.'
    )
    args = parser.parse_args()

    logger.info("=" * 70)
    logger.info("🚀 Triggering Stage Analysis Pipeline via CLI")
    logger.info(f"Max Tickers: {'All' if args.max_tickers is None else args.max_tickers}")
    logger.info(f"Max Workers: {args.workers}")
    logger.info("=" * 70)

    try:
        result = stage_analyzer_service.run_full_analysis_pipeline(
            max_workers=args.workers,
            max_tickers=args.max_tickers
        )
        logger.info("-" * 70)
        logger.info(f"✅ Pipeline finished with status: {result.get('status')}")
        logger.info(f"Found {result.get('found', 0)} promising stocks.")
        logger.info("=" * 70)

    except Exception as e:
        logger.error("An unexpected error occurred during the analysis pipeline.", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()