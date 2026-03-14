"""
Performance Monitoring Module for Query Execution

This module provides comprehensive performance tracking for query execution,
including metrics collection, timing, and monitoring capabilities.
"""

import time
import logging
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from datetime import datetime
from collections import deque
import threading

logger = logging.getLogger(__name__)


@dataclass
class QueryMetrics:
    """Individual query performance metrics"""

    query_id: str
    query: str  # Truncated for privacy
    start_time: datetime
    end_time: Optional[datetime] = None
    latency_ms: float = 0.0
    tokens_used: int = 0
    sources_count: int = 0
    confidence: float = 0.0
    status: str = "in_progress"  # in_progress, success, error
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to dictionary"""
        return {
            "query_id": self.query_id,
            "query": self.query[:100] if len(self.query) > 100 else self.query,  # Truncate for privacy
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "latency_ms": self.latency_ms,
            "tokens_used": self.tokens_used,
            "sources_count": self.sources_count,
            "confidence": self.confidence,
            "status": self.status,
            "error_message": self.error_message,
            "metadata": self.metadata,
        }


class PerformanceMonitor:
    """
    Performance monitor for tracking query execution metrics.

    Features:
    - Track query latency, tokens used, and other metrics
    - Maintain sliding window of recent queries
    - Calculate aggregate statistics (avg, p50, p95, p99)
    - Thread-safe for concurrent query execution
    """

    def __init__(self, max_history: int = 1000):
        """
        Initialize performance monitor

        Args:
            max_history: Maximum number of queries to keep in history
        """
        self.max_history = max_history
        self._query_history: deque = deque(maxlen=max_history)
        self._active_queries: Dict[str, QueryMetrics] = {}
        self._lock = threading.RLock()
        logger.info(f"Performance monitor initialized with max_history={max_history}")

    def start_query(self, query_id: str, query: str, metadata: Optional[Dict[str, Any]] = None) -> QueryMetrics:
        """
        Start tracking a query

        Args:
            query_id: Unique identifier for the query
            query: Query text (will be truncated for storage)
            metadata: Optional metadata to attach to the query

        Returns:
            QueryMetrics object for this query
        """
        with self._lock:
            if query_id in self._active_queries:
                logger.warning(f"Query {query_id} already being tracked. Overwriting.")

            metrics = QueryMetrics(
                query_id=query_id,
                query=query,
                start_time=datetime.utcnow(),
                metadata=metadata or {}
            )

            self._active_queries[query_id] = metrics
            logger.debug(f"Started tracking query {query_id}")

            return metrics

    def end_query(
        self,
        query_id: str,
        latency_ms: float,
        tokens_used: int = 0,
        sources_count: int = 0,
        confidence: float = 0.0,
        status: str = "success",
        error_message: Optional[str] = None,
    ) -> Optional[QueryMetrics]:
        """
        End tracking for a query

        Args:
            query_id: Unique identifier for the query
            latency_ms: Query execution time in milliseconds
            tokens_used: Number of tokens used (for LLM queries)
            sources_count: Number of sources retrieved
            confidence: Confidence score
            status: Query status (success, error)
            error_message: Error message if status is error

        Returns:
            QueryMetrics object if query was tracked, None otherwise
        """
        with self._lock:
            if query_id not in self._active_queries:
                logger.warning(f"Query {query_id} not found in active queries")
                return None

            metrics = self._active_queries.pop(query_id)
            metrics.end_time = datetime.utcnow()
            metrics.latency_ms = latency_ms
            metrics.tokens_used = tokens_used
            metrics.sources_count = sources_count
            metrics.confidence = confidence
            metrics.status = status
            metrics.error_message = error_message

            # Add to history
            self._query_history.append(metrics)

            logger.debug(
                f"Ended tracking query {query_id}: "
                f"latency={latency_ms:.2f}ms, status={status}"
            )

            return metrics

    def get_query_metrics(self, query_id: str) -> Optional[QueryMetrics]:
        """
        Get metrics for a specific query

        Args:
            query_id: Unique identifier for the query

        Returns:
            QueryMetrics object if found, None otherwise
        """
        with self._lock:
            # Check active queries first
            if query_id in self._active_queries:
                return self._active_queries[query_id]

            # Check history
            for metrics in reversed(self._query_history):
                if metrics.query_id == query_id:
                    return metrics

            return None

    def get_statistics(self, limit: Optional[int] = None) -> Dict[str, Any]:
        """
        Calculate aggregate statistics from query history

        Args:
            limit: Maximum number of recent queries to analyze (None = all)

        Returns:
            Dictionary with statistics
        """
        with self._lock:
            history = list(self._query_history)

            if limit:
                history = history[-limit:]

            if not history:
                return {
                    "total_queries": 0,
                    "avg_latency_ms": 0.0,
                    "p50_latency_ms": 0.0,
                    "p95_latency_ms": 0.0,
                    "p99_latency_ms": 0.0,
                    "success_rate": 0.0,
                    "avg_tokens_used": 0.0,
                    "avg_sources_count": 0.0,
                    "avg_confidence": 0.0,
                }

            # Filter successful queries for latency percentiles
            successful_queries = [m for m in history if m.status == "success"]
            latencies = sorted([m.latency_ms for m in successful_queries])

            # Calculate percentiles
            def percentile(data: List[float], p: float) -> float:
                if not data:
                    return 0.0
                index = int(len(data) * p / 100)
                return data[min(index, len(data) - 1)]

            total_queries = len(history)
            successful_queries_count = len(successful_queries)

            return {
                "total_queries": total_queries,
                "avg_latency_ms": sum(m.latency_ms for m in successful_queries) / successful_queries_count if successful_queries_count else 0.0,
                "p50_latency_ms": percentile(latencies, 50),
                "p95_latency_ms": percentile(latencies, 95),
                "p99_latency_ms": percentile(latencies, 99),
                "success_rate": successful_queries_count / total_queries if total_queries > 0 else 0.0,
                "avg_tokens_used": sum(m.tokens_used for m in history) / total_queries,
                "avg_sources_count": sum(m.sources_count for m in history) / total_queries,
                "avg_confidence": sum(m.confidence for m in history) / total_queries,
            }

    def get_recent_queries(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get recent query metrics

        Args:
            limit: Maximum number of recent queries to return

        Returns:
            List of query metric dictionaries
        """
        with self._lock:
            history = list(self._query_history)[-limit:]
            return [m.to_dict() for m in reversed(history)]

    def get_active_queries(self) -> List[Dict[str, Any]]:
        """
        Get currently active (in-progress) queries

        Returns:
            List of active query metric dictionaries
        """
        with self._lock:
            return [m.to_dict() for m in self._active_queries.values()]

    def clear_history(self) -> int:
        """
        Clear query history

        Returns:
            Number of queries cleared
        """
        with self._lock:
            count = len(self._query_history)
            self._query_history.clear()
            logger.info(f"Cleared {count} queries from history")
            return count

    def get_history_size(self) -> int:
        """
        Get current size of query history

        Returns:
            Number of queries in history
        """
        with self._lock:
            return len(self._query_history)


# Global performance monitor instance
_performance_monitor: Optional[PerformanceMonitor] = None
_monitor_lock = threading.Lock()


def get_performance_monitor() -> PerformanceMonitor:
    """
    Get the global performance monitor instance

    Returns:
        PerformanceMonitor instance
    """
    global _performance_monitor

    if _performance_monitor is None:
        with _monitor_lock:
            if _performance_monitor is None:
                _performance_monitor = PerformanceMonitor()
                logger.info("Created global performance monitor instance")

    return _performance_monitor


def reset_performance_monitor():
    """
    Reset the global performance monitor instance

    Useful for testing or reinitialization
    """
    global _performance_monitor

    with _monitor_lock:
        _performance_monitor = None
        logger.info("Reset global performance monitor instance")
