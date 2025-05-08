#!/bin/bash

# Start cron
cron

# Keep container running
tail -f /dev/null


echo "Starting crawler..."
python crawler.py >> /app/crawl_metrics.log 2>&1