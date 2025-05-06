FROM python:3.11-slim

WORKDIR /app

# Cài các gói cần thiết
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy toàn bộ mã
COPY . .

# Cho phép thực thi script
RUN chmod +x entrypoint.sh

# Thiết lập cron
RUN apt-get update && apt-get install -y cron

# Copy file cron và cài vào hệ thống
RUN crontab crontab.txt

# Start cron và chạy background

CMD ["bash", "-c", "python crawler.py >> /app/crawl_metrics.log 2>&1"]

