import pytest
from unittest.mock import Mock, patch

@pytest.fixture(autouse=True)
def mock_openai_embeddings():
    """Mock OpenAI embeddings for all tests"""
    with patch("app.core.embeddings.OpenAIEmbeddings") as mock:
        instance = mock.return_value
        instance.embed_query.side_effect = lambda x: [0.1] * 1536
        instance.embed_texts.side_effect = lambda x: [[0.1] * 1536 for _ in x]
        instance.dimension = 1536
        yield mock

@pytest.fixture(autouse=True)
def mock_openai_chat():
    """Mock OpenAI chat completions for all tests"""
    with patch("openai.chat.completions.create") as mock:
        mock.return_value.choices = [
            Mock(message=Mock(content="Mocked answer"))
        ]
        mock.return_value.usage.total_tokens = 100
        yield mock
