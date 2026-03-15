"""
Document Deduplication Service

This module provides functionality to detect and handle duplicate documents
using content hashing and similarity detection.

Features:
- Exact duplicate detection using SHA256 hashing
- Near-duplicate detection using similarity thresholds
- Configurable deduplication strategies
- Thread-safe operation
"""

from typing import List, Dict, Any, Optional, Set, Tuple
from dataclasses import dataclass, field
from pathlib import Path
import hashlib
import logging
from threading import Lock
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class DeduplicationResult:
    """Result of deduplication operation"""
    total_documents: int
    unique_documents: int
    duplicates_found: int
    duplicates_removed: int
    processing_time_ms: float
    strategy_used: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "total_documents": self.total_documents,
            "unique_documents": self.unique_documents,
            "duplicates_found": self.duplicates_found,
            "duplicates_removed": self.duplicates_removed,
            "processing_time_ms": self.processing_time_ms,
            "strategy_used": self.strategy_used
        }


@dataclass
class DocumentHash:
    """Document hash information"""
    doc_id: str
    content_hash: str
    metadata: Dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.now)


class DeduplicationStrategy:
    """Base class for deduplication strategies"""

    def deduplicate(
        self,
        documents: List[Any]
    ) -> Tuple[List[Any], DeduplicationResult]:
        """
        Deduplicate documents.

        Args:
            documents: List of Document objects to deduplicate

        Returns:
            Tuple of (unique_documents, result)
        """
        raise NotImplementedError


class ExactHashDeduplication(DeduplicationStrategy):
    """
    Exact duplicate detection using content hashing.

    This strategy calculates SHA256 hash of document content and
    removes exact duplicates.
    """

    def __init__(self):
        self._hashes: Set[str] = set()
        self._seen_documents: Dict[str, Any] = {}

    def _compute_hash(self, content: str) -> str:
        """Compute SHA256 hash of document content"""
        return hashlib.sha256(content.encode('utf-8')).hexdigest()

    def deduplicate(
        self,
        documents: List[Any]
    ) -> Tuple[List[Any], DeduplicationResult]:
        """
        Remove exact duplicates based on content hash.

        Args:
            documents: List of Document objects to deduplicate

        Returns:
            Tuple of (unique_documents, result)
        """
        import time
        start_time = time.time()

        unique_docs = []
        duplicates_count = 0

        for doc in documents:
            content_hash = self._compute_hash(doc.content)

            if content_hash not in self._hashes:
                self._hashes.add(content_hash)
                self._seen_documents[content_hash] = doc
                unique_docs.append(doc)
                logger.debug(f"Unique document: {doc.doc_id} (hash: {content_hash[:16]}...)")
            else:
                duplicates_count += 1
                logger.info(
                    f"Duplicate found: {doc.doc_id} matches "
                    f"{self._seen_documents[content_hash].doc_id}"
                )

        elapsed_ms = (time.time() - start_time) * 1000

        result = DeduplicationResult(
            total_documents=len(documents),
            unique_documents=len(unique_docs),
            duplicates_found=duplicates_count,
            duplicates_removed=duplicates_count,
            processing_time_ms=elapsed_ms,
            strategy_used="exact_hash"
        )

        logger.info(
            f"Deduplication complete: {len(unique_docs)}/{len(documents)} unique "
            f"({duplicates_count} duplicates removed in {elapsed_ms:.2f}ms)"
        )

        return unique_docs, result


class SimilarityDeduplication(DeduplicationStrategy):
    """
    Near-duplicate detection using similarity metrics.

    This strategy uses MinHash or other similarity algorithms to detect
    documents that are similar but not identical.
    """

    def __init__(self, similarity_threshold: float = 0.95):
        """
        Initialize similarity-based deduplication.

        Args:
            similarity_threshold: Threshold for considering documents similar (0.0-1.0)
        """
        if not 0.0 <= similarity_threshold <= 1.0:
            raise ValueError("similarity_threshold must be between 0.0 and 1.0")

        self.similarity_threshold = similarity_threshold
        self._document_signatures: List[Tuple[str, Any]] = []

    def _compute_signature(self, content: str) -> str:
        """
        Compute document signature for similarity comparison.

        Uses a simple word-based signature for demonstration.
        Production systems might use MinHash, SimHash, or other LSH techniques.

        Args:
            content: Document content

        Returns:
            Document signature string
        """
        # Simple approach: sort unique words and create signature
        words = set(content.lower().split())
        sorted_words = sorted(words)
        return " ".join(sorted_words[:50])  # First 50 unique words as signature

    def _compute_similarity(self, sig1: str, sig2: str) -> float:
        """
        Compute Jaccard similarity between two signatures.

        Args:
            sig1: First document signature
            sig2: Second document signature

        Returns:
            Similarity score between 0.0 and 1.0
        """
        set1 = set(sig1.split())
        set2 = set(sig2.split())

        if not set1 or not set2:
            return 0.0

        intersection = len(set1 & set2)
        union = len(set1 | set2)

        return intersection / union if union > 0 else 0.0

    def deduplicate(
        self,
        documents: List[Any]
    ) -> Tuple[List[Any], DeduplicationResult]:
        """
        Remove near-duplicates based on similarity threshold.

        Args:
            documents: List of Document objects to deduplicate

        Returns:
            Tuple of (unique_documents, result)
        """
        import time
        start_time = time.time()

        unique_docs = []
        duplicates_count = 0
        duplicate_pairs = []

        for doc in documents:
            doc_signature = self._compute_signature(doc.content)
            is_duplicate = False

            # Check against existing unique documents
            for existing_sig, existing_doc in self._document_signatures:
                similarity = self._compute_similarity(doc_signature, existing_sig)

                if similarity >= self.similarity_threshold:
                    is_duplicate = True
                    duplicates_count += 1
                    duplicate_pairs.append((existing_doc.doc_id, doc.doc_id, similarity))
                    logger.info(
                        f"Similar document found: {doc.doc_id} is "
                        f"{similarity:.2%} similar to {existing_doc.doc_id}"
                    )
                    break

            if not is_duplicate:
                unique_docs.append(doc)
                self._document_signatures.append((doc_signature, doc))

        elapsed_ms = (time.time() - start_time) * 1000

        result = DeduplicationResult(
            total_documents=len(documents),
            unique_documents=len(unique_docs),
            duplicates_found=duplicates_count,
            duplicates_removed=duplicates_count,
            processing_time_ms=elapsed_ms,
            strategy_used=f"similarity_{self.similarity_threshold}"
        )

        logger.info(
            f"Similarity deduplication complete: {len(unique_docs)}/{len(documents)} unique "
            f"({duplicates_count} similar documents removed in {elapsed_ms:.2f}ms)"
        )

        return unique_docs, result


