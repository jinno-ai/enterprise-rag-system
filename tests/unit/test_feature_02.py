"""
Unit tests for Circuit Breaker Pattern (Feature 02)

Tests the circuit breaker implementation for preventing cascading failures
when calling external APIs (LLM, vector database, etc.).

Test coverage includes:
- State transitions (CLOSED, OPEN, HALF_OPEN)
- Success and failure handling
- Configuration validation
- Decorator and context manager usage
- Statistics tracking
- Thread safety basics
"""

import pytest
import time
from datetime import datetime
from unittest.mock import Mock, patch

from app.core.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitState,
    CircuitBreakerOpenError,
    CircuitBreakerRegistry,
    get_circuit_breaker,
)


class TestCircuitBreakerConfig:
    """Test CircuitBreakerConfig validation"""

    def test_valid_config(self):
        """Test creating a valid configuration"""
        config = CircuitBreakerConfig(
            failure_threshold=5,
            success_threshold=2,
            timeout=60.0,
            half_open_max_calls=3
        )

        assert config.failure_threshold == 5
        assert config.success_threshold == 2
        assert config.timeout == 60.0
        assert config.half_open_max_calls == 3

    def test_invalid_failure_threshold(self):
        """Test that invalid failure_threshold raises ValueError"""
        with pytest.raises(ValueError, match="failure_threshold must be positive"):
            CircuitBreakerConfig(failure_threshold=0)

        with pytest.raises(ValueError, match="failure_threshold must be positive"):
            CircuitBreakerConfig(failure_threshold=-1)

    def test_invalid_success_threshold(self):
        """Test that invalid success_threshold raises ValueError"""
        with pytest.raises(ValueError, match="success_threshold must be positive"):
            CircuitBreakerConfig(success_threshold=0)

    def test_invalid_timeout(self):
        """Test that invalid timeout raises ValueError"""
        with pytest.raises(ValueError, match="timeout must be positive"):
            CircuitBreakerConfig(timeout=0)

    def test_invalid_half_open_max_calls(self):
        """Test that invalid half_open_max_calls raises ValueError"""
        with pytest.raises(ValueError, match="half_open_max_calls must be positive"):
            CircuitBreakerConfig(half_open_max_calls=0)


class TestCircuitBreakerInitialization:
    """Test CircuitBreaker initialization"""

    def test_initialization_with_defaults(self):
        """Test creating circuit breaker with default values"""
        cb = CircuitBreaker(service_name="test_service")

        assert cb.service_name == "test_service"
        assert cb.state == CircuitState.CLOSED
        assert cb.config.failure_threshold == 5
        assert cb.config.success_threshold == 2
        assert cb.config.timeout == 60.0
        assert cb.config.half_open_max_calls == 3

    def test_initialization_with_custom_config(self):
        """Test creating circuit breaker with custom configuration"""
        config = CircuitBreakerConfig(
            failure_threshold=10,
            success_threshold=3,
            timeout=120.0,
            half_open_max_calls=5
        )
        cb = CircuitBreaker(service_name="test_service", config=config)

        assert cb.config.failure_threshold == 10
        assert cb.config.success_threshold == 3
        assert cb.config.timeout == 120.0
        assert cb.config.half_open_max_calls == 5

    def test_initialization_with_keyword_args(self):
        """Test creating circuit breaker with keyword arguments"""
        cb = CircuitBreaker(
            service_name="test_service",
            failure_threshold=8,
            success_threshold=4,
            timeout=90.0,
            half_open_max_calls=6
        )

        assert cb.config.failure_threshold == 8
        assert cb.config.success_threshold == 4
        assert cb.config.timeout == 90.0
        assert cb.config.half_open_max_calls == 6

    def test_initial_statistics(self):
        """Test that statistics are initialized correctly"""
        cb = CircuitBreaker(service_name="test_service")

        assert cb.stats.total_calls == 0
        assert cb.stats.successful_calls == 0
        assert cb.stats.failed_calls == 0
        assert cb.stats.rejected_calls == 0
        assert cb.stats.consecutive_failures == 0
        assert cb.stats.consecutive_successes == 0
        assert cb.stats.last_failure_time is None
        assert cb.stats.last_success_time is None


