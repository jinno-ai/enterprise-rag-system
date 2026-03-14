"""
Query Suggestion Service

Provides intelligent query suggestions based on:
1. Document content analysis
2. User query history
3. Popular/search trends
4. Semantic similarity to existing documents
"""

import logging
import threading
from typing import List, Dict, Any, Optional, Set
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import Counter, defaultdict
import re

from app.core.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()


@dataclass
class QuerySuggestion:
    """A query suggestion with metadata"""
    query: str
    score: float
    source: str  # 'content', 'history', 'trending', 'semantic'
    frequency: int = 1
    last_used: Optional[datetime] = None
    category: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'query': self.query,
            'score': round(self.score, 3),
            'source': self.source,
            'frequency': self.frequency,
            'last_used': self.last_used.isoformat() if self.last_used else None,
            'category': self.category
        }


@dataclass
class SuggestionRequest:
    """Request for query suggestions"""
    partial_query: str = ""
    max_suggestions: int = 10
    include_history: bool = True
    include_trending: bool = True
    include_semantic: bool = True
    user_id: Optional[str] = None


class QueryHistoryTracker:
    """
    Tracks user query history for personalized suggestions.

    Maintains in-memory history with automatic expiration of old queries.
    Thread-safe for concurrent access.
    """

    def __init__(self, max_history_size: int = 1000, history_ttl_days: int = 30):
        self.max_history_size = max_history_size
        self.history_ttl_days = history_ttl_days
        # Structure: {user_id: [(query, timestamp), ...]}
        self.user_history: Dict[str, List[tuple]] = defaultdict(list)
        # Structure: {query: frequency}
        self.global_frequency: Counter = Counter()
        # Structure: {query: last_timestamp}
        self.last_seen: Dict[str, datetime] = {}
        # Thread safety
        self._lock = threading.RLock()

    def add_query(self, query: str, user_id: Optional[str] = None) -> None:
        """
        Add a query to the history.

        Args:
            query: The query string
            user_id: Optional user identifier for personalization
        """
        with self._lock:
            timestamp = datetime.now()
            normalized_query = query.strip().lower()

            if not normalized_query:
                return

            # Add to user-specific history
            if user_id:
                user_history_list = self.user_history[user_id]
                user_history_list.append((normalized_query, timestamp))

                # Trim history if needed
                if len(user_history_list) > self.max_history_size:
                    user_history_list = user_history_list[-self.max_history_size:]
                    self.user_history[user_id] = user_history_list

            # Update global statistics
            self.global_frequency[normalized_query] += 1
            self.last_seen[normalized_query] = timestamp

            logger.debug(f"Recorded query: {normalized_query} for user: {user_id}")

    def get_user_history(
        self,
        user_id: str,
        limit: int = 10,
        min_age_seconds: Optional[int] = None
    ) -> List[str]:
        """
        Get recent queries for a specific user.

        Args:
            user_id: User identifier
            limit: Maximum number of queries to return
            min_age_seconds: Minimum age in seconds (for filtering recent queries)

        Returns:
            List of query strings
        """
        with self._lock:
            if user_id not in self.user_history:
                return []

            history = self.user_history[user_id]
            cutoff_time = datetime.now() - timedelta(seconds=min_age_seconds) if min_age_seconds else None

            # Filter by age if specified
            if cutoff_time:
                history = [(q, t) for q, t in history if t >= cutoff_time]

            # Get unique queries, most recent first
            seen = set()
            recent_queries = []
            for query, timestamp in reversed(history):
                if query not in seen:
                    recent_queries.append(query)
                    seen.add(query)
                    if len(recent_queries) >= limit:
                        break

            return recent_queries

    def get_trending_queries(
        self,
        limit: int = 10,
        min_frequency: int = 2
    ) -> List[tuple]:
        """
        Get globally trending queries.

        Args:
            limit: Maximum number of queries to return
            min_frequency: Minimum frequency threshold

        Returns:
            List of (query, frequency) tuples
        """
        with self._lock:
            # Filter by minimum frequency
            filtered = {
                query: freq for query, freq in self.global_frequency.items()
                if freq >= min_frequency
            }

            # Sort by frequency and recency
            trending = sorted(
                filtered.items(),
                key=lambda x: (x[1], self.last_seen.get(x[0], datetime.min)),
                reverse=True
            )

            return trending[:limit]

    def cleanup_old_entries(self) -> int:
        """
        Remove old entries from history.

        Returns:
            Number of entries removed
        """
        with self._lock:
            cutoff_time = datetime.now() - timedelta(days=self.history_ttl_days)
            removed = 0

            # Clean user histories
            for user_id in list(self.user_history.keys()):
                user_history_list = self.user_history[user_id]
                original_length = len(user_history_list)

                # Remove old entries
                self.user_history[user_id] = [
                    (query, timestamp) for query, timestamp in user_history_list
                    if timestamp >= cutoff_time
                ]

                removed += original_length - len(self.user_history[user_id])

                # Remove empty histories
                if not self.user_history[user_id]:
                    del self.user_history[user_id]

            logger.info(f"Cleaned up {removed} old history entries")
            return removed


