import asyncio
import aiohttp
from aiohttp import ClientSession
from tqdm import tqdm
import mysql.connector
from datetime import datetime
import logging
import time
import csv
import os

logger = logging.getLogger(__name__)
def load_token():
    with open("../token.txt", "r") as f:
        return f.read().strip()

GITHUB_TOKEN = load_token()
HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
    "User-Agent": "release-crawler"
}

# ====== MySQL Config ======
# Commented out as we're only using CSV now
# DB_CONFIG = {
#     'host': 'localhost',
#     'user': 'root',
#     'password': 'Hangnga98#',
#     'database': 'github_crawler'
# }

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

# Async hàm lấy repo
async def fetch_repos(session: ClientSession, url: str):
    async with session.get(url, headers=HEADERS) as resp:
        if resp.status != 200:
            return []
        data = await resp.json()
        return data.get("items", [])

# Async hàm lấy release
async def fetch_releases(session: aiohttp.ClientSession, full_name: str, token: str) -> list:
    """
    Fetch releases for a given GitHub repository.

    Args:
        session (aiohttp.ClientSession): The aiohttp session to reuse
        full_name (str): Repository full name (e.g., "torvalds/linux")
        token (str): GitHub personal access token

    Returns:
        list: List of release dictionaries or empty list
    """
    url = f"https://api.github.com/repos/{full_name}/releases"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "github-crawler"
    }

    try:
        async with session.get(url, headers=headers) as response:
            if response.status == 403:
                logger.error(f"403 Forbidden for {full_name}")
                rate_limit_remaining = response.headers.get("X-RateLimit-Remaining")
                rate_limit_reset = response.headers.get("X-RateLimit-Reset")
                if rate_limit_remaining == "0" and rate_limit_reset:
                    reset_time = int(rate_limit_reset)
                    wait_seconds = max(reset_time - int(time.time()), 0)
                    logger.warning(f"Rate limit hit. Sleeping for {wait_seconds}s")
                    await asyncio.sleep(wait_seconds)
                    return await fetch_releases(session, full_name, token)  # retry
                else:
                    text = await response.text()
                    logger.error(f"403 error details: {text}")
                    return []

            elif response.status != 200:
                logger.error(f"Failed to fetch releases for {full_name}. Status: {response.status}")
                text = await response.text()
                logger.debug(f"Response text: {text}")
                return []

            data = await response.json()
            if isinstance(data, list):
                return data
            else:
                logger.warning(f"Unexpected data format for {full_name}")
                return []

    except aiohttp.ClientError as e:
        logger.error(f"Client error fetching {full_name}: {str(e)}")
        return []

    except asyncio.TimeoutError:
        logger.error(f"Timeout fetching {full_name}")
        return []

    except Exception as e:
        logger.exception(f"Unexpected error: {str(e)}")
        return []


# Commented out database function
# def save_repos_to_mysql(repos):
#     conn = mysql.connector.connect(**DB_CONFIG)
#     cursor = conn.cursor()
#     for repo in repos:
#         full_name = repo["full_name"]
#         description = repo.get("description")
#         stars = repo.get("stargazers_count", 0)
#         language = repo.get("language")
#         created_at = parse_time(repo.get("created_at"))
#         updated_at = parse_time(repo.get("updated_at"))
#
#         cursor.execute("""
#             INSERT IGNORE INTO repositories
#             (full_name, description, stars, language, created_at, updated_at)
#             VALUES (%s, %s, %s, %s, %s, %s)
#         """, (full_name, description, stars, language, created_at, updated_at))
#
#     conn.commit()
#     cursor.close()
#     conn.close()

