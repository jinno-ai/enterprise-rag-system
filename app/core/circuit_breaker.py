"""
Circuit Breaker Pattern Implementation

This module implements the circuit breaker pattern to prevent cascading failures
when calling external services. It provides fault tolerance and graceful degradation.

States:
- CLOSED: Normal operation, requests pass through
- OPEN: Circuit is tripped, requests fail immediately
- HALF_OPEN: Testing if service has recovered
"""

import time
import asyncio
import inspect
from datetime import datetime
from enum import Enum
from typing import Callable, Optional, Any, Dict, TypeVar
from functools import wraps
from dataclasses import dataclass, field

from app.core.logging_config import get_logger
from app.core import metrics

logger = get_logger(__name__)

T = TypeVar('T')


class CircuitState(Enum):
    """Circuit breaker states"""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Circuit tripped, blocking requests
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker"""
    failure_threshold: int = 5        # Failures before tripping
    success_threshold: int = 2        # Successes to close circuit
    timeout: float = 60.0             # Seconds before attempting recovery
    half_open_max_calls: int = 3      # Max calls allowed in HALF_OPEN state
    expected_exception: Exception = Exception  # Exception type to catch

    def __post_init__(self):
        """Validate configuration"""
        if self.failure_threshold <= 0:
            raise ValueError("failure_threshold must be positive")
        if self.success_threshold <= 0:
            raise ValueError("success_threshold must be positive")
        if self.timeout <= 0:
            raise ValueError("timeout must be positive")
        if self.half_open_max_calls <= 0:
            raise ValueError("half_open_max_calls must be positive")


@dataclass
class CircuitBreakerStats:
    """Statistics for circuit breaker"""
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    rejected_calls: int = 0
    last_failure_time: Optional[datetime] = None
    last_success_time: Optional[datetime] = None
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    state_transitions: Dict[str, int] = field(default_factory=lambda: {
        "closed_to_open": 0,
        "open_to_half_open": 0,
        "half_open_to_closed": 0,
        "half_open_to_open": 0
    })


class CircuitBreakerError(Exception):
    """Raised when circuit is open"""
    pass


class CircuitBreakerOpenError(CircuitBreakerError):
    """Exception raised when circuit is open"""

    def __init__(self, message: str = "Circuit breaker is OPEN - rejecting request"):
        self.message = message
        super().__init__(self.message)


class CircuitBreaker:
    """
    Circuit breaker implementation for external service calls.

    Supports both synchronous and asynchronous protected functions, use as a
    decorator (``protect``) or context manager, and tracks detailed statistics.

    Usage:
        breaker = CircuitBreaker(
            name="openai_api",
            failure_threshold=5,
            timeout=60.0
        )

        @breaker.protect
        def external_api_call():
            # Your API call here
            pass

        result = breaker.call(external_api_call)
    """

    def __init__(
        self,
        name: Optional[str] = None,
        config: Optional[CircuitBreakerConfig] = None,
        *,
        service_name: Optional[str] = None,
        failure_threshold: int = 5,
        success_threshold: int = 2,
        timeout: float = 60.0,
        half_open_max_calls: int = 3
    ):
        """
        Initialize circuit breaker

        Args:
            name: Unique identifier for this circuit breaker (alias of service_name)
            config: Configuration options (individual params ignored when given)
            service_name: Name of the service being protected
            failure_threshold: Number of failures before tripping (default: 5)
            success_threshold: Successes needed to close circuit in HALF_OPEN (default: 2)
            timeout: Seconds before attempting recovery from OPEN state (default: 60.0)
            half_open_max_calls: Max calls allowed in HALF_OPEN state (default: 3)
        """
        resolved = name or service_name
        if not resolved:
            raise ValueError("Either name or service_name must be provided")
        self.name = resolved
        self.service_name = resolved

        if config is None:
            config = CircuitBreakerConfig(
                failure_threshold=failure_threshold,
                success_threshold=success_threshold,
                timeout=timeout,
                half_open_max_calls=half_open_max_calls
            )
        self.config = config

        # State
        self._state = CircuitState.CLOSED
        self._last_state_change = datetime.utcnow()
        self._half_open_call_count = 0
        self._opened_count = 0
        self._last_failure_time: Optional[float] = None

        # Statistics
        self.stats = CircuitBreakerStats()

        logger.info(
            f"Circuit breaker '{resolved}' initialized: "
            f"failure_threshold={self.config.failure_threshold}, "
            f"timeout={self.config.timeout}s"
        )

    @property
    def state(self) -> CircuitState:
        """Get current state (pure read; OPEN -> HALF_OPEN happens lazily on next call)"""
        return self._state

    @property
    def failure_count(self) -> int:
        """Get consecutive failure count"""
        return self.stats.consecutive_failures

    @property
    def opened_count(self) -> int:
        """Get number of times circuit has been opened"""
        return self._opened_count

    def _check_state_transition(self):
        """
        Check if automatic state transition is needed
        (OPEN -> HALF_OPEN after timeout)
        """
        if self._state == CircuitState.OPEN:
            time_since_change = (datetime.utcnow() - self._last_state_change).total_seconds()
            if time_since_change >= self.config.timeout:
                self._transition_to(CircuitState.HALF_OPEN)
                logger.info(
                    f"Circuit breaker '{self.service_name}' "
                    f"OPEN -> HALF_OPEN (after {time_since_change:.1f}s)"
                )

    def _transition_to(self, new_state: CircuitState):
        """Transition to new state"""
        old_state = self._state

        # Track state transitions
        transition_key = f"{old_state.value}_to_{new_state.value}"
        if transition_key in self.stats.state_transitions:
            self.stats.state_transitions[transition_key] += 1

        # Update state and timestamp
        self._state = new_state
        self._last_state_change = datetime.utcnow()

        if new_state == CircuitState.OPEN:
            self._opened_count += 1

        # Reset counters on certain transitions
        if new_state == CircuitState.HALF_OPEN:
            self._half_open_call_count = 0
            self.stats.consecutive_successes = 0

        metrics.circuit_breaker_state_change.labels(
            name=self.name,
            from_state=old_state.value,
            to_state=new_state.value
        ).inc()

    def _record_success(self):
        """Record a successful call"""
        self.stats.successful_calls += 1
        self.stats.total_calls += 1
        self.stats.last_success_time = datetime.utcnow()
        self.stats.consecutive_successes += 1
        self.stats.consecutive_failures = 0

    def _record_failure(self):
        """Record a failed call"""
        self.stats.failed_calls += 1
        self.stats.total_calls += 1
        self.stats.last_failure_time = datetime.utcnow()
        self.stats.consecutive_failures += 1
        self.stats.consecutive_successes = 0
        self._last_failure_time = time.time()

    def _record_rejection(self):
        """Record a rejected call (circuit is open)"""
        self.stats.rejected_calls += 1
        self.stats.total_calls += 1

    def _pre_call_check(self) -> CircuitState:
        """
        Validate state before executing a call.

        Returns:
            State at the time of the call

        Raises:
            CircuitBreakerOpenError: If the call is rejected
        """
        self._check_state_transition()  # may auto-transition OPEN -> HALF_OPEN
        current_state = self._state

        if current_state == CircuitState.OPEN:
            self._record_rejection()
            metrics.circuit_breaker_rejected.labels(name=self.name).inc()
            raise CircuitBreakerOpenError(
                f"Circuit breaker '{self.service_name}' is OPEN - "
                f"rejecting request. Last failure: "
                f"{self.stats.last_failure_time.strftime('%Y-%m-%d %H:%M:%S') if self.stats.last_failure_time else 'N/A'}"
            )

        if current_state == CircuitState.HALF_OPEN:
            if self._half_open_call_count >= self.config.half_open_max_calls:
                self._record_rejection()
                metrics.circuit_breaker_rejected.labels(name=self.name).inc()
                raise CircuitBreakerOpenError(
                    f"Circuit breaker '{self.service_name}' is HALF_OPEN - "
                    f"max test calls ({self.config.half_open_max_calls}) reached"
                )
            self._half_open_call_count += 1

        return current_state

    def call(self, func: Callable[..., Any], *args, **kwargs) -> Any:
        """
        Execute a function through the circuit breaker.

        Synchronous functions are executed and returned directly; for async
        functions a coroutine is returned that must be awaited (``await
        breaker.call(async_fn)``).

        Args:
            func: Function (sync or async) to execute
            *args: Positional arguments for the function
            **kwargs: Keyword arguments for the function

        Returns:
            Result of the function call

        Raises:
            CircuitBreakerOpenError: If circuit is OPEN
            Exception: If the function raises an exception
        """
        current_state = self._pre_call_check()

        try:
            result = func(*args, **kwargs)
        except self.config.expected_exception as e:
            self._handle_failure(current_state)
            metrics.circuit_breaker_failure.labels(
                name=self.name,
                exception_type=type(e).__name__
            ).inc()
            raise
        except Exception:
            self._handle_failure(current_state)
            raise

        if inspect.iscoroutine(result):
            return self._call_async(result, current_state)

        self._handle_success(current_state)
        return result

    async def _call_async(self, coroutine, state_at_call: CircuitState) -> Any:
        """Await a coroutine produced by ``call`` with breaker accounting"""
        try:
            value = await coroutine
        except self.config.expected_exception as e:
            self._handle_failure(state_at_call)
            metrics.circuit_breaker_failure.labels(
                name=self.name,
                exception_type=type(e).__name__
            ).inc()
            raise
        except Exception:
            self._handle_failure(state_at_call)
            raise

        self._handle_success(state_at_call)
        return value

    def call_sync(self, func: Callable[..., T], *args, **kwargs) -> T:
        """
        Execute synchronous function through circuit breaker

        Args:
            func: Synchronous function to execute
            *args: Function arguments
            **kwargs: Function keyword arguments

        Returns:
            Function result

        Raises:
            CircuitBreakerOpenError: If circuit is open
        """
        current_state = self._pre_call_check()

        try:
            result = func(*args, **kwargs)
        except self.config.expected_exception as e:
            self._handle_failure(current_state)
            metrics.circuit_breaker_failure.labels(
                name=self.name,
                exception_type=type(e).__name__
            ).inc()
            raise
        except Exception:
            self._handle_failure(current_state)
            raise

        self._handle_success(current_state)
        return result

    def _handle_success(self, state_at_call: CircuitState):
        """Handle a successful function call"""
        self._record_success()

        if state_at_call == CircuitState.HALF_OPEN:
            # Check if we should close the circuit
            if self.stats.consecutive_successes >= self.config.success_threshold:
                self._transition_to(CircuitState.CLOSED)
                logger.info(
                    f"Circuit breaker '{self.service_name}' "
                    f"HALF_OPEN -> CLOSED "
                    f"(after {self.stats.consecutive_successes} consecutive successes)"
                )

    def _handle_failure(self, state_at_call: CircuitState):
        """Handle a failed function call"""
        self._record_failure()

        if state_at_call == CircuitState.CLOSED:
            # Check if we should open the circuit
            if self.stats.consecutive_failures >= self.config.failure_threshold:
                self._transition_to(CircuitState.OPEN)
                logger.warning(
                    f"Circuit breaker '{self.service_name}' "
                    f"CLOSED -> OPEN "
                    f"(after {self.stats.consecutive_failures} consecutive failures)"
                )

        elif state_at_call == CircuitState.HALF_OPEN:
            # Any failure in HALF_OPEN reopens the circuit
            self._transition_to(CircuitState.OPEN)
            logger.warning(
                f"Circuit breaker '{self.service_name}' "
                f"HALF_OPEN -> OPEN (failure during recovery test)"
            )

    def protect(self, func: Optional[Callable[..., Any]] = None):
        """
        Decorator to protect a function with the circuit breaker

        Can be used with or without arguments:
        ```python
        @circuit_breaker.protect
        def my_function():
            pass

        @circuit_breaker.protect()
        def my_function_with_args():
            pass
        ```
        """
        def decorator(f: Callable[..., Any]) -> Callable[..., Any]:
            @wraps(f)
            def wrapper(*args, **kwargs):
                return self.call(f, *args, **kwargs)
            return wrapper

        if func is not None:
            # Called as @circuit_breaker.protect
            return decorator(func)
        else:
            # Called as @circuit_breaker.protect()
            return decorator

    def __enter__(self):
        """Context manager entry - raise if circuit is open"""
        self._check_state_transition()  # may auto-transition OPEN -> HALF_OPEN
        current_state = self._state

        if current_state == CircuitState.OPEN:
            self._record_rejection()
            raise CircuitBreakerOpenError(
                f"Circuit breaker '{self.service_name}' is OPEN"
            )

        if current_state == CircuitState.HALF_OPEN:
            if self._half_open_call_count >= self.config.half_open_max_calls:
                self._record_rejection()
                raise CircuitBreakerOpenError(
                    f"Circuit breaker '{self.service_name}' HALF_OPEN max calls reached"
                )
            self._half_open_call_count += 1

        self._state_at_context_entry = current_state
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - record success/failure"""
        if exc_type is None:
            self._handle_success(self._state_at_context_entry)
        else:
            self._handle_failure(self._state_at_context_entry)
        return False  # Don't suppress exceptions

    def reset(self):
        """Manually reset circuit breaker to closed state"""
        self._state = CircuitState.CLOSED
        self._last_state_change = datetime.utcnow()
        self._half_open_call_count = 0
        self._last_failure_time = None
        self.stats = CircuitBreakerStats()
        logger.info(f"Circuit breaker '{self.service_name}' manually reset")

    def get_state_info(self) -> Dict[str, Any]:
        """
        Get detailed state information

        Returns:
            Dictionary with current state and statistics
        """
        return {
            "service_name": self.service_name,
            "state": self.state.value,
            "last_state_change": self._last_state_change.isoformat(),
            "stats": {
                "total_calls": self.stats.total_calls,
                "successful_calls": self.stats.successful_calls,
                "failed_calls": self.stats.failed_calls,
                "rejected_calls": self.stats.rejected_calls,
                "consecutive_failures": self.stats.consecutive_failures,
                "consecutive_successes": self.stats.consecutive_successes,
                "success_rate": (
                    self.stats.successful_calls / self.stats.total_calls
                    if self.stats.total_calls > 0
                    else 0.0
                )
            },
            "config": {
                "failure_threshold": self.config.failure_threshold,
                "success_threshold": self.config.success_threshold,
                "timeout": self.config.timeout,
                "half_open_max_calls": self.config.half_open_max_calls
            }
        }

    def __repr__(self) -> str:
        return (
            f"CircuitBreaker(name='{self.name}', "
            f"state={self._state.value}, "
            f"failures={self.stats.consecutive_failures}/{self.config.failure_threshold})"
        )


