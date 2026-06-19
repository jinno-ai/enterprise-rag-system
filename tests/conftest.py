import pytest
from unittest.mock import Mock, patch

@pytest.fixture(autouse=True)
def mock_openai():
    """Global mock for OpenAI services to prevent external API calls during tests"""
    with patch('openai.embeddings.create') as mock_embed, \
         patch('openai.chat.completions.create') as mock_chat:

        # Mock embedding response
        mock_embed.return_value = Mock(
            data=[Mock(embedding=[0.1] * 1536) for _ in range(10)]
        )

        # Mock chat completion response
        mock_chat.return_value = Mock(
            choices=[Mock(message=Mock(content="Mocked answer"))],
            usage=Mock(total_tokens=100)
        )

        yield mock_embed, mock_chat
