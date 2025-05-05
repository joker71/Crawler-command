import requests
import mysql.connector
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

# Đọc token từ file
def read_token_from_file(file_path='../token.txt'):
    with open(file_path, 'r') as f:
        return f.read().strip()


# Kết nối cơ sở dữ liệu MySQL
def create_db_connection():
    # Kết nối đến MySQL
    conn = mysql.connector.connect(
        host='localhost',  # Thay thế bằng host của bạn nếu cần
        user='root',  # Tên người dùng MySQL
        password='abcde12345-',  # Mật khẩu người dùng MySQL
        database='github_data'  # Cơ sở dữ liệu bạn đã tạo
    )
    return conn


# Lưu thông tin repositories vào cơ sở dữ liệu MySQL
def save_repository(conn, repo):
    cursor = conn.cursor()
    cursor.execute('''INSERT INTO repositories (name, full_name, url)
                      VALUES (%s, %s, %s)''',
                   (repo['name'], repo['full_name'], repo['html_url']))
    conn.commit()
    return cursor.lastrowid  # Return the repo id


# Hàm chuyển đổi thời gian từ ISO 8601 sang MySQL DATETIME format
def convert_to_mysql_datetime(iso_datetime_str):
    # Kiểm tra nếu chuỗi có định dạng 'Z' ở cuối (chỉ ra UTC)
    if iso_datetime_str.endswith('Z'):
        iso_datetime_str = iso_datetime_str[:-1]  # Loại bỏ 'Z'
        iso_datetime_str += '+00:00'  # Thêm múi giờ UTC
    # Chuyển đổi chuỗi ISO 8601 thành đối tượng datetime
    return datetime.strptime(iso_datetime_str, '%Y-%m-%dT%H:%M:%S%z').strftime('%Y-%m-%d %H:%M:%S')

# Lưu releases vào cơ sở dữ liệu MySQL
def save_releases(conn, repo_id, releases):
    cursor = conn.cursor()
    for release in releases:
        created_at_mysql = convert_to_mysql_datetime(release['created_at'])
        cursor.execute('''INSERT INTO releases (repo_id, name, url, tag_name, created_at) 
                          VALUES (%s, %s, %s, %s, %s)''',
                       (repo_id, release['name'], release['html_url'], release['tag_name'], created_at_mysql))
    conn.commit()

# Lưu commits vào cơ sở dữ liệu MySQL
def save_commits(conn, repo_id, commits):
    cursor = conn.cursor()
    for commit in commits:
        commit_date_mysql = convert_to_mysql_datetime(commit['commit']['author']['date'])
        cursor.execute('''INSERT INTO commits (repo_id, sha, message, date) 
                          VALUES (%s, %s, %s, %s)''',
                       (repo_id, commit['sha'], commit['commit']['message'], commit_date_mysql))
    conn.commit()

# Lấy releases của một repository
def get_releases(repo_full_name, headers):
    url = f'https://api.github.com/repos/{repo_full_name}/releases'
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()
    return []


# Lấy commits của một repository
def get_commits(repo_full_name, headers):
    url = f'https://api.github.com/repos/{repo_full_name}/commits'
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()
    return []


# Crawler thông tin repositories, releases và commits
# No multiprocess
def fetch_repositories_and_data(token, per_page=100, total_repos=5000):
    headers = {'Authorization': f'token {token}'}
    url = 'https://api.github.com/repositories'

    all_repos = []
    page = 1
    conn = create_db_connection()

    while len(all_repos) < total_repos:
        response = requests.get(url, params={'per_page': per_page, 'page': page}, headers=headers)
        if response.status_code == 200:
            repos = response.json()
            all_repos.extend(repos)
            print(f"Fetched {len(repos)} repositories, total: {len(all_repos)}")
            page += 1

            for repo in repos:
                repo_id = save_repository(conn, repo)  # Lưu repository vào DB
                releases = get_releases(repo['full_name'], headers)  # Lấy releases
                save_releases(conn, repo_id, releases)  # Lưu releases vào DB

                commits = get_commits(repo['full_name'], headers)  # Lấy commits
                save_commits(conn, repo_id, commits)  # Lưu commits vào DB

            # Tôn trọng rate limit, đợi nếu cần
            remaining = int(response.headers.get('X-RateLimit-Remaining', 60))
            if remaining <= 0:
                reset_time = int(response.headers.get('X-RateLimit-Reset', time.time()))
                wait_time = reset_time - time.time() + 10  # Đợi 10 giây sau khi rate limit reset
                print(f"Rate limit reached. Sleeping for {wait_time} seconds...")
                time.sleep(wait_time)
        else:
            print(f"Failed to fetch repositories: {response.status_code}")
            break

        time.sleep(2)  # Sleep giữa các request

    conn.close()
    return all_repos


def process_repository(conn, repo, headers):
    repo_id = save_repository(conn, repo)  # Lưu repository vào DB
    releases = get_releases(repo['full_name'], headers)  # Lấy releases
    save_releases(conn, repo_id, releases)  # Lưu releases vào DB

    commits = get_commits(repo['full_name'], headers)  # Lấy commits
    save_commits(conn, repo_id, commits)  # Lưu commits vào DB
# Crawler tất cả repositories, sử dụng ThreadPoolExecutor để chạy song song
def fetch_repositories_and_data_multiprocess(token, per_page=100, total_repos=5000):
    headers = {'Authorization': f'token {token}'}
    url = 'https://api.github.com/repositories'

    all_repos = []
    page = 1
    conn = create_db_connection()

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = []
        while len(all_repos) < total_repos:
            response = requests.get(url, params={'per_page': per_page, 'page': page}, headers=headers)
            if response.status_code == 200:
                repos = response.json()
                all_repos.extend(repos)
                print(f"Fetched {len(repos)} repositories, total: {len(all_repos)}")
                page += 1

                for repo in repos:
                    # Sử dụng ThreadPoolExecutor để chạy song song
                    futures.append(executor.submit(process_repository, conn, repo, headers))

                # Tôn trọng rate limit, đợi nếu cần
                remaining = int(response.headers.get('X-RateLimit-Remaining', 60))
                if remaining <= 0:
                    reset_time = int(response.headers.get('X-RateLimit-Reset', time.time()))
                    wait_time = reset_time - time.time() + 10  # Đợi 10 giây sau khi rate limit reset
                    print(f"Rate limit reached. Sleeping for {wait_time} seconds...")
                    time.sleep(wait_time)
            else:
                print(f"Failed to fetch repositories: {response.status_code}")
                break

            time.sleep(2)  # Sleep giữa các request

        # Chờ tất cả các tác vụ song song hoàn thành
        for future in as_completed(futures):
            future.result()  # Chờ và kiểm tra lỗi nếu có

    conn.close()
    return all_repos


if __name__ == '__main__':
    # Đọc token từ file
    token = read_token_from_file('../token.txt')

    # Fetch repositories, releases, và commits
    # fetch_repositories_and_data(token, total_repos=5000)
    fetch_repositories_and_data_multiprocess(token, total_repos=5000)