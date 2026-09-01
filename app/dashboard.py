"""
Search Analytics Dashboard

This module provides a web-based dashboard for visualizing search analytics data,
including query performance, latency trends, and user behavior patterns.
"""

import logging
from typing import List, Dict, Any
from datetime import datetime, timezone

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd

import httpx

logger = logging.getLogger(__name__)

# Configuration
API_BASE_URL = "http://localhost:8000"
PAGE_TITLE = "Enterprise RAG - Search Analytics"
PAGE_ICON = "📊"


def fetch_analytics_statistics() -> Dict[str, Any]:
    """
    Fetch analytics statistics from the API

    Returns:
        Dictionary with analytics statistics
    """
    try:
        response = httpx.get(f"{API_BASE_URL}/api/v1/analytics/statistics", timeout=10.0)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Error fetching statistics: {e}")
        return {}


def fetch_recent_queries(limit: int = 10) -> List[Dict[str, Any]]:
    """
    Fetch recent queries from the API

    Args:
        limit: Number of queries to fetch

    Returns:
        List of query metrics
    """
    try:
        response = httpx.get(
            f"{API_BASE_URL}/api/v1/analytics/queries/recent",
            params={"limit": limit},
            timeout=10.0
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Error fetching recent queries: {e}")
        return []


def fetch_time_series(hours: int = 24, interval_minutes: int = 60) -> List[Dict[str, Any]]:
    """
    Fetch time series data from the API

    Args:
        hours: Number of hours to look back
        interval_minutes: Time interval in minutes

    Returns:
        List of time series data points
    """
    try:
        response = httpx.get(
            f"{API_BASE_URL}/api/v1/analytics/queries/time-series",
            params={"hours": hours, "interval_minutes": interval_minutes},
            timeout=10.0
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Error fetching time series: {e}")
        return []


def fetch_top_queries(limit: int = 10) -> List[Dict[str, Any]]:
    """
    Fetch top queries from the API

    Args:
        limit: Number of top queries to fetch

    Returns:
        List of top queries
    """
    try:
        response = httpx.get(
            f"{API_BASE_URL}/api/v1/analytics/queries/top",
            params={"limit": limit},
            timeout=10.0
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Error fetching top queries: {e}")
        return []


def render_latency_percentiles(stats: Dict[str, Any]) -> None:
    """
    Render latency percentiles chart

    Args:
        stats: Statistics dictionary
    """
    if not stats:
        st.warning("No statistics available")
        return

    percentiles = ["p50", "p95", "p99"]
    values = [stats.get(f"{p}_latency_ms", 0) for p in percentiles]

    fig = go.Figure(data=[
        go.Bar(
            x=percentiles,
            y=values,
            marker_color=['#3498db', '#e74c3c', '#f39c12'],
            text=[f"{v:.2f}ms" for v in values],
            textposition='auto'
        )
    ])

    fig.update_layout(
        title="Query Latency Percentiles",
        xaxis_title="Percentile",
        yaxis_title="Latency (ms)",
        height=400
    )

    st.plotly_chart(fig, use_container_width=True)


def render_time_series_chart(time_series: List[Dict[str, Any]]) -> None:
    """
    Render time series chart

    Args:
        time_series: List of time series data points
    """
    if not time_series:
        st.warning("No time series data available")
        return

    df = pd.DataFrame(time_series)
    df['timestamp'] = pd.to_datetime(df['timestamp'])

    fig = go.Figure()

    # Add query count
    fig.add_trace(go.Scatter(
        x=df['timestamp'],
        y=df['count'],
        mode='lines+markers',
        name='Query Count',
        line=dict(color='#3498db', width=2),
        yaxis='y'
    ))

    # Add latency on secondary axis
    fig.add_trace(go.Scatter(
        x=df['timestamp'],
        y=df['avg_latency_ms'],
        mode='lines+markers',
        name='Avg Latency (ms)',
        line=dict(color='#e74c3c', width=2),
        yaxis='y2'
    ))

    fig.update_layout(
        title="Query Volume and Latency Over Time",
        xaxis_title="Time",
        yaxis=dict(
            title="Query Count",
            titlefont=dict(color="#3498db"),
            tickfont=dict(color="#3498db")
        ),
        yaxis2=dict(
            title="Avg Latency (ms)",
            titlefont=dict(color="#e74c3c"),
            tickfont=dict(color="#e74c3c"),
            overlaying="y",
            side="right"
        ),
        height=400,
        hovermode='x unified'
    )

    st.plotly_chart(fig, use_container_width=True)


def render_top_queries_chart(top_queries: List[Dict[str, Any]]) -> None:
    """
    Render top queries chart

    Args:
        top_queries: List of top query data
    """
    if not top_queries:
        st.warning("No top queries data available")
        return

    df = pd.DataFrame(top_queries)
    df['query_truncated'] = df['query'].str[:50] + '...'  # Truncate long queries

    fig = go.Figure(data=[
        go.Bar(
            x=df['count'],
            y=df['query_truncated'],
            orientation='h',
            marker_color='#3498db',
            text=df['count'],
            textposition='auto'
        )
    ])

    fig.update_layout(
        title=f"Top {len(df)} Queries by Frequency",
        xaxis_title="Query Count",
        yaxis_title="Query",
        height=400 + len(df) * 20
    )

    st.plotly_chart(fig, use_container_width=True)


def render_query_statistics(stats: Dict[str, Any]) -> None:
    """
    Render query statistics as metrics

    Args:
        stats: Statistics dictionary
    """
    if not stats:
        st.warning("No statistics available")
        return

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            label="Total Queries",
            value=f"{stats.get('total_queries', 0):,}"
        )

    with col2:
        st.metric(
            label="Success Rate",
            value=f"{stats.get('success_rate', 0) * 100:.1f}%"
        )

    with col3:
        st.metric(
            label="Avg Latency",
            value=f"{stats.get('avg_latency_ms', 0):.2f}ms"
        )

    with col4:
        st.metric(
            label="Avg Tokens",
            value=f"{stats.get('avg_tokens_used', 0):.0f}"
        )


def render_recent_queries_table(queries: List[Dict[str, Any]]) -> None:
    """
    Render recent queries table

    Args:
        queries: List of query metrics
    """
    if not queries:
        st.warning("No recent queries available")
        return

    df = pd.DataFrame(queries)

    # Format timestamp
    if 'start_time' in df.columns:
        df['start_time'] = pd.to_datetime(df['start_time']).dt.strftime('%Y-%m-%d %H:%M:%S')

    # Select and rename columns
    display_columns = {
        'query': 'Query',
        'start_time': 'Time',
        'latency_ms': 'Latency (ms)',
        'tokens_used': 'Tokens',
        'confidence': 'Confidence',
        'status': 'Status'
    }

    df_display = df[list(display_columns.keys())].rename(columns=display_columns)

    # Truncate long queries
    df_display['Query'] = df_display['Query'].str[:60]

    st.dataframe(
        df_display,
        use_container_width=True,
        hide_index=True
    )


def render_confidence_distribution(queries: List[Dict[str, Any]]) -> None:
    """
    Render confidence score distribution

    Args:
        queries: List of query metrics
    """
    if not queries:
        st.warning("No query data available")
        return

    confidences = [q.get('confidence', 0) for q in queries if q.get('status') == 'success']

    if not confidences:
        st.warning("No successful queries with confidence scores")
        return

    fig = go.Figure(data=[
        go.Histogram(
            x=confidences,
            nbinsx=20,
            marker_color='#3498db',
            opacity=0.7
        )
    ])

    fig.update_layout(
        title="Confidence Score Distribution",
        xaxis_title="Confidence Score",
        yaxis_title="Count",
        height=400
    )

    st.plotly_chart(fig, use_container_width=True)


def main() -> None:
    """
    Main dashboard application
    """
    st.set_page_config(
        page_title=PAGE_TITLE,
        page_icon=PAGE_ICON,
        layout="wide",
        initial_sidebar_state="expanded"
    )

    st.title(PAGE_TITLE)
    st.markdown("---")

    # Sidebar configuration
    st.sidebar.header("Configuration")

    global API_BASE_URL

    api_url_input = st.sidebar.text_input(
        "API Base URL",
        value=API_BASE_URL,
        help="Base URL of the RAG API"
    )

    if api_url_input != API_BASE_URL:
        API_BASE_URL = api_url_input

    # Time range selector
    time_range = st.sidebar.selectbox(
        "Time Range",
        options=[1, 6, 12, 24, 48, 72, 168],
        format_func=lambda x: f"{x} hours" if x < 24 else f"{x // 24} days",
        index=3
    )

    # Auto-refresh toggle
    auto_refresh = st.sidebar.checkbox("Auto Refresh (30s)", value=False)

    # Fetch data
    with st.spinner("Loading analytics data..."):
        stats = fetch_analytics_statistics()
        recent_queries = fetch_recent_queries(limit=100)
        time_series = fetch_time_series(hours=time_range, interval_minutes=60)
        top_queries = fetch_top_queries(limit=10)

    # Render dashboard sections
    col1, col2 = st.columns([2, 1])

    with col1:
        st.subheader("Query Statistics")
        render_query_statistics(stats)

    with col2:
        st.subheader("Performance Summary")
        if stats:
            st.info(f"""
            - **Avg Sources**: {stats.get('avg_sources_count', 0):.1f}
            - **Avg Confidence**: {stats.get('avg_confidence', 0):.2f}
            - **P95 Latency**: {stats.get('p95_latency_ms', 0):.2f}ms
            - **P99 Latency**: {stats.get('p99_latency_ms', 0):.2f}ms
            """)

    st.markdown("---")

    # Charts row
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Latency Percentiles")
        render_latency_percentiles(stats)

    with col2:
        st.subheader("Confidence Distribution")
        render_confidence_distribution(recent_queries)

    st.markdown("---")

    # Time series chart
    st.subheader(f"Query Trends (Last {time_range} hours)")
    render_time_series_chart(time_series)

    st.markdown("---")

    # Top queries and recent queries
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Top Queries")
        render_top_queries_chart(top_queries)

    with col2:
        st.subheader("Recent Queries")
        with st.expander("Show recent queries", expanded=True):
            render_recent_queries_table(recent_queries[:20])

    # Auto-refresh
    if auto_refresh:
        st.rerun()


if __name__ == "__main__":
    main()
