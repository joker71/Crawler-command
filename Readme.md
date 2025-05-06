# GitHub Release Crawler

##  Giới thiệu

Dự án này triển khai một **hệ thống crawler thu thập thông tin các bản phát hành (release)** của **5000 repository nhiều sao nhất trên GitHub**. Mục tiêu là xây dựng một công cụ **song song hoá quá trình crawl** và **lưu kết quả vào MySQL**, phục vụ cho việc phân tích hoặc xây dựng hệ thống tra cứu dữ liệu phần mềm mã nguồn mở.

###  Tính năng chính

- Thu thập thông tin **release** của các repository từ GitHub.
- Sử dụng **API GitHub** kết hợp với **đa luồng / đa tiến trình** để tăng tốc crawl.
- Quản lý **rate limit thông minh**, tự động chờ hoặc đổi token nếu bị giới hạn.
- Dữ liệu được **lưu vào MySQL** gồm thông tin repository và danh sách release.
- Chạy tự động bằng **Docker** và cron job mỗi 20 phút.

---

##  Cài đặt và chạy local

### 1. Clone dự án

```bash
git clone https://github.com/your-username/github-release-crawler.git
cd github-release-crawler
```

##  Cài đặt và chạy 
```bash
python -m venv .venv
source .venv/bin/activate  # hoặc .venv\Scripts\activate trên Windows
pip install -r requirements.txt

```

## File Token

ghp_abc123...
ghp_xyz789...

## Cấu hình kết nối MySQL

MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=yourpass
MYSQL_DB=github_releases

## Chạy bằng Docker
### 1. Build Docker image
```bash
docker build -t github-crawler .
```
### 2. Run một lần (test)
```bash

docker run --rm --env-file .env github-crawler
```
### 3. Run định kỳ mỗi 20 phút với cron + Docker
Thêm dòng sau vào crontab -e:

```bash

*/20 * * * * docker run --rm --env-file /path/to/.env github-crawler
```
### Hoặc tạo container chạy nền kèm cron:

```bash

docker run -d --name github-crawler \
  --env-file /path/to/.env \
  github-crawler
```