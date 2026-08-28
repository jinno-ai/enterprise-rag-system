"""
Analytics API for Search Analytics Dashboard

This module provides API endpoints for accessing search analytics data,
including query statistics, performance metrics, and trends.
"""

import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.performance import get_performance_monitor

logger = logging.getLogger(__name__)

# Create router for analytics endpoints
router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])


class AnalyticsStatistics(BaseModel):
    """Analytics statistics model"""

    total_queries: int = Field(..., description="Total number of queries")
    avg_latency_ms: float = Field(..., description="Average query latency in milliseconds")
    p50_latency_ms: float = Field(..., description="Median query latency")
    p95_latency_ms: float = Field(..., description="95th percentile query latency")
    p99_latency_ms: float = Field(..., description="99th percentile query latency")
    success_rate: float = Field(..., description="Query success rate (0-1)")
    avg_tokens_used: float = Field(..., description="Average tokens used per query")
    avg_sources_count: float = Field(..., description="Average sources retrieved")
    avg_confidence: float = Field(..., description="Average confidence score")


class QueryMetrics(BaseModel):
    """Individual query metrics model"""

    query_id: str
    query: str
    start_time: str
    end_time: Optional[str]
    latency_ms: float
    tokens_used: int
    sources_count: int
    confidence: float
    status: str
    error_message: Optional[str]


class TimeSeriesData(BaseModel):
    """Time series data point"""

    timestamp: str
    count: int
    avg_latency_ms: float


class TopQueries(BaseModel):
    """Top query model"""

    query: str
    count: int
    avg_latency_ms: float
    avg_confidence: float


@router.get("/statistics", response_model=AnalyticsStatistics)
async def get_analytics_statistics(
    limit: Optional[int] = Query(
        default=None,
        ge=1,
        le=10000,
        description="Limit number of queries to analyze (None = all)"
    )
) -> AnalyticsStatistics:
    """
    Get analytics statistics

    Returns aggregated statistics for query performance metrics,
    including latency percentiles, success rate, and resource usage.

    Args:
        limit: Maximum number of recent queries to analyze

    Returns:
        AnalyticsStatistics with aggregated metrics
    """
    try:
        monitor = get_performance_monitor()
        stats = monitor.get_statistics(limit=limit)
        return AnalyticsStatistics(**stats)
    except Exception as e:
        logger.error(f"Error getting analytics statistics: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve statistics: {str(e)}")


@router.get("/queries/recent", response_model=List[QueryMetrics])
async def get_recent_queries(
    limit: int = Query(
        default=10,
        ge=1,
        le=100,
        description="Number of recent queries to return"
    )
) -> List[QueryMetrics]:
    """
    Get recent query metrics

    Returns the most recent queries with their performance metrics.

    Args:
        limit: Maximum number of recent queries to return

    Returns:
        List of QueryMetrics
    """
    try:
        monitor = get_performance_monitor()
        queries = monitor.get_recent_queries(limit=limit)
        return [QueryMetrics(**q) for q in queries]
    except Exception as e:
        logger.error(f"Error getting recent queries: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve recent queries: {str(e)}")


@router.get("/queries/active", response_model=List[QueryMetrics])
async def get_active_queries() -> List[QueryMetrics]:
    """
    Get currently active queries

    Returns queries that are currently in progress.

    Returns:
        List of active QueryMetrics
    """
    try:
        monitor = get_performance_monitor()
        queries = monitor.get_active_queries()
        return [QueryMetrics(**q) for q in queries]
    except Exception as e:
        logger.error(f"Error getting active queries: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve active queries: {str(e)}")


