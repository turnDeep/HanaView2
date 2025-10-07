#!/bin/bash

# Set the application directory
APP_DIR="/app/backend"
cd $APP_DIR

echo "Starting Stage Analysis Cron Job at $(date)"

# Source the environment variables
if [ -f "cron-env.sh" ]; then
    . ./cron-env.sh
else
    echo "cron-env.sh not found, running without it."
fi

# Run with ticker update (週1回など)
echo "Running stage analysis with ticker update..."
python -m stage --update-tickers > /var/log/cron_stage_analysis.log 2>&1
ANALYSIS_EXIT_CODE=$?

if [ $ANALYSIS_EXIT_CODE -eq 0 ]; then
    echo "Stage analysis completed successfully."
    echo "Sending completion notification..."
    curl -X POST http://127.0.0.1:8000/api/stage/notify-completion
else
    echo "Stage analysis failed with exit code $ANALYSIS_EXIT_CODE."
fi

echo "Stage Analysis Cron Job finished at $(date)"
echo "----------------------------------------------------"