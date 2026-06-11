import pytest
from unittest.mock import Mock, patch

@pytest.fixture(autouse=True)
def mock_openai_services():
    """Mock OpenAI services globally for tests"""
    with patch("openai.chat.completions.create") as mock_chat, \
         patch("openai.embeddings.create") as mock_embed:

        # Mock Chat Completion
        mock_chat.return_value.choices = [
            Mock(message=Mock(content="Mocked LLM answer"), finish_reason="stop")
        ]
        mock_chat.return_value.usage.total_tokens = 50

        # Mock Embeddings
        mock_embed.return_value.data = [
            Mock(embedding=[0.1] * 1536)
        ]

        yield mock_chat, mock_embed
