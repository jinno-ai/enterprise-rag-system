"""
Global pytest configuration and fixtures
"""

import pytest
from unittest.mock import Mock, patch

@pytest.fixture(autouse=True)
def mock_openai_chat():
    """Mock OpenAI chat completions globally"""
    with patch('openai.resources.chat.completions.Completions.create') as mock_create:
        mock_response = Mock()
        mock_response.choices = [Mock(message=Mock(content="Mocked LLM response"), finish_reason="stop")]
        mock_response.usage = Mock(total_tokens=100)
        mock_create.return_value = mock_response
        yield mock_create

@pytest.fixture(autouse=True)
def mock_openai_embeddings():
    """Mock OpenAI embeddings globally"""
    with patch('openai.resources.embeddings.Embeddings.create') as mock_create:
        mock_response = Mock()
        # Mock 1536-dimensional vector
        mock_response.data = [Mock(embedding=[0.1] * 1536)]
        mock_create.return_value = mock_response
        yield mock_create
