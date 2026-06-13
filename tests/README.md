# Test Documentation

## Overview

This document describes the test infrastructure and execution procedures for the Enterprise RAG System.

## Test Structure

```
tests/
├── conftest.py              # Shared test configuration and fixtures
├── unit/                    # Unit tests (fast, isolated)
│   ├── test_rag_pipeline.py # RAG pipeline tests
│   └── test_api_routes.py   # API endpoint tests
└── integration/             # Integration tests (slower, may require external services)
    └── test_rag_integration.py
```

## Prerequisites

Before running tests, ensure you have:

1. Installed dependencies. For the unit suite, the lightweight, verified set is
   enough (heavy ML libs are mocked) and is what CI uses:
```bash
pip install -r requirements-test.txt
```
   For integration tests against real providers, install the full set:
```bash
pip install -r requirements.txt
```

2. Set required environment variables (for testing):
```bash
export OPENAI_API_KEY="test-key-for-testing"  # or your actual key
export LLM_MODEL="gpt-4"
export EMBEDDING_MODEL="text-embedding-ada-002"
```

**Note**: Unit tests use a mock configuration, so you don't need real API keys.
Integration tests that call external providers are **automatically skipped**
unless `OPENAI_API_KEY` is set to a real key (starting with `sk-`).

## Running Tests

### Run All Unit Tests

```bash
pytest tests/unit/ -v
```

### Run Specific Test File

```bash
pytest tests/unit/test_rag_pipeline.py -v
```

### Run Specific Test

```bash
pytest tests/unit/test_rag_pipeline.py::test_rag_pipeline_initialization -v
```

### Run with Coverage Report

```bash
pytest --cov=app --cov-report=html --cov-report=term
```

### Run Integration Tests Only

```bash
pytest -m integration -v
```

### Run Unit Tests Only

```bash
pytest -m unit -v
```

## Test Markers

Tests are organized using pytest markers:

- `@pytest.mark.unit`: Unit tests (fast, isolated, no external dependencies)
- `@pytest.mark.integration`: Integration tests (slower, may require external services)
- `@pytest.mark.slow`: Slow-running tests
- `@pytest.mark.api`: API endpoint tests

## Configuration

The `pytest.ini` file at the project root configures pytest with:

- Test discovery patterns
- Output formatting
- Marker definitions
- Test paths
- Asyncio mode

### pytest.ini

```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts =
    -v
    --strict-markers
    --tb=short
    --disable-warnings
```

## Test Categories

### Unit Tests (`tests/unit/`)

**test_rag_pipeline.py**:
- RAG pipeline initialization
- Query execution with mocked dependencies
- Error handling (no results)
- Batch query processing
- Confidence calculation
- Prompt building

**test_api_routes.py**:
- Request validation
- Query endpoint success and error cases
- Batch query endpoint
- Health check endpoint
- Response model serialization

### Integration Tests (`tests/integration/`)

- End-to-end RAG pipeline
- Vector database operations
- Hybrid retrieval
- Context compression
- Batch query with real components
- Metadata filtering

## Writing New Tests

### Unit Test Example

```python
import pytest
from unittest.mock import Mock, patch
from app.services.rag_pipeline import RAGPipeline

@pytest.fixture
def mock_retriever():
    """Mock retriever"""
    retriever = Mock()
    retriever.retrieve.return_value = []
    return retriever

def test_rag_pipeline_initialization(mock_retriever):
    """Test RAG pipeline initialization"""
    pipeline = RAGPipeline(
        retriever=mock_retriever,
        llm_model='gpt-4'
    )
    assert pipeline.llm_model == 'gpt-4'
```

### API Test Example

```python
from fastapi.testclient import TestClient
from unittest.mock import patch

def test_query_endpoint_success(client):
    """Test successful query"""
    response = client.post(
        "/query/",
        json={"query": "What is AI?", "top_k": 5}
    )
    assert response.status_code == 200
    data = response.json()
    assert "answer" in data
```

## Test Fixtures

Common fixtures are defined in `tests/conftest.py`:

- `test_config`: Test configuration settings
- `reset_settings`: Resets settings between tests

## Best Practices

1. **Use mocks for external dependencies**: Unit tests should be isolated and fast
2. **Test behavior, not implementation**: Focus on what the code does, not how
3. **Keep tests simple**: Each test should verify one thing
4. **Use descriptive names**: `test_rag_pipeline_query_with_no_results`
5. **Organize tests logically**: Group related tests in classes
6. **Handle async properly**: Use `@pytest.mark.asyncio` for async tests

## Troubleshooting

### Import Errors

If you see import errors:
```bash
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
pytest tests/ -v
```

### Missing Dependencies

If tests fail due to missing dependencies:
```bash
pip install -r requirements.txt
```

### Environment Variable Errors

Set test environment variables:
```bash
export OPENAI_API_KEY="test-key-for-testing"
pytest tests/ -v
```

## Continuous Integration

Tests run in GitHub Actions (`.github/workflows/test.yml`):

- **`unit-tests`** — blocking gate. Runs `pytest tests/unit` with coverage on
  Python 3.10 and 3.11 using `requirements-test.txt`. A failure fails the build.
- **`integration-tests`** — informational (`continue-on-error: true`). Runs
  `pytest tests/integration`; provider-dependent tests skip unless the
  `OPENAI_API_KEY` secret is configured.

```yaml
# Blocking unit-test gate (excerpt)
- name: Install test dependencies
  run: pip install -r requirements-test.txt
- name: Run unit tests
  run: pytest tests/unit -v --cov=app --cov-report=term-missing
```

## Test Coverage

Current test coverage focuses on:
- ✅ RAG pipeline core functionality
- ✅ API endpoint validation and error handling
- ✅ Request/response models
- ⏳ Enhanced edge case coverage
- ⏳ Performance tests

## Next Steps

1. Add more unit tests for:
   - Document loading
   - Vector database operations
   - Embedding generation
   - Context compression

2. Add integration tests for:
   - Complete RAG workflows
   - Error recovery scenarios
   - Performance benchmarks

3. Set up continuous integration with automated test runs

## Resources

- [pytest Documentation](https://docs.pytest.org/)
- [FastAPI Testing Docs](https://fastapi.tiangolo.com/tutorial/testing/)
- [pytest-mock Documentation](https://pytest-mock.readthedocs.io/)