class TestCircuitBreakerStateTransitions:
    """Test circuit breaker state transitions"""

    def test_closed_state_on_success(self):
        """Test that circuit stays CLOSED on successful calls"""
        cb = CircuitBreaker(service_name="test_service", failure_threshold=3)

        def successful_call():
            return "success"

        # Successful calls should keep circuit closed
        for _ in range(5):
            result = cb.call(successful_call)
            assert result == "success"
            assert cb.state == CircuitState.CLOSED

    def test_closed_to_open_on_failures(self):
        """Test transition from CLOSED to OPEN after failure threshold"""
        cb = CircuitBreaker(
            service_name="test_service",
            failure_threshold=3,
            success_threshold=2
        )

        def failing_call():
            raise Exception("Service error")

        # First two failures should not trip the circuit
        for i in range(2):
            with pytest.raises(Exception):
                cb.call(failing_call)
            assert cb.state == CircuitState.CLOSED
            assert cb.stats.consecutive_failures == i + 1

        # Third failure should trip the circuit
        with pytest.raises(Exception):
            cb.call(failing_call)

        assert cb.state == CircuitState.OPEN
        assert cb.stats.consecutive_failures == 3

    def test_open_to_half_open_after_timeout(self):
        """Test transition from OPEN to HALF_OPEN after timeout"""
        cb = CircuitBreaker(
            service_name="test_service",
            failure_threshold=2,
            timeout=1.0  # 1 second timeout
        )

        def failing_call():
            raise Exception("Service error")

        # Trip the circuit
        with pytest.raises(Exception):
            cb.call(failing_call)
        with pytest.raises(Exception):
            cb.call(failing_call)

        assert cb.state == CircuitState.OPEN

        # Wait for timeout
        time.sleep(1.1)

        # Check state should transition to HALF_OPEN
        current_state = cb.state
        assert current_state == CircuitState.HALF_OPEN

    def test_half_open_to_closed_on_successes(self):
        """Test transition from HALF_OPEN to CLOSED after success threshold"""
        cb = CircuitBreaker(
            service_name="test_service",
            failure_threshold=2,
            success_threshold=2,
            timeout=1.0
        )

        def failing_call():
            raise Exception("Service error")

        def successful_call():
            return "success"

        # Trip the circuit
        with pytest.raises(Exception):
            cb.call(failing_call)
        with pytest.raises(Exception):
            cb.call(failing_call)

        assert cb.state == CircuitState.OPEN

        # Wait for timeout
        time.sleep(1.1)

        # Successful calls should close the circuit
        cb.call(successful_call)
        assert cb.state == CircuitState.HALF_OPEN

        cb.call(successful_call)
        assert cb.state == CircuitState.CLOSED

    def test_half_open_to_open_on_failure(self):
        """Test transition from HALF_OPEN to OPEN on any failure"""
        cb = CircuitBreaker(
            service_name="test_service",
            failure_threshold=2,
            success_threshold=3,
            timeout=1.0
        )

        def failing_call():
            raise Exception("Service error")

        def successful_call():
            return "success"

        # Trip the circuit
        with pytest.raises(Exception):
            cb.call(failing_call)
        with pytest.raises(Exception):
            cb.call(failing_call)

        # Wait for timeout
        time.sleep(1.1)

        # One success
        cb.call(successful_call)
        assert cb.state == CircuitState.HALF_OPEN

        # Failure should reopen circuit
        with pytest.raises(Exception):
            cb.call(failing_call)

        assert cb.state == CircuitState.OPEN


class TestCircuitBreakerOpenBehavior:
    """Test circuit breaker behavior when OPEN"""

    def test_open_rejects_calls(self):
        """Test that OPEN circuit rejects calls immediately"""
        cb = CircuitBreaker(
            service_name="test_service",
            failure_threshold=2
        )

        def failing_call():
            raise Exception("Service error")

        # Trip the circuit
        with pytest.raises(Exception):
            cb.call(failing_call)
        with pytest.raises(Exception):
            cb.call(failing_call)

        assert cb.state == CircuitState.OPEN

        # Should reject immediately without calling the function
        with pytest.raises(CircuitBreakerOpenError):
            cb.call(failing_call)

        assert cb.stats.rejected_calls > 0

    def test_open_error_message(self):
        """Test that OPEN error contains useful information"""
        cb = CircuitBreaker(
            service_name="test_service",
            failure_threshold=2
        )

        def failing_call():
            raise Exception("Service error")

        # Trip the circuit
        with pytest.raises(Exception):
            cb.call(failing_call)
        with pytest.raises(Exception):
            cb.call(failing_call)

        # Check error message
        with pytest.raises(CircuitBreakerOpenError) as exc_info:
            cb.call(lambda: "test")

        assert "test_service" in str(exc_info.value)
        assert "OPEN" in str(exc_info.value)


