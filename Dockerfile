
FROM python:3.11-slim

WORKDIR /app

# Cài các gói cần thiết
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy toàn bộ mã
COPY . .

# Thiết lập cron
RUN apt-get update && apt-get install -y cron


CMD ["python", "crawler_schedule.py"]


