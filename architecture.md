# GitHub Repository Crawler Architecture

## System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        Main Crawler (nohope.py)                 │
└───────────────────────────────┬─────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Token Manager (token_manager.py)           │
└───────────────────────────────┬─────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                        GitHub API                               │
└───────────────────────────────┬─────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                        CSV Storage                              │
└─────────────────────────────────────────────────────────────────┘
```

## Component Details

### 1. Main Crawler (nohope.py)
The orchestrator of the entire system.

#### Data Flow:
```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Repository │     │   Release   │     │    CSV      │
│  Fetching   │────▶│  Fetching   │────▶│   Saving    │
└─────────────┘     └─────────────┘     └─────────────┘
```

#### Key Features:
- Asynchronous operations using `aiohttp`
- SSL/TLS security with certificate verification
- Incremental data saving
- Comprehensive logging

### 2. Token Manager (token_manager.py)
Manages GitHub API authentication and rate limiting.

#### Token Management Flow:
```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Token     │     │   Rate      │     │   Request   │
│  Rotation   │────▶│   Limit     │────▶│  Queueing   │
└─────────────┘     └─────────────┘     └─────────────┘
```

#### Key Features:
- Multiple token support
- Automatic token rotation
- Rate limit monitoring
- Token cooldown system
- Success/failure tracking

## Token Manager Detailed Architecture

### Token Rotation System
```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Current Token  │     │  Check Rate     │     │  Next Token     │
│  Status Check   │────▶│  Limit Status   │────▶│  Selection      │
└─────────────────┘     └─────────────────┘     └─────────────────┘
        │                        │                        │
        │                        ▼                        ▼
        │                ┌─────────────────┐     ┌─────────────────┐
        └───────────────▶│  Cooldown      │     │  Update Token   │
                         │  Management    │     │  Status         │
                         └─────────────────┘     └─────────────────┘
```

#### Token Rotation Process:
1. **Token Status Monitoring**
   - Tracks remaining requests per token
   - Monitors success/failure rates
   - Records last usage time

2. **Rate Limit Management**
   - Minimum remaining requests threshold (default: 100)
   - Reset time tracking
   - Cooldown period enforcement

3. **Token Selection**
   - Round-robin token selection
   - Skips tokens in cooldown
   - Prioritizes tokens with higher remaining limits

### Rate Limiting System
```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Request        │     │  Rate Limit     │     │  Request        │
│  Received       │────▶│  Check          │────▶│  Execution      │
└─────────────────┘     └─────────────────┘     └─────────────────┘
        │                        │                        │
        │                        ▼                        ▼
        │                ┌─────────────────┐     ┌─────────────────┐
        └───────────────▶│  Wait Time     │     │  Update Rate    │
                         │  Calculation    │     │  Limit Status   │
                         └─────────────────┘     └─────────────────┘
```

#### Rate Limit Features:
1. **Request Interval Control**
   - Minimum time between requests (default: 0.1s)
   - Dynamic wait time calculation
   - Burst request prevention

2. **Limit Monitoring**
   - Real-time remaining request tracking
   - Reset time synchronization
   - Automatic cooldown activation

3. **Token Cooldown**
   - Automatic cooldown when limit is low
   - Cooldown period based on reset time
   - Token reactivation after cooldown

### Request Queuing System
```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Request        │     │  Queue          │     │  Request        │
│  Submission     │────▶│  Management     │────▶│  Processing     │
└─────────────────┘     └─────────────────┘     └─────────────────┘
        │                        │                        │
        │                        ▼                        ▼
        │                ┌─────────────────┐     ┌─────────────────┐
        └───────────────▶│  Priority      │     │  Result         │
                         │  Assignment    │     │  Handling       │
                         └─────────────────┘     └─────────────────┘
```

#### Queue Management Features:
1. **Request Queue**
   - FIFO (First In, First Out) queue
   - Request metadata storage
   - Priority-based processing

2. **Queue Processing**
   - Concurrent request handling
   - Automatic retry mechanism
   - Error handling and logging

3. **Result Management**
   - Success/failure tracking
   - Response caching
   - Error reporting

### Token Status Tracking
```
TokenStatus
├── token: str                    # GitHub API token
├── remaining: int               # Remaining requests
├── limit: int                   # Total request limit
├── reset_time: int             # Rate limit reset time
├── last_used: float            # Last request timestamp
├── success_count: int          # Successful requests
├── failure_count: int          # Failed requests
├── is_cooling_down: bool       # Cooldown status
└── cooldown_until: float       # Cooldown end time
```

### Error Handling and Recovery
1. **Token Errors**
   - Automatic token rotation on failure
   - Cooldown period enforcement
   - Error logging and tracking

2. **Rate Limit Errors**
   - Automatic retry with backoff
   - Token rotation on limit exceeded
   - Request queuing during cooldown

3. **Network Errors**
   - Request retry mechanism
   - Token status preservation
   - Error reporting and logging

### 3. Data Storage
Single-file CSV storage system.

#### Storage Structure:
```
releases.csv
├── repo_name
├── tag_name
├── release_name
├── published_at
└── body
```

## Process Flow

1. **Repository Collection**:
   ```
   Main Crawler
   ├── Generate search queries
   ├── Fetch repositories
   └── Save to CSV
   ```

2. **Release Collection**:
   ```
   Main Crawler
   ├── For each repository:
   │   ├── Fetch releases
   │   └── Append to releases.csv
   └── Continue until all repositories processed
   ```

3. **Token Management**:
   ```
   Token Manager
   ├── Monitor rate limits
   ├── Rotate tokens when needed
   └── Queue requests
   ```

## Error Handling

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Error     │     │   Retry     │     │   Log       │
│  Detection  │────▶│  Mechanism  │────▶│  Error      │
└─────────────┘     └─────────────┘     └─────────────┘
```

## Security Features

- SSL/TLS with certificate verification
- Secure token management
- Rate limit compliance
- No token exposure in logs

## Performance Optimizations

1. **Asynchronous Operations**:
   - Concurrent API requests
   - Non-blocking I/O operations

2. **Token Management**:
   - Efficient token rotation
   - Smart request scheduling
   - Cooldown periods

3. **Data Storage**:
   - Single-file approach
   - Incremental saving
   - UTF-8 encoding

## Monitoring and Logging

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Token     │     │   Rate      │     │   Success   │
│   Status    │────▶│   Limits    │────▶│   Metrics   │
└─────────────┘     └─────────────┘     └─────────────┘
```

## System Requirements

- Python 3.7+
- Required packages:
  - aiohttp
  - tqdm
  - mysql-connector
  - certifi

## File Structure

```
project/
├── nohope.py           # Main crawler
├── token_manager.py    # Token management
├── output/            # Data storage
│   └── releases.csv   # Single output file
└── token.txt         # Token storage
``` 