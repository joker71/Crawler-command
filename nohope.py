import asyncio
import logging
import os
import ssl
from datetime import datetime

import aiohttp
import certifi
import mysql.connector
from aiohttp import ClientSession, TCPConnector

from token_manager import TokenManager

DB_CONFIG = {
    'host': 'host.docker.internal',
    'user': 'root',
    'password': 'abcde12345-',
    'database': 'github_crawler'
}

# Configure logging with more detailed format
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    filename='log.txt',  # Log được ghi vào file
    filemode='a'
)
logger = logging.getLogger(__name__)

# Initialize token manager
token_manager = TokenManager(min_remaining_requests=100, request_interval=0.1)

# Load tokens
try:
    token_manager.load_tokens("token.txt")
    logger.info("Successfully loaded tokens")
except Exception as e:
    logger.error(f"Failed to load tokens: {e}")
    raise

HEADERS = {
    "Accept": "application/vnd.github+json",
    "User-Agent": "release-crawler"
}

# Create SSL context
ssl_context = ssl.create_default_context(cafile=certifi.where())
logger.info("SSL context created with certifi certificates")

SEARCH_URL = "https://api.github.com/search/repositories"
RELEASES_URL = "https://api.github.com/repos/{repo}/releases"
COMMITS_URL = "https://api.github.com/repos/{repo}/commits?sha={tag_name}"


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
    logger.info(f"Generated {len(queries)} search queries")
    return queries[:50]  # Limit to 50 queries for testing


async def fetch_repos(session: ClientSession, url: str):
    try:
        logger.debug(f"Fetching repos from: {url}")
        data = await token_manager.queue_request(session, url, HEADERS)
        if data:
            items = data.get("items", [])
            logger.info(f"Successfully fetched {len(items)} repos from {url}")
            return items
        return []
    except Exception as e:
        logger.error(f"Error fetching repos from {url}: {str(e)}")
        return []


async def fetch_releases(session: aiohttp.ClientSession, full_name: str) -> list:
    url = f"https://api.github.com/repos/{full_name}/releases"
    try:
        logger.debug(f"Fetching releases for {full_name}")
        data = await token_manager.queue_request(session, url, HEADERS)
        if isinstance(data, list):
            logger.info(f"Successfully fetched {len(data)} releases for {full_name}")
            return data
        return []
    except Exception as e:
        logger.error(f"Error fetching releases for {full_name}: {str(e)}")
        return []


async def fetch_commits(session: aiohttp.ClientSession, full_name: str, tag_name: str):
    url = f"https://api.github.com/repos/{full_name}/commits?sha={tag_name}"
    try:
        logger.debug(f"Fetching commits for {full_name} with tag {tag_name}")
        data = await token_manager.queue_request(session, url, HEADERS)
        if isinstance(data, list):
            logger.info(f"Successfully fetched {len(data)} commits for {full_name} with tag {tag_name}")
            return data
        return []
    except Exception as e:
        logger.error(f"Error fetching commits for {full_name} with tag {tag_name}: {str(e)}")
        return []


async def get_top_5000_repos():
    queries = generate_search_queries()
    repos = []
    connector = TCPConnector(ssl=ssl_context)
    logger.info("Starting to fetch top repositories...")
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [fetch_repos(session, url) for url in queries]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, list):
                repos.extend(r)
            else:
                logger.error(f"Error in task: {str(r)}")
    logger.info(f"Total repositories fetched: {len(repos)}")
    return repos[:5000]


def parse_time(timestr):
    if timestr:
        try:
            return datetime.strptime(timestr, "%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            return None
    return None


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


def save_release(release_data, repo_name):
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()

    insert_query = """
        INSERT INTO releases (id, repo_name, tag_name, release_name, published_at, body)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE 
            tag_name = VALUES(tag_name),
            release_name = VALUES(release_name),
            published_at = VALUES(published_at),
            body = VALUES(body)
    """

    for release in release_data:
        body = ' '.join(release.get('body', '').replace('\n', ' ').replace('\r', ' ').split())
        published_at = release.get('published_at', None)
        try:
            if published_at:
                published_at = datetime.fromisoformat(published_at.replace('Z', '+00:00'))

            cursor.execute(insert_query, (
                release.get('id'),
                repo_name,
                release.get('tag_name', ''),
                release.get('name', ''),
                published_at,
                body
            ))
        except Exception as e:
            logger.error(f"Error saving release {release.get('id')}: {e}")

    conn.commit()
    cursor.close()
    conn.close()
    logger.info(f"Saved {len(release_data)} releases for {repo_name} to MySQL")


def save_commits(commits, repo_name, tag_name, release_id):
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()

    insert_query = """
        INSERT INTO commits (commit_sha, repo_name, tag_name, message, release_id)
        VALUES (%s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE 
            message = VALUES(message),
            tag_name = VALUES(tag_name)
    """

    for commit in commits:
        commit_info = commit.get('commit', {})
        message = ' '.join(commit_info.get('message', '').replace('\n', ' ').replace('\r', ' ').split())
        try:
            cursor.execute(insert_query, (
                commit.get('sha', ''),
                repo_name,
                tag_name,
                message,
                release_id
            ))
        except Exception as e:
            logger.error(f"Error saving commit {commit.get('sha')}: {e}")

    conn.commit()
    cursor.close()
    conn.close()
    logger.info(f"Saved {len(commits)} commits for {repo_name} at tag {tag_name} to MySQL")


async def crawl_all_releases(repos):
    results = []
    connector = TCPConnector(ssl=ssl_context, limit=10)  # Reduce concurrent connections
    logger.info(f"Starting to fetch releases for {len(repos)} repositories...")

    # Create the output file with headers at the start
    output_dir = 'output'
    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, "releases.csv")

    # Initialize releases.csv with headers
    fieldnames = ['repo_name', 'tag_name', 'release_name', 'published_at', 'body', 'id']

    async with aiohttp.ClientSession(connector=connector) as session:
        # Process repositories in smaller batches
        BATCH_SIZE = 5  # Reduce batch size

        for i in range(0, len(repos), BATCH_SIZE):
            batch = repos[i:i + BATCH_SIZE]
            logger.info(f"Processing batch {i // BATCH_SIZE + 1}/{(len(repos) + BATCH_SIZE - 1) // BATCH_SIZE}")

            # Create tasks for the batch
            tasks = []
            for repo in batch:
                task = asyncio.create_task(fetch_releases(session, repo))
                tasks.append((repo, task))

            # Add delay between batches to prevent rate limit exhaustion
            if i > 0:
                await asyncio.sleep(2)  # 2 second delay between batches

            # Wait for all tasks in the batch to complete
            for repo, task in tasks:
                try:
                    releases = await task
                    if releases:
                        save_release(releases, repo)
                        results.append({repo: releases})
                        logger.info(f"Processed and saved {len(releases)} releases for {repo}")
                    else:
                        logger.warning(f"No releases found for {repo}")
                except Exception as e:
                    logger.error(f"Error processing releases for {repo}: {str(e)}")
                    continue

            logger.info(f"Completed batch {i // BATCH_SIZE + 1}")

    logger.info(f"Completed fetching releases for all repositories")
    return results


