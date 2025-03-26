# app/utils/api_request.py

import logging
import time
import requests
from functools import wraps
from app.utils.circuit_breaker import circuit_breaker

logger = logging.getLogger(__name__)

class APIRequestError(Exception):
    """Base exception for API request errors"""
    def __init__(self, message, status_code=None, response=None):
        self.message = message
        self.status_code = status_code
        self.response = response
        super().__init__(self.message)


class APITimeoutError(APIRequestError):
    """Exception raised when an API request times out"""
    pass


class APIRateLimitError(APIRequestError):
    """Exception raised when rate limited by the API"""
    pass


def with_timeout(timeout=10):
    """
    Decorator to add timeout to functions that make API requests
    
    Usage:
        @with_timeout(timeout=5)
        def get_coinbase_data():
            # Function that makes API requests
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            import signal
            
            def timeout_handler(signum, frame):
                raise APITimeoutError(f"Function {func.__name__} timed out after {timeout} seconds")
                
            # Set the timeout handler
            original_handler = signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(timeout)
            
            try:
                return func(*args, **kwargs)
            finally:
                # Reset the alarm and restore the original handler
                signal.alarm(0)
                signal.signal(signal.SIGALRM, original_handler)
                
        return wrapper
    return decorator


def safe_request(method, url, **kwargs):
    """
    Make a safe HTTP request with proper error handling
    
    Args:
        method: HTTP method (get, post, put, delete)
        url: Request URL
        **kwargs: Additional arguments for requests
        
    Returns:
        Response object
        
    Raises:
        APIRequestError: For request errors
        APITimeoutError: For timeout errors
        APIRateLimitError: For rate limit errors
    """
    # Set some sensible defaults
    kwargs.setdefault('timeout', 10)
    
    # Track timing for logging
    start_time = time.time()
    
    try:
        response = requests.request(method, url, **kwargs)
        elapsed = time.time() - start_time
        
        # Log the request
        logger.debug(f"{method.upper()} {url} completed in {elapsed:.2f}s with status {response.status_code}")
        
        # Handle different response status codes
        if response.status_code == 429:
            raise APIRateLimitError(
                "Rate limit exceeded",
                status_code=response.status_code,
                response=response
            )
            
        if response.status_code >= 500:
            raise APIRequestError(
                f"Server error: {response.status_code}",
                status_code=response.status_code,
                response=response
            )
            
        if response.status_code >= 400:
            raise APIRequestError(
                f"Client error: {response.status_code}",
                status_code=response.status_code,
                response=response
            )
            
        return response
        
    except requests.Timeout:
        logger.warning(f"{method.upper()} {url} timed out after {kwargs['timeout']}s")
        raise APITimeoutError(f"Request timed out after {kwargs['timeout']} seconds")
        
    except requests.ConnectionError as e:
        logger.error(f"{method.upper()} {url} connection error: {str(e)}")
        raise APIRequestError(f"Connection error: {str(e)}")
        
    except requests.RequestException as e:
        logger.error(f"{method.upper()} {url} request error: {str(e)}")
        raise APIRequestError(f"Request error: {str(e)}")