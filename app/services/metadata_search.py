"""
Metadata Search Service for RAG System

This module implements advanced metadata filtering and search capabilities.
It provides a flexible interface for filtering documents by metadata fields.
"""

from typing import List, Dict, Any, Optional, Union
from dataclasses import dataclass
from enum import Enum
import re
import logging

from app.core.vectordb import SearchResult, VectorDB
from app.core.embeddings import EmbeddingModel

logger = logging.getLogger(__name__)


class FilterOperator(str, Enum):
    """Supported filter operators"""
    EQ = "eq"           # Equals
    NE = "ne"           # Not equals
    GT = "gt"           # Greater than
    GTE = "gte"         # Greater than or equal
    LT = "lt"           # Less than
    LTE = "lte"         # Less than or equal
    IN = "in"           # In list
    NIN = "nin"         # Not in list
    CONTAINS = "contains"  # Contains substring
    REGEX = "regex"     # Regular expression match
    EXISTS = "exists"   # Field exists


@dataclass
class MetadataFilter:
    """Metadata filter specification"""
    field: str
    operator: FilterOperator
    value: Any = None

    def __post_init__(self):
        """Validate filter specification"""
        if self.operator in [FilterOperator.EQ, FilterOperator.NE, FilterOperator.GT,
                             FilterOperator.GTE, FilterOperator.LT, FilterOperator.LTE,
                             FilterOperator.CONTAINS, FilterOperator.REGEX] and self.value is None:
            raise ValueError(f"Operator {self.operator} requires a value")

        if self.operator in [FilterOperator.IN, FilterOperator.NIN]:
            if not isinstance(self.value, list):
                raise ValueError(f"Operator {self.operator} requires a list value")

        if self.operator == FilterOperator.REGEX:
            try:
                re.compile(self.value)
            except re.error as e:
                raise ValueError(f"Invalid regex pattern: {e}")


@dataclass
class MetadataSearchResult:
    """Result from metadata search"""
    id: str
    score: float
    metadata: Dict[str, Any]
    text: str
    matched_filters: List[str]


