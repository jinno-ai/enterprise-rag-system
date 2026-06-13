import pytest
from unittest.mock import Mock, patch

@pytest.fixture(autouse=True)
def mock_openai_services():
    """Mock OpenAI embedding and chat completion services globally for tests"""
    with patch("openai.embeddings.create") as mock_embed, \
         patch("openai.chat.completions.create") as mock_chat:

        # Setup embedding mock
        mock_embed.return_value.data = [
            Mock(embedding=[0.1] * 1536) for _ in range(100)
        ]

        # Setup chat completion mock
        mock_chat.return_value.choices = [
            Mock(message=Mock(content="Mocked LLM response"))
        ]
        mock_chat.return_value.usage.total_tokens = 50

        yield mock_embed, mock_chat
