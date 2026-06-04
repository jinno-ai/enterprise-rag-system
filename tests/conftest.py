import pytest
from unittest.mock import Mock, patch

@pytest.fixture(autouse=True)
def mock_openai_api():
    """Mock OpenAI API calls globally for tests"""
    with patch('openai.embeddings.create') as mock_embed, \
         patch('openai.chat.completions.create') as mock_chat:

        # Mock embedding response
        mock_embed.return_value.data = [Mock(embedding=[0.1] * 1536)]

        # Mock chat response
        mock_chat.return_value.choices = [Mock(message=Mock(content="Test answer"))]
        mock_chat.return_value.usage.total_tokens = 50

        yield mock_embed, mock_chat

@pytest.fixture(autouse=True)
def mock_app_openai_embeddings():
    """Mock app.core.embeddings.OpenAIEmbeddings globally for tests"""
    with patch('app.core.embeddings.openai.embeddings.create') as mock_embed:
        mock_embed.return_value.data = [Mock(embedding=[0.1] * 1536)]
        yield mock_embed