async def crawl_all_commits(repos):
    results = []
    connector = TCPConnector(ssl=ssl_context, limit=10)  # Reduce concurrent connections
    logger.info(f"Starting to fetch commits for repositories...")

    # Create the output file with headers at the start
    output_dir = 'output'
    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, "commits.csv")

    async with aiohttp.ClientSession(connector=connector) as session:
        # Read releases.csv to get repo and tag information
        releases_file = os.path.join(output_dir, "releases.csv")
        if not os.path.exists(releases_file):
            logger.error("releases.csv not found. Please fetch releases first.")
            return results

        # Read all releases and group them by repository
        repo_releases = {}

        # Process repositories in smaller batches
        BATCH_SIZE = 5  # Reduce batch size
        repos_to_process = list(repo_releases.keys())

        for i in range(0, len(repos_to_process), BATCH_SIZE):
            batch_repos = repos_to_process[i:i + BATCH_SIZE]
            logger.info(
                f"Processing batch {i // BATCH_SIZE + 1}/{(len(repos_to_process) + BATCH_SIZE - 1) // BATCH_SIZE}")

            # Create tasks for each repository's releases
            tasks = []
            for repo in batch_repos:
                # Process first 3 releases per repository to reduce load
                for release in repo_releases[repo][:3]:
                    tag = release['tag_name']
                    release_id = release['release_id']
                    if tag and release_id:
                        task = asyncio.create_task(fetch_commits(session, repo, tag))
                        tasks.append((repo, tag, release_id, task))

            # Add delay between batches to prevent rate limit exhaustion
            if i > 0:
                await asyncio.sleep(2)  # 2 second delay between batches

            # Wait for all tasks in the batch to complete
            for repo, tag, release_id, task in tasks:
                try:
                    commits = await task
                    if commits:
                        save_commits(commits, repo, tag, release_id)
                        results.append({f"{repo}:{tag}": commits})
                        logger.info(f"Processed and saved {len(commits)} commits for {repo} at tag {tag}")
                    else:
                        logger.warning(f"No commits found for {repo} at tag {tag}")
                except Exception as e:
                    logger.error(f"Error processing commits for {repo} at tag {tag}: {str(e)}")
                    continue

            logger.info(f"Completed batch {i // BATCH_SIZE + 1}")

    logger.info(f"Completed fetching commits for all repositories")
    return results


async def crawl():
    logger.info("Starting GitHub repository crawler...")
    print("📦 Đang lấy danh sách top 5000 repositories...")
    repos = await get_top_5000_repos()
    print(f"✅ Đã thu thập {len(repos)} repositories.")

    csv_path = save_repos_to_mysql(repos)
    print(f"💾 Đã lưu thông tin repositories vào {csv_path}")

    repo_names = [repo["full_name"] for repo in repos]
    logger.info(f"Starting to fetch releases for {len(repo_names)} repositories")

    print("⏳ Đang lấy thông tin release...")
    releases = await crawl_all_releases(repo_names)
    print("✅ Đã lưu thông tin releases")

    print("⏳ Đang lấy thông tin commits...")
    commits = await crawl_all_commits(repo_names)
    print("✅ Đã lưu thông tin commits")

    # Print token status at the end
    token_status = token_manager.get_token_status()
    logger.info("\nToken Usage Summary:")
    for status in token_status:
        logger.info(f"Token {status['token_index']}:")
        logger.info(f"  - Remaining requests: {status['remaining']}/{status['limit']}")
        logger.info(f"  - Success rate: {status['success_rate']:.2%}")
        logger.info(f"  - Status: {'Cooling down' if status['is_cooling_down'] else 'Active'}")

    logger.info("Crawler completed successfully")
    print("🎉 Hoàn tất!")

async def run_periodically():
    while True:
        await crawl()
        await asyncio.sleep(10,800)  # 4 phút = 240 giây

if __name__ == "__main__":
    asyncio.run(run_periodically())
