"""
Unit tests for Query Suggestion (Feature 29)

Tests the query suggestion service that provides intelligent suggestions based on:
1. Content analysis (query templates)
2. User query history
3. Trending/popular queries
"""

import pytest
from unittest.mock import Mock, patch
from datetime import datetime, timedelta

from app.services.suggestion import (
    QuerySuggestion,
    QueryHistoryTracker,
    QuerySuggestionService,
    SuggestionRequest,
    get_suggestion_service
)


@pytest.fixture
def history_tracker():
    """Create a fresh history tracker for each test"""
    return QueryHistoryTracker(max_history_size=100, history_ttl_days=30)


@pytest.fixture
def suggestion_service(history_tracker):
    """Create a suggestion service with tracker"""
    return QuerySuggestionService(
        history_tracker=history_tracker,
        enable_history=True,
        enable_trending=True
    )


class TestQuerySuggestion:
    """Tests for QuerySuggestion dataclass"""

    def test_suggestion_creation(self):
        """Test creating a query suggestion"""
        suggestion = QuerySuggestion(
            query="test query",
            score=0.9,
            source="history",
            frequency=5,
            last_used=datetime.now(),
            category="policy"
        )

        assert suggestion.query == "test query"
        assert suggestion.score == 0.9
        assert suggestion.source == "history"
        assert suggestion.frequency == 5
        assert suggestion.category == "policy"

    def test_suggestion_to_dict(self):
        """Test converting suggestion to dictionary"""
        timestamp = datetime.now()
        suggestion = QuerySuggestion(
            query="test query",
            score=0.85,
            source="content",
            frequency=3,
            last_used=timestamp,
            category="procedures"
        )

        result = suggestion.to_dict()

        assert result['query'] == "test query"
        assert result['score'] == 0.85
        assert result['source'] == "content"
        assert result['frequency'] == 3
        assert result['category'] == "procedures"
        assert result['last_used'] == timestamp.isoformat()


class TestSuggestionRequest:
    """Tests for SuggestionRequest dataclass"""

    def test_default_values(self):
        """Test suggestion request with default values"""
        request = SuggestionRequest()

        assert request.partial_query == ""
        assert request.max_suggestions == 10
        assert request.include_history is True
        assert request.include_trending is True
        assert request.user_id is None

    def test_custom_values(self):
        """Test suggestion request with custom values"""
        request = SuggestionRequest(
            partial_query="company policy",
            max_suggestions=20,
            include_history=False,
            include_trending=False,
            user_id="test_user"
        )

        assert request.partial_query == "company policy"
        assert request.max_suggestions == 20
        assert request.include_history is False
        assert request.include_trending is False
        assert request.user_id == "test_user"


