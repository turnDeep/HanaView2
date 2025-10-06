#!/bin/bash

# Set the application directory
APP_DIR="/app/backend"
cd $APP_DIR

echo "Starting Stage Analysis Cron Job at $(date)"

# Source the environment variables to get API keys, etc.
if [ -f "cron-env.sh" ]; then
    . ./cron-env.sh
else
    echo "cron-env.sh not found, running without it."
fi

# Run the stage analysis pipeline
# We'll use the stage.py script as a CLI entry point
echo "Running stage analysis..."
python -m stage --max-tickers 500 --workers 8 > /var/log/cron_stage_analysis.log 2>&1
ANALYSIS_EXIT_CODE=$?

if [ $ANALYSIS_EXIT_CODE -eq 0 ]; then
    echo "Stage analysis completed successfully."
    # Notify the main application to send push notifications
    echo "Sending completion notification..."
    curl -X POST http://127.0.0.1:8000/api/stage/notify-completion
else
    echo "Stage analysis failed with exit code $ANALYSIS_EXIT_CODE."
fi

echo "Stage Analysis Cron Job finished at $(date)"
echo "----------------------------------------------------"