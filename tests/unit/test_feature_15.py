"""
Unit tests for Document Metadata Search (Feature 15)

Tests metadata search service and API endpoints.
Ensures flexible metadata filtering with proper error handling.
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from fastapi.testclient import TestClient
from fastapi import FastAPI
from typing import List, Dict, Any

from app.services.metadata_search import (
    MetadataSearchService,
    MetadataFilter,
    MetadataSearchResult,
    FilterOperator
)
from app.core.vectordb import SearchResult


@pytest.fixture
def mock_vector_db():
    """Mock vector database for testing"""
    vector_db = Mock()
    return vector_db


@pytest.fixture
def mock_embedding_model():
    """Mock embedding model for testing"""
    embedding_model = Mock()
    embedding_model.embed_query.return_value = [0.1, 0.2, 0.3]
    return embedding_model


@pytest.fixture
def sample_search_results():
    """Sample search results for testing"""
    return [
        SearchResult(
            id="doc1",
            score=0.95,
            metadata={
                "filename": "policy_hr.pdf",
                "department": "HR",
                "year": 2024,
                "category": "policy",
                "author": "john.doe@company.com"
            },
            text="HR policy document about remote work"
        ),
        SearchResult(
            id="doc2",
            score=0.85,
            metadata={
                "filename": "policy_it.pdf",
                "department": "IT",
                "year": 2023,
                "category": "guidelines",
                "author": "jane.smith@company.com"
            },
            text="IT guidelines for software development"
        ),
        SearchResult(
            id="doc3",
            score=0.75,
            metadata={
                "filename": "handbook_sales.pdf",
                "department": "Sales",
                "year": 2024,
                "category": "handbook",
                "author": "bob.wilson@company.com"
            },
            text="Sales handbook and commission structure"
        ),
        SearchResult(
            id="doc4",
            score=0.65,
            metadata={
                "filename": "policy_finance.pdf",
                "department": "Finance",
                "year": 2023,
                "category": "policy",
                "status": "draft"
            },
            text="Finance policy document (draft)"
        ),
        SearchResult(
            id="doc5",
            score=0.55,
            metadata={
                "filename": "guidelines_marketing.pdf",
                "department": "Marketing",
                "year": 2022,
                "category": "guidelines",
                "budget": 50000
            },
            text="Marketing guidelines and budget allocation"
        )
    ]


class TestMetadataFilter:
    """Test suite for MetadataFilter validation"""

    def test_filter_eq_valid(self):
        """Test equality filter with valid value"""
        filter_spec = MetadataFilter(
            field="department",
            operator=FilterOperator.EQ,
            value="HR"
        )
        assert filter_spec.field == "department"
        assert filter_spec.operator == FilterOperator.EQ
        assert filter_spec.value == "HR"

    def test_filter_in_operator_with_list(self):
        """Test IN operator with list value"""
        filter_spec = MetadataFilter(
            field="department",
            operator=FilterOperator.IN,
            value=["HR", "IT", "Finance"]
        )
        assert filter_spec.operator == FilterOperator.IN
        assert isinstance(filter_spec.value, list)
        assert len(filter_spec.value) == 3

    def test_filter_in_operator_without_list_raises_error(self):
        """Test IN operator without list raises error"""
        with pytest.raises(ValueError, match="requires a list value"):
            MetadataFilter(
                field="department",
                operator=FilterOperator.IN,
                value="HR"
            )

    def test_filter_regex_valid_pattern(self):
        """Test regex filter with valid pattern"""
        filter_spec = MetadataFilter(
            field="email",
            operator=FilterOperator.REGEX,
            value=r"^[a-z]+@[a-z]+\.[a-z]+$"
        )
        assert filter_spec.operator == FilterOperator.REGEX

    def test_filter_regex_invalid_pattern_raises_error(self):
        """Test regex filter with invalid pattern raises error"""
        with pytest.raises(ValueError, match="Invalid regex pattern"):
            MetadataFilter(
                field="email",
                operator=FilterOperator.REGEX,
                value="[invalid(regex"
            )

    def test_filter_operator_without_value_raises_error(self):
        """Test filter operators that require value"""
        with pytest.raises(ValueError, match="requires a value"):
            MetadataFilter(
                field="department",
                operator=FilterOperator.EQ,
                value=None
            )

    def test_filter_exists_operator_no_value(self):
        """Test EXISTS operator doesn't require value"""
        filter_spec = MetadataFilter(
            field="status",
            operator=FilterOperator.EXISTS
        )
        assert filter_spec.operator == FilterOperator.EXISTS
        assert filter_spec.value is None