class TestCircuitBreakerHalfOpenBehavior:
    """Test circuit breaker behavior in HALF_OPEN state"""

    def test_half_open_limits_calls(self):
        """Test that HALF_OPEN limits the number of test calls"""
        cb = CircuitBreaker(
            service_name="test_service",
            failure_threshold=2,
            success_threshold=5,  # High threshold so we don't close circuit
            half_open_max_calls=2,
            timeout=1.0
        )

        def failing_call():
            raise Exception("Service error")

        # Trip the circuit
        with pytest.raises(Exception):
            cb.call(failing_call)
        with pytest.raises(Exception):
            cb.call(failing_call)

        # Wait for timeout
        time.sleep(1.1)

        def slow_call():
            time.sleep(0.1)
            return "success"

        # Access state to trigger transition to HALF_OPEN
        current_state = cb.state
        assert current_state == CircuitState.HALF_OPEN

        # Should allow max_calls (2 calls)
        result1 = cb.call(slow_call)
        assert result1 == "success"

        result2 = cb.call(slow_call)
        assert result2 == "success"

        # Third call should be rejected (exceeded half_open_max_calls)
        with pytest.raises(CircuitBreakerOpenError, match="max test calls"):
            cb.call(slow_call)


class TestCircuitBreakerDecorator:
    """Test circuit breaker decorator usage"""

    def test_protect_decorator_without_args(self):
        """Test using @circuit_breaker.protect decorator"""
        cb = CircuitBreaker(
            service_name="test_service",
            failure_threshold=2  # Trip after 2 failures
        )

        call_count = {"count": 0}

        @cb.protect
        def my_function():
            call_count["count"] += 1
            raise Exception("Error")  # Always fail

        # First two calls fail and trip the circuit
        with pytest.raises(Exception, match="Error"):
            my_function()

        assert call_count["count"] == 1
        assert cb.state == CircuitState.CLOSED  # Still closed after 1 failure

        with pytest.raises(Exception, match="Error"):
            my_function()

        assert call_count["count"] == 2
        assert cb.state == CircuitState.OPEN  # Open after 2 failures

        # Third call is blocked by circuit breaker
        with pytest.raises(CircuitBreakerOpenError):
            my_function()

        # Function should only be called twice (third call rejected by circuit breaker)
        assert call_count["count"] == 2

    def test_protect_decorator_with_args(self):
        """Test using @circuit_breaker.protect() decorator with arguments"""
        cb = CircuitBreaker(
            service_name="test_service",
            failure_threshold=2
        )

        @cb.protect()
        def my_function(x, y):
            return x + y

        result = my_function(1, 2)
        assert result == 3


class TestCircuitBreakerContextManager:
    """Test circuit breaker context manager usage"""

    def test_context_manager_success(self):
        """Test using circuit breaker as context manager on success"""
        cb = CircuitBreaker(
            service_name="test_service",
            failure_threshold=3
        )

        with cb:
            result = 1 + 1

        assert result == 2
        assert cb.stats.successful_calls == 1
        assert cb.stats.consecutive_successes == 1

    def test_context_manager_failure(self):
        """Test using circuit breaker as context manager on failure"""
        cb = CircuitBreaker(
            service_name="test_service",
            failure_threshold=2
        )

        # First failure
        with pytest.raises(ValueError):
            with cb:
                raise ValueError("Error")

        assert cb.stats.failed_calls == 1
        assert cb.state == CircuitState.CLOSED

        # Second failure - should trip circuit
        with pytest.raises(ValueError):
            with cb:
                raise ValueError("Error")

        assert cb.stats.failed_calls == 2
        assert cb.state == CircuitState.OPEN

    def test_context_manager_open_rejects(self):
        """Test that context manager raises when circuit is open"""
        cb = CircuitBreaker(
            service_name="test_service",
            failure_threshold=2
        )

        def failing_operation():
            raise Exception("Error")

        # Trip the circuit
        with pytest.raises(Exception):
            with cb:
                failing_operation()

        with pytest.raises(Exception):
            with cb:
                failing_operation()

        # Should raise immediately without entering context
        with pytest.raises(CircuitBreakerOpenError):
            with cb:
                assert False, "Should not reach here"


