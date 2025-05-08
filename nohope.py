import asyncio
import aiohttp
from aiohttp import ClientSession, TCPConnector
from tqdm import tqdm
import mysql.connector
from datetime import datetime
import logging
import time
import csv
import os
import ssl
import certifi
from token_manager import TokenManager

# Configure logging with more detailed format
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
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

def save_release(release_data, repo_name, output_dir='output'):
    os.makedirs(output_dir, exist_ok=True)
    filename = "releases.csv"
    filepath = os.path.join(output_dir, filename)
    
    fieldnames = ['repo_name', 'tag_name', 'release_name', 'published_at', 'body', 'id']
    file_exists = os.path.exists(filepath)
    
    with open(filepath, 'a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        
        for release in release_data:
            body = release.get('body', '').replace('\n', ' ').replace('\r', ' ')
            body = ' '.join(body.split())
            writer.writerow({
                'repo_name': repo_name,
                'tag_name': release.get('tag_name', ''),
                'release_name': release.get('name', ''),
                'published_at': release.get('published_at', ''),
                'body': body,
                'id': release.get('id', '')
            })
    
    logger.info(f"Saved {len(release_data)} releases for {repo_name} to {filepath}")
    return filepath

def save_commits(commits, repo_name, tag_name, release_id, output_dir='output'):
    os.makedirs(output_dir, exist_ok=True)
    filename = "commits.csv"
    filepath = os.path.join(output_dir, filename)

    fieldnames = [
        'repo_name',
        'tag_name', 
        'commit_sha',
        'message',
        'release_id'
    ]
    file_exists = os.path.exists(filepath)

    with open(filepath, 'a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()

        for commit in commits:
            commit_info = commit.get('commit', {})
            message = commit_info.get('message', '').replace('\n', ' ').replace('\r', ' ')
            message = ' '.join(message.split())
            writer.writerow({
                'repo_name': repo_name,
                'tag_name': tag_name,
                'commit_sha': commit.get('sha', ''),
                'message': commit_info.get('message', ''),
                'release_id': str(release_id)  # Ensure release_id is string
            })
    
    logger.info(f"Saved {len(commits)} commits for {repo_name} at tag {tag_name}")
    return filepath


async def crawl_all_releases(repos):
    results = []
    connector = TCPConnector(ssl=ssl_context)
    logger.info(f"Starting to fetch releases for {len(repos)} repositories...")
    
    # Create the output file with headers at the start
    output_dir = 'output'
    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, "releases.csv")
    fieldnames = ['repo_name', 'tag_name', 'release_name', 'published_at', 'body']
    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
    
    async with aiohttp.ClientSession(connector=connector) as session:
        for repo in repos:
            try:
                releases = await fetch_releases(session, repo)
                if releases:  # Only save if we got some releases
                    save_release(releases, repo)
                    results.append({repo: releases})
            except Exception as e:
                logger.error(f"Error processing releases for {repo}: {str(e)}")
                continue
    
    logger.info(f"Completed fetching releases for all repositories")
    return results

async def crawl_all_commits(repos):
    results = []
    connector = TCPConnector(ssl=ssl_context)
    logger.info(f"Starting to fetch commits for repositories...")
    
    # Create the output file with headers at the start
    output_dir = 'output'
    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, "commits.csv")
    
    # Read releases.csv to get repo and tag information
    releases_file = os.path.join(output_dir, "releases.csv")
    if not os.path.exists(releases_file):
        logger.error("releases.csv not found. Please fetch releases first.")
        return results

    # Initialize commits.csv with headers
    fieldnames = [
        'repo_name',
        'tag_name', 
        'commit_sha',
        'message',
        'release_id'
    ]
    
    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
    
    async with aiohttp.ClientSession(connector=connector) as session:
        with open(releases_file, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                repo = row['repo_name']
                tag = row['tag_name']
                release_id = row['id']
                if not tag or not release_id:  # Skip if no tag name or release id
                    continue
                
                try:
                    commits = await fetch_commits(session, repo, tag)
                    if commits:  # Only save if we got some commits
                        save_commits(commits, repo, tag, release_id)
                        results.append({f"{repo}:{tag}": commits})
                        logger.info(f"Processed commits for {repo} at tag {tag} (Release ID: {release_id})")
                except Exception as e:
                    logger.error(f"Error processing commits for {repo} at tag {tag}: {str(e)}")
                    continue
    
    logger.info(f"Completed fetching commits for all repositories")
    return results

def save_to_csv(data, output_type='repos', output_dir='output', filename=None):
    os.makedirs(output_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if not filename:
        filename = f"{output_type}_{timestamp}.csv"
    
    filepath = os.path.join(output_dir, filename)
    logger.info(f"Saving {output_type} data to {filepath}")
    
    if output_type == 'repos':
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
                            'body': release.get('body', '')[:500]
                        })
    
    logger.info(f"Successfully saved {output_type} data to {filepath}")
    return filepath

async def main():
    logger.info("Starting GitHub repository crawler...")
    print("📦 Đang lấy danh sách top 5000 repositories...")
    repos = await get_top_5000_repos()
    print(f"✅ Đã thu thập {len(repos)} repositories.")

    csv_path = save_to_csv(repos, output_type='repos')
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
    print("\nToken Usage Summary:")
    for status in token_status:
        print(f"Token {status['token_index']}:")
        print(f"  - Remaining requests: {status['remaining']}/{status['limit']}")
        print(f"  - Success rate: {status['success_rate']:.2%}")
        print(f"  - Status: {'Cooling down' if status['is_cooling_down'] else 'Active'}")

    logger.info("Crawler completed successfully")
    print("🎉 Hoàn tất!")

if __name__ == "__main__":
    asyncio.run(main()) 