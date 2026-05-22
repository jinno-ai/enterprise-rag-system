import pytest
from unittest.mock import Mock, patch

@pytest.fixture(autouse=True)
def mock_openai_chat_completion():
    """Mock OpenAI chat completion for all tests"""
    with patch("openai.chat.completions.create") as mock:
        mock_response = Mock()
        mock_response.choices = [
            Mock(message=Mock(content="This is a mocked response answer based on context."))
        ]
        mock_response.usage = Mock(total_tokens=100)
        mock.return_value = mock_response
        yield mock

@pytest.fixture(autouse=True)
def mock_openai_embeddings():
    """Mock OpenAI embeddings for all tests"""
    with patch("openai.embeddings.create") as mock:
        mock.side_effect = lambda model, input: Mock(
            data=[Mock(embedding=[0.1] * 1536) for _ in (input if isinstance(input, list) else [input])]
        )
        yield mock