class TestQueryHistoryTracker:
    """Tests for QueryHistoryTracker"""

    def test_add_query_basic(self, history_tracker):
        """Test adding a basic query"""
        history_tracker.add_query("test query", user_id="user1")

        assert "user1" in history_tracker.user_history
        assert len(history_tracker.user_history["user1"]) == 1
        assert history_tracker.global_frequency["test query"] == 1

    def test_add_query_without_user(self, history_tracker):
        """Test adding query without user ID"""
        history_tracker.add_query("test query")

        # Should update global stats but not user history
        assert len(history_tracker.user_history) == 0
        assert history_tracker.global_frequency["test query"] == 1

    def test_add_query_normalization(self, history_tracker):
        """Test query normalization"""
        history_tracker.add_query("  Test Query  ", user_id="user1")

        query, timestamp = history_tracker.user_history["user1"][0]
        assert query == "test query"

    def test_add_empty_query(self, history_tracker):
        """Test that empty queries are ignored"""
        history_tracker.add_query("   ", user_id="user1")

        assert len(history_tracker.user_history) == 0

    def test_multiple_users(self, history_tracker):
        """Test tracking queries for multiple users"""
        history_tracker.add_query("query1", user_id="user1")
        history_tracker.add_query("query2", user_id="user2")
        history_tracker.add_query("query1", user_id="user1")

        assert len(history_tracker.user_history["user1"]) == 2
        assert len(history_tracker.user_history["user2"]) == 1
        assert history_tracker.global_frequency["query1"] == 2

    def test_get_user_history_basic(self, history_tracker):
        """Test getting user history"""
        history_tracker.add_query("query1", user_id="user1")
        history_tracker.add_query("query2", user_id="user1")
        history_tracker.add_query("query1", user_id="user1")  # Duplicate

        history = history_tracker.get_user_history("user1", limit=10)

        # Should return unique queries, most recent first
        assert len(history) == 2
        assert "query1" in history
        assert "query2" in history

    def test_get_user_history_limit(self, history_tracker):
        """Test getting user history with limit"""
        for i in range(10):
            history_tracker.add_query(f"query{i}", user_id="user1")

        history = history_tracker.get_user_history("user1", limit=5)

        assert len(history) == 5

    def test_get_user_history_nonexistent(self, history_tracker):
        """Test getting history for nonexistent user"""
        history = history_tracker.get_user_history("nonexistent", limit=10)

        assert history == []

    def test_get_trending_queries_basic(self, history_tracker):
        """Test getting trending queries"""
        history_tracker.add_query("popular query", user_id="user1")
        history_tracker.add_query("popular query", user_id="user2")
        history_tracker.add_query("popular query", user_id="user3")
        history_tracker.add_query("unpopular query", user_id="user1")

        trending = history_tracker.get_trending_queries(limit=10, min_frequency=2)

        assert len(trending) == 1
        assert trending[0][0] == "popular query"
        assert trending[0][1] == 3

    def test_get_trending_queries_min_frequency(self, history_tracker):
        """Test trending queries with minimum frequency threshold"""
        for i in range(5):
            history_tracker.add_query("popular", user_id=f"user{i}")

        history_tracker.add_query("unpopular", user_id="user1")

        trending = history_tracker.get_trending_queries(limit=10, min_frequency=3)

        assert len(trending) == 1
        assert trending[0][0] == "popular"

    def test_cleanup_old_entries(self, history_tracker):
        """Test cleanup of old entries"""
        # Add old entry by mocking timestamp
        old_time = datetime.now() - timedelta(days=40)
        with patch('app.services.suggestion.datetime') as mock_datetime:
            mock_datetime.now.return_value = old_time
            history_tracker.add_query("old query", user_id="user1")

        # Add recent entry
        history_tracker.add_query("recent query", user_id="user1")

        # Clean up
        removed = history_tracker.cleanup_old_entries()

        # Should remove old entry
        assert removed >= 1
        assert len(history_tracker.user_history["user1"]) == 1
        assert history_tracker.user_history["user1"][0][0] == "recent query"

    def test_max_history_size(self, history_tracker):
        """Test that history is trimmed when exceeding max size"""
        small_tracker = QueryHistoryTracker(max_history_size=5)

        # Add more than max size
        for i in range(10):
            small_tracker.add_query(f"query{i}", user_id="user1")

        # Should be trimmed to max size
        assert len(small_tracker.user_history["user1"]) <= 5