class CircuitBreakerRegistry:
    """
    Registry for managing multiple circuit breakers

    Example:
        ```python
        registry = CircuitBreakerRegistry()

        # Get or create circuit breaker for a service
        cb = registry.get_or_create("openai_api", failure_threshold=5)
        ```
    """

    def __init__(self):
        self._circuit_breakers: Dict[str, CircuitBreaker] = {}

    def get_or_create(
        self,
        service_name: str,
        **kwargs
    ) -> CircuitBreaker:
        """
        Get existing circuit breaker or create new one

        Args:
            service_name: Name of the service
            **kwargs: Configuration for new circuit breaker if needed

        Returns:
            CircuitBreaker instance
        """
        if service_name not in self._circuit_breakers:
            self._circuit_breakers[service_name] = CircuitBreaker(
                name=service_name,
                **kwargs
            )
        return self._circuit_breakers[service_name]

    def get_all_states(self) -> Dict[str, Dict[str, Any]]:
        """Get state information for all circuit breakers"""
        return {
            name: cb.get_state_info()
            for name, cb in self._circuit_breakers.items()
        }

    def reset_all(self):
        """Reset all circuit breakers"""
        for cb in self._circuit_breakers.values():
            cb.reset()


# Global registry instance
_global_registry = CircuitBreakerRegistry()


