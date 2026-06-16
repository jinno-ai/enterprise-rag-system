import pytest
from unittest.mock import Mock, patch

@pytest.fixture(autouse=True)
def mock_openai_services():
    """Mock OpenAI services to prevent real API calls during tests"""
    with patch("openai.chat.completions.create") as mock_chat, \
         patch("openai.embeddings.create") as mock_embeddings:

        # Mock Chat Response
        mock_chat.return_value.choices = [
            Mock(message=Mock(content="Mocked LLM answer"), finish_reason="stop")
        ]
        mock_chat.return_value.usage = Mock(total_tokens=100)

        # Mock Embeddings Response
        mock_embeddings.return_value.data = [
            Mock(embedding=[0.1] * 1536)
        ]

        yield mock_chat, mock_embeddings

@pytest.fixture(autouse=True)
def mock_anthropic_services():
    """Mock Anthropic services"""
    with patch("anthropic.resources.messages.Messages.create") as mock_messages:
        mock_messages.return_value.content = [
            Mock(text="Mocked Anthropic answer")
        ]
        mock_messages.return_value.usage = Mock(input_tokens=50, output_tokens=50)

        yield mock_messages