class TestMetadataSearchService:
    """Test suite for MetadataSearchService functionality"""

    def test_apply_filter_eq(self, mock_vector_db, mock_embedding_model):
        """Test equality filter application"""
        service = MetadataSearchService(mock_vector_db, mock_embedding_model)

        result = SearchResult(
            id="doc1",
            score=0.9,
            metadata={"department": "HR"},
            text="Test document"
        )

        filter_spec = MetadataFilter(
            field="department",
            operator=FilterOperator.EQ,
            value="HR"
        )

        assert service.apply_filter(result, filter_spec) is True

    def test_apply_filter_eq_no_match(self, mock_vector_db, mock_embedding_model):
        """Test equality filter with no match"""
        service = MetadataSearchService(mock_vector_db, mock_embedding_model)

        result = SearchResult(
            id="doc1",
            score=0.9,
            metadata={"department": "IT"},
            text="Test document"
        )

        filter_spec = MetadataFilter(
            field="department",
            operator=FilterOperator.EQ,
            value="HR"
        )

        assert service.apply_filter(result, filter_spec) is False

    def test_apply_filter_ne(self, mock_vector_db, mock_embedding_model):
        """Test not equals filter"""
        service = MetadataSearchService(mock_vector_db, mock_embedding_model)

        result = SearchResult(
            id="doc1",
            score=0.9,
            metadata={"department": "IT"},
            text="Test document"
        )

        filter_spec = MetadataFilter(
            field="department",
            operator=FilterOperator.NE,
            value="HR"
        )

        assert service.apply_filter(result, filter_spec) is True

    def test_apply_filter_gt(self, mock_vector_db, mock_embedding_model):
        """Test greater than filter"""
        service = MetadataSearchService(mock_vector_db, mock_embedding_model)

        result = SearchResult(
            id="doc1",
            score=0.9,
            metadata={"year": 2024},
            text="Test document"
        )

        filter_spec = MetadataFilter(
            field="year",
            operator=FilterOperator.GT,
            value=2023
        )

        assert service.apply_filter(result, filter_spec) is True

    def test_apply_filter_gte(self, mock_vector_db, mock_embedding_model):
        """Test greater than or equal filter"""
        service = MetadataSearchService(mock_vector_db, mock_embedding_model)

        result = SearchResult(
            id="doc1",
            score=0.9,
            metadata={"year": 2023},
            text="Test document"
        )

        filter_spec = MetadataFilter(
            field="year",
            operator=FilterOperator.GTE,
            value=2023
        )

        assert service.apply_filter(result, filter_spec) is True

    def test_apply_filter_lt(self, mock_vector_db, mock_embedding_model):
        """Test less than filter"""
        service = MetadataSearchService(mock_vector_db, mock_embedding_model)

        result = SearchResult(
            id="doc1",
            score=0.9,
            metadata={"year": 2022},
            text="Test document"
        )

        filter_spec = MetadataFilter(
            field="year",
            operator=FilterOperator.LT,
            value=2023
        )

        assert service.apply_filter(result, filter_spec) is True

    def test_apply_filter_lte(self, mock_vector_db, mock_embedding_model):
        """Test less than or equal filter"""
        service = MetadataSearchService(mock_vector_db, mock_embedding_model)

        result = SearchResult(
            id="doc1",
            score=0.9,
            metadata={"year": 2023},
            text="Test document"
        )

        filter_spec = MetadataFilter(
            field="year",
            operator=FilterOperator.LTE,
            value=2023
        )

        assert service.apply_filter(result, filter_spec) is True

    def test_apply_filter_in(self, mock_vector_db, mock_embedding_model):
        """Test IN filter"""
        service = MetadataSearchService(mock_vector_db, mock_embedding_model)

        result = SearchResult(
            id="doc1",
            score=0.9,
            metadata={"department": "HR"},
            text="Test document"
        )

        filter_spec = MetadataFilter(
            field="department",
            operator=FilterOperator.IN,
            value=["HR", "IT", "Finance"]
        )

        assert service.apply_filter(result, filter_spec) is True

    def test_apply_filter_nin(self, mock_vector_db, mock_embedding_model):
        """Test NOT IN filter"""
        service = MetadataSearchService(mock_vector_db, mock_embedding_model)

        result = SearchResult(
            id="doc1",
            score=0.9,
            metadata={"department": "Marketing"},
            text="Test document"
        )

        filter_spec = MetadataFilter(
            field="department",
            operator=FilterOperator.NIN,
            value=["HR", "IT", "Finance"]
        )

        assert service.apply_filter(result, filter_spec) is True

    def test_apply_filter_contains(self, mock_vector_db, mock_embedding_model):
        """Test contains filter (case insensitive)"""
        service = MetadataSearchService(mock_vector_db, mock_embedding_model)

        result = SearchResult(
            id="doc1",
            score=0.9,
            metadata={"filename": "policy_hr_remote_work.pdf"},
            text="Test document"
        )

        filter_spec = MetadataFilter(
            field="filename",
            operator=FilterOperator.CONTAINS,
            value="remote"
        )

        assert service.apply_filter(result, filter_spec) is True

    def test_apply_filter_regex(self, mock_vector_db, mock_embedding_model):
        """Test regex filter"""
        service = MetadataSearchService(mock_vector_db, mock_embedding_model)

        result = SearchResult(
            id="doc1",
            score=0.9,
            metadata={"email": "john.doe@company.com"},
            text="Test document"
        )

        filter_spec = MetadataFilter(
            field="email",
            operator=FilterOperator.REGEX,
            value=r"^[a-z]+\.?[a-z]+@company\.com$"
        )

        assert service.apply_filter(result, filter_spec) is True

    def test_apply_filter_exists_field_present(self, mock_vector_db, mock_embedding_model):
        """Test EXISTS filter when field is present"""
        service = MetadataSearchService(mock_vector_db, mock_embedding_model)

        result = SearchResult(
            id="doc1",
            score=0.9,
            metadata={"status": "draft", "department": "HR"},
            text="Test document"
        )

        filter_spec = MetadataFilter(
            field="status",
            operator=FilterOperator.EXISTS
        )

        assert service.apply_filter(result, filter_spec) is True

    def test_apply_filter_exists_field_absent(self, mock_vector_db, mock_embedding_model):
        """Test EXISTS filter when field is absent"""
        service = MetadataSearchService(mock_vector_db, mock_embedding_model)

        result = SearchResult(
            id="doc1",
            score=0.9,
            metadata={"department": "HR"},
            text="Test document"
        )

        filter_spec = MetadataFilter(
            field="status",
            operator=FilterOperator.EXISTS
        )

        assert service.apply_filter(result, filter_spec) is False

    def test_apply_filters_match_all_true(self, mock_vector_db, mock_embedding_model, sample_search_results):
        """Test multiple filters with AND logic (match_all=True)"""
        service = MetadataSearchService(mock_vector_db, mock_embedding_model)

        filters = [
            MetadataFilter(field="category", operator=FilterOperator.EQ, value="policy"),
            MetadataFilter(field="year", operator=FilterOperator.GTE, value=2024)
        ]

        results = service.apply_filters(sample_search_results, filters, match_all=True)

        # Should only return doc1 (category=policy AND year=2024)
        assert len(results) == 1
        assert results[0].id == "doc1"
        assert set(results[0].matched_filters) == {"category", "year"}

    def test_apply_filters_match_all_false(self, mock_vector_db, mock_embedding_model, sample_search_results):
        """Test multiple filters with OR logic (match_all=False)"""
        service = MetadataSearchService(mock_vector_db, mock_embedding_model)

        filters = [
            MetadataFilter(field="department", operator=FilterOperator.EQ, value="HR"),
            MetadataFilter(field="department", operator=FilterOperator.EQ, value="Sales")
        ]

        results = service.apply_filters(sample_search_results, filters, match_all=False)

        # Should return doc1 (HR) and doc3 (Sales)
        assert len(results) == 2
        departments = {r.metadata.get("department") for r in results}
        assert departments == {"HR", "Sales"}

    def test_apply_filters_no_matches(self, mock_vector_db, mock_embedding_model, sample_search_results):
        """Test filters with no matching results"""
        service = MetadataSearchService(mock_vector_db, mock_embedding_model)

        filters = [
            MetadataFilter(field="department", operator=FilterOperator.EQ, value="Executive")
        ]

        results = service.apply_filters(sample_search_results, filters, match_all=True)

        assert len(results) == 0

    def test_search_by_metadata_basic(self, mock_vector_db, mock_embedding_model, sample_search_results):
        """Test basic metadata search"""
        mock_vector_db.search.return_value = sample_search_results

        service = MetadataSearchService(mock_vector_db, mock_embedding_model)

        filters = [
            MetadataFilter(field="category", operator=FilterOperator.EQ, value="policy")
        ]

        results = service.search_by_metadata(
            query="remote work policy",
            filters=filters,
            top_k=5
        )

        assert len(results) == 2  # doc1 and doc4 have category=policy
        assert all(isinstance(r, MetadataSearchResult) for r in results)

    def test_search_by_metadata_with_comparison(self, mock_vector_db, mock_embedding_model, sample_search_results):
        """Test metadata search with comparison operators"""
        mock_vector_db.search.return_value = sample_search_results

        service = MetadataSearchService(mock_vector_db, mock_embedding_model)

        filters = [
            MetadataFilter(field="year", operator=FilterOperator.GTE, value=2024)
        ]

        results = service.search_by_metadata(
            query="recent documents",
            filters=filters,
            top_k=10
        )

        # Should return doc1 and doc3 (year >= 2024)
        assert len(results) == 2
        assert all(r.metadata.get("year", 0) >= 2024 for r in results)

    def test_search_by_metadata_empty_filters(self, mock_vector_db, mock_embedding_model, sample_search_results):
        """Test metadata search with no filters (fallback to regular search)"""
        mock_vector_db.search.return_value = sample_search_results[:2]

        service = MetadataSearchService(mock_vector_db, mock_embedding_model)

        results = service.search_by_metadata(
            query="test query",
            filters=[],
            top_k=5
        )

        assert len(results) == 2
        assert all(r.matched_filters == [] for r in results)

    def test_get_unique_metadata_values(self, mock_vector_db, mock_embedding_model, sample_search_results):
        """Test getting unique metadata values"""
        mock_vector_db.search.return_value = sample_search_results

        service = MetadataSearchService(mock_vector_db, mock_embedding_model)

        values = service.get_unique_metadata_values(field="department")

        # Should return unique departments sorted
        assert set(values) == {"Finance", "HR", "IT", "Marketing", "Sales"}
        assert values == sorted(values)

    def test_build_filter_from_dict_simple(self, mock_vector_db, mock_embedding_model):
        """Test building filters from simple dictionary format"""
        service = MetadataSearchService(mock_vector_db, mock_embedding_model)

        filter_dict = {
            "department": "HR",
            "year": 2024
        }

        filters = service.build_filter_from_dict(filter_dict)

        assert len(filters) == 2
        assert all(isinstance(f, MetadataFilter) for f in filters)
        assert filters[0].field == "department"
        assert filters[0].operator == FilterOperator.EQ
        assert filters[0].value == "HR"

    def test_build_filter_from_dict_complex(self, mock_vector_db, mock_embedding_model):
        """Test building filters from complex dictionary format with operators"""
        service = MetadataSearchService(mock_vector_db, mock_embedding_model)

        filter_dict = {
            "department": {"operator": "eq", "value": "HR"},
            "year": {"operator": "gte", "value": 2023}
        }

        filters = service.build_filter_from_dict(filter_dict)

        assert len(filters) == 2
        assert filters[0].operator == FilterOperator.EQ
        assert filters[1].operator == FilterOperator.GTE
        assert filters[1].value == 2023

    def test_build_filter_from_dict_invalid_filter_skipped(self, mock_vector_db, mock_embedding_model):
        """Test that invalid filters are skipped with warning"""
        import logging
        service = MetadataSearchService(mock_vector_db, mock_embedding_model)

        filter_dict = {
            "department": "HR",
            "year": {"operator": "in", "value": "not_a_list"}  # Invalid: IN requires list
        }

        # Should skip invalid filter and only return valid one
        filters = service.build_filter_from_dict(filter_dict)

        assert len(filters) == 1
        assert filters[0].field == "department"


