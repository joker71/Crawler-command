# GitHub Repository and Release Crawler

## Architecture Overview

```
┌───────────────────────────────────────────────────────────┐
│                       nohope.py                           │
├───────────────────────────────────────────────────────────┤
│                                                           │
│  ┌─────────────────┐        ┌──────────────────────┐      │
│  │  Configuration  │        │  GitHub API Client   │      │
│  │  - GitHub Token │        │  - Authentication    │      │
│  │  - API URLs     │        │  - Rate Limiting     │      │
│  └─────────────────┘        └──────────────────────┘      │
│          │                            │                   │
│          ▼                            ▼                   │
│  ┌─────────────────┐        ┌──────────────────────┐      │
│  │ Query Generator │        │  Async HTTP Client   │      │
│  │ - Date Ranges   │────┬──▶│  - Concurrent Fetch  │      │
│  │ - Search Params │    │   │  - Error Handling    │      │
│  └─────────────────┘    │   └──────────────────────┘      │
│                         │              │                   │
│                         │              ▼                   │
│                         │   ┌──────────────────────┐      │
│                         │   │  Data Processing     │      │
│                         └──▶│  - Parse Repository  │      │
│                             │  - Parse Release     │      │
│                             └──────────────────────┘      │
│                                        │                   │
│                                        ▼                   │
│                      ┌───────────────────────────────┐     │
│                      │       Data Storage            │     │
│                      │  ┌──────────────┐ ┌────────┐  │     │
│                      │  │ CSV Exporter │ │ MySQL  │  │     │
│                      │  └──────────────┘ └────────┘  │     │
│                      └───────────────────────────────┘     │
│                                                           │
└───────────────────────────────────────────────────────────┘
```

## Component Description

### Configuration
- **GitHub Token Management**: Securely loads authentication token from file
- **API URLs**: Defines endpoints for repository search and release data

### Query Generator
- **Date-Based Search**: Segments queries by time periods to maximize result coverage
- **Pagination**: Implements paging to handle GitHub API's result limits
- **Search Parameters**: Configures query parameters for repository filtering

### GitHub API Client
- **Authentication**: Sets up proper headers for authenticated API access
- **Rate Limiting**: Respects GitHub API rate limits through response header analysis

### Async HTTP Client
- **Concurrent Fetching**: Uses asyncio and aiohttp for efficient parallel requests
- **Semaphore Control**: Limits concurrent connections to avoid overloading
- **Error Handling**: Gracefully handles connection errors and retries

### Data Processing
- **Repository Data**: Extracts and normalizes repository information
- **Release Data**: Processes release details for each repository

### Data Storage
- **CSV Export**: Saves data to CSV files with customizable options
  - Repository data (name, stars, language, etc.)
  - Release data (tag names, descriptions, dates)
- **MySQL Storage**: (Optional) Saves data to relational database tables

## Data Flow

1. Generate search queries based on repository creation dates and stars
2. Concurrently fetch top repositories using GitHub search API
3. Extract repository metadata (name, stars, language, etc.)
4. Store repository data to CSV file
5. For each repository, fetch its releases asynchronously
6. Process and normalize release data
7. Store release data to CSV file

## Key Features

- **Asynchronous Processing**: Efficiently handles thousands of API requests
- **Rate Limit Handling**: Automatically pauses when approaching GitHub API limits
- **Error Resilience**: Continues operation despite individual request failures
- **Flexible Output**: Saves data in CSV format for easy analysis
- **Progress Reporting**: Shows real-time progress with clear status messages

## Usage

```python
# Run the crawler
python nohope.py
```

## Output

The crawler generates two types of CSV files in the output directory:
- `repos_[timestamp].csv`: Repository metadata
- `releases_[timestamp].csv`: Release information

## Dependencies

- aiohttp: Asynchronous HTTP client
- tqdm: Progress bar visualization
- mysql-connector-python: (Optional) MySQL database connectivity 