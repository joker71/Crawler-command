import asyncio
import time
import logging
from dataclasses import dataclass
from typing import Optional, Dict, Any, List, Deque
from collections import deque
from aiohttp import ClientSession
import random

# Configure logging
logger = logging.getLogger(__name__)

@dataclass
class TokenStatus:
    """Data class to store token status and rate limit information"""
    token: str
    remaining: int = 5000
    limit: int = 5000
    reset_time: int = 0
    last_used: float = 0
    success_count: int = 0
    failure_count: int = 0
    is_cooling_down: bool = False
    cooldown_until: float = 0

class TokenManager:
    """Manages multiple GitHub tokens with rate limiting and rotation"""
    
    def __init__(self, min_remaining_requests: int = 100, request_interval: float = 0.1):
        """
        Initialize the token manager
        
        Args:
            min_remaining_requests: Minimum number of requests to keep in reserve
            request_interval: Minimum time between requests in seconds
        """
        self.tokens: List[TokenStatus] = []
        self.current_token_index: int = 0
        self.min_remaining_requests = min_remaining_requests
        self.request_interval = request_interval
        self.request_queue: Deque[Dict[str, Any]] = deque()
        self.processing = False

    def load_tokens(self, token_file_path: str) -> None:
        """Load tokens from a file"""
        try:
            with open(token_file_path, 'r') as f:
                content = f.read().strip()
                # Split by comma and clean up tokens
                tokens = [t.strip() for t in content.split(',') if t.strip()]
                self.tokens = [TokenStatus(token=t) for t in tokens]
                logger.info(f"Loaded {len(self.tokens)} tokens")
        except Exception as e:
            logger.error(f"Error loading tokens: {e}")
            raise

    def get_current_token(self) -> Optional[TokenStatus]:
        """Get the current active token"""
        if not self.tokens:
            return None
        return self.tokens[self.current_token_index]

    def rotate_token(self) -> None:
        """Rotate to the next available token"""
        if not self.tokens:
            return

        original_index = self.current_token_index
        while True:
            self.current_token_index = (self.current_token_index + 1) % len(self.tokens)
            if self.current_token_index == original_index:
                # We've tried all tokens, wait for cooldown
                logger.warning("All tokens are in cooldown, waiting...")
                time.sleep(60)  # Wait a minute before trying again
                continue

            current_token = self.get_current_token()
            if not current_token.is_cooling_down:
                logger.info(f"Rotated to token {self.current_token_index + 1}")
                break

    def update_token_status(self, token: TokenStatus, headers: Dict[str, str]) -> None:
        """Update token status from response headers"""
        try:
            remaining = int(headers.get('X-RateLimit-Remaining', 0))
            limit = int(headers.get('X-RateLimit-Limit', 5000))
            reset_time = int(headers.get('X-RateLimit-Reset', 0))
            
            token.remaining = remaining
            token.limit = limit
            token.reset_time = reset_time
            token.last_used = time.time()
            
            # Log rate limit status
            logger.info(f"Token {self.current_token_index + 1} - "
                       f"Remaining: {remaining}/{limit} "
                       f"(Reset in {reset_time - int(time.time())} seconds)")
            
            # Check if token needs cooldown
            if remaining < self.min_remaining_requests:
                token.is_cooling_down = True
                token.cooldown_until = reset_time
                logger.warning(f"Token {self.current_token_index + 1} entering cooldown")
                self.rotate_token()
                
        except (ValueError, TypeError) as e:
            logger.error(f"Error parsing rate limit headers: {e}")

    def should_wait(self, token: TokenStatus) -> bool:
        """Determine if we should wait before making the next request"""
        current_time = time.time()
        
        # Check if token is in cooldown
        if token.is_cooling_down:
            if current_time < token.cooldown_until:
                return True
            token.is_cooling_down = False
        
        # Check if we're too close to the rate limit
        if token.remaining <= self.min_remaining_requests:
            wait_time = token.reset_time - current_time
            if wait_time > 0:
                logger.info(f"Rate limit low, waiting {wait_time:.2f} seconds")
                return True
                
        # Check if we need to respect the request interval
        time_since_last = current_time - token.last_used
        if time_since_last < self.request_interval:
            return True
            
        return False

    def get_wait_time(self, token: TokenStatus) -> float:
        """Calculate how long to wait before the next request"""
        current_time = time.time()
        
        # If token is in cooldown
        if token.is_cooling_down:
            return max(0, token.cooldown_until - current_time)
        
        # If we're running low on requests, wait until reset
        if token.remaining <= self.min_remaining_requests:
            return max(0, token.reset_time - current_time)
            
        # Otherwise, respect the request interval
        time_since_last = current_time - token.last_used
        return max(0, self.request_interval - time_since_last)

    async def queue_request(self, session: ClientSession, url: str, headers: Dict[str, str]) -> Any:
        """Queue a request and handle rate limiting with token rotation"""
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            current_token = self.get_current_token()
            if not current_token:
                logger.error("No tokens available")
                return None

            # Update headers with current token
            headers['Authorization'] = f"token {current_token.token}"
            
            # Wait if necessary
            while self.should_wait(current_token):
                wait_time = self.get_wait_time(current_token)
                if wait_time > 0:
                    logger.debug(f"Waiting {wait_time:.2f} seconds before next request")
                    await asyncio.sleep(wait_time)
            
            try:
                async with session.get(url, headers=headers) as response:
                    # Update token status from response headers
                    self.update_token_status(current_token, response.headers)
                    
                    if response.status == 200:
                        current_token.success_count += 1
                        return await response.json()
                    elif response.status == 403:
                        current_token.failure_count += 1
                        logger.error(f"Rate limit exceeded for {url}")
                        self.rotate_token()
                        retry_count += 1
                        continue
                    else:
                        current_token.failure_count += 1
                        logger.error(f"HTTP {response.status} for {url}")
                        retry_count += 1
                        continue
                        
            except Exception as e:
                current_token.failure_count += 1
                logger.error(f"Error making request to {url}: {str(e)}")
                retry_count += 1
                continue
        
        logger.error(f"Failed to make request after {max_retries} retries")
        return None

    def get_token_status(self) -> List[Dict[str, Any]]:
        """Get status of all tokens"""
        return [{
            "token_index": i + 1,
            "remaining": t.remaining,
            "limit": t.limit,
            "success_rate": t.success_count / (t.success_count + t.failure_count) if (t.success_count + t.failure_count) > 0 else 0,
            "is_cooling_down": t.is_cooling_down,
            "cooldown_until": t.cooldown_until
        } for i, t in enumerate(self.tokens)] 