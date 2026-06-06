import pytest
from unittest.mock import Mock

@pytest.fixture(autouse=True)
def mock_openai_embeddings(mocker):
    """Mock OpenAI embeddings to avoid API calls during tests"""
    mock_create = mocker.patch("openai.embeddings.create")

    def side_effect(model, input, **kwargs):
        mock_response = Mock()
        if isinstance(input, str):
            mock_response.data = [Mock(embedding=[0.1] * 1536)]
        else:
            mock_response.data = [Mock(embedding=[0.1] * 1536) for _ in input]
        return mock_response

    mock_create.side_effect = side_effect
    return mock_create

@pytest.fixture(autouse=True)
def mock_openai_chat(mocker):
    """Mock OpenAI chat completions to avoid API calls during tests"""
    mock_create = mocker.patch("openai.chat.completions.create")

    mock_response = Mock()
    mock_response.choices = [
        Mock(message=Mock(content="Mocked LLM answer for testing."))
    ]
    mock_response.usage = Mock(total_tokens=50)

    mock_create.return_value = mock_response
    return mock_create