@router.get("/queries/time-series", response_model=List[TimeSeriesData])
async def get_query_time_series(
    hours: int = Query(
        default=24,
        ge=1,
        le=168,
        description="Number of hours to look back (max 7 days)"
    ),
    interval_minutes: int = Query(
        default=60,
        ge=5,
        le=1440,
        description="Interval size in minutes"
    )
) -> List[TimeSeriesData]:
    """
    Get query time series data

    Returns aggregated metrics over time intervals, useful for plotting
    trends and patterns.

    Args:
        hours: Number of hours to look back
        interval_minutes: Size of each time interval in minutes

    Returns:
        List of TimeSeriesData points
    """
    try:
        monitor = get_performance_monitor()

        # Calculate time range
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(hours=hours)

        # Get all queries in history
        all_queries = monitor.get_recent_queries(limit=monitor.get_history_size())

        # Filter by time range
        filtered_queries = [
            q for q in all_queries
            if datetime.fromisoformat(q['start_time'].replace('Z', '+00:00')) >= start_time
        ]

        # Group by time interval
        time_series = {}
        for query in filtered_queries:
            query_time = datetime.fromisoformat(query['start_time'].replace('Z', '+00:00'))

            # Calculate bucket
            epoch_seconds = int(query_time.timestamp())
            interval_seconds = interval_minutes * 60
            bucket_epoch = (epoch_seconds // interval_seconds) * interval_seconds
            bucket_time = datetime.fromtimestamp(bucket_epoch, tz=timezone.utc)

            bucket_key = bucket_time.isoformat()

            if bucket_key not in time_series:
                time_series[bucket_key] = {
                    'count': 0,
                    'total_latency': 0.0
                }

            time_series[bucket_key]['count'] += 1
            if query['status'] == 'success':
                time_series[bucket_key]['total_latency'] += query['latency_ms']

        # Convert to response format
        result = []
        for timestamp in sorted(time_series.keys()):
            data = time_series[timestamp]
            avg_latency = data['total_latency'] / data['count'] if data['count'] > 0 else 0.0

            result.append(TimeSeriesData(
                timestamp=timestamp,
                count=data['count'],
                avg_latency_ms=avg_latency
            ))

        return result

    except Exception as e:
        logger.error(f"Error getting time series data: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve time series: {str(e)}")


@router.get("/queries/top", response_model=List[TopQueries])
async def get_top_queries(
    limit: int = Query(
        default=10,
        ge=1,
        le=50,
        description="Number of top queries to return"
    )
) -> List[TopQueries]:
    """
    Get top queries by frequency

    Returns the most frequently executed queries with their average
    performance metrics.

    Args:
        limit: Maximum number of top queries to return

    Returns:
        List of TopQueries
    """
    try:
        monitor = get_performance_monitor()
        queries = monitor.get_recent_queries(limit=monitor.get_history_size())

        # Aggregate by query text
        query_stats: Dict[str, Dict[str, Any]] = {}

        for q in queries:
            query_text = q['query']
            if query_text not in query_stats:
                query_stats[query_text] = {
                    'count': 0,
                    'total_latency': 0.0,
                    'total_confidence': 0.0,
                    'successful_count': 0
                }

            query_stats[query_text]['count'] += 1
            if q['status'] == 'success':
                query_stats[query_text]['total_latency'] += q['latency_ms']
                query_stats[query_text]['total_confidence'] += q['confidence']
                query_stats[query_text]['successful_count'] += 1

        # Calculate averages and sort by count
        result = []
        for query_text, stats in query_stats.items():
            successful = stats['successful_count']
            result.append(TopQueries(
                query=query_text,
                count=stats['count'],
                avg_latency_ms=stats['total_latency'] / successful if successful > 0 else 0.0,
                avg_confidence=stats['total_confidence'] / successful if successful > 0 else 0.0
            ))

        # Sort by count (descending) and limit
        result.sort(key=lambda x: x.count, reverse=True)
        return result[:limit]

    except Exception as e:
        logger.error(f"Error getting top queries: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve top queries: {str(e)}")


@router.post("/queries/clear")
async def clear_query_history() -> Dict[str, Any]:
    """
    Clear query history

    Clears all stored query metrics from memory. This is useful for
    testing or resetting the analytics data.

    Returns:
        Confirmation message with count of cleared queries
    """
    try:
        monitor = get_performance_monitor()
        count = monitor.clear_history()
        return {
            "success": True,
            "cleared_count": count,
            "message": f"Cleared {count} queries from history"
        }
    except Exception as e:
        logger.error(f"Error clearing query history: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to clear history: {str(e)}")


@router.get("/health")
async def analytics_health_check() -> Dict[str, Any]:
    """
    Health check for analytics module

    Returns the status of the analytics system.
    """
    try:
        monitor = get_performance_monitor()
        history_size = monitor.get_history_size()

        return {
            "status": "healthy",
            "history_size": history_size,
            "max_history": monitor.max_history
        }
    except Exception as e:
        logger.error(f"Error in analytics health check: {e}")
        return {
            "status": "unhealthy",
            "error": str(e)
        }
