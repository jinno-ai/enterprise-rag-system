import pytest
from unittest.mock import Mock, patch

@pytest.fixture(autouse=True)
def mock_openai_services():
    """Mock OpenAI services to prevent external API calls and billing errors."""
    with patch("openai.embeddings.create") as mock_embed,          patch("openai.chat.completions.create") as mock_chat:

        # Mock embedding response
        mock_embed.return_value.data = [
            Mock(embedding=[0.1] * 1536) for _ in range(10)
        ]

        # Mock chat response
        mock_chat.return_value.choices = [
            Mock(message=Mock(content="Mocked answer"))
        ]
        mock_chat.return_value.usage.total_tokens = 50

        yield mock_embed, mock_chat
