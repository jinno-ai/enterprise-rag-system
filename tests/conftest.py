import pytest
from unittest.mock import Mock, patch

@pytest.fixture(autouse=True)
def mock_openai_embeddings():
    """Mock OpenAI embeddings to avoid API calls during tests"""
    with patch('app.core.embeddings.OpenAIEmbeddings.embed_texts') as mock_embed_texts, \
         patch('app.core.embeddings.OpenAIEmbeddings.embed_query') as mock_embed_query:

        # Mock embed_texts to return random vectors of correct dimension
        def side_effect_texts(texts):
            return [[0.1] * 1536 for _ in texts]

        mock_embed_texts.side_effect = side_effect_texts
        mock_embed_query.return_value = [0.1] * 1536

        yield mock_embed_texts, mock_embed_query

@pytest.fixture(autouse=True)
def mock_openai_chat():
    """Mock OpenAI chat completions"""
    with patch('openai.chat.completions.create') as mock_create:
        mock_response = Mock()
        mock_response.choices = [Mock(message=Mock(content="Mocked LLM response"), finish_reason="stop")]
        mock_response.usage = Mock(total_tokens=100)
        mock_create.return_value = mock_response
        yield mock_create
