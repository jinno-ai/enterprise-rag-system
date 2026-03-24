import pytest
import tempfile
import os
from unittest.mock import MagicMock

from app.core.vectordb import get_vector_db
from app.core.embeddings import get_embedding_model
from app.services.retrieval import HybridRetriever, RetrievalResult
from app.services.rag_pipeline import RAGPipeline

@pytest.fixture
def temp_vector_db():
    with tempfile.TemporaryDirectory() as tmpdir:
        index_path = os.path.join(tmpdir, "test_index.bin")
        yield index_path

@pytest.fixture
def sample_documents():
    return [
        {
            "text": "Machine learning is a subset of artificial intelligence.",
            "metadata": {"source": "doc1.pdf", "page": 1}
        },
        {
            "text": "Deep learning uses neural networks.",
            "metadata": {"source": "doc2.pdf", "page": 1}
        }
    ]

@pytest.fixture(autouse=True)
def mock_openai(mocker):
    # Patch where it is USED
    mock_emb = mocker.patch("app.core.embeddings.openai.embeddings.create")
    mock_emb.return_value.data = [MagicMock(embedding=[0.1] * 1536) for _ in range(10)]

    mock_chat = mocker.patch("app.services.rag_pipeline.openai.chat.completions.create")
    mock_chat.return_value.choices = [
        MagicMock(message=MagicMock(content="Mocked RAG Answer"), finish_reason="stop")
    ]
    mock_chat.return_value.usage.total_tokens = 50
    return mock_emb, mock_chat

@pytest.mark.integration
def test_rag_pipeline_end_to_end(temp_vector_db, sample_documents):
    vector_db = get_vector_db(db_type="faiss", index_path=temp_vector_db)
    vector_db.create_index(dimension=1536)
    vector_db.connect()
    embedding_model = get_embedding_model()
    retriever = HybridRetriever(vector_db=vector_db, embedding_model=embedding_model)
    pipeline = RAGPipeline(retriever=retriever)

    texts = [doc["text"] for doc in sample_documents]
    embeddings = [[0.1]*1536 for _ in texts]
    vector_db.add_documents(texts, embeddings, [doc["metadata"] for doc in sample_documents])

    response = pipeline.query("What is machine learning?")
    assert response.answer == "Mocked RAG Answer"
    assert len(response.sources) > 0

@pytest.mark.integration
def test_vector_db_operations(temp_vector_db, sample_documents):
    vector_db = get_vector_db(db_type="faiss", index_path=temp_vector_db)
    vector_db.create_index(dimension=1536)
    vector_db.connect()
    embedding_model = get_embedding_model()

    texts = [doc["text"] for doc in sample_documents]
    embeddings = embedding_model.embed_texts(texts)
    vector_db.add_documents(texts, embeddings, [doc["metadata"] for doc in sample_documents])

    query_embedding = [0.1] * 1536
    results = vector_db.search(query_embedding, top_k=2)
    assert len(results) > 0

@pytest.mark.integration
def test_batch_query():
    vector_db = get_vector_db(db_type="faiss", index_path=":memory:")
    vector_db.create_index(dimension=1536)
    vector_db.connect()
    embedding_model = get_embedding_model()
    retriever = HybridRetriever(vector_db=vector_db, embedding_model=embedding_model)
    pipeline = RAGPipeline(retriever=retriever)

    responses = pipeline.batch_query(["Q1?", "Q2?"])
    assert len(responses) == 2