class QuerySuggestionService:
    """
    Service for generating intelligent query suggestions.

    Combines multiple suggestion sources:
    1. Content-based: Suggestions from document analysis
    2. History-based: User's past queries
    3. Trending: Popular queries across all users
    4. Semantic: Similar queries based on embeddings (future enhancement)
    """

    def __init__(
        self,
        history_tracker: Optional[QueryHistoryTracker] = None,
        enable_history: bool = True,
        enable_trending: bool = True
    ):
        self.history_tracker = history_tracker or QueryHistoryTracker()
        self.enable_history = enable_history
        self.enable_trending = enable_trending

        # Predefined suggestion categories based on common RAG use cases
        self.suggestion_templates = {
            'policy': [
                "what is the company policy on",
                "company policy regarding",
                "policy for remote work",
                "vacation policy",
                "employee benefits policy"
            ],
            'procedures': [
                "how do I",
                "procedure for",
                "process to",
                "steps to",
                "guidelines for"
            ],
            'resources': [
                "where can I find",
                "available resources for",
                "documentation on",
                "training materials for",
                "who is responsible for"
            ],
            'general': [
                "explain",
                "describe",
                "compare",
                "difference between",
                "advantages of"
            ]
        }

    def _extract_query_type(self, query: str) -> Optional[str]:
        """
        Determine the type/category of a query.

        Args:
            query: Query string

        Returns:
            Category name or None
        """
        query_lower = query.lower()

        if any(word in query_lower for word in ['policy', 'rule', 'guideline']):
            return 'policy'
        elif any(word in query_lower for word in ['how', 'procedure', 'process', 'step']):
            return 'procedures'
        elif any(word in query_lower for word in ['where', 'find', 'resource', 'document']):
            return 'resources'
        else:
            return 'general'

    def _generate_completions(
        self,
        partial_query: str,
        max_suggestions: int = 10
    ) -> List[QuerySuggestion]:
        """
        Generate query completions based on partial input.

        Args:
            partial_query: Partial query string
            max_suggestions: Maximum number of suggestions

        Returns:
            List of QuerySuggestion objects
        """
        suggestions = []
        partial_lower = partial_query.strip().lower()

        if not partial_lower:
            return suggestions

        # Check against suggestion templates
        for category, templates in self.suggestion_templates.items():
            for template in templates:
                if template.startswith(partial_lower) or partial_lower in template:
                    score = self._calculate_completion_score(partial_lower, template)
                    suggestions.append(QuerySuggestion(
                        query=partial_query + template[len(partial_lower):] if template.startswith(partial_lower) else template,
                        score=score,
                        source='content',
                        category=category
                    ))

                    if len(suggestions) >= max_suggestions:
                        return suggestions

        return suggestions

    def _calculate_completion_score(self, partial: str, completion: str) -> float:
        """
        Calculate relevance score for a completion.

        Args:
            partial: Partial query
            completion: Suggested completion

        Returns:
            Score between 0 and 1
        """
        # Higher score for exact prefix match
        if completion.startswith(partial):
            return 0.9

        # Lower score for partial match
        if partial in completion:
            return 0.7

        # Calculate similarity based on shared words
        partial_words = set(partial.split())
        completion_words = set(completion.split())

        if not partial_words:
            return 0.5

        overlap = len(partial_words & completion_words)
        return min(overlap / len(partial_words), 1.0)

    def _get_history_suggestions(
        self,
        user_id: Optional[str],
        partial_query: str,
        max_suggestions: int = 5
    ) -> List[QuerySuggestion]:
        """
        Get suggestions based on user history.

        Args:
            user_id: User identifier
            partial_query: Partial query string
            max_suggestions: Maximum number of suggestions

        Returns:
            List of QuerySuggestion objects
        """
        if not self.enable_history or not user_id:
            return []

        suggestions = []
        history_queries = self.history_tracker.get_user_history(user_id, limit=50)

        partial_lower = partial_query.strip().lower()

        for query in history_queries:
            if partial_lower in query:
                frequency = self.history_tracker.global_frequency.get(query, 1)
                score = min(0.5 + (frequency * 0.1), 1.0)

                suggestions.append(QuerySuggestion(
                    query=query,
                    score=score,
                    source='history',
                    frequency=frequency,
                    last_used=self.history_tracker.last_seen.get(query),
                    category=self._extract_query_type(query)
                ))

                if len(suggestions) >= max_suggestions:
                    break

        return suggestions

    def _get_trending_suggestions(
        self,
        max_suggestions: int = 5
    ) -> List[QuerySuggestion]:
        """
        Get trending query suggestions.

        Args:
            max_suggestions: Maximum number of suggestions

        Returns:
            List of QuerySuggestion objects
        """
        if not self.enable_trending:
            return []

        suggestions = []
        trending = self.history_tracker.get_trending_queries(
            limit=max_suggestions,
            min_frequency=2
        )

        for query, frequency in trending:
            # Normalize score based on frequency
            score = min(0.5 + (frequency * 0.05), 1.0)

            suggestions.append(QuerySuggestion(
                query=query,
                score=score,
                source='trending',
                frequency=frequency,
                last_used=self.history_tracker.last_seen.get(query),
                category=self._extract_query_type(query)
            ))

        return suggestions

    def get_suggestions(
        self,
        request: SuggestionRequest
    ) -> List[Dict[str, Any]]:
        """
        Get query suggestions based on the request.

        Args:
            request: SuggestionRequest with parameters

        Returns:
            List of suggestion dictionaries
        """
        all_suggestions = []

        # Generate completions for partial query
        if request.partial_query:
            completions = self._generate_completions(
                request.partial_query,
                request.max_suggestions
            )
            all_suggestions.extend(completions)

        # Get history-based suggestions
        if request.include_history and request.user_id:
            history_suggestions = self._get_history_suggestions(
                request.user_id,
                request.partial_query,
                max_suggestions=request.max_suggestions // 2
            )
            all_suggestions.extend(history_suggestions)

        # Get trending suggestions
        if request.include_trending:
            trending_suggestions = self._get_trending_suggestions(
                max_suggestions=request.max_suggestions // 2
            )
            all_suggestions.extend(trending_suggestions)

        # Remove duplicates and sort by score
        unique_suggestions = {}
        for suggestion in all_suggestions:
            query_key = suggestion.query.lower()
            if query_key not in unique_suggestions or suggestion.score > unique_suggestions[query_key].score:
                unique_suggestions[query_key] = suggestion

        # Sort by score and limit
        sorted_suggestions = sorted(
            unique_suggestions.values(),
            key=lambda s: s.score,
            reverse=True
        )[:request.max_suggestions]

        return [s.to_dict() for s in sorted_suggestions]

    def track_query(self, query: str, user_id: Optional[str] = None) -> None:
        """
        Track a query for future suggestions.

        Args:
            query: The query string
            user_id: Optional user identifier
        """
        self.history_tracker.add_query(query, user_id)


# Global instance with thread-safe initialization
_suggestion_service: Optional[QuerySuggestionService] = None
_suggestion_lock = threading.Lock()


def get_suggestion_service() -> QuerySuggestionService:
    """Get or create the global suggestion service instance (thread-safe)"""
    global _suggestion_service
    if _suggestion_service is None:
        with _suggestion_lock:
            if _suggestion_service is None:  # Double-checked locking
                _suggestion_service = QuerySuggestionService()
    return _suggestion_service
