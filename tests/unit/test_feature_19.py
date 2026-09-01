"""
Unit tests for Query Caching with TTL (Feature 19)

Tests the Redis-based cache implementation for RAG query results with TTL support.
"""

import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta

from app.core.cache import QueryCache, get_cache


@pytest.fixture
def mock_redis():
    """Mock Redis client"""
    with patch('app.core.cache.redis.Redis') as mock:
        mock_client = MagicMock()
        mock.return_value = mock_client
        mock_client.ping.return_value = True
        yield mock_client


@pytest.fixture
def cache_instance(mock_redis):
    """Create cache instance with mocked Redis"""
    cache = QueryCache(
        redis_host="localhost",
        redis_port=6379,
        default_ttl=3600,
        enabled=True
    )
    cache.redis_client = mock_redis
    return cache


@pytest.fixture
def sample_query_data():
    """Sample query response data"""
    return {
        'answer': 'This is a test answer based on the context.',
        'sources': [
            {
                'index': 1,
                'document': 'test1.pdf',
                'page': 1,
                'relevance_score': 0.85,
                'text_preview': 'Sample document text...'
            }
        ],
        'confidence': 0.85,
        'latency_ms': 150,
        'tokens_used': 100,
        'retrieval_results': [
            {
                'document': 'Sample document text',
                'score': 0.85,
                'metadata': {'filename': 'test1.pdf', 'page': 1}
            }
        ]
    }


class TestQueryCacheInitialization:
    """Test cache initialization scenarios"""

    @patch('app.core.cache.redis.Redis')
    def test_cache_initialization_success(self, mock_redis):
        """Test successful cache initialization"""
        mock_client = MagicMock()
        mock_redis.return_value = mock_client
        mock_client.ping.return_value = True

        cache = QueryCache(redis_host="localhost", redis_port=6379)

        assert cache.enabled is True
        assert cache.default_ttl == 3600
        assert cache.redis_client is not None
        assert cache.stats['hits'] == 0
        assert cache.stats['misses'] == 0

    @patch('app.core.cache.redis.Redis')
    def test_cache_initialization_redis_unavailable(self, mock_redis):
        """Test cache behavior when Redis is unavailable"""
        mock_client = MagicMock()
        mock_redis.return_value = mock_client
        mock_client.ping.side_effect = Exception("Connection failed")

        cache = QueryCache(redis_host="localhost", redis_port=6379)

        assert cache.enabled is False
        assert cache.redis_client is None

    @patch('app.core.cache.redis.Redis')
    def test_cache_disabled_explicitly(self, mock_redis):
        """Test cache can be explicitly disabled"""
        cache = QueryCache(enabled=False)

        assert cache.enabled is False
        assert cache.redis_client is None


class TestCacheKeyGeneration:
    """Test cache key generation from query parameters"""

    def test_generate_cache_key_basic(self, cache_instance):
        """Test basic cache key generation"""
        key = cache_instance._generate_cache_key(
            query="What is AI?",
            top_k=5,
            use_hybrid=True
        )

        assert key.startswith("rag:query:")
        assert len(key) == len("rag:query:") + 64  # SHA256 hash

    def test_generate_cache_key_with_filters(self, cache_instance):
        """Test cache key generation with metadata filters"""
        key1 = cache_instance._generate_cache_key(
            query="test query",
            top_k=5,
            use_hybrid=True,
            filter_dict={'category': 'tech', 'year': 2024}
        )

        key2 = cache_instance._generate_cache_key(
            query="test query",
            top_k=5,
            use_hybrid=True,
            filter_dict={'year': 2024, 'category': 'tech'}
        )

        # Same filters in different order should produce same key
        assert key1 == key2

    def test_generate_cache_key_case_insensitive(self, cache_instance):
        """Test that query case doesn't affect cache key"""
        key1 = cache_instance._generate_cache_key(query="Test Query")
        key2 = cache_instance._generate_cache_key(query="test query")

        assert key1 == key2

    def test_generate_cache_key_different_params(self, cache_instance):
        """Test different parameters produce different keys"""
        key1 = cache_instance._generate_cache_key(
            query="test query",
            top_k=5,
            use_hybrid=True
        )

        key2 = cache_instance._generate_cache_key(
            query="test query",
            top_k=10,
            use_hybrid=True
        )

        assert key1 != key2


