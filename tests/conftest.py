import pytest
from unittest.mock import Mock, patch

@pytest.fixture(autouse=True)
def mock_openai_embeddings():
    """Mock OpenAI embeddings to avoid API calls during tests"""
    with patch('openai.embeddings.create') as mock_create:
        # Mock response for a single text or list of texts
        def side_effect(model, input, **kwargs):
            mock_response = Mock()
            if isinstance(input, str):
                input = [input]

            mock_data = []
            for _ in input:
                item = Mock()
                item.embedding = [0.1] * 1536  # Standard Ada-002 dimension
                mock_data.append(item)

            mock_response.data = mock_data
            return mock_response

        mock_create.side_effect = side_effect
        yield mock_create

@pytest.fixture(autouse=True)
def mock_openai_chat():
    """Mock OpenAI chat completions"""
    with patch('openai.chat.completions.create') as mock_create:
        mock_response = Mock()
        mock_choice = Mock()
        mock_choice.message.content = "This is a mocked LLM response."
        mock_choice.finish_reason = "stop"
        mock_response.choices = [mock_choice]
        mock_response.usage.total_tokens = 50
        mock_create.return_value = mock_response
        yield mock_create
