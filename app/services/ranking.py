"""
Query Result Ranking Service

Implements learning-to-rank for result ordering optimization.
Provides multiple ranking strategies, feature weighting, and diversity promotion.
"""

import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
import re

logger = logging.getLogger(__name__)


# Constants
DEFAULT_MIN_SCORE = 0.0
DEFAULT_MAX_SCORE = 1.0
DEFAULT_FRESHNESS_DECAY_DAYS = 365


class RankingStrategy(str, Enum):
    """Ranking strategy types"""
    LINEAR = "linear"                # Linear combination of features
    EXPONENTIAL = "exponential"      # Exponential to amplify differences
    RECIPROCAL_RANK = "rrf"          # Reciprocal Rank Fusion


@dataclass
class RankingConfig:
    """Configuration for result ranking"""
    strategy: RankingStrategy = RankingStrategy.LINEAR
    min_score: float = DEFAULT_MIN_SCORE
    max_score: float = DEFAULT_MAX_SCORE

    # Feature weights (will be normalized to sum to 1.0)
    semantic_weight: float = 0.6
    keyword_weight: float = 0.3
    freshness_weight: float = 0.1

    # Diversity promotion
    enable_diversity: bool = True
    diversity_threshold: float = 0.3

    # Freshness calculation
    freshness_decay_days: int = DEFAULT_FRESHNESS_DECAY_DAYS

    def __post_init__(self):
        """Normalize weights to sum to 1.0"""
        total = (
            self.semantic_weight +
            self.keyword_weight +
            self.freshness_weight
        )

        if total > 0:
            self.semantic_weight /= total
            self.keyword_weight /= total
            self.freshness_weight /= total


class RankingError(Exception):
    """Exception raised for ranking errors"""
    pass