class TestCacheGetOperations:
    """Test cache retrieval operations"""

    def test_cache_hit(self, cache_instance, sample_query_data):
        """Test successful cache hit"""
        cache_key = "rag:query:test123"
        serialized_data = json.dumps(sample_query_data)
        cache_instance.redis_client.get.return_value = serialized_data

        result = cache_instance.get(cache_key)

        assert result is not None
        assert result['answer'] == sample_query_data['answer']
        assert cache_instance.stats['hits'] == 1
        assert cache_instance.stats['misses'] == 0

    def test_cache_miss(self, cache_instance):
        """Test cache miss"""
        cache_key = "rag:query:test123"
        cache_instance.redis_client.get.return_value = None

        result = cache_instance.get(cache_key)

        assert result is None
        assert cache_instance.stats['misses'] == 1
        assert cache_instance.stats['hits'] == 0

    def test_cache_get_when_disabled(self, cache_instance):
        """Test cache get returns None when disabled"""
        cache_instance.enabled = False
        cache_instance.redis_client = None

        result = cache_instance.get("rag:query:test123")

        assert result is None

    def test_cache_get_redis_error(self, cache_instance):
        """Test cache get handles Redis errors gracefully"""
        cache_instance.redis_client.get.side_effect = Exception("Redis error")

        result = cache_instance.get("rag:query:test123")

        assert result is None
        assert cache_instance.stats['errors'] == 1

    def test_cache_get_invalid_json(self, cache_instance):
        """Test cache get handles invalid JSON"""
        cache_instance.redis_client.get.return_value = "invalid json"

        result = cache_instance.get("rag:query:test123")

        assert result is None
        assert cache_instance.stats['errors'] == 1


class TestCacheSetOperations:
    """Test cache storage operations"""

    def test_cache_set_success(self, cache_instance, sample_query_data):
        """Test successful cache set"""
        cache_key = "rag:query:test123"
        cache_instance.redis_client.setex.return_value = True

        result = cache_instance.set(cache_key, sample_query_data, ttl=3600)

        assert result is True
        cache_instance.redis_client.setex.assert_called_once()
        call_args = cache_instance.redis_client.setex.call_args
        assert call_args[0][0] == cache_key
        assert call_args[0][1] == 3600

    def test_cache_set_with_custom_ttl(self, cache_instance, sample_query_data):
        """Test cache set with custom TTL"""
        cache_key = "rag:query:test123"
        cache_instance.redis_client.setex.return_value = True

        cache_instance.set(cache_key, sample_query_data, ttl=7200)

        call_args = cache_instance.redis_client.setex.call_args
        assert call_args[0][1] == 7200

    def test_cache_set_when_disabled(self, cache_instance, sample_query_data):
        """Test cache set returns False when disabled"""
        cache_instance.enabled = False
        cache_instance.redis_client = None

        result = cache_instance.set("rag:query:test123", sample_query_data)

        assert result is False

    def test_cache_set_adds_metadata(self, cache_instance, sample_query_data):
        """Test that cache set adds timestamp and TTL metadata"""
        cache_key = "rag:query:test123"
        cache_instance.redis_client.setex.return_value = True

        cache_instance.set(cache_key, sample_query_data, ttl=3600)

        call_args = cache_instance.redis_client.setex.call_args
        serialized_data = call_args[0][2]
        data = json.loads(serialized_data)

        assert 'cached_at' in data
        assert 'cache_ttl' in data
        assert data['cache_ttl'] == 3600

    def test_cache_set_redis_error(self, cache_instance, sample_query_data):
        """Test cache set handles Redis errors gracefully"""
        cache_instance.redis_client.setex.side_effect = Exception("Redis error")

        result = cache_instance.set("rag:query:test123", sample_query_data)

        assert result is False
        assert cache_instance.stats['errors'] == 1


class TestCacheDeleteOperations:
    """Test cache deletion operations"""

    def test_cache_delete_success(self, cache_instance):
        """Test successful cache delete"""
        cache_instance.redis_client.delete.return_value = 1

        result = cache_instance.delete("rag:query:test123")

        assert result is True
        cache_instance.redis_client.delete.assert_called_once_with("rag:query:test123")

    def test_cache_delete_nonexistent_key(self, cache_instance):
        """Test deleting non-existent key"""
        cache_instance.redis_client.delete.return_value = 0

        result = cache_instance.delete("rag:query:test123")

        assert result is False

    def test_cache_delete_when_disabled(self, cache_instance):
        """Test cache delete returns False when disabled"""
        cache_instance.enabled = False
        cache_instance.redis_client = None

        result = cache_instance.delete("rag:query:test123")

        assert result is False