def get_circuit_breaker(
    service_name: str,
    **kwargs
) -> CircuitBreaker:
    """
    Get or create a circuit breaker from the global registry

    Args:
        service_name: Name of the service
        **kwargs: Configuration for new circuit breaker if needed

    Returns:
        CircuitBreaker instance
    """
    return _global_registry.get_or_create(service_name, **kwargs)


def circuit_breaker(
    name: str,
    failure_threshold: int = 5,
    success_threshold: int = 2,
    timeout: float = 60.0,
    expected_exception: Exception = Exception
):
    """
    Decorator for applying circuit breaker to async functions

    Args:
        name: Circuit breaker name
        failure_threshold: Failures before tripping
        success_threshold: Successes to close circuit
        timeout: Seconds before attempting recovery
        expected_exception: Exception type to catch

    Returns:
        Decorated function

    Example:
        @circuit_breaker(name="api_call", failure_threshold=3)
        async def my_api_call():
            return await external_service.call()
    """
    # Global registry of circuit breakers
    _registry = {}

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        # Get or create circuit breaker
        if name not in _registry:
            config = CircuitBreakerConfig(
                failure_threshold=failure_threshold,
                success_threshold=success_threshold,
                timeout=timeout,
                expected_exception=expected_exception
            )
            _registry[name] = CircuitBreaker(name, config)

        breaker = _registry[name]

        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await breaker.call(func, *args, **kwargs)

        # Attach circuit breaker to function for access
        wrapper.circuit_breaker = breaker
        return wrapper

    return decorator
