#!/bin/bash

# Log start time
echo "=== Job started at $(date) ===" >> "$HOME/git/zoom_downloader/cron_log.txt"

# Source conda setup
source "$HOME/.bash_profile"

# Load environment variables
cd "$HOME/git/zoom_downloader"
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

# Run the script
/opt/anaconda3/bin/python "$HOME/git/zoom_downloader/$1" >> "$HOME/git/zoom_downloader/cron_log.txt" 2>&1

# Log end time and status
echo "=== Job ended at $(date) with status $? ===" >> "$HOME/git/zoom_downloader/cron_log.txt"