class TestCircuitBreakerStatistics:
    """Test circuit breaker statistics tracking"""

    def test_statistics_tracking(self):
        """Test that statistics are tracked correctly"""
        cb = CircuitBreaker(service_name="test_service", failure_threshold=5)

        def successful_call():
            return "success"

        def failing_call():
            raise Exception("Error")

        # 3 successful calls
        for _ in range(3):
            cb.call(successful_call)

        # 2 failed calls
        for _ in range(2):
            with pytest.raises(Exception):
                cb.call(failing_call)

        assert cb.stats.total_calls == 5
        assert cb.stats.successful_calls == 3
        assert cb.stats.failed_calls == 2
        assert cb.stats.consecutive_failures == 2
        assert cb.stats.last_success_time is not None
        assert cb.stats.last_failure_time is not None

    def test_consecutive_counters_reset(self):
        """Test that consecutive counters reset appropriately"""
        cb = CircuitBreaker(
            service_name="test_service",
            failure_threshold=3
        )

        def successful_call():
            return "success"

        def failing_call():
            raise Exception("Error")

        # Failure then success
        with pytest.raises(Exception):
            cb.call(failing_call)

        assert cb.stats.consecutive_failures == 1

        cb.call(successful_call)

        assert cb.stats.consecutive_failures == 0
        assert cb.stats.consecutive_successes == 1

        # Success then failure
        with pytest.raises(Exception):
            cb.call(failing_call)

        assert cb.stats.consecutive_successes == 0
        assert cb.stats.consecutive_failures == 1

    def test_state_transition_tracking(self):
        """Test that state transitions are tracked"""
        cb = CircuitBreaker(
            service_name="test_service",
            failure_threshold=2,
            timeout=1.0
        )

        def failing_call():
            raise Exception("Error")

        # Trip circuit (CLOSED -> OPEN)
        with pytest.raises(Exception):
            cb.call(failing_call)
        with pytest.raises(Exception):
            cb.call(failing_call)

        assert cb.stats.state_transitions["closed_to_open"] == 1

        # Wait for timeout (OPEN -> HALF_OPEN)
        time.sleep(1.1)
        _ = cb.state  # Trigger state check
        assert cb.stats.state_transitions["open_to_half_open"] == 1


class TestCircuitBreakerReset:
    """Test circuit breaker reset functionality"""

    def test_reset_to_initial_state(self):
        """Test resetting circuit breaker to initial state"""
        cb = CircuitBreaker(
            service_name="test_service",
            failure_threshold=3
        )

        def failing_call():
            raise Exception("Error")

        # Trip the circuit
        for _ in range(3):
            with pytest.raises(Exception):
                cb.call(failing_call)

        assert cb.state == CircuitState.OPEN
        assert cb.stats.total_calls == 3

        # Reset
        cb.reset()

        assert cb.state == CircuitState.CLOSED
        assert cb.stats.total_calls == 0
        assert cb.stats.consecutive_failures == 0


class TestCircuitBreakerGetStateInfo:
    """Test circuit breaker state information retrieval"""

    def test_get_state_info(self):
        """Test getting detailed state information"""
        cb = CircuitBreaker(
            service_name="test_service",
            failure_threshold=3,
            success_threshold=2
        )

        def successful_call():
            return "success"

        cb.call(successful_call)

        state_info = cb.get_state_info()

        assert state_info["service_name"] == "test_service"
        assert state_info["state"] == "closed"
        assert "last_state_change" in state_info
        assert state_info["stats"]["total_calls"] == 1
        assert state_info["stats"]["successful_calls"] == 1
        assert state_info["config"]["failure_threshold"] == 3
        assert state_info["config"]["success_threshold"] == 2