class DocumentDeduplicator:
    """
    Main deduplication service that orchestrates different strategies.

    Provides a unified interface for document deduplication with support
    for multiple strategies and thread-safe operation.
    """

    def __init__(self, strategy: DeduplicationStrategy = None):
        """
        Initialize deduplicator with specified strategy.

        Args:
            strategy: Deduplication strategy to use. Defaults to ExactHashDeduplication
        """
        self.strategy = strategy or ExactHashDeduplication()
        self._lock = Lock()
        self._deduplication_history: List[DeduplicationResult] = []

    def deduplicate(
        self,
        documents: List[Any]
    ) -> Tuple[List[Any], DeduplicationResult]:
        """
        Deduplicate documents using configured strategy.

        Thread-safe operation.

        Args:
            documents: List of Document objects to deduplicate

        Returns:
            Tuple of (unique_documents, result)
        """
        with self._lock:
            if not documents:
                logger.warning("Empty document list provided for deduplication")
                empty_result = DeduplicationResult(
                    total_documents=0,
                    unique_documents=0,
                    duplicates_found=0,
                    duplicates_removed=0,
                    processing_time_ms=0.0,
                    strategy_used=type(self.strategy).__name__
                )
                return [], empty_result

            logger.info(f"Starting deduplication for {len(documents)} documents")

            unique_docs, result = self.strategy.deduplicate(documents)

            # Track history
            self._deduplication_history.append(result)

            # Limit history size
            if len(self._deduplication_history) > 100:
                self._deduplication_history = self._deduplication_history[-50:]

            return unique_docs, result

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get deduplication statistics.

        Returns:
            Dictionary with deduplication statistics
        """
        if not self._deduplication_history:
            return {
                "total_runs": 0,
                "total_documents_processed": 0,
                "total_duplicates_removed": 0,
                "average_processing_time_ms": 0.0
            }

        total_docs = sum(r.total_documents for r in self._deduplication_history)
        total_duplicates = sum(r.duplicates_removed for r in self._deduplication_history)
        avg_time = sum(r.processing_time_ms for r in self._deduplication_history) / len(self._deduplication_history)

        return {
            "total_runs": len(self._deduplication_history),
            "total_documents_processed": total_docs,
            "total_duplicates_removed": total_duplicates,
            "average_processing_time_ms": round(avg_time, 2),
            "last_run": self._deduplication_history[-1].to_dict()
        }

    def clear_history(self) -> None:
        """Clear deduplication history"""
        with self._lock:
            self._deduplication_history.clear()
            logger.info("Deduplication history cleared")


# Global deduplicator instance for singleton pattern
_deduplicator: Optional[DocumentDeduplicator] = None
_deduplicator_config: Dict[str, Any] = {
    "strategy": "exact",
    "similarity_threshold": 0.95
}
_deduplicator_lock = Lock()


def get_deduplicator(
    strategy: str = "exact",
    similarity_threshold: float = 0.95
) -> DocumentDeduplicator:
    """
    Factory function to get a configured deduplicator (singleton pattern).

    Returns the global deduplicator instance, reconfiguring it if
    the parameters differ from the current configuration.

    Args:
        strategy: Strategy type ("exact" or "similarity")
        similarity_threshold: Threshold for similarity strategy (0.0-1.0)

    Returns:
        Configured DocumentDeduplicator instance

    Raises:
        ValueError: If strategy type is unknown
    """
    global _deduplicator, _deduplicator_config

    with _deduplicator_lock:
        # Check if we need to recreate the deduplicator with new config
        if (_deduplicator is None or
            _deduplicator_config["strategy"] != strategy or
            _deduplicator_config["similarity_threshold"] != similarity_threshold):

            # Create new strategy
            if strategy == "exact":
                dedup_strategy = ExactHashDeduplication()
            elif strategy == "similarity":
                dedup_strategy = SimilarityDeduplication(similarity_threshold=similarity_threshold)
            else:
                raise ValueError(
                    f"Unknown strategy: {strategy}. "
                    f"Supported strategies: 'exact', 'similarity'"
                )

            # Create new deduplicator
            _deduplicator = DocumentDeduplicator(strategy=dedup_strategy)
            _deduplicator_config = {
                "strategy": strategy,
                "similarity_threshold": similarity_threshold
            }

            logger.info(f"Created new deduplicator with strategy: {strategy}")

        return _deduplicator


def reset_deduplicator() -> None:
    """
    Reset the global deduplicator instance.

    This clears all history and creates a fresh instance on next call.
    Useful for testing or when starting a new ingestion session.
    """
    global _deduplicator
    with _deduplicator_lock:
        _deduplicator = None
        logger.info("Global deduplicator reset")

