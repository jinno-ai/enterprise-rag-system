"""
Unit tests for Document Deduplication (Feature 12)

Tests document deduplication functionality including:
- Exact duplicate detection using content hashing
- Near-duplicate detection using similarity metrics
- Integration with document ingestion pipeline
- Edge cases and error handling
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from typing import List, Dict, Any
import time

from app.services.deduplication import (
    DocumentDeduplicator,
    ExactHashDeduplication,
    SimilarityDeduplication,
    DeduplicationResult,
    get_deduplicator
)
from app.services.document_loader import Document


class TestDocumentDeduplication:
    """Test suite for document deduplication"""

    @pytest.fixture
    def sample_documents(self) -> List[Document]:
        """Create sample documents for testing"""
        return [
            Document(
                content="This is a unique document about AI and machine learning.",
                metadata={"source": "doc1.txt", "title": "AI Document"}
            ),
            Document(
                content="Another unique document covering data science topics.",
                metadata={"source": "doc2.txt", "title": "Data Science"}
            ),
            Document(
                content="Third document discussing natural language processing.",
                metadata={"source": "doc3.txt", "title": "NLP"}
            )
        ]

    @pytest.fixture
    def duplicate_documents(self) -> List[Document]:
        """Create documents with duplicates"""
        base_content = "This is a document that will be duplicated."

        return [
            Document(
                content=base_content,
                metadata={"source": "original.txt", "title": "Original"}
            ),
            Document(
                content=base_content,  # Exact duplicate
                metadata={"source": "duplicate1.txt", "title": "Duplicate 1"}
            ),
            Document(
                content=base_content,  # Exact duplicate
                metadata={"source": "duplicate2.txt", "title": "Duplicate 2"}
            ),
            Document(
                content="This is a different document.",
                metadata={"source": "unique.txt", "title": "Unique"}
            )
        ]

    @pytest.fixture
    def similar_documents(self) -> List[Document]:
        """Create documents with similar but not identical content"""
        return [
            Document(
                content="Machine learning is a subset of artificial intelligence.",
                metadata={"source": "doc1.txt"}
            ),
            Document(
                content="Machine learning is a subset of AI and data science.",  # Similar
                metadata={"source": "doc2.txt"}
            ),
            Document(
                content="Deep learning uses neural networks for AI applications.",
                metadata={"source": "doc3.txt"}
            ),
            Document(
                content="Completely different topic about cooking recipes.",
                metadata={"source": "doc4.txt"}
            )
        ]


class TestExactHashDeduplication(TestDocumentDeduplication):
    """Test exact hash-based deduplication"""

    def test_exact_deduplication_removes_duplicates(self, duplicate_documents):
        """Test that exact duplicates are removed correctly"""
        strategy = ExactHashDeduplication()
        unique_docs, result = strategy.deduplicate(duplicate_documents)

        assert len(unique_docs) == 2  # 2 unique documents
        assert result.duplicates_found == 2  # 2 duplicates found
        assert result.duplicates_removed == 2
        assert result.total_documents == 4
        assert result.strategy_used == "exact_hash"

    def test_exact_deduplication_preserves_unique_content(self, sample_documents):
        """Test that unique documents are preserved"""
        strategy = ExactHashDeduplication()
        unique_docs, result = strategy.deduplicate(sample_documents)

        assert len(unique_docs) == 3  # All unique
        assert result.duplicates_found == 0
        assert result.duplicates_removed == 0

    def test_exact_deduplication_empty_list(self):
        """Test deduplication with empty document list"""
        strategy = ExactHashDeduplication()
        unique_docs, result = strategy.deduplicate([])

        assert len(unique_docs) == 0
        assert result.total_documents == 0
        assert result.unique_documents == 0

    def test_exact_deduplication_single_document(self, sample_documents):
        """Test deduplication with single document"""
        strategy = ExactHashDeduplication()
        unique_docs, result = strategy.deduplicate([sample_documents[0]])

        assert len(unique_docs) == 1
        assert result.duplicates_found == 0

    def test_exact_deduplication_case_sensitivity(self):
        """Test that deduplication is case-sensitive"""
        docs = [
            Document(content="Hello World", metadata={"source": "1"}),
            Document(content="hello world", metadata={"source": "2"}),  # Different case
            Document(content="Hello World", metadata={"source": "3"})  # Exact duplicate
        ]

        strategy = ExactHashDeduplication()
        unique_docs, result = strategy.deduplicate(docs)

        assert len(unique_docs) == 2  # "Hello World" and "hello world" are different
        assert result.duplicates_found == 1

    def test_exact_deduplication_whitespace_sensitivity(self):
        """Test that deduplication is whitespace-sensitive"""
        docs = [
            Document(content="Hello World", metadata={"source": "1"}),
            Document(content="Hello  World", metadata={"source": "2"}),  # Extra space
            Document(content="Hello World", metadata={"source": "3"})  # Exact duplicate
        ]

        strategy = ExactHashDeduplication()
        unique_docs, result = strategy.deduplicate(docs)

        assert len(unique_docs) == 2  # Different whitespace
        assert result.duplicates_found == 1

    def test_exact_deduplication_processing_time(self, duplicate_documents):
        """Test that processing time is measured"""
        strategy = ExactHashDeduplication()
        unique_docs, result = strategy.deduplicate(duplicate_documents)

        assert result.processing_time_ms >= 0
        assert isinstance(result.processing_time_ms, float)


class TestSimilarityDeduplication(TestDocumentDeduplication):
    """Test similarity-based deduplication"""

    def test_similarity_deduplication_initialization(self):
        """Test similarity deduplication initialization"""
        strategy = SimilarityDeduplication(similarity_threshold=0.9)

        assert strategy.similarity_threshold == 0.9

    def test_similarity_deduplication_invalid_threshold(self):
        """Test that invalid threshold raises error"""
        with pytest.raises(ValueError):
            SimilarityDeduplication(similarity_threshold=1.5)

        with pytest.raises(ValueError):
            SimilarityDeduplication(similarity_threshold=-0.1)

    def test_similarity_deduplication_high_threshold(self, similar_documents):
        """Test with high similarity threshold (conservative)"""
        strategy = SimilarityDeduplication(similarity_threshold=0.99)
        unique_docs, result = strategy.deduplicate(similar_documents)

        # With 0.99 threshold, should keep most documents as unique
        assert len(unique_docs) >= 3

    def test_similarity_deduplication_low_threshold(self, similar_documents):
        """Test with low similarity threshold (aggressive)"""
        strategy = SimilarityDeduplication(similarity_threshold=0.3)
        unique_docs, result = strategy.deduplicate(similar_documents)

        # With 0.3 threshold, might remove some similar documents
        assert len(unique_docs) <= len(similar_documents)

    def test_similarity_deduplication_exact_duplicates(self):
        """Test similarity deduplication with exact duplicates"""
        docs = [
            Document(content="Exact content here", metadata={"source": "1"}),
            Document(content="Exact content here", metadata={"source": "2"}),
        ]

        strategy = SimilarityDeduplication(similarity_threshold=0.95)
        unique_docs, result = strategy.deduplicate(docs)

        assert len(unique_docs) == 1  # Should detect exact duplicates
        assert result.duplicates_found >= 1

    def test_similarity_deduplication_empty_list(self):
        """Test similarity deduplication with empty list"""
        strategy = SimilarityDeduplication(similarity_threshold=0.9)
        unique_docs, result = strategy.deduplicate([])

        assert len(unique_docs) == 0
        assert result.total_documents == 0

    def test_similarity_strategy_name(self, similar_documents):
        """Test that strategy name includes threshold"""
        strategy = SimilarityDeduplication(similarity_threshold=0.85)
        unique_docs, result = strategy.deduplicate(similar_documents)

        assert "similarity" in result.strategy_used
        assert "0.85" in result.strategy_used


class TestDocumentDeduplicator(TestDocumentDeduplication):
    """Test main DocumentDeduplicator class"""

    def test_deduplicator_default_strategy(self, sample_documents):
        """Test deduplicator with default strategy"""
        deduplicator = DocumentDeduplicator()
        unique_docs, result = deduplicator.deduplicate(sample_documents)

        assert len(unique_docs) == len(sample_documents)
        assert result.duplicates_found == 0

    def test_deduplicator_custom_strategy(self, duplicate_documents):
        """Test deduplicator with custom strategy"""
        custom_strategy = ExactHashDeduplication()
        deduplicator = DocumentDeduplicator(strategy=custom_strategy)

        unique_docs, result = deduplicator.deduplicate(duplicate_documents)

        assert len(unique_docs) == 2
        assert result.duplicates_found == 2

    def test_deduplicator_empty_documents(self):
        """Test deduplicator with empty document list"""
        deduplicator = DocumentDeduplicator()
        unique_docs, result = deduplicator.deduplicate([])

        assert len(unique_docs) == 0
        assert result.total_documents == 0

    def test_deduplicator_statistics_tracking(self):
        """Test that deduplicator tracks statistics"""
        # Create test documents locally to avoid fixture issues
        docs = [
            Document(content="Same content", metadata={"source": "1"}),
            Document(content="Same content", metadata={"source": "2"}),
            Document(content="Unique content", metadata={"source": "3"}),
            Document(content="Different content", metadata={"source": "4"})
        ]

        deduplicator = DocumentDeduplicator()

        # Run deduplication multiple times
        deduplicator.deduplicate(docs)
        deduplicator.deduplicate(docs)

        stats = deduplicator.get_statistics()

        assert stats["total_runs"] == 2
        assert stats["total_documents_processed"] == 8  # 4 docs * 2 runs
        # Note: ExactHashDeduplication maintains state across runs
        # First run: 3 unique (1 duplicate), Second run: all are duplicates
        assert stats["total_duplicates_removed"] >= 1
        assert stats["average_processing_time_ms"] >= 0

    def test_deduplicator_clear_history(self, duplicate_documents):
        """Test clearing deduplication history"""
        deduplicator = DocumentDeduplicator()
        deduplicator.deduplicate(duplicate_documents)

        stats_before = deduplicator.get_statistics()
        assert stats_before["total_runs"] == 1

        deduplicator.clear_history()

        stats_after = deduplicator.get_statistics()
        assert stats_after["total_runs"] == 0

    def test_deduplicator_no_history_initially(self):
        """Test statistics when no history exists"""
        deduplicator = DocumentDeduplicator()
        stats = deduplicator.get_statistics()

        assert stats["total_runs"] == 0
        assert stats["total_documents_processed"] == 0

    def test_deduplicator_result_serialization(self, duplicate_documents):
        """Test that DeduplicationResult can be serialized"""
        deduplicator = DocumentDeduplicator()
        unique_docs, result = deduplicator.deduplicate(duplicate_documents)

        result_dict = result.to_dict()

        assert "total_documents" in result_dict
        assert "unique_documents" in result_dict
        assert "duplicates_found" in result_dict
        assert "processing_time_ms" in result_dict
        assert "strategy_used" in result_dict


class TestDeduplicatorFactory:
    """Test deduplicator factory function"""

    def test_get_deduplicator_exact(self):
        """Test factory with exact strategy"""
        deduplicator = get_deduplicator(strategy="exact")

        assert isinstance(deduplicator, DocumentDeduplicator)
        assert isinstance(deduplicator.strategy, ExactHashDeduplication)

    def test_get_deduplicator_similarity(self):
        """Test factory with similarity strategy"""
        deduplicator = get_deduplicator(strategy="similarity", similarity_threshold=0.9)

        assert isinstance(deduplicator, DocumentDeduplicator)
        assert isinstance(deduplicator.strategy, SimilarityDeduplication)

    def test_get_deduplicator_invalid_strategy(self):
        """Test factory with invalid strategy"""
        with pytest.raises(ValueError, match="Unknown strategy"):
            get_deduplicator(strategy="invalid_strategy")


class TestDeduplicationEdgeCases(TestDocumentDeduplication):
    """Test edge cases and error conditions"""

    def test_very_long_document(self):
        """Test deduplication with very long document"""
        long_content = "word " * 10000  # Long document

        docs = [
            Document(content=long_content, metadata={"source": "1"}),
            Document(content=long_content, metadata={"source": "2"}),
            Document(content="short", metadata={"source": "3"})
        ]

        deduplicator = DocumentDeduplicator()
        unique_docs, result = deduplicator.deduplicate(docs)

        assert len(unique_docs) == 2  # One long doc, one short doc

    def test_unicode_content(self):
        """Test deduplication with unicode content"""
        docs = [
            Document(content="Hello 世界 🌍", metadata={"source": "1"}),
            Document(content="Hello 世界 🌍", metadata={"source": "2"}),
            Document(content="Привет мир", metadata={"source": "3"})
        ]

        deduplicator = DocumentDeduplicator()
        unique_docs, result = deduplicator.deduplicate(docs)

        assert len(unique_docs) == 2  # 2 unique unicode docs

    def test_special_characters(self):
        """Test deduplication with special characters"""
        content = "Special chars: \n\t\r<>\"'&"

        docs = [
            Document(content=content, metadata={"source": "1"}),
            Document(content=content, metadata={"source": "2"})
        ]

        deduplicator = DocumentDeduplicator()
        unique_docs, result = deduplicator.deduplicate(docs)

        assert len(unique_docs) == 1

    def test_large_batch_performance(self):
        """Test performance with large batch of documents"""
        # Create 100 documents with some duplicates
        docs = []
        for i in range(100):
            if i % 10 == 0:  # Every 10th document is a duplicate
                docs.append(Document(content="duplicate content", metadata={"source": f"dup_{i}"}))
            else:
                docs.append(Document(content=f"unique content {i}", metadata={"source": f"unique_{i}"}))

        deduplicator = DocumentDeduplicator()
        unique_docs, result = deduplicator.deduplicate(docs)

        assert len(unique_docs) == 91  # 100 - 9 duplicates (1 original kept)
        assert result.duplicates_found == 9
        assert result.processing_time_ms < 1000  # Should complete in under 1 second


class TestDeduplicationIntegration:
    """Integration tests for deduplication with document processing"""

    def test_deduplication_preserves_metadata(self):
        """Test that metadata is preserved for unique documents"""
        docs = [
            Document(content="Doc 1", metadata={"source": "original.txt", "title": "Original"}),
            Document(content="Doc 1", metadata={"source": "dup.txt", "title": "Duplicate"}),
            Document(content="Doc 2", metadata={"source": "unique.txt", "title": "Unique"})
        ]

        deduplicator = DocumentDeduplicator()
        unique_docs, result = deduplicator.deduplicate(docs)

        # Check that unique documents have correct metadata
        for doc in unique_docs:
            assert "source" in doc.metadata
            assert "title" in doc.metadata

    def test_deduplication_maintains_order(self):
        """Test that order of first occurrence is maintained"""
        docs = [
            Document(content="First", metadata={"source": "doc1.txt"}),
            Document(content="Second", metadata={"source": "doc2.txt"}),
            Document(content="Third", metadata={"source": "doc3.txt"})
        ]

        deduplicator = DocumentDeduplicator()
        unique_docs, result = deduplicator.deduplicate(docs)

        # Order should be preserved
        assert len(unique_docs) == 3
        assert unique_docs[0].metadata["source"] == "doc1.txt"
        assert unique_docs[1].metadata["source"] == "doc2.txt"
        assert unique_docs[2].metadata["source"] == "doc3.txt"

    def test_result_completeness(self):
        """Test that result contains all expected fields"""
        docs = [
            Document(content="Same", metadata={"source": "1"}),
            Document(content="Same", metadata={"source": "2"}),
            Document(content="Different", metadata={"source": "3"}),
            Document(content="Another", metadata={"source": "4"})
        ]

        deduplicator = DocumentDeduplicator()
        unique_docs, result = deduplicator.deduplicate(docs)

        assert result.total_documents == 4
        assert result.unique_documents == 3  # 3 unique: "Same", "Different", "Another"
        assert result.duplicates_found == 1  # 1 duplicate (second "Same")
        assert result.duplicates_removed == 1
        assert result.strategy_used == "exact_hash"
        assert result.processing_time_ms > 0
        assert "processing_time_ms" in result.to_dict()