class TestCacheClearOperations:
    """Test cache clear operations"""

    def test_cache_clear_success(self, cache_instance):
        """Test successful cache clear"""
        cache_instance.redis_client.scan_iter.return_value = [
            "rag:query:key1",
            "rag:query:key2",
            "rag:query:key3"
        ]
        cache_instance.redis_client.delete.return_value = 3

        result = cache_instance.clear()

        assert result is True
        assert cache_instance.redis_client.delete.call_count == 1

    def test_cache_clear_empty_cache(self, cache_instance):
        """Test clearing empty cache"""
        cache_instance.redis_client.scan_iter.return_value = []

        result = cache_instance.clear()

        assert result is True
        cache_instance.redis_client.delete.assert_not_called()

    def test_cache_clear_when_disabled(self, cache_instance):
        """Test cache clear returns False when disabled"""
        cache_instance.enabled = False
        cache_instance.redis_client = None

        result = cache_instance.clear()

        assert result is False


class TestCacheStatistics:
    """Test cache statistics tracking"""

    def test_get_cache_stats(self, cache_instance):
        """Test getting cache statistics"""
        cache_instance.stats['hits'] = 10
        cache_instance.stats['misses'] = 5
        cache_instance.stats['errors'] = 1

        stats = cache_instance.get_stats()

        assert stats['hits'] == 10
        assert stats['misses'] == 5
        assert stats['errors'] == 1
        assert stats['total_requests'] == 15
        assert stats['hit_rate'] == 0.667

    def test_hit_rate_calculation_no_requests(self, cache_instance):
        """Test hit rate calculation with no requests"""
        stats = cache_instance.get_stats()

        assert stats['hit_rate'] == 0.0
        assert stats['total_requests'] == 0

    def test_reset_stats(self, cache_instance):
        """Test resetting cache statistics"""
        cache_instance.stats['hits'] = 10
        cache_instance.stats['misses'] = 5

        cache_instance.reset_stats()

        assert cache_instance.stats['hits'] == 0
        assert cache_instance.stats['misses'] == 0
        assert cache_instance.stats['errors'] == 0


class TestGlobalCacheInstance:
    """Test global cache instance management"""

    def test_get_cache_singleton(self):
        """Test that get_cache returns singleton instance"""
        with patch('app.core.cache.QueryCache') as mock_cache_class:
            mock_instance = MagicMock()
            mock_cache_class.return_value = mock_instance

            cache1 = get_cache()
            cache2 = get_cache()

            # Should return same instance
            assert cache1 is cache2

    def test_get_cache_initializes_once(self):
        """Test that cache is initialized only once"""
        # Reset global cache instance
        import app.core.cache
        app.core.cache._global_cache = None

        with patch('app.core.cache.QueryCache') as mock_cache_class:
            mock_instance = MagicMock()
            mock_cache_class.return_value = mock_instance

            get_cache()
            get_cache()
            get_cache()

            # Should initialize only once
            assert mock_cache_class.call_count == 1

        # Reset again for other tests
        app.core.cache._global_cache = None


class TestCacheIntegration:
    """Integration tests for cache behavior"""

    def test_cache_end_to_end_flow(self, cache_instance, sample_query_data):
        """Test complete cache flow: miss -> set -> hit"""
        cache_key = "rag:query:test123"

        # Initial miss
        cache_instance.redis_client.get.return_value = None
        result1 = cache_instance.get(cache_key)
        assert result1 is None
        assert cache_instance.stats['misses'] == 1

        # Set data
        cache_instance.redis_client.setex.return_value = True
        cache_instance.set(cache_key, sample_query_data)

        # Hit
        serialized = json.dumps(sample_query_data, default=str)
        cache_instance.redis_client.get.return_value = serialized
        result2 = cache_instance.get(cache_key)
        assert result2 is not None
        assert result2['answer'] == sample_query_data['answer']
        assert cache_instance.stats['hits'] == 1

    def test_cache_with_different_queries(self, cache_instance, sample_query_data):
        """Test that different queries produce different cache entries"""
        key1 = cache_instance._generate_cache_key("What is AI?")
        key2 = cache_instance._generate_cache_key("What is ML?")

        assert key1 != key2

    def test_cache_ttl_expiration_simulation(self, cache_instance, sample_query_data):
        """Test cache behavior with TTL (simulated)"""
        cache_key = "rag:query:test123"

        # Set with specific TTL
        cache_instance.redis_client.setex.return_value = True
        cache_instance.set(cache_key, sample_query_data, ttl=60)

        # Verify TTL was passed correctly
        call_args = cache_instance.redis_client.setex.call_args
        assert call_args[0][1] == 60