class TestMetadataSearchAPI:
    """Test suite for metadata search API endpoints"""

    @pytest.fixture
    def client(self):
        """Create test client for API testing"""
        from app.api.routes.query import router as query_router

        test_app = FastAPI()
        test_app.include_router(query_router, prefix="/api/v1")

        # Mock the RAG pipeline dependency
        def mock_get_rag_pipeline():
            pipeline = Mock()

            # Create mock retriever
            mock_vector_db = Mock()
            mock_vector_db.search.return_value = [
                SearchResult(
                    id="doc1",
                    score=0.9,
                    metadata={"department": "HR", "year": 2024},
                    text="Test document"
                )
            ]

            pipeline.retriever = Mock()
            pipeline.retriever.vector_db = mock_vector_db

            # Create mock embedding model
            mock_embedding_model = Mock()
            mock_embedding_model.embed_query.return_value = [0.1, 0.2, 0.3]
            pipeline.embedding_model = mock_embedding_model

            return pipeline

        with patch('app.main.get_rag_pipeline', mock_get_rag_pipeline):
            yield TestClient(test_app)

    def test_metadata_search_endpoint_success(self, client):
        """Test metadata search API endpoint with valid request"""
        response = client.post(
            "/api/v1/query/metadata",
            json={
                "query": "remote work policy",
                "filters": {"department": "HR"},
                "top_k": 5
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert "total_found" in data
        assert data["query"] == "remote work policy"

    def test_metadata_search_endpoint_with_complex_filters(self, client):
        """Test metadata search API with complex filter specification"""
        response = client.post(
            "/api/v1/query/metadata",
            json={
                "query": "recent policies",
                "filters": {
                    "category": {"operator": "eq", "value": "policy"},
                    "year": {"operator": "gte", "value": 2024}
                },
                "top_k": 10,
                "match_all": True
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data["results"], list)

    def test_metadata_search_endpoint_match_any(self, client):
        """Test metadata search API with OR logic (match_all=False)"""
        response = client.post(
            "/api/v1/query/metadata",
            json={
                "query": "documents",
                "filters": {
                    "department": "HR"
                },
                "match_all": False
            }
        )

        assert response.status_code == 200

    def test_metadata_search_endpoint_empty_filters(self, client):
        """Test metadata search API with empty filters returns error"""
        response = client.post(
            "/api/v1/query/metadata",
            json={
                "query": "test",
                "filters": {},
                "top_k": 5
            }
        )

        assert response.status_code == 400  # Bad Request

    def test_metadata_search_endpoint_invalid_regex(self, client):
        """Test metadata search API with invalid regex pattern"""
        response = client.post(
            "/api/v1/query/metadata",
            json={
                "query": "test",
                "filters": {
                    "email": {"operator": "regex", "value": "[invalid"}
                }
            }
        )

        assert response.status_code == 400  # Bad Request

    def test_metadata_search_endpoint_validation_top_k_too_small(self, client):
        """Test metadata search API validation - top_k too small"""
        response = client.post(
            "/api/v1/query/metadata",
            json={
                "query": "test",
                "filters": {"department": "HR"},
                "top_k": 0  # Invalid: must be >= 1
            }
        )

        assert response.status_code == 422  # Validation error

    def test_metadata_search_endpoint_validation_top_k_too_large(self, client):
        """Test metadata search API validation - top_k exceeds maximum"""
        response = client.post(
            "/api/v1/query/metadata",
            json={
                "query": "test",
                "filters": {"department": "HR"},
                "top_k": 25  # Invalid: must be <= 20
            }
        )

        assert response.status_code == 422  # Validation error

    def test_metadata_search_endpoint_validation_missing_query(self, client):
        """Test metadata search API validation - missing query"""
        response = client.post(
            "/api/v1/query/metadata",
            json={
                "filters": {"department": "HR"},
                "top_k": 5
            }
        )

        assert response.status_code == 422  # Validation error

    def test_metadata_values_endpoint_success(self, client):
        """Test getting unique metadata values endpoint"""
        response = client.post(
            "/api/v1/query/metadata/values",
            json={
                "field": "department",
                "top_k": 100
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert "values" in data
        assert "field" in data
        assert "total" in data

    def test_metadata_values_endpoint_with_query(self, client):
        """Test getting metadata values with query filter"""
        response = client.post(
            "/api/v1/query/metadata/values",
            json={
                "field": "department",
                "query": "company policy",
                "top_k": 50
            }
        )

        assert response.status_code == 200

    def test_metadata_values_endpoint_validation_missing_field(self, client):
        """Test metadata values endpoint validation - missing field"""
        response = client.post(
            "/api/v1/query/metadata/values",
            json={
                "top_k": 100
            }
        )

        assert response.status_code == 422  # Validation error

    def test_metadata_search_response_structure(self, client):
        """Test metadata search response has correct structure"""
        response = client.post(
            "/api/v1/query/metadata",
            json={
                "query": "test query",
                "filters": {"department": "HR"},
                "top_k": 5
            }
        )

        assert response.status_code == 200
        data = response.json()

        # Check response structure
        assert "results" in data
        assert "total_found" in data
        assert "query" in data

        # Check result items have required fields
        if len(data["results"]) > 0:
            result = data["results"][0]
            assert "id" in result
            assert "score" in result
            assert "metadata" in result
            assert "text" in result
            assert "matched_filters" in result


class TestMetadataSearchEdgeCases:
    """Test suite for edge cases and error handling"""

    def test_filter_with_missing_field(self, mock_vector_db, mock_embedding_model):
        """Test filter on field that doesn't exist in metadata"""
        service = MetadataSearchService(mock_vector_db, mock_embedding_model)

        result = SearchResult(
            id="doc1",
            score=0.9,
            metadata={"department": "HR"},
            text="Test document"
        )

        # Filter on non-existent field
        filter_spec = MetadataFilter(
            field="status",
            operator=FilterOperator.EXISTS
        )

        assert service.apply_filter(result, filter_spec) is False

    def test_filter_with_none_field_value(self, mock_vector_db, mock_embedding_model):
        """Test filter on field with None value"""
        service = MetadataSearchService(mock_vector_db, mock_embedding_model)

        result = SearchResult(
            id="doc1",
            score=0.9,
            metadata={"department": None},
            text="Test document"
        )

        filter_spec = MetadataFilter(
            field="department",
            operator=FilterOperator.EQ,
            value="HR"
        )

        assert service.apply_filter(result, filter_spec) is False

    def test_numeric_filter_with_string_value(self, mock_vector_db, mock_embedding_model):
        """Test numeric comparison with string metadata value"""
        service = MetadataSearchService(mock_vector_db, mock_embedding_model)

        result = SearchResult(
            id="doc1",
            score=0.9,
            metadata={"year": "2024"},  # String instead of int
            text="Test document"
        )

        filter_spec = MetadataFilter(
            field="year",
            operator=FilterOperator.GT,
            value=2023
        )

        # Should convert string to int and compare
        assert service.apply_filter(result, filter_spec) is True

    def test_contains_filter_case_insensitive(self, mock_vector_db, mock_embedding_model):
        """Test contains filter is case insensitive"""
        service = MetadataSearchService(mock_vector_db, mock_embedding_model)

        result = SearchResult(
            id="doc1",
            score=0.9,
            metadata={"filename": "Policy_HR_2024.pdf"},
            text="Test document"
        )

        filter_spec = MetadataFilter(
            field="filename",
            operator=FilterOperator.CONTAINS,
            value="policy"  # lowercase
        )

        assert service.apply_filter(result, filter_spec) is True

    def test_large_filter_list(self, mock_vector_db, mock_embedding_model, sample_search_results):
        """Test applying many filters at once"""
        service = MetadataSearchService(mock_vector_db, mock_embedding_model)

        filters = [
            MetadataFilter(field=f"field{i}", operator=FilterOperator.EXISTS)
            for i in range(10)
        ]

        results = service.apply_filters(sample_search_results, filters, match_all=True)

        # None should match all 10 filters (fields don't exist)
        assert len(results) == 0
