# app/utils/health_check.py

import logging
import threading
import time
from datetime import datetime, timedelta
from functools import wraps
from sqlalchemy import text
from app import db
from app.utils.circuit_breaker import CircuitBreaker

logger = logging.getLogger(__name__)

class HealthCheck:
    """System health monitor with self-healing capabilities"""
    
    # Health statuses
    STATUS_HEALTHY = "healthy"
    STATUS_DEGRADED = "degraded"
    STATUS_UNHEALTHY = "unhealthy"
    
    # Singleton instance
    _instance = None
    _lock = threading.Lock()
    
    @classmethod
    def get_instance(cls):
        """Get or create the singleton instance"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance
    
    def __init__(self):
        """Initialize the health check system"""
        # Health status registry
        self.services = {
            'coinbase_api': {
                'status': self.STATUS_HEALTHY,
                'last_check': datetime.now(),
                'failures': 0,
                'max_failures': 5,
                'recovery_attempts': 0
            },
            'database': {
                'status': self.STATUS_HEALTHY, 
                'last_check': datetime.now(),
                'failures': 0,
                'max_failures': 3,
                'recovery_attempts': 0
            },
            'webhook_processor': {
                'status': self.STATUS_HEALTHY,
                'last_check': datetime.now(),
                'failures': 0,
                'max_failures': 3,
                'recovery_attempts': 0
            }
        }
        
        # Initialize but don't start
        self.check_interval = 60  # seconds
        self.shutdown_flag = threading.Event()
        self.health_thread = None  # Don't create thread yet
        
    def start(self, app=None):
        """Start the health check background thread with app context"""
        if self.health_thread is None or not self.health_thread.is_alive():
            self.app = app  # Store app reference
            self.health_thread = threading.Thread(target=self._health_check_loop, daemon=True)
            self.health_thread.start()
            logger.info("Health check system started")
    
    def _health_check_loop(self):
        """Background thread that performs periodic health checks"""
        while not self.shutdown_flag.is_set():
            try:
                # Use app context if available
                if hasattr(self, 'app') and self.app:
                    with self.app.app_context():
                        self.check_database_health()
                        self.check_coinbase_api_health()
                else:
                    # Skip database checks if no app context
                    self.check_coinbase_api_health()
                
                # Sleep until next check interval
                self.shutdown_flag.wait(self.check_interval)
            except Exception as e:
                logger.error(f"Error in health check loop: {str(e)}")
                # Don't crash the thread, wait and try again
                time.sleep(10)
    
    def shutdown(self):
        """Shut down the health check system"""
        self.shutdown_flag.set()
        self.health_thread.join(timeout=5)
    
    def check_database_health(self):
        """Check database connectivity and performance"""
        try:
            # Import SQLAlchemy text function
            from sqlalchemy import text
            
            # Simple query to test database connectivity
            start_time = time.time()
            db.session.execute(text("SELECT 1"))
            response_time = time.time() - start_time
            
            # Update service status
            service = self.services['database']
            service['last_check'] = datetime.now()
            
            # Check response time
            if response_time > 1.0:  # More than 1 second is concerning
                service['failures'] += 1
                if service['failures'] >= service['max_failures']:
                    service['status'] = self.STATUS_DEGRADED
                    logger.warning("Database health check: DEGRADED (slow response)")
            else:
                # Reset failures count on success
                service['failures'] = 0
                service['status'] = self.STATUS_HEALTHY
                service['recovery_attempts'] = 0
                
        except Exception as e:
            logger.error(f"Database health check failed: {str(e)}")
            
            # Update service status
            service = self.services['database']
            service['last_check'] = datetime.now()
            service['failures'] += 1
            
            if service['failures'] >= service['max_failures']:
                service['status'] = self.STATUS_UNHEALTHY
                logger.critical("Database health check: UNHEALTHY")
                
                # Try recovery
                if service['recovery_attempts'] < 3:
                    self._attempt_database_recovery()
                    service['recovery_attempts'] += 1
    
    def check_coinbase_api_health(self):
        """Check Coinbase API connectivity"""
        # This would use a simple API call to test connectivity
        # For demonstration purposes, we'll just check the circuit breaker
        cb = CircuitBreaker.get_or_create('coinbase_api')
        
        service = self.services['coinbase_api']
        service['last_check'] = datetime.now()
        
        if cb.state == cb.OPEN:
            service['status'] = self.STATUS_UNHEALTHY
            logger.warning("Coinbase API health check: UNHEALTHY (circuit breaker open)")
        elif cb.state == cb.HALF_OPEN:
            service['status'] = self.STATUS_DEGRADED
            logger.info("Coinbase API health check: DEGRADED (circuit breaker half-open)")
        else:
            service['status'] = self.STATUS_HEALTHY
            service['failures'] = 0
            service['recovery_attempts'] = 0
    
    def _attempt_database_recovery(self):
        """Try to recover database connection"""
        logger.info("Attempting database recovery...")
        try:
            # Import SQLAlchemy text function
            from sqlalchemy import text
            
            # Close and reopen connection
            db.session.remove()
            # Test if it worked
            db.session.execute(text("SELECT 1"))
            logger.info("Database recovery successful")
            
            # Update service status
            service = self.services['database']
            service['status'] = self.STATUS_DEGRADED  # Downgrade from UNHEALTHY
            service['failures'] = service['max_failures'] - 1  # Reduce failure count
            
        except Exception as e:
            logger.error(f"Database recovery failed: {str(e)}")
    
    def get_system_health(self):
        """Get overall system health status"""
        # If any critical service is unhealthy, the system is unhealthy
        if any(s['status'] == self.STATUS_UNHEALTHY for s in self.services.values()):
            return self.STATUS_UNHEALTHY
            
        # If any service is degraded, the system is degraded
        elif any(s['status'] == self.STATUS_DEGRADED for s in self.services.values()):
            return self.STATUS_DEGRADED
            
        # Otherwise, the system is healthy
        return self.STATUS_HEALTHY
    
    def get_service_status(self, service_name):
        """Get the status of a specific service"""
        if service_name in self.services:
            return self.services[service_name]['status']
        return None


def health_check_required(service_name):
    """
    Decorator to check service health before executing a function
    
    Usage:
        @health_check_required('coinbase_api')
        def call_coinbase():
            # Function implementation
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            health_check = HealthCheck.get_instance()
            service_status = health_check.get_service_status(service_name)
            
            if service_status == HealthCheck.STATUS_UNHEALTHY:
                logger.error(f"Service {service_name} is unhealthy, cannot execute {func.__name__}")
                raise ServiceUnhealthyError(f"Service {service_name} is currently unavailable")
                
            # Execute function even if service is degraded, but log a warning
            if service_status == HealthCheck.STATUS_DEGRADED:
                logger.warning(f"Service {service_name} is degraded, executing {func.__name__} anyway")
                
            return func(*args, **kwargs)
        return wrapper
    return decorator


class ServiceUnhealthyError(Exception):
    """Exception raised when a required service is unhealthy"""
    pass