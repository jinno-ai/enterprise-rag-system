import pytest
from unittest.mock import Mock, patch

@pytest.fixture(autouse=True)
def mock_openai():
    with patch("openai.embeddings.create") as mock_embed,          patch("openai.chat.completions.create") as mock_chat:

        # Mock embeddings
        mock_embed.return_value.data = [
            Mock(embedding=[0.1] * 1536) for _ in range(100)
        ]

        # Mock chat
        mock_chat.return_value.choices = [
            Mock(message=Mock(content="Mocked answer"), finish_reason="stop")
        ]
        mock_chat.return_value.usage.total_tokens = 50

        yield mock_embed, mock_chat
