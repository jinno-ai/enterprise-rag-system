import pytest
from unittest.mock import Mock, patch

@pytest.fixture(autouse=True)
def mock_openai_services():
    """Globally mock OpenAI services for all tests"""
    with patch("openai.embeddings.create") as mock_embed, \
         patch("openai.chat.completions.create") as mock_chat:

        # Mock embeddings response
        mock_embed.return_value.data = [Mock(embedding=[0.1] * 1536)]

        # Mock chat response
        mock_chat.return_value.choices = [
            Mock(message=Mock(content="Mocked answer"), finish_reason="stop")
        ]
        mock_chat.return_value.usage.total_tokens = 100

        yield