class TestQuerySuggestionService:
    """Tests for QuerySuggestionService"""

    def test_service_initialization(self, suggestion_service):
        """Test service initialization"""
        assert suggestion_service.enable_history is True
        assert suggestion_service.enable_trending is True
        assert len(suggestion_service.suggestion_templates) > 0

    def test_extract_query_type_policy(self, suggestion_service):
        """Test query type extraction for policy queries"""
        query_type = suggestion_service._extract_query_type("What is the company policy on remote work?")
        assert query_type == "policy"

    def test_extract_query_type_procedures(self, suggestion_service):
        """Test query type extraction for procedure queries"""
        query_type = suggestion_service._extract_query_type("How do I request vacation time?")
        assert query_type == "procedures"

    def test_extract_query_type_resources(self, suggestion_service):
        """Test query type extraction for resource queries"""
        query_type = suggestion_service._extract_query_type("Where can I find training materials?")
        assert query_type == "resources"

    def test_extract_query_type_general(self, suggestion_service):
        """Test query type extraction for general queries"""
        query_type = suggestion_service._extract_query_type("Explain the benefits package")
        assert query_type == "general"

    def test_generate_completions_partial_match(self, suggestion_service):
        """Test generating completions for partial query"""
        suggestions = suggestion_service._generate_completions(
            partial_query="company policy",
            max_suggestions=10
        )

        # Should get completions from templates
        assert len(suggestions) > 0
        assert all(s.source == "content" for s in suggestions)
        assert all(s.score > 0 for s in suggestions)

    def test_generate_completions_empty_partial(self, suggestion_service):
        """Test completions with empty partial query"""
        suggestions = suggestion_service._generate_completions(
            partial_query="",
            max_suggestions=10
        )

        assert len(suggestions) == 0

    def test_calculate_completion_score_exact_prefix(self, suggestion_service):
        """Test completion score for exact prefix match"""
        score = suggestion_service._calculate_completion_score(
            partial="company policy",
            completion="company policy on remote work"
        )

        assert score >= 0.9

    def test_calculate_completion_score_partial_match(self, suggestion_service):
        """Test completion score for partial match"""
        score = suggestion_service._calculate_completion_score(
            partial="policy",
            completion="company policy on remote work"
        )

        assert 0.7 <= score < 0.9

    def test_get_history_suggestions(self, suggestion_service):
        """Test getting history-based suggestions"""
        # Add some history
        suggestion_service.history_tracker.add_query("company policy on remote work", user_id="user1")
        suggestion_service.history_tracker.add_query("remote work guidelines", user_id="user1")
        suggestion_service.history_tracker.add_query("vacation policy", user_id="user1")

        # Get suggestions
        suggestions = suggestion_service._get_history_suggestions(
            user_id="user1",
            partial_query="remote",
            max_suggestions=10
        )

        # Should get matching history suggestions
        assert len(suggestions) > 0
        assert all(s.source == "history" for s in suggestions)
        assert any("remote" in s.query.lower() for s in suggestions)

    def test_get_history_suggestions_no_user(self, suggestion_service):
        """Test history suggestions without user ID"""
        suggestions = suggestion_service._get_history_suggestions(
            user_id=None,
            partial_query="test",
            max_suggestions=10
        )

        assert len(suggestions) == 0

    def test_get_trending_suggestions(self, suggestion_service):
        """Test getting trending suggestions"""
        # Add popular queries
        for i in range(5):
            suggestion_service.history_tracker.add_query("remote work policy", user_id=f"user{i}")
            suggestion_service.history_tracker.add_query("vacation policy", user_id=f"user{i}")

        # Get trending
        suggestions = suggestion_service._get_trending_suggestions(max_suggestions=10)

        assert len(suggestions) > 0
        assert all(s.source == "trending" for s in suggestions)
        assert all(s.frequency >= 2 for s in suggestions)

    def test_get_trending_suggestions_disabled(self, suggestion_service):
        """Test trending suggestions when disabled"""
        suggestion_service.enable_trending = False

        suggestions = suggestion_service._get_trending_suggestions(max_suggestions=10)

        assert len(suggestions) == 0

    def test_get_suggestions_comprehensive(self, suggestion_service):
        """Test getting comprehensive suggestions from all sources"""
        # Setup: Add history
        suggestion_service.history_tracker.add_query("remote work policy", user_id="user1")
        suggestion_service.history_tracker.add_query("remote work policy", user_id="user2")
        suggestion_service.history_tracker.add_query("vacation policy", user_id="user1")

        # Create request
        request = SuggestionRequest(
            partial_query="remote",
            max_suggestions=10,
            include_history=True,
            include_trending=True,
            user_id="user1"
        )

        # Get suggestions
        suggestions = suggestion_service.get_suggestions(request)

        # Should get suggestions from multiple sources
        assert len(suggestions) > 0
        assert all('query' in s for s in suggestions)
        assert all('score' in s for s in suggestions)
        assert all('source' in s for s in suggestions)

        # Check for variety in sources
        sources = set(s['source'] for s in suggestions)
        assert len(sources) > 0

    def test_get_suggestions_no_partial(self, suggestion_service):
        """Test getting suggestions without partial query"""
        request = SuggestionRequest(
            partial_query="",
            max_suggestions=10,
            include_history=True,
            include_trending=True,
            user_id="user1"
        )

        suggestions = suggestion_service.get_suggestions(request)

        # Should still get trending suggestions
        assert isinstance(suggestions, list)

    def test_get_suggestions_deduplication(self, suggestion_service):
        """Test that duplicate suggestions are removed"""
        # Add query that matches template
        suggestion_service.history_tracker.add_query("company policy on remote work", user_id="user1")

        request = SuggestionRequest(
            partial_query="company policy",
            max_suggestions=10,
            include_history=True,
            include_trending=False,
            user_id="user1"
        )

        suggestions = suggestion_service.get_suggestions(request)

        # Check no duplicates (case-insensitive)
        query_lower = [s['query'].lower() for s in suggestions]
        assert len(query_lower) == len(set(query_lower))

    def test_track_query(self, suggestion_service):
        """Test tracking a query"""
        suggestion_service.track_query("test query", user_id="user1")

        assert "user1" in suggestion_service.history_tracker.user_history
        assert suggestion_service.history_tracker.global_frequency["test query"] == 1

    def test_get_suggestions_sorted_by_score(self, suggestion_service):
        """Test that suggestions are sorted by score"""
        request = SuggestionRequest(
            partial_query="company",
            max_suggestions=10,
            include_history=False,
            include_trending=False
        )

        suggestions = suggestion_service.get_suggestions(request)

        # Verify sorted order
        scores = [s['score'] for s in suggestions]
        assert scores == sorted(scores, reverse=True)

    def test_max_suggestions_limit(self, suggestion_service):
        """Test that max_suggestions limit is respected"""
        request = SuggestionRequest(
            partial_query="policy",
            max_suggestions=5,
            include_history=True,
            include_trending=True
        )

        suggestions = suggestion_service.get_suggestions(request)

        assert len(suggestions) <= 5


