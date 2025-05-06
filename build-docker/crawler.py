import asyncio
import time

import aiohttp
from aiohttp import TCPConnector
from tqdm import tqdm
import mysql.connector
from datetime import datetime

# ====== Đọc GitHub Token từ file ======
def load_token():
    with open("token.txt", "r") as f:
        return f.read().strip()

GITHUB_TOKEN = load_token()
HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
    "User-Agent": "release-crawler"
}

# ====== MySQL Config ======
DB_CONFIG = {
    # 'host': 'host.docker.internal',
    'host': 'localhost',
    'user': 'root',
    'password': 'Hangnga98#',
    'database': 'github_crawler'
}

SEARCH_URL = "https://api.github.com/search/repositories"
RELEASES_URL = "https://api.github.com/repos/{repo}/releases"

def generate_search_queries():
    queries = []
    years = [("2010-01-01", "2015-01-01"),
             ("2015-01-01", "2018-01-01"),
             ("2018-01-01", "2020-01-01"),
             ("2020-01-01", "2022-01-01"),
             ("2022-01-01", "2023-12-31")]
    for start, end in years:
        for page in range(1, 11):
            query = f"{SEARCH_URL}?q=stars:>1+created:{start}..{end}&sort=stars&order=desc&page={page}&per_page=100"
            queries.append(query)
    return queries[:50]

async def fetch_repos(session, url):
    async with session.get(url, headers=HEADERS) as resp:
        if resp.status != 200:
            return []
        data = await resp.json()
        return data.get("items", [])

async def fetch_release(session, repo_full_name):
    url = RELEASES_URL.format(repo=repo_full_name)
    async with session.get(url, headers=HEADERS) as resp:
        if resp.status == 200:
            return {repo_full_name: await resp.json()}
        return {repo_full_name: []}

def save_repos_to_mysql(repos):
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()
    for repo in repos:
        full_name = repo["full_name"]
        description = repo.get("description")
        stars = repo.get("stargazers_count", 0)
        language = repo.get("language")
        created_at = parse_time(repo.get("created_at"))
        updated_at = parse_time(repo.get("updated_at"))

        cursor.execute("""
            INSERT IGNORE INTO repositories
            (full_name, description, stars, language, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (full_name, description, stars, language, created_at, updated_at))

    conn.commit()
    cursor.close()
    conn.close()

def save_releases_to_mysql(releases):
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()

    for item in releases:
        for repo, release_list in item.items():
            for release in release_list:
                tag = release.get("tag_name")
                name = release.get("name")
                published = parse_time(release.get("published_at"))
                body = release.get("body")

                cursor.execute("""
                    INSERT INTO github_releases (repo_name, tag_name, published_at, release_name, body)
                    VALUES (%s, %s, %s, %s, %s)
                """, (repo, tag, published, name, body))

    conn.commit()
    cursor.close()
    conn.close()

def parse_time(timestr):
    if timestr:
        try:
            return datetime.strptime(timestr, "%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            return None
    return None

async def get_top_5000_repos():
    queries = generate_search_queries()
    repos = []
    connector = TCPConnector(ssl=False)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [fetch_repos(session, url) for url in queries]
        results = await asyncio.gather(*tasks)
        for r in results:
            repos.extend(r)
    return repos[:5000]

async def crawl_all_releases(repo_names):
    results = []
    semaphore = asyncio.Semaphore(20)
    connector = TCPConnector(ssl=False)

    async def sem_fetch(repo):
        async with semaphore:
            return await fetch_release(session, repo)

    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [sem_fetch(repo) for repo in repo_names]
        for future in tqdm(asyncio.as_completed(tasks), total=len(tasks)):
            result = await future
            results.append(result)
    return results



async def main():
    start_time = time.time()
    repos = await get_top_5000_repos()
    print(f"✅ Đã thu thập {len(repos)} repositories.")

    print("🛢️ Lưu thông tin repositories vào MySQL...")
    save_repos_to_mysql(repos)

    repo_names = [repo["full_name"] for repo in repos]

    print("⏳ Đang lấy thông tin release...")
    releases = await crawl_all_releases(repo_names)

    print("🛢️ Lưu thông tin release vào MySQL...")
    save_releases_to_mysql(releases)

    print("🎉 Hoàn tất!")
    total_repos = len(repos)
    releases_count = len(releases)
    end_time = time.time()
    total_time = end_time - start_time
    print(f"🕒 Tổng thời gian crawl: {total_time:.2f} giây")
    print(f"🚀 Tốc độ xử lý repos: {total_repos / total_time:.2f} repos/s")
    print(f"🚀 Tốc độ xử lý releases: {releases_count / total_time:.2f} releases/s")


if __name__ == "__main__":
    asyncio.run(main())
