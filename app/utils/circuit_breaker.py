# app/utils/circuit_breaker.py

import time
import logging
from functools import wraps
from threading import Lock

logger = logging.getLogger(__name__)

class CircuitBreaker:
    """
    Circuit breaker implementation to prevent cascading failures 
    when external services are unavailable
    """
    
    # Class-level circuit breakers store
    _breakers = {}
    _lock = Lock()
    
    # Circuit states
    CLOSED = 'closed'       # Normal operation, requests go through
    OPEN = 'open'           # Circuit is open, requests fail fast
    HALF_OPEN = 'half_open' # Testing if service is back online
    
    def __init__(self, name, failure_threshold=5, recovery_timeout=30, 
                 failure_window=60, half_open_max_calls=3):
        """
        Initialize a circuit breaker
        
        Args:
            name (str): Name for this circuit breaker
            failure_threshold (int): Number of failures before opening circuit
            recovery_timeout (int): Seconds to wait before trying half-open state
            failure_window (int): Time window in seconds to count failures
            half_open_max_calls (int): Max calls to allow in half-open state
        """
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_window = failure_window
        self.half_open_max_calls = half_open_max_calls
        
        # Initial state
        self.state = self.CLOSED
        self.failures = []
        self.last_failure_time = 0
        self.half_open_calls = 0
        
    @classmethod
    def get_or_create(cls, name, **kwargs):
        """Get existing circuit breaker or create new one"""
        with cls._lock:
            if name not in cls._breakers:
                cls._breakers[name] = CircuitBreaker(name, **kwargs)
            return cls._breakers[name]
    
    def record_failure(self):
        """Record a failure and potentially open the circuit"""
        current_time = time.time()
        
        # Add the current failure
        self.failures.append(current_time)
        self.last_failure_time = current_time
        
        # Remove old failures outside the window
        self.failures = [t for t in self.failures 
                        if t > current_time - self.failure_window]
        
        # Check if we need to open the circuit
        if self.state == self.CLOSED and len(self.failures) >= self.failure_threshold:
            logger.warning(f"Circuit breaker '{self.name}' opened after {len(self.failures)} failures")
            self.state = self.OPEN
        elif self.state == self.HALF_OPEN:
            logger.warning(f"Circuit breaker '{self.name}' opened again after half-open failure")
            self.state = self.OPEN
            self.half_open_calls = 0
    
    def record_success(self):
        """Record a success and potentially close the circuit"""
        if self.state == self.HALF_OPEN:
            self.half_open_calls += 1
            if self.half_open_calls >= self.half_open_max_calls:
                logger.info(f"Circuit breaker '{self.name}' closed after successful half-open calls")
                self.state = self.CLOSED
                self.failures = []
                self.half_open_calls = 0
    
    def allow_request(self):
        """Check if request should be allowed through"""
        current_time = time.time()
        
        if self.state == self.CLOSED:
            return True
        
        if self.state == self.OPEN:
            # Check if recovery timeout has elapsed
            if current_time - self.last_failure_time > self.recovery_timeout:
                logger.info(f"Circuit breaker '{self.name}' entering half-open state")
                self.state = self.HALF_OPEN
                self.half_open_calls = 0
                return True
            return False
            
        if self.state == self.HALF_OPEN:
            # Allow limited number of requests in half-open state
            return self.half_open_calls < self.half_open_max_calls
        
        return True


def circuit_breaker(name, **cb_kwargs):
    """
    Decorator that wraps a function with circuit breaker logic
    
    Usage:
        @circuit_breaker('coinbase_api')
        def call_coinbase_api():
            # Function implementation
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            breaker = CircuitBreaker.get_or_create(name, **cb_kwargs)
            
            if not breaker.allow_request():
                logger.warning(f"Circuit breaker '{name}' is open, request rejected")
                raise CircuitBreakerOpenError(f"Circuit breaker '{name}' is open")
            
            try:
                result = func(*args, **kwargs)
                breaker.record_success()
                return result
            except Exception as e:
                breaker.record_failure()
                raise
        return wrapper
    return decorator


class CircuitBreakerOpenError(Exception):
    """Exception raised when circuit breaker is open"""
    pass