# Commented out database function
# def save_releases_to_mysql(releases):
#     conn = mysql.connector.connect(**DB_CONFIG)
#     cursor = conn.cursor()
#
#     for item in releases:
#         for repo, release_list in item.items():
#             for release in release_list:
#                 tag = release.get("tag_name")
#                 name = release.get("name")
#                 published = parse_time(release.get("published_at"))
#                 body = release.get("body")
#
#                 cursor.execute("""
#                     INSERT INTO github_releases (repo_name, tag_name, published_at, release_name, body)
#                     VALUES (%s, %s, %s, %s, %s)
#                 """, (repo, tag, published, name, body))
#
#     conn.commit()
#     cursor.close()
#     conn.close()

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
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_repos(session, url) for url in queries]
        results = await asyncio.gather(*tasks)
        for r in results:
            repos.extend(r)
    return repos[:5000]

# Hàm crawl toàn bộ release song song
async def crawl_all_releases(repos):
    results = []
    semaphore = asyncio.Semaphore(20)  # giới hạn max 20 request song song

    async with aiohttp.ClientSession() as session:
        tasks = [fetch_releases(session, repo, GITHUB_TOKEN) for repo in repos]
        results = await asyncio.gather(*tasks)
    return results

def save_to_csv(data, output_type='repos', output_dir='output', filename=None):
    """
    Save repository or release data to CSV files.

    Args:
        data (list): List of repositories or releases data to save
        output_type (str): Type of data - 'repos' or 'releases'
        output_dir (str): Directory to save the CSV files
        filename (str, optional): Custom filename. If None, a default name will be generated.

    Returns:
        str: Path to the saved CSV file
    """
    os.makedirs(output_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if not filename:
        filename = f"{output_type}_{timestamp}.csv"
    
    filepath = os.path.join(output_dir, filename)
    
    if output_type == 'repos':
        # Define headers for repository CSV
        fieldnames = ['full_name', 'description', 'stars', 'language', 'created_at', 'updated_at']
        
        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            
            for repo in data:
                writer.writerow({
                    'full_name': repo['full_name'],
                    'description': repo.get('description', ''),
                    'stars': repo.get('stargazers_count', 0),
                    'language': repo.get('language', ''),
                    'created_at': repo.get('created_at', ''),
                    'updated_at': repo.get('updated_at', '')
                })
    
    elif output_type == 'releases':
        # Define headers for releases CSV
        fieldnames = ['repo_name', 'tag_name', 'release_name', 'published_at', 'body']
        
        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            
            for item in data:
                for repo, release_list in item.items():
                    for release in release_list:
                        writer.writerow({
                            'repo_name': repo,
                            'tag_name': release.get('tag_name', ''),
                            'release_name': release.get('name', ''),
                            'published_at': release.get('published_at', ''),
                            'body': release.get('body', '')[:500]  # Limit body text length
                        })
    
    else:
        raise ValueError(f"Invalid output_type: {output_type}. Must be 'repos' or 'releases'")
    
    logger.info(f"Saved {output_type} data to {filepath}")
    return filepath

async def main():
    print("📦 Đang lấy danh sách top 5000 repositories...")
    repos = await get_top_5000_repos()
    print(f"✅ Đã thu thập {len(repos)} repositories.")

    # Commented out database saving
    # print("🛢️ Lưu thông tin repositories vào MySQL...")
    # save_repos_to_mysql(repos)
    
    # Save repos to CSV
    csv_path = save_to_csv(repos, output_type='repos')
    print(f"💾 Đã lưu thông tin repositories vào {csv_path}")

    repo_names = [repo["full_name"] for repo in repos]

    print("⏳ Đang lấy thông tin release...")
    releases = await crawl_all_releases(repo_names)

    # Commented out database saving
    # print("🛢️ Lưu thông tin release vào MySQL...")
    # save_releases_to_mysql(releases)
    
    # Save releases to CSV
    releases_csv_path = save_to_csv(releases, output_type='releases')
    print(f"💾 Đã lưu thông tin releases vào {releases_csv_path}")

    print("🎉 Hoàn tất!")

if __name__ == "__main__":
    asyncio.run(main())