class TestGlobalSuggestionService:
    """Tests for global suggestion service instance"""

    def test_get_suggestion_service_singleton(self):
        """Test that get_suggestion_service returns singleton"""
        service1 = get_suggestion_service()
        service2 = get_suggestion_service()

        assert service1 is service2

    def test_global_service_functionality(self):
        """Test that global service works correctly"""
        service = get_suggestion_service()

        request = SuggestionRequest(
            partial_query="test",
            max_suggestions=5
        )

        suggestions = service.get_suggestions(request)

        assert isinstance(suggestions, list)


class TestEdgeCases:
    """Tests for edge cases and error conditions"""

    def test_very_long_partial_query(self, suggestion_service):
        """Test with very long partial query"""
        long_query = "test " * 100
        request = SuggestionRequest(
            partial_query=long_query,
            max_suggestions=10
        )

        suggestions = suggestion_service.get_suggestions(request)

        # Should handle gracefully
        assert isinstance(suggestions, list)

    def test_special_characters_in_query(self, suggestion_service):
        """Test with special characters in query"""
        request = SuggestionRequest(
            partial_query="policy @#$%",
            max_suggestions=10
        )

        suggestions = suggestion_service.get_suggestions(request)

        # Should handle gracefully
        assert isinstance(suggestions, list)

    def test_unicode_in_query(self, suggestion_service):
        """Test with unicode characters in query"""
        request = SuggestionRequest(
            partial_query="policy 日本語",
            max_suggestions=10
        )

        suggestions = suggestion_service.get_suggestions(request)

        # Should handle gracefully
        assert isinstance(suggestions, list)

    def test_zero_max_suggestions(self, suggestion_service):
        """Test with zero max_suggestions"""
        request = SuggestionRequest(
            partial_query="test",
            max_suggestions=0
        )

        suggestions = suggestion_service.get_suggestions(request)

        assert len(suggestions) == 0

    def test_very_large_max_suggestions(self, suggestion_service):
        """Test with very large max_suggestions"""
        request = SuggestionRequest(
            partial_query="test",
            max_suggestions=10000
        )

        suggestions = suggestion_service.get_suggestions(request)

        # Should limit to available suggestions
        assert isinstance(suggestions, list)

    def test_all_sources_disabled(self, suggestion_service):
        """Test with all suggestion sources disabled"""
        suggestion_service.enable_history = False
        suggestion_service.enable_trending = False

        request = SuggestionRequest(
            partial_query="test query",
            max_suggestions=10,
            include_history=False,
            include_trending=False
        )

        suggestions = suggestion_service.get_suggestions(request)

        # Should only get content-based suggestions
        assert isinstance(suggestions, list)