class MetadataSearchService:
    """Service for metadata-based search and filtering"""

    def __init__(
        self,
        vector_db: VectorDB,
        embedding_model: EmbeddingModel
    ):
        """
        Initialize metadata search service

        Args:
            vector_db: Vector database instance
            embedding_model: Embedding model instance
        """
        self.vector_db = vector_db
        self.embedding_model = embedding_model

    def apply_filter(
        self,
        result: SearchResult,
        filter_spec: MetadataFilter
    ) -> bool:
        """
        Apply a single filter to a search result

        Args:
            result: Search result to filter
            filter_spec: Filter specification

        Returns:
            True if result passes the filter, False otherwise
        """
        field_value = result.metadata.get(filter_spec.field)

        try:
            if filter_spec.operator == FilterOperator.EQ:
                return field_value == filter_spec.value

            elif filter_spec.operator == FilterOperator.NE:
                return field_value != filter_spec.value

            elif filter_spec.operator == FilterOperator.GT:
                if field_value is None:
                    return False
                return float(field_value) > float(filter_spec.value)

            elif filter_spec.operator == FilterOperator.GTE:
                if field_value is None:
                    return False
                return float(field_value) >= float(filter_spec.value)

            elif filter_spec.operator == FilterOperator.LT:
                if field_value is None:
                    return False
                return float(field_value) < float(filter_spec.value)

            elif filter_spec.operator == FilterOperator.LTE:
                if field_value is None:
                    return False
                return float(field_value) <= float(filter_spec.value)

            elif filter_spec.operator == FilterOperator.IN:
                return field_value in filter_spec.value

            elif filter_spec.operator == FilterOperator.NIN:
                return field_value not in filter_spec.value

            elif filter_spec.operator == FilterOperator.CONTAINS:
                if field_value is None:
                    return False
                return str(filter_spec.value).lower() in str(field_value).lower()

            elif filter_spec.operator == FilterOperator.REGEX:
                if field_value is None:
                    return False
                pattern = re.compile(filter_spec.value)
                return bool(pattern.search(str(field_value)))

            elif filter_spec.operator == FilterOperator.EXISTS:
                return filter_spec.field in result.metadata

            return False

        except (ValueError, TypeError) as e:
            logger.warning(f"Filter error on field {filter_spec.field}: {e}")
            return False

    def apply_filters(
        self,
        results: List[SearchResult],
        filters: List[MetadataFilter],
        match_all: bool = True
    ) -> List[MetadataSearchResult]:
        """
        Apply multiple filters to search results

        Args:
            results: List of search results
            filters: List of filter specifications
            match_all: If True, all filters must match (AND). If False, any filter can match (OR)

        Returns:
            List of filtered results with match information
        """
        filtered_results = []

        for result in results:
            matched_filters = []

            for filter_spec in filters:
                if self.apply_filter(result, filter_spec):
                    matched_filters.append(filter_spec.field)

            # Check if result matches the filter criteria
            passes_filter = False
            if match_all:
                # All filters must match
                passes_filter = len(matched_filters) == len(filters)
            else:
                # Any filter can match
                passes_filter = len(matched_filters) > 0

            if passes_filter:
                filtered_results.append(MetadataSearchResult(
                    id=result.id,
                    score=result.score,
                    metadata=result.metadata,
                    text=result.text,
                    matched_filters=matched_filters
                ))

        return filtered_results

    def search_by_metadata(
        self,
        query: str,
        filters: List[MetadataFilter],
        top_k: int = 5,
        match_all: bool = True,
        use_semantic: bool = True
    ) -> List[MetadataSearchResult]:
        """
        Search with metadata filtering

        Args:
            query: Search query
            filters: List of metadata filters
            top_k: Number of results to return
            match_all: If True, all filters must match (AND). If False, any filter can match (OR)
            use_semantic: If True, use semantic search. If False, return all matching documents

        Returns:
            List of filtered search results
        """
        if not filters:
            logger.warning("No filters provided, performing regular search")
            # Fall back to regular search without metadata filtering
            search_results = self.vector_db.search(
                query_vector=self.embedding_model.embed_query(query),
                top_k=top_k
            )
            return [
                MetadataSearchResult(
                    id=r.id,
                    score=r.score,
                    metadata=r.metadata,
                    text=r.text,
                    matched_filters=[]
                )
                for r in search_results
            ]

        # Perform semantic search
        search_results = self.vector_db.search(
            query_vector=self.embedding_model.embed_query(query),
            top_k=top_k * 2  # Get more results for filtering
        )

        # Apply metadata filters
        filtered_results = self.apply_filters(
            results=search_results,
            filters=filters,
            match_all=match_all
        )

        # Sort by score and return top_k
        filtered_results.sort(key=lambda x: x.score, reverse=True)
        return filtered_results[:top_k]

    def get_unique_metadata_values(
        self,
        field: str,
        query: Optional[str] = None,
        top_k: int = 100
    ) -> List[Any]:
        """
        Get unique values for a metadata field

        Args:
            field: Metadata field name
            query: Optional query to filter results
            top_k: Number of documents to scan

        Returns:
            List of unique values
        """
        if query:
            search_results = self.vector_db.search(
                query_vector=self.embedding_model.embed_query(query),
                top_k=top_k
            )
        else:
            # Get a sample of documents
            search_results = self.vector_db.search(
                query_vector=self.embedding_model.embed_query(""),
                top_k=top_k
            )

        values = set()
        for result in search_results:
            field_value = result.metadata.get(field)
            if field_value is not None:
                values.add(field_value)

        return sorted(list(values))

    def build_filter_from_dict(
        self,
        filter_dict: Dict[str, Any]
    ) -> List[MetadataFilter]:
        """
        Build filter list from dictionary specification

        Supports simple format: {"field": "value"}
        And complex format: {"field": {"operator": "eq", "value": "value"}}

        Args:
            filter_dict: Filter specification dictionary

        Returns:
            List of MetadataFilter objects
        """
        filters = []

        for field, spec in filter_dict.items():
            if isinstance(spec, dict):
                # Complex format with operator
                operator = FilterOperator(spec.get("operator", "eq"))
                value = spec.get("value")
            else:
                # Simple format (equals operator)
                operator = FilterOperator.EQ
                value = spec

            try:
                filters.append(MetadataFilter(
                    field=field,
                    operator=operator,
                    value=value
                ))
            except ValueError as e:
                logger.warning(f"Skipping invalid filter for field {field}: {e}")

        return filters