class ResultRanker:
    """
    Result ranking service for query results

    Implements multiple ranking strategies with configurable feature weighting
    and diversity promotion for improved result relevance.
    """

    def __init__(self, config: Optional[RankingConfig] = None):
        """
        Initialize the result ranker

        Args:
            config: Ranking configuration (uses defaults if not provided)
        """
        self.config = config or RankingConfig()
        logger.info(
            f"Initialized ResultRanker with strategy={self.config.strategy}, "
            f"semantic_weight={self.config.semantic_weight:.2f}, "
            f"keyword_weight={self.config.keyword_weight:.2f}, "
            f"freshness_weight={self.config.freshness_weight:.2f}"
        )

    def rank(
        self,
        results: List[Dict[str, Any]],
        query: str,
        top_k: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Rank query results using configured strategy

        Args:
            results: List of retrieval results with scores
            query: Original query string
            top_k: Optional limit on number of results to return

        Returns:
            List of ranked results with added 'final_score' field

        Raises:
            RankingError: If ranking fails
        """
        if not results:
            return []

        # Validate results
        self._validate_results(results)

        try:
            # Extract scores
            semantic_scores = [r.get("score", 0.0) for r in results]
            keyword_scores = [r.get("keyword_score", 0.0) for r in results]

            # Normalize scores to [0, 1]
            semantic_scores = self._normalize_scores(semantic_scores)
            keyword_scores = self._normalize_scores(keyword_scores)

            # Calculate freshness scores
            freshness_scores = [
                self._calculate_freshness_score(r.get("metadata", {}))
                for r in results
            ]

            # Calculate query affinity scores
            affinity_scores = [
                compute_query_affinity(query, r.get("document", ""))
                for r in results
            ]

            # Combine scores based on strategy
            if self.config.strategy == RankingStrategy.LINEAR:
                final_scores = self._linear_combination(
                    semantic_scores,
                    keyword_scores,
                    freshness_scores,
                    affinity_scores
                )
            elif self.config.strategy == RankingStrategy.EXPONENTIAL:
                final_scores = self._exponential_combination(
                    semantic_scores,
                    keyword_scores,
                    freshness_scores,
                    affinity_scores
                )
            elif self.config.strategy == RankingStrategy.RECIPROCAL_RANK:
                final_scores = self._reciprocal_rank_fusion(
                    semantic_scores,
                    keyword_scores,
                    freshness_scores
                )
            else:
                raise RankingError(f"Unknown ranking strategy: {self.config.strategy}")

            # Add final scores to results
            for i, result in enumerate(results):
                result["final_score"] = round(final_scores[i], 4)
                result["original_score"] = result.get("score", 0.0)

            # Sort by final score
            ranked_results = sorted(
                results,
                key=lambda x: x["final_score"],
                reverse=True
            )

            # Apply diversity promotion if enabled
            if self.config.enable_diversity:
                ranked_results = promote_diversity(
                    ranked_results,
                    threshold=self.config.diversity_threshold,
                    top_k=top_k or len(ranked_results)
                )

            # Limit to top_k if specified
            if top_k:
                ranked_results = ranked_results[:top_k]

            logger.debug(
                f"Ranked {len(ranked_results)} results for query: {query[:50]}..."
            )

            return ranked_results

        except Exception as e:
            logger.error(f"Ranking failed: {e}", exc_info=True)
            raise RankingError(f"Failed to rank results: {e}")

    def _validate_results(self, results: List[Dict[str, Any]]) -> None:
        """Validate that results have required fields"""
        for i, result in enumerate(results):
            if "score" not in result:
                raise RankingError(
                    f"Result at index {i} missing required field 'score'"
                )

            # Check score is numeric
            try:
                float(result["score"])
            except (TypeError, ValueError):
                raise RankingError(
                    f"Result at index {i} has non-numeric 'score' field"
                )

    def _normalize_scores(self, scores: List[float]) -> List[float]:
        """
        Normalize scores to [min_score, max_score] range

        Args:
            scores: List of scores to normalize

        Returns:
            List of normalized scores
        """
        if not scores:
            return []

        # Clip scores to [0, 1] range first
        clipped = [max(0.0, min(1.0, s)) for s in scores]

        # If all scores are the same, return as-is
        if len(set(clipped)) == 1:
            return clipped

        # Scale to [min_score, max_score]
        min_val = min(clipped)
        max_val = max(clipped)

        if max_val == min_val:
            return [self.config.max_score] * len(clipped)

        scaled = [
            self.config.min_score +
            (s - min_val) / (max_val - min_val) *
            (self.config.max_score - self.config.min_score)
            for s in clipped
        ]

        return scaled

    def _calculate_freshness_score(self, metadata: Dict[str, Any]) -> float:
        """
        Calculate freshness/recency score from metadata

        Args:
            metadata: Document metadata

        Returns:
            Freshness score in [0, 1], where 1 is most recent
        """
        # Check for timestamp in metadata
        timestamp_str = metadata.get("created_at") or metadata.get("timestamp")

        if not timestamp_str:
            # No timestamp, return neutral score
            return 0.5

        try:
            # Parse timestamp (ISO format)
            if isinstance(timestamp_str, str):
                timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            else:
                timestamp = timestamp_str

            # Calculate age in days
            age_days = (datetime.now() - timestamp).days

            # Exponential decay based on age
            decay_factor = age_days / self.config.freshness_decay_days
            freshness = 2.718 ** (-decay_factor)  # e^(-x)

            return max(0.0, min(1.0, freshness))

        except Exception as e:
            logger.warning(f"Failed to calculate freshness score: {e}")
            return 0.5

    def _linear_combination(
        self,
        semantic_scores: List[float],
        keyword_scores: List[float],
        freshness_scores: List[float],
        affinity_scores: List[float]
    ) -> List[float]:
        """
        Calculate linear combination of feature scores

        Args:
            semantic_scores: Semantic similarity scores
            keyword_scores: Keyword match scores
            freshness_scores: Freshness/recency scores
            affinity_scores: Query-result affinity scores

        Returns:
            Combined final scores
        """
        final_scores = []

        for i in range(len(semantic_scores)):
            # Weighted linear combination
            score = (
                self.config.semantic_weight * semantic_scores[i] +
                self.config.keyword_weight * keyword_scores[i] +
                self.config.freshness_weight * freshness_scores[i]
            )

            # Add affinity boost (up to 10% boost)
            affinity_boost = affinity_scores[i] * 0.1
            score = min(1.0, score + affinity_boost)

            final_scores.append(score)

        return final_scores

    def _exponential_combination(
        self,
        semantic_scores: List[float],
        keyword_scores: List[float],
        freshness_scores: List[float],
        affinity_scores: List[float]
    ) -> List[float]:
        """
        Calculate exponential combination (amplifies differences)

        Args:
            semantic_scores: Semantic similarity scores
            keyword_scores: Keyword match scores
            freshness_scores: Freshness/recency scores
            affinity_scores: Query-result affinity scores

        Returns:
            Combined final scores
        """
        final_scores = []

        for i in range(len(semantic_scores)):
            # Apply exponential to amplify differences
            semantic_exp = semantic_scores[i] ** 2
            keyword_exp = keyword_scores[i] ** 2
            freshness_exp = freshness_scores[i] ** 2

            # Weighted combination
            score = (
                self.config.semantic_weight * semantic_exp +
                self.config.keyword_weight * keyword_exp +
                self.config.freshness_weight * freshness_exp
            )

            # Add affinity boost
            affinity_boost = affinity_scores[i] * 0.1
            score = min(1.0, score + affinity_boost)

            final_scores.append(score)

        return final_scores

    def _reciprocal_rank_fusion(
        self,
        semantic_scores: List[float],
        keyword_scores: List[float],
        freshness_scores: List[float]
    ) -> List[float]:
        """
        Calculate Reciprocal Rank Fusion (RRF) score

        RRF combines multiple ranked lists by using reciprocal of rank positions.

        Args:
            semantic_scores: Semantic similarity scores
            keyword_scores: Keyword match scores
            freshness_scores: Freshness/recency scores

        Returns:
            Combined final scores
        """
        k = 60  # RRF constant

        # Convert scores to ranks (higher score = better rank)
        semantic_ranks = _scores_to_ranks(semantic_scores)
        keyword_ranks = _scores_to_ranks(keyword_scores)
        freshness_ranks = _scores_to_ranks(freshness_scores)

        final_scores = []

        for i in range(len(semantic_scores)):
            # RRF formula: sum(1 / (k + rank))
            rrf_score = (
                1 / (k + semantic_ranks[i]) +
                1 / (k + keyword_ranks[i]) +
                1 / (k + freshness_ranks[i])
            )

            # Normalize to [0, 1]
            normalized_score = min(1.0, rrf_score * k)

            final_scores.append(normalized_score)

        return final_scores


def _scores_to_ranks(scores: List[float]) -> List[int]:
    """
    Convert scores to rank positions (1-based)

    Args:
        scores: List of scores

    Returns:
        List of ranks (1 = best score)
    """
    # Sort scores in descending order
    sorted_scores = sorted(scores, reverse=True)

    # Create rank mapping
    rank_map = {score: i + 1 for i, score in enumerate(sorted_scores)}

    # Map scores to ranks
    ranks = [rank_map[score] for score in scores]

    return ranks


def compute_query_affinity(query: str, document: str) -> float:
    """
    Compute query-document affinity based on term overlap

    Args:
        query: Query string
        document: Document text

    Returns:
        Affinity score in [0, 1]
    """
    if not query or not document:
        return 0.0

    # Tokenize (case-insensitive, alphanumeric)
    query_terms = set(re.findall(r'\w+', query.lower()))
    doc_terms = set(re.findall(r'\w+', document.lower()))

    if not query_terms or not doc_terms:
        return 0.0

    # Calculate overlap ratio
    overlap = query_terms & doc_terms

    # Affinity = overlap / query terms
    affinity = len(overlap) / len(query_terms)

    return min(1.0, affinity)


def promote_diversity(
    results: List[Dict[str, Any]],
    threshold: float = 0.3,
    top_k: int = 10
) -> List[Dict[str, Any]]:
    """
    Promote diversity in ranked results

    Ensures that top-k results are not too similar to each other
    by reordering results when similarity exceeds threshold.

    Args:
        results: Ranked list of results
        threshold: Similarity threshold (0-1)
        top_k: Number of top results to diversify

    Returns:
        Reordered results with improved diversity
    """
    if not results or len(results) <= 1:
        return results

    # Always preserve the top result
    diversified = [results[0]]

    # For remaining results, check diversity before adding to top_k
    for candidate in results[1:]:
        # If we already have top_k results, just add the rest
        if len(diversified) >= top_k:
            diversified.append(candidate)
            continue

        # Check if candidate is diverse enough from current top results
        is_diverse = True

        for existing in diversified:
            similarity = compute_query_affinity(
                existing.get("document", ""),
                candidate.get("document", "")
            )

            if similarity > threshold:
                is_diverse = False
                break

        # Add if diverse, or if we have few results (to avoid empty results)
        if is_diverse or len(diversified) < min(3, len(results)):
            diversified.append(candidate)

    return diversified


def rank_results(
    results: List[Dict[str, Any]],
    query: str,
    config: Optional[RankingConfig] = None,
    top_k: Optional[int] = None
) -> List[Dict[str, Any]]:
    """
    Convenience function for ranking results

    Args:
        results: List of retrieval results
        query: Query string
        config: Optional ranking configuration
        top_k: Optional limit on results

    Returns:
        Ranked results
    """
    ranker = ResultRanker(config)
    return ranker.rank(results, query, top_k=top_k)
