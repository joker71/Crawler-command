import asyncio
import time
import logging
from dataclasses import dataclass
from typing import Optional, Dict, Any, Deque
from collections import deque
from aiohttp import ClientSession

# Configure logging
logger = logging.getLogger(__name__)

@dataclass
class RateLimitInfo:
    """Data class to store rate limit information"""
    remaining: int
    limit: int
    reset_time: int
    last_updated: float

class RateLimitManager:
    """Manages GitHub API rate limits and request scheduling"""
    
    def __init__(self, min_remaining_requests: int = 50, request_interval: float = 0.1):
        """
        Initialize the rate limit manager
        
        Args:
            min_remaining_requests: Minimum number of requests to keep in reserve
            request_interval: Minimum time between requests in seconds
        """
        self.rate_limit_info: Optional[RateLimitInfo] = None
        self.request_queue: Deque[Dict[str, Any]] = deque()
        self.processing = False
        self.min_remaining_requests = min_remaining_requests
        self.request_interval = request_interval

    def update_rate_limit_info(self, headers: Dict[str, str]) -> None:
        """
        Update rate limit information from response headers
        
        Args:
            headers: Response headers from GitHub API
        """
        try:
            remaining = int(headers.get('X-RateLimit-Remaining', 0))
            limit = int(headers.get('X-RateLimit-Limit', 5000))
            reset_time = int(headers.get('X-RateLimit-Reset', 0))
            
            self.rate_limit_info = RateLimitInfo(
                remaining=remaining,
                limit=limit,
                reset_time=reset_time,
                last_updated=time.time()
            )
            
            # Log rate limit status
            logger.info(f"Rate Limit Status - Remaining: {remaining}/{limit} "
                       f"(Reset in {reset_time - int(time.time())} seconds)")
            
            # Warning if approaching limit
            if remaining < self.min_remaining_requests:
                logger.warning(f"Rate limit is running low! {remaining} requests remaining")
                
        except (ValueError, TypeError) as e:
            logger.error(f"Error parsing rate limit headers: {e}")

    def should_wait(self) -> bool:
        """
        Determine if we should wait before making the next request
        
        Returns:
            bool: True if we should wait, False otherwise
        """
        if not self.rate_limit_info:
            return False
            
        current_time = time.time()
        
        # Check if we're too close to the rate limit
        if self.rate_limit_info.remaining <= self.min_remaining_requests:
            wait_time = self.rate_limit_info.reset_time - current_time
            if wait_time > 0:
                logger.info(f"Rate limit low, waiting {wait_time:.2f} seconds")
                return True
                
        # Check if we need to respect the request interval
        time_since_last = current_time - self.rate_limit_info.last_updated
        if time_since_last < self.request_interval:
            return True
            
        return False

    def get_wait_time(self) -> float:
        """
        Calculate how long to wait before the next request
        
        Returns:
            float: Number of seconds to wait
        """
        if not self.rate_limit_info:
            return 0
            
        current_time = time.time()
        
        # If we're running low on requests, wait until reset
        if self.rate_limit_info.remaining <= self.min_remaining_requests:
            return max(0, self.rate_limit_info.reset_time - current_time)
            
        # Otherwise, respect the request interval
        time_since_last = current_time - self.rate_limit_info.last_updated
        return max(0, self.request_interval - time_since_last)

    async def queue_request(self, session: ClientSession, url: str, headers: Dict[str, str]) -> Any:
        """
        Queue a request and handle rate limiting
        
        Args:
            session: aiohttp ClientSession
            url: Request URL
            headers: Request headers
            
        Returns:
            Any: Response data or None if request failed
        """
        while self.should_wait():
            wait_time = self.get_wait_time()
            if wait_time > 0:
                logger.debug(f"Waiting {wait_time:.2f} seconds before next request")
                await asyncio.sleep(wait_time)
        
        try:
            async with session.get(url, headers=headers) as response:
                # Update rate limit info from response headers
                self.update_rate_limit_info(response.headers)
                
                if response.status == 200:
                    return await response.json()
                elif response.status == 403:
                    logger.error(f"Rate limit exceeded for {url}")
                    return None
                else:
                    logger.error(f"HTTP {response.status} for {url}")
                    return None
                    
        except Exception as e:
            logger.error(f"Error making request to {url}: {str(e)}")
            return None

    def get_rate_limit_status(self) -> Dict[str, Any]:
        """
        Get current rate limit status
        
        Returns:
            Dict containing rate limit information
        """
        if not self.rate_limit_info:
            return {
                "remaining": 0,
                "limit": 0,
                "reset_time": 0,
                "time_until_reset": 0
            }
            
        current_time = time.time()
        return {
            "remaining": self.rate_limit_info.remaining,
            "limit": self.rate_limit_info.limit,
            "reset_time": self.rate_limit_info.reset_time,
            "time_until_reset": max(0, self.rate_limit_info.reset_time - current_time)
        } 