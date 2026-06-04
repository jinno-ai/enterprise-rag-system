import pytest
from unittest.mock import Mock

@pytest.fixture(autouse=True)
def mock_openai_services(mocker):
    """Mock OpenAI services globally"""
    # Mock Chat Completions
    # Note: In newer openai versions, the structure is different, but the pipeline uses the older style or mocks might need adjustment
    # Pipeline uses: response = openai.chat.completions.create(...)

    mock_chat = mocker.patch("openai.resources.chat.completions.Completions.create")
    mock_chat.return_value = Mock(
        choices=[Mock(message=Mock(content="Mocked answer based on context."), finish_reason="stop")],
        usage=Mock(total_tokens=100)
    )

    # Mock Embeddings
    # Pipeline uses: response = openai.embeddings.create(...)
    mock_embeddings = mocker.patch("openai.resources.embeddings.Embeddings.create")
    mock_embeddings.return_value = Mock(
        data=[Mock(embedding=[0.1] * 1536) for _ in range(10)] # Handle batch
    )

    return mock_chat, mock_embeddings
