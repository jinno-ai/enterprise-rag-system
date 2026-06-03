import pytest
from unittest.mock import Mock, patch

@pytest.fixture(autouse=True)
def mock_openai_services():
    """Mock OpenAI chat completions and embeddings for all tests"""
    with patch("openai.resources.chat.completions.Completions.create") as mock_chat, \
         patch("openai.resources.embeddings.Embeddings.create") as mock_embed:

        # Mock chat response
        mock_chat.return_value.choices = [
            Mock(message=Mock(content="Mocked LLM answer from conftest"))
        ]
        mock_chat.return_value.usage.total_tokens = 50

        # Mock embedding response
        mock_embed_resp = Mock()
        mock_embed_resp.data = [Mock(embedding=[0.1] * 1536)]
        mock_embed.return_value = mock_embed_resp

        yield mock_chat, mock_embed
