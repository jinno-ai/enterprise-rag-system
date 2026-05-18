"""
Global test configuration and fixtures
"""

import pytest
from unittest.mock import Mock, patch

@pytest.fixture(autouse=True)
def mock_openai_embeddings():
    """Mock OpenAI embeddings to avoid API calls during tests"""
    with patch('openai.embeddings.create') as mock_create:
        # Mock response for a single text
        mock_data_single = Mock()
        mock_data_single.embedding = [0.1] * 1536

        # Mock response for multiple texts
        def side_effect(model, input, **kwargs):
            mock_res = Mock()
            if isinstance(input, str):
                mock_res.data = [mock_data_single]
            else:
                mock_res.data = [Mock(embedding=[0.1] * 1536) for _ in input]
            return mock_res

        mock_create.side_effect = side_effect
        yield mock_create

@pytest.fixture(autouse=True)
def mock_openai_chat():
    """Mock OpenAI chat completions to avoid API calls during tests"""
    with patch('openai.chat.completions.create') as mock_create:
        mock_response = Mock()
        mock_choice = Mock()
        mock_message = Mock()
        mock_message.content = "This is a mocked response from OpenAI."
        mock_choice.message = mock_message
        mock_choice.finish_reason = "stop"
        mock_response.choices = [mock_choice]
        mock_response.usage = Mock(total_tokens=50)

        mock_create.return_value = mock_response
        yield mock_create