class TestCircuitBreakerRegistry:
    """Test circuit breaker registry functionality"""

    def test_get_or_create(self):
        """Test getting or creating circuit breakers from registry"""
        registry = CircuitBreakerRegistry()

        # Create new circuit breaker
        cb1 = registry.get_or_create("service1", failure_threshold=5)
        assert cb1.service_name == "service1"
        assert cb1.config.failure_threshold == 5

        # Get existing circuit breaker (should return same instance)
        cb2 = registry.get_or_create("service1", failure_threshold=10)
        assert cb1 is cb2  # Same instance
        assert cb1.config.failure_threshold == 5  # Original config preserved

        # Create different circuit breaker
        cb3 = registry.get_or_create("service2", failure_threshold=3)
        assert cb3.service_name == "service2"
        assert cb3 is not cb1

    def test_get_all_states(self):
        """Test getting all circuit breaker states"""
        registry = CircuitBreakerRegistry()

        cb1 = registry.get_or_create("service1", failure_threshold=5)
        cb2 = registry.get_or_create("service2", failure_threshold=3)

        states = registry.get_all_states()

        assert "service1" in states
        assert "service2" in states
        assert states["service1"]["state"] == "closed"
        assert states["service2"]["state"] == "closed"

    def test_reset_all(self):
        """Test resetting all circuit breakers"""
        registry = CircuitBreakerRegistry()

        cb1 = registry.get_or_create("service1", failure_threshold=2)
        cb2 = registry.get_or_create("service2", failure_threshold=2)

        def failing_call():
            raise Exception("Error")

        # Trip both circuits
        for cb in [cb1, cb2]:
            for _ in range(2):
                with pytest.raises(Exception):
                    cb.call(failing_call)

        assert cb1.state == CircuitState.OPEN
        assert cb2.state == CircuitState.OPEN

        # Reset all
        registry.reset_all()

        assert cb1.state == CircuitState.CLOSED
        assert cb2.state == CircuitState.CLOSED


class TestGlobalCircuitBreaker:
    """Test global circuit breaker function"""

    def test_get_circuit_breaker(self):
        """Test getting circuit breaker from global registry"""
        cb1 = get_circuit_breaker("global_service", failure_threshold=7)
        cb2 = get_circuit_breaker("global_service")

        assert cb1 is cb2
        assert cb1.config.failure_threshold == 7

    def test_isolated_global_instances(self):
        """Test that different service names create different instances"""
        cb1 = get_circuit_breaker("service_a")
        cb2 = get_circuit_breaker("service_b")

        assert cb1 is not cb2


class TestCircuitBreakerEdgeCases:
    """Test edge cases and boundary conditions"""

    def test_immediate_timeout_transition(self):
        """Test state transition immediately after timeout"""
        cb = CircuitBreaker(
            service_name="test_service",
            failure_threshold=2,
            timeout=0.5
        )

        def failing_call():
            raise Exception("Error")

        # Trip circuit
        with pytest.raises(Exception):
            cb.call(failing_call)
        with pytest.raises(Exception):
            cb.call(failing_call)

        assert cb.state == CircuitState.OPEN

        # Wait just past timeout
        time.sleep(0.6)

        # Should transition to HALF_OPEN
        assert cb.state == CircuitState.HALF_OPEN

    def test_zero_consecutive_after_reset(self):
        """Test that consecutive counters are zero after reset"""
        cb = CircuitBreaker(
            service_name="test_service",
            failure_threshold=3
        )

        def failing_call():
            raise Exception("Error")

        # Generate some failures
        for _ in range(2):
            with pytest.raises(Exception):
                cb.call(failing_call)

        assert cb.stats.consecutive_failures == 2

        # Reset
        cb.reset()

        assert cb.stats.consecutive_failures == 0
        assert cb.stats.consecutive_successes == 0

    def test_success_rate_calculation(self):
        """Test success rate calculation in state info"""
        cb = CircuitBreaker(service_name="test_service")

        def successful_call():
            return "success"

        def failing_call():
            raise Exception("Error")

        # 7 success, 3 failures = 70% success rate
        for _ in range(7):
            cb.call(successful_call)

        for _ in range(3):
            with pytest.raises(Exception):
                cb.call(failing_call)

        state_info = cb.get_state_info()
        success_rate = state_info["stats"]["success_rate"]

        assert abs(success_rate - 0.7) < 0.01  # Allow small floating point error

    def test_no_calls_success_rate(self):
        """Test success rate when no calls have been made"""
        cb = CircuitBreaker(service_name="test_service")

        state_info = cb.get_state_info()
        assert state_info["stats"]["success_rate"] == 0.0